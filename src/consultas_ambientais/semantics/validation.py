"""Politica semantica pura: nenhum LLM, SQL ou estimativa de area e executado."""
from pydantic import ValidationError

from ..contracts import Metric, Operation, QueryPlan, Unit
from .catalog import digest
from .models import QueryIntent, SemanticDecision
from .normalization import normalize


METRICS={"area":Metric.AREA,"participacao":Metric.SHARE,"participacao percentual":Metric.SHARE,
         "diferenca liquida":Metric.DELTA,"variacao absoluta":Metric.DELTA,"reducao liquida":Metric.REDUCTION,
         "variacao percentual":Metric.CHANGE,"pontos percentuais":Metric.POINTS,
         "diferenca em pontos percentuais":Metric.POINTS}
UNITS={"ha":Unit.HA,"hectare":Unit.HA,"hectares":Unit.HA,"km2":Unit.KM2,
       "quilometros quadrados":Unit.KM2,"m2":Unit.M2,"metros quadrados":Unit.M2,
       "percentual":Unit.PERCENT,"por cento":Unit.PERCENT,"pp":Unit.PP,"pontos percentuais":Unit.PP}


def validate_intent(intent,classes,territories,capabilities):
    def decision(status,reason,message,**kwargs):
        return SemanticDecision(status=status,reason=reason,message=message,
            class_catalog_sha256=classes.sha256,territory_catalog_sha256=territories.sha256,
            capabilities_sha256=digest(capabilities),**kwargs)
    if (capabilities.class_catalog_sha256!=classes.sha256 or
            capabilities.territory_catalog_sha256!=territories.sha256):
        return decision("erro_tecnico","catalogos_incompativeis","Os catalogos e o manifesto de capacidades pertencem a versoes diferentes.")
    try:
        intent=intent if isinstance(intent,QueryIntent) else QueryIntent.model_validate(intent)
    except ValidationError:
        return decision("precisa_esclarecimento","intencao_invalida","A selecao de operacao, territorio ou classe precisa ser corrigida.")
    if intent.requested_concept=="perda_bruta" or (intent.metric_term and normalize(intent.metric_term)=="perda bruta"):
        return decision("dados_indisponiveis","matriz_de_transicao_ausente","Perda bruta exige matriz de transicao, indisponivel no MVP.")
    if intent.requested_concept!="cobertura":
        return decision("fora_do_escopo","conceito_nao_suportado","As fontes e o motor atual descrevem cobertura mapeada; nao suportam esse conceito como conclusao.")
    terms=[normalize(c.term or "") for c in intent.classes]
    if any(t in {"vegetacao nativa","nao observado","nodata","no data"} for t in terms):
        return decision("fora_do_escopo","grupo_ou_nodata_sem_definicao","Nao existe mapeamento aprovado para esse termo; nenhum codigo sera inventado.")
    if intent.metric_term and normalize(intent.metric_term) in {"perda bruta","ganho bruto","desmatamento","evento de inundacao"}:
        return decision("fora_do_escopo","metrica_nao_suportada","Perda bruta, desmatamento e eventos de inundacao nao se deduzem de diferencas marginais de area.")
    if intent.metric_term and normalize(intent.metric_term) in {"percentual","porcentagem","perda","mudanca"}:
        return decision("precisa_esclarecimento","metrica_ambigua","Especifique area, participacao, diferenca liquida, variacao percentual ou pontos percentuais.")
    metric=intent.metric
    if intent.metric_term:
        parsed=METRICS.get(normalize(intent.metric_term))
        if parsed is None:return decision("precisa_esclarecimento","metrica_desconhecida","Especifique uma metrica permitida.")
        if metric and metric!=parsed:return decision("precisa_esclarecimento","metricas_divergentes","A metrica e o termo informado divergem.")
        metric=parsed
    if metric is None:return decision("precisa_esclarecimento","metrica_ausente","Informe a metrica pretendida.")
    unit=intent.unit
    if intent.unit_term:
        parsed=Unit.PERCENT if intent.unit_term.strip()=="%" else UNITS.get(normalize(intent.unit_term))
        if parsed is None:return decision("precisa_esclarecimento","unidade_desconhecida","Informe uma unidade suportada.")
        if unit and unit!=parsed:return decision("precisa_esclarecimento","unidades_divergentes","As unidades informadas divergem.")
        unit=parsed
    if unit is None:return decision("precisa_esclarecimento","unidade_ausente","Informe a unidade de apresentacao.")
    class_codes=[]
    for ref in intent.classes:
        result=classes.resolve(ref.term,ref.code)
        if result.status!="resolvido":
            return decision("precisa_esclarecimento",result.reason,"Especifique a classe ou seu codigo oficial.",class_candidates=result.candidates)
        class_codes.extend(result.selected_codes)
    leaves=classes.expand(class_codes)
    codes=[];notes=[]
    if intent.operation==Operation.RANKING:
        if not intent.scope_uf or intent.territories or intent.limit is None:
            return decision("precisa_esclarecimento","universo_ranking_ambiguo","Ranking exige uma UF, limite e o universo completo dos municipios dessa UF.")
        if not territories.municipality_universe(intent.scope_uf):
            return decision("dados_indisponiveis","universo_territorial_ausente","Nao ha municipios catalogados para a UF solicitada.")
    else:
        if not intent.territories:return decision("precisa_esclarecimento","territorio_ausente","Informe territorio e UF quando necessario.")
        for ref in intent.territories:
            result=territories.resolve(ref)
            if result.status!="resolvido":
                return decision("precisa_esclarecimento",result.reason,"Confirme o territorio por codigo ou por nome e UF.",territory_candidates=result.candidates)
            code=result.selected_codes[0]
            if intent.scope_uf and territories.by_code[code].uf!=intent.scope_uf:
                return decision("precisa_esclarecimento","territorio_e_escopo_incoerentes","O territorio pertence a outra UF.",territory_candidates=result.candidates)
            codes.append(code);notes.extend(result.notes)
    denominator=intent.denominator
    expected={Metric.SHARE:"area_observada",Metric.CHANGE:"area_inicial",Metric.POINTS:"participacao_por_ano"}.get(metric)
    if denominator is None:denominator=expected
    try:
        plan=QueryPlan(operation=intent.operation,metric=metric,unit=unit,territory_codes=codes,
            scope_uf=intent.scope_uf,class_codes=leaves,years=intent.years,denominator=denominator,
            direction=intent.direction,limit=intent.limit)
    except ValidationError:
        return decision("precisa_esclarecimento","plano_semanticamente_incoerente","Confira anos, unidade, denominador e quantidade de territorios para a operacao.")
    kwargs={"normalized_plan":plan,"notes":list(dict.fromkeys(notes))}
    if plan.operation not in capabilities.supported_operations:
        return decision("fora_do_escopo","operacao_nao_suportada","Esta operacao nao e suportada pelo motor configurado.",**kwargs)
    if not set(plan.years)<=set(capabilities.available_raster_years):
        return decision("dados_indisponiveis","ano_sem_fonte_verificada","Um ou mais anos solicitados nao tem fonte verificada no manifesto.",**kwargs)
    temporal=plan.metric in {Metric.DELTA,Metric.REDUCTION,Metric.CHANGE,Metric.POINTS}
    required_years=[tuple(plan.years)] if temporal else [(y,) for y in plan.years]
    universe=territories.municipality_universe(plan.scope_uf) if plan.operation==Operation.RANKING else set(codes)
    coverage={(r.territory_code,tuple(r.years)):r for r in capabilities.materializations}
    missing=[]
    for code in sorted(universe):
        for years in required_years:
            record=coverage.get((code,years))
            if (record is None or not record.complete or not set(leaves)<=set(record.class_codes)
                    or (temporal and not record.common_support_id)):
                missing.append({"territory_code":code,"years":list(years)})
    if missing:
        reason="ranking_com_cobertura_incompleta" if plan.operation==Operation.RANKING else "estatisticas_nao_materializadas"
        return decision("dados_indisponiveis",reason,"As estatisticas completas necessarias ainda nao foram materializadas.",
                        **{**kwargs,"notes":[*kwargs["notes"],f"Selecoes sem cobertura completa: {len(missing)}."]})
    if not capabilities.engine_ready:
        return decision("dados_indisponiveis","executor_indisponivel","O executor ambiental ainda nao esta disponivel.",**kwargs)
    return decision("plano_validado","selecoes_e_capacidades_validadas","Plano pronto para o motor; nenhum resultado quantitativo foi calculado nesta etapa.",**kwargs)
