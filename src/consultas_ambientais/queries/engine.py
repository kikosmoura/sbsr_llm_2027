"""Executor deterministico. Entrada JSON e validada novamente; LLM nao participa."""
import json
import math
from pathlib import Path
from pydantic import ValidationError
from ..contracts import QueryPlan,Metric,Operation,ProcessingQuality,Territory
from ..semantics.catalog import ClassCatalog,digest
from ..semantics.territories import TerritoryCatalog
from ..semantics.models import QueryIntent
from ..semantics.validation import validate_intent
from ..storage.derived import DerivedStore,file_sha
from ..answers.models import QueryAnswer,QueryEvidence,QueryValue,SourceReference,RankingInfo,ExecutionContext
from ..answers.render import render
from .models import ValidatedPlan,QueryFailure,technical,clarify,unavailable,TEMPORAL_METRICS,MAX_TERRITORIES,MAX_RANK_CANDIDATES,MAX_PLAN_BYTES
from .metrics import convert_signed_area,temporal_change,share_percent,percentage_point_change


def executor_digest():
    base=Path(__file__).parents[1]
    files=sorted([*base.joinpath("queries").glob("*.py"),*base.joinpath("answers").glob("*.py"),base/"storage/derived.py",base/"contracts.py"])
    return digest({str(p.relative_to(base)):file_sha(p) for p in files})


def parse_plan(raw):
    raw=raw.model_dump(mode="json") if isinstance(raw,QueryPlan) else raw
    if isinstance(raw,dict) and isinstance(raw.get("metric"),str) and raw.get("metric") in {"perda_bruta","ganho_bruto"}:
        raise unavailable("matriz_de_transicao_ausente","Perda e ganho brutos exigem matriz de transicao, indisponivel no MVP.")
    if isinstance(raw,dict) and raw.get("scope_uf")=="BR":
        raise QueryFailure("fora_do_escopo","ranking_nacional_nao_suportado","O ranking disponivel se limita aos municipios de uma UF explicitamente materializada.")
    try:
        plan=QueryPlan.model_validate(raw.model_dump() if isinstance(raw,QueryPlan) else raw)
    except ValidationError:raise clarify("plano_invalido") from None
    return plan


def preflight(raw,classes,territories):
    plan=parse_plan(raw)
    if len(plan.territory_codes)>MAX_TERRITORIES:raise clarify("limite_de_territorios_excedido")
    if plan.scope_uf and not territories.municipality_universe(plan.scope_uf):raise clarify("uf_desconhecida")
    for code in plan.territory_codes:
        entry=territories.by_code.get(code)
        if entry is None:raise clarify("territorio_desconhecido")
        if plan.scope_uf and entry.uf!=plan.scope_uf:raise clarify("territorio_e_uf_incoerentes")
    try:leaves=classes.expand(plan.class_codes)
    except ValueError:raise clarify("classe_desconhecida") from None
    if plan.operation==Operation.RANKING:
        universe=tuple(sorted(territories.municipality_universe(plan.scope_uf)))
        if not universe or len(universe)>MAX_RANK_CANDIDATES:raise unavailable("universo_do_ranking_excede_capacidade")
    else:universe=tuple(sorted(plan.territory_codes))
    canonical=QueryPlan.model_validate({**plan.model_dump(),"class_codes":leaves,"years":sorted(plan.years),"territory_codes":sorted(plan.territory_codes)})
    return plan,canonical,universe


class QueryEngine:
    def __init__(self,root,project,run_id,territories,capabilities):
        self.root=Path(root);self.project=project;self.run_id=run_id
        self.territories_path=Path(territories);self.capabilities_path=Path(capabilities)
        self.seal=object();self.store=None

    def answer(self,raw):
        try:
            # Arquivos de consulta sao pequenos; nenhuma entrada bruta e registrada.
            if len(json.dumps(raw.model_dump(mode="json") if isinstance(raw,QueryPlan) else raw).encode())>MAX_PLAN_BYTES:
                raise clarify("plano_excede_limite_de_bytes")
            parsed=parse_plan(raw)
            classes=ClassCatalog.load();territories=TerritoryCatalog.load(self.territories_path)
            requested,plan,universe=preflight(parsed,classes,territories)
            store=DerivedStore(self.root,self.project,self.run_id,classes,territories,self.capabilities_path)
            self.store=store;self.classes=classes;self.territories=territories
            intent=QueryIntent(operation=plan.operation,metric=plan.metric,unit=plan.unit,
                territories=[{"code":c} for c in plan.territory_codes],scope_uf=plan.scope_uf,
                classes=[{"code":c} for c in plan.class_codes],years=plan.years,denominator=plan.denominator,
                direction=plan.direction,limit=plan.limit)
            decision=validate_intent(intent,classes,territories,store.capabilities)
            if decision.status!="plano_validado":raise QueryFailure(decision.status,decision.reason,decision.message)
            support="comum" if plan.metric.value in TEMPORAL_METRICS else "anual"
            validated=ValidatedPlan(requested,decision.normalized_plan,universe,support,self.seal)
            return self.execute(validated)
        except QueryFailure as e:
            return QueryAnswer(status=e.status,reason=e.reason,message=e.message)
        except Exception:
            # Falhas de leitura, schema, hashes ou SQL nunca produzem resultados parciais.
            e=technical()
            return QueryAnswer(status=e.status,reason=e.reason,message=e.message)

    def execute(self,validated):
        if not isinstance(validated,ValidatedPlan) or validated.seal is not self.seal or self.store is None:
            raise technical("plano_nao_validado_pelo_executor")
        plan=validated.executed;data=self.store.read(validated)
        plan_id=digest(plan);implementation=executor_digest()
        answer_id=digest({"plan":plan_id,"requested":validated.requested.model_dump(mode="json"),
            "run":self.run_id,"run_manifest":self.store.manifest_sha256,"executor":implementation,
            "territories":self.territories.sha256})
        rows=[]
        for code in validated.candidate_codes:
            observations=data[code]["observations"]
            groups=[observations] if validated.support=="comum" else [[o] for o in observations]
            for group in groups:
                value,area,denominator,reason=_calculate(plan.metric,plan.unit,group)
                rows.append({"code":code,"observations":group,"value":value,"area":area,"denominator":denominator,"reason":reason})
        ranking=None
        if plan.operation==Operation.RANKING:
            if set(data)!=set(validated.candidate_codes):raise unavailable("ranking_com_universo_incompleto")
            undefined=sorted(r["code"] for r in rows if r["value"] is None)
            defined=[r for r in rows if r["value"] is not None]
            filtered=0
            if plan.metric==Metric.REDUCTION:
                filtered=sum(r["value"]<=0 for r in defined)
                defined=[r for r in defined if r["value"]>0]
            # Chave numerica completa, sem arredondar; empate exato por codigo IBGE textual.
            defined.sort(key=lambda r:((r["value"] if plan.direction=="asc" else -r["value"]),r["code"]))
            selected=defined[:plan.limit]
            ranking=RankingInfo(scope_uf=plan.scope_uf,candidate_codes=list(validated.candidate_codes),
                candidate_count=len(validated.candidate_codes),verified_count=len(data),metric=plan.metric,
                sign_convention=_sign(plan.metric),direction=plan.direction,limit=plan.limit,
                filtered_non_reductions=filtered,undefined_codes=undefined,qualifying_count=len(defined),returned_count=len(selected))
            rows=selected
        evidence=[];values=[]
        for index,row in enumerate(rows):
            code=row["code"];entry=self.territories.by_code[code];observations=row["observations"]
            years=[o["year"] for o in observations];info=data[code]
            evidence_id=digest({"answer":answer_id,"territory":code,"years":years,"metric":plan.metric.value})
            sources=self._sources(code,years)
            denominator_values=_denominators(plan.metric,observations)
            e=QueryEvidence(evidence_id=evidence_id,plan_id=plan_id,run_id=self.run_id,
                territory=Territory(kind=entry.kind,code=code,name=entry.name_original,uf=entry.uf,
                    geometry_hash=info["geometry_sha256"],edition=self.store.identity["config"]["territorial_edition"]),
                class_codes=plan.class_codes,requested_class_codes=validated.requested.class_codes,
                class_names=[self.classes.by_code[c].name+f" [{c}]" for c in plan.class_codes],years=years,
                source_revision=self.store.identity["config"]["source_revision"],source_ids=[s.source_id for s in sources],sources=sources,
                area_method=self.store.identity["method"],metric=plan.metric,observations=observations,
                denominator_definition=_denominator_definition(plan.metric),denominator_values_ha=denominator_values,
                provenance=info["provenance"],mesh_sha256=self.store.identity["mesh_sha256"],catalog_sha256=self.classes.sha256,
                run_manifest_sha256=self.store.manifest_sha256,
                quality=ProcessingQuality(state="completo",observed_area_ha=observations[0]["observed_area_ha"],
                    nodata_area_ha=observations[0]["nodata_area_ha"],common_support_id=info["common_support_id"],area_method=self.store.identity["method"],
                    notes=["Revisao oficial do espelho e edicao territorial nao comprovadas."]))
            evidence.append(e)
            values.append(QueryValue(evidence_id=evidence_id,value=row["value"],unit=plan.unit,metric=plan.metric,
                area_value_ha=row["area"],denominator_value=row["denominator"],denominator_unit="ha" if denominator_values else None,
                undefined_reason=row["reason"],rank=index+1 if ranking else None))
        # Frase e gerada somente depois que todo o resultado foi verificado.
        answer=QueryAnswer(status="respondida",reason="consulta_executada",message="Resultado verificado.",
            answer_id=answer_id,plan_id=plan_id,executor_sha256=implementation,requested_plan=validated.requested,plan=plan,
            execution=ExecutionContext(run_id=self.run_id,run_manifest_sha256=self.store.manifest_sha256,
                collection=self.store.identity["config"]["collection"],source_revision=self.store.identity["config"]["source_revision"],
                territorial_edition=self.store.identity["config"]["territorial_edition"],method=self.store.identity["method"],
                mesh_sha256=self.store.identity["mesh_sha256"],catalog_sha256=self.classes.sha256,years=plan.years,
                class_names=[self.classes.by_code[c].name+f" [{c}]" for c in plan.class_codes],sources=self._sources(None,plan.years)),
            evidence=evidence,values=values,ranking=ranking,
            notes=["Valores sem arredondamento no JSON/CSV; texto com duas casas decimais.",
                "Diferenca liquida nao mede perda bruta, desmatamento ou causas."])
        answer.message=render(answer)
        return answer

    def _sources(self,code,years):
        m=self.store.manifest;identity=self.store.identity
        sources=[SourceReference(source_id="run:"+self.run_id,kind="execucao",sha256=self.store.manifest_sha256),
            SourceReference(source_id="mesh:"+identity["mesh_sha256"],kind="malha",sha256=identity["mesh_sha256"]),
            SourceReference(source_id="classes:"+self.classes.sha256,kind="catalogo",sha256=self.classes.sha256)]
        for f in self.store.parts[code]["files"] if code else []:
            sources.append(SourceReference(source_id=f["name"]+":"+f["sha256"],kind="particao_areas" if f["name"]=="areas.parquet" else "particao_qualidade",sha256=f["sha256"]))
        for year,src,sha in zip(identity["years"],m["sources"],m["input_crop_hashes"]):
            if year in years:
                from ..settings import https_url
                url=https_url(src["url"])
                sources.append(SourceReference(source_id="mirror:"+digest(src),kind="raster_espelho",year=year,public_url=url,etag=src.get("etag")))
                sources.append(SourceReference(source_id="crop:"+sha,kind="recorte",sha256=sha,year=year))
        return sources


def _calculate(metric,unit,obs):
    initial=obs[0]["class_area_ha"]
    if metric==Metric.AREA:return convert_signed_area(initial,unit.value),initial,None,None
    if metric==Metric.SHARE:
        denominator=obs[0]["observed_area_ha"];value=share_percent(initial,denominator)
        return value,None,denominator,"suporte_observado_zero" if value is None else None
    final=obs[1]["class_area_ha"];change=temporal_change(initial,final)
    if metric in {Metric.DELTA,Metric.REDUCTION}:
        ha=change["delta_ha"] if metric==Metric.DELTA else change["reduction_ha"]
        return convert_signed_area(ha,unit.value),ha,None,None
    if metric==Metric.CHANGE:return change["change_percent"],None,initial,change["undefined_reason"]
    if metric==Metric.POINTS:
        value=percentage_point_change(initial,obs[0]["observed_area_ha"],final,obs[1]["observed_area_ha"])
        return value,None,None,"suporte_observado_zero" if value is None else None
    raise technical("metrica_sem_template")


def _denominators(metric,obs):
    if metric==Metric.CHANGE:return [obs[0]["class_area_ha"]]
    if metric in {Metric.SHARE,Metric.POINTS}:return [o["observed_area_ha"] for o in obs]
    return []


def _denominator_definition(metric):
    return {Metric.SHARE:"area observada no ano e suporte selecionados",
        Metric.CHANGE:"area inicial da classe no suporte comum",
        Metric.POINTS:"areas observadas inicial e final no mesmo suporte comum"}.get(metric)


def _sign(metric):
    return {Metric.DELTA:"final menos inicial; negativo indica reducao liquida",
        Metric.REDUCTION:"inicial menos final, positivo; somente municipios com reducao",
        Metric.CHANGE:"100*(final-inicial)/inicial; negativo indica reducao; base zero indefinida",
        Metric.POINTS:"participacao final menos inicial, em pontos percentuais"}.get(metric,"valor nao negativo")
