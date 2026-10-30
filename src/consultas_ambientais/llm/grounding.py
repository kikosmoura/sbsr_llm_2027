"""Guardas locais de ancoragem e ambiguidade; nao calculam valores ambientais."""
import re
from ..contracts import Metric,Operation,Unit
from ..semantics.normalization import normalize
from ..semantics.models import QueryIntent,TerritoryReference
from .dialogue_models import ValidationIssue

class NeedClarification(Exception):
    def __init__(self,field,reason,mention=None,candidates=None):
        self.field=field;self.reason=reason;self.mention=mention;self.candidates=candidates or []
        super().__init__(reason)

class GroundingError(ValueError):
    def __init__(self,field,code):
        self.issues=[ValidationIssue(path=["intent",field],code=code)]
        super().__init__(code)

class PolicyStop(Exception):
    def __init__(self,status,reason,message):
        self.status=status;self.reason=reason;self.message=message
        super().__init__(reason)

UNITS={"ha":"ha","hectare":"ha","hectares":"ha","km2":"km2","quilometros quadrados":"km2",
    "m2":"m2","metro quadrado":"m2","metros quadrados":"m2","quilometro quadrado":"km2","percentual":"percentual","por cento":"percentual","porcentagem":"percentual",
    "pontos percentuais":"pontos_percentuais","pp":"pontos_percentuais"}
METRIC_CHOICES=[{"code":"area","name":"Área em ha, km² ou m²"},
    {"code":"participacao","name":"Participação: classe / área observada"},
    {"code":"diferenca_liquida","name":"Diferença líquida: final menos inicial"},
    {"code":"reducao_liquida","name":"Redução líquida positiva"},
    {"code":"variacao_percentual","name":"Variação percentual em relação à área inicial"},
    {"code":"diferenca_pontos_percentuais","name":"Diferença de participação em pontos percentuais"}]
UNIT_CHOICES=[{"code":u.value,"name":u.value} for u in Unit]


def contains(mention,text):
    if mention=="%":return "%" in text
    value=normalize(mention)
    return bool(value) and bool(re.search(r"(?<![a-z0-9])"+re.escape(value)+r"(?![a-z0-9])",normalize(text)))


def policy(question):
    text=normalize(question)
    if re.search(r"\b(select|drop table|delete from|insert into|execute sql|executar sql|sql livre|shell|python)\b",text):
        raise PolicyStop("fora_do_escopo","codigo_ou_sql_nao_permitido","A interface aceita consultas ambientais tipadas; não executa SQL, expressões ou código da pergunta.")
    if re.search(r"\b(brasil|nacional)\b",text) and re.search(r"\b(ranking|maior|maiores|menor|menores|mais)\b",text):
        raise PolicyStop("fora_do_escopo","ranking_nacional_nao_suportado","O ranking se limita ao universo completo de municípios de uma UF explicitamente materializada.")
    if "perda bruta" in text or "ganho bruto" in text:
        raise PolicyStop("dados_indisponiveis","matriz_de_transicao_ausente","Perda e ganho brutos exigem matriz de transição, indisponível no MVP.")
    if re.search(r"\b(causa|causas|causou|porque|motivo|razao|ilegal|ilegalidade|crime|culpa|desmatamento|desmatou|inundacao|enchente|acuracia|qualidade|mudanca real|previsao|prever|projecao)\b|por que",text):
        raise PolicyStop("fora_do_escopo","conceito_nao_inferivel","As fontes descrevem cobertura mapeada; diferenças marginais não comprovam causas, ilegalidade, desmatamento, inundação, qualidade temática ou mudança real específica no terreno.")
    if "vegetacao nativa" in text or "nodata" in text or "nao observado" in text:
        raise PolicyStop("fora_do_escopo","classe_sem_definicao_aprovada","O termo não tem código/classe aprovado nesta interface; nenhum código será inventado.")


def uf_code(text,territories):
    normalized=normalize(text)
    found={e.uf for e in territories.data.entries if e.kind=="uf" and normalized in
        {normalize(e.uf),normalize(e.name_original),*(normalize(v) for v in e.search_aliases)}}
    return next(iter(found)) if len(found)==1 else None


def explicit_ufs(question,territories):
    found=set()
    for e in territories.data.entries:
        if e.kind!="uf":continue
        short=bool(re.search(r"(?<![A-Za-z])"+e.uf+r"(?![A-Za-z])",question)) or bool(re.search(r"/\s*"+e.uf+r"\b",question,re.I))
        long=any(contains(a,question) for a in [e.name_original,*e.search_aliases] if len(normalize(a))>2)
        if short or long:found.add(e.uf)
    return found


def local_uf(mention,question,territories):
    text=normalize(question);key=normalize(mention)
    adjacent={uf for uf in explicit_ufs(question,territories) if re.search(r"\b"+re.escape(key)+r"\s+"+uf.lower()+r"\b",text)}
    if len(adjacent)==1:return next(iter(adjacent))
    all_ufs=explicit_ufs(question,territories)
    return next(iter(all_ufs)) if len(all_ufs)==1 else None


def metric_from_question(question,bindings):
    if bindings.get("metrica"):return Metric(bindings["metrica"]["code"])
    q=normalize(question)
    if "pontos percentuais" in q:return Metric.POINTS
    if "variacao percentual" in q or "em relacao a area inicial" in q or "em relacao a cobertura inicial" in q:return Metric.CHANGE
    if re.search(r"\b(participacao|proporcao)\b|fracao da area observada",q):return Metric.SHARE
    if "%" in question or re.search(r"\b(percentual|porcentagem|por cento)\b",q):
        raise NeedClarification("metrica","denominador_nao_definido",candidates=METRIC_CHOICES[1:])
    if re.search(r"\b(reducao|reduziram|reduziu)\b",q):return Metric.REDUCTION
    temporal=bool(re.search(r"\b(mudou|mudaram|diferenca|variacao absoluta|saldo liquido)\b",q))
    if temporal:return Metric.DELTA
    if re.search(r"\b(area|areas|hectare|hectares|km2|m2)\b",q):return Metric.AREA
    raise NeedClarification("metrica","metrica_nao_definida",candidates=METRIC_CHOICES)


def unit_from_question(question,mention,metric,bindings):
    confirmed=bindings.get("unidade")
    if confirmed:
        expected=confirmed["code"]
        if mention and normalize(mention) not in {normalize(expected),normalize(confirmed["label"])}:
            actual=UNITS.get(normalize(mention),"percentual" if mention=="%" else None)
            if actual!=expected:raise GroundingError("unit_mention","unidade_diverge_da_escolha_confirmada")
        return Unit(expected)
    named={unit for alias,unit in UNITS.items() if unit in {"ha","km2","m2"} and contains(alias,question)}
    if len(named)>1:raise NeedClarification("unidade","multiplas_unidades_sem_selecao",candidates=UNIT_CHOICES[:3])
    if mention:
        if not contains(mention,question):raise GroundingError("unit_mention","unidade_nao_citada")
        parsed=UNITS.get(normalize(mention),"percentual" if mention=="%" else None)
        if not parsed:raise NeedClarification("unidade","unidade_desconhecida",candidates=UNIT_CHOICES)
        return Unit(parsed)
    expected={Metric.SHARE:Unit.PERCENT,Metric.CHANGE:Unit.PERCENT,Metric.POINTS:Unit.PP}.get(metric)
    if expected:return expected
    raise NeedClarification("unidade","unidade_de_area_ausente",candidates=UNIT_CHOICES[:3])


def requested_years(question,bindings,operation):
    if bindings.get("periodo"):return bindings["periodo"]["years"]
    years=sorted({int(y) for y in re.findall(r"(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])",question)})
    if not years:raise NeedClarification("periodo","periodo_ausente")
    if operation==Operation.SERIES and len(years)==2 and re.search(r"(?:de|entre)\s*"+str(years[0])+r"\s*(?:a|até|ate|–|-)\s*"+str(years[1]),question,re.I):
        years=list(range(years[0],years[1]+1))
    return years


def ranking_limit(question,bindings):
    if bindings.get("limite"):return bindings["limite"]["limit"]
    q=normalize(question);words={"um":1,"uma":1,"dois":2,"duas":2,"tres":3,"quatro":4,"cinco":5,"seis":6,"sete":7,"oito":8,"nove":9,"dez":10,"vinte":20}
    matches=re.findall(r"\b(top)\s+(\d+)\b",q)
    found=[int(n) for _,n in matches]
    for number in re.findall(r"\b(\d+|"+"|".join(words)+r")\s+(?:maiores|menores|municipios|cidades)\b",q):
        found.append(int(number) if number.isdigit() else words[number])
    if not found and re.search(r"\bqual (?:o )?municipio\b",q):found=[1]
    if len(set(found))!=1 or not 1<=found[0]<=100:raise NeedClarification("limite","limite_ranking_ausente_ou_invalido")
    return found[0]


def operation_from_question(question,metric,count,bindings):
    if bindings.get("operacao"):return Operation(bindings["operacao"]["code"])
    q=normalize(question)
    ranking=bool(re.search(r"\b(ranking|top|maior|maiores|menor|menores|mais reduziram)\b",q)) and bool(re.search(r"\b(municipio|municipios|cidades)\b",q))
    if ranking:return Operation.RANKING
    if "serie" in q or "ano a ano" in q:return Operation.SERIES
    if count>=2:return Operation.TERRITORIAL
    if metric in {Metric.DELTA,Metric.REDUCTION,Metric.CHANGE,Metric.POINTS}:return Operation.TEMPORAL
    if len(set(re.findall(r"\b(?:19|20)[0-9]{2}\b",question)))>1:return Operation.SERIES
    return Operation.SHARE if metric==Metric.SHARE else Operation.AREA


def ground(proposal,question,bindings,context,classes,territories):
    candidate=proposal.intent
    # Ambiguidade lexical original prevalece sobre escolhas arbitrarias do modelo.
    if not bindings.get("classe"):
        for m in context["class_mentions"]:
            if len(m["candidate_codes"])>1:
                raise NeedClarification("classe","classe_ambigua",m["mention"],
                    [{"code":c,"name":classes.by_code[c].name,"kind":classes.by_code[c].kind} for c in m["candidate_codes"]])
    metric=metric_from_question(question,bindings)
    if candidate.metric is None:raise NeedClarification("metrica","metrica_ausente",candidates=METRIC_CHOICES)
    if candidate.metric!=metric:raise GroundingError("metric","metrica_diverge_da_pergunta")
    if candidate.metric_mention and not contains(candidate.metric_mention,question) and not bindings.get("metrica"):
        raise GroundingError("metric_mention","metrica_nao_citada")
    # Confere homonimos antes de usar o filtro que o modelo sugeriu.
    for m in context["territory_mentions"]:
        if bindings.get("territorio") and normalize(bindings["territorio"]["mention"])==m["mention"]:continue
        entries=[territories.by_code[c] for c in m["candidate_codes"]]
        if all(e.kind=="uf" for e in entries):continue
        kind="municipio" if re.search(r"\b(municipio|cidade)\b",normalize(question)) else None
        result=territories.resolve(TerritoryReference(name=m["mention"],uf=local_uf(m["mention"],question,territories),kind=kind))
        if result.status!="resolvido":raise NeedClarification("territorio",result.reason,m["mention"],result.candidates)
    resolved=[];references=[]
    for ref in candidate.territories:
        binding=bindings.get("territorio")
        accepted_binding=binding and normalize(ref.mention) in {normalize(binding["mention"]),normalize(binding["name"]),binding["code"]}
        if accepted_binding:
            result=territories.resolve(TerritoryReference(code=binding["code"]))
        else:
            if not contains(ref.mention,question):raise GroundingError("territories","territorio_nao_citado")
            uf=local_uf(ref.mention,question,territories)
            if ref.uf_mention:
                proposed=uf_code(ref.uf_mention,territories)
                entry=territories.by_code.get(ref.mention) if re.fullmatch(r'[0-9]{7}',ref.mention) else None
                if entry:
                    if proposed!=entry.uf:raise GroundingError('territories','uf_diverge_do_codigo_ibge')
                    if uf and uf!=proposed:raise GroundingError('territories','uf_diverge_da_pergunta')
                    uf=entry.uf
                else:
                    if not proposed or proposed not in explicit_ufs(question,territories):raise GroundingError("territories","uf_nao_citada")
                    if uf and uf!=proposed:raise GroundingError("territories","uf_diverge_da_pergunta")
                    if not uf:raise NeedClarification("territorio","vinculo_municipio_uf_ambiguo",ref.mention)
            if re.fullmatch(r"[0-9]{7}",ref.mention):reference=TerritoryReference(code=ref.mention,uf=uf)
            elif uf_code(ref.mention,territories) and normalize(ref.mention) in {normalize(e.uf) for e in territories.data.entries if e.kind=="uf"}:
                reference=TerritoryReference(kind="uf",uf=uf_code(ref.mention,territories))
            else:
                # kind so restringe busca quando a pergunta o declara ou todos os candidatos tem o mesmo tipo.
                natural_kind="municipio" if re.search(r"\b(municipio|cidade)\b",normalize(question)) else "uf" if re.search(r"\b(estado|uf)\b",normalize(question)) else None
                reference=TerritoryReference(name=ref.mention,uf=uf,kind=natural_kind)
            result=territories.resolve(reference)
        if result.status!="resolvido":raise NeedClarification("territorio",result.reason,ref.mention,result.candidates)
        code=str(result.selected_codes[0]);resolved.append(code);references.append({"code":code})
    operation=operation_from_question(question,metric,len(resolved),bindings)
    if candidate.operation is None:
        if operation==Operation.RANKING and candidate.scope_uf_mention and candidate.limit is not None:
            raise GroundingError('operation','operacao_ausente_na_proposta')
        raise NeedClarification("operacao","operacao_ausente")
    if candidate.operation!=operation:raise GroundingError("operation","operacao_diverge_da_pergunta")
    scope=None;limit=None;direction="desc"
    if operation==Operation.RANKING:
        if resolved:raise GroundingError("territories","ranking_territorios_deve_ser_vazio")
        if bindings.get("escopo"):scope=bindings["escopo"]["uf"]
        else:
            ufs=explicit_ufs(question,territories)
            scope=next(iter(ufs)) if len(ufs)==1 else None
        if not scope:raise NeedClarification("escopo","uf_do_ranking_ausente_ou_ambigua")
        if not candidate.scope_uf_mention and not bindings.get("escopo"):raise NeedClarification("escopo","uf_do_ranking_ausente")
        if candidate.scope_uf_mention and uf_code(candidate.scope_uf_mention,territories)!=scope:raise GroundingError("scope_uf_mention","escopo_divergente")
        limit=ranking_limit(question,bindings)
        if candidate.limit!=limit:raise GroundingError("limit","limite_diverge_da_pergunta")
        q=normalize(question)
        direction=bindings["ordenacao"]["direction"] if bindings.get("ordenacao") else "asc" if re.search(r"\b(menor|menores)\b",q) else "desc" if re.search(r"\b(maior|maiores|mais)\b",q) else None
        if direction is None:raise NeedClarification("ordenacao","ordem_do_ranking_ausente")
        if candidate.direction!=direction:raise GroundingError("direction","ordem_diverge_da_pergunta")
    else:
        if not resolved:raise NeedClarification("territorio","territorio_ausente")
        # Nao permitir omitir um dos territorios explicitamente reconhecidos.
        for m in context["territory_mentions"]:
            municipality_codes={c for c in m["candidate_codes"] if territories.by_code[c].kind=="municipio"}
            if municipality_codes and not municipality_codes.intersection(resolved):raise GroundingError("territories","territorio_citado_omitido")
    class_refs=[];selected=[]
    if not candidate.classes:raise NeedClarification("classe","classe_ausente")
    for ref in candidate.classes:
        binding=bindings.get("classe")
        accepted=binding and normalize(ref.mention) in {normalize(binding["mention"]),normalize(binding["name"]),str(binding["code"])}
        if accepted:resolution=classes.resolve(code=binding["code"])
        else:
            if not contains(ref.mention,question):raise GroundingError("classes","classe_nao_citada")
            numeric=re.fullmatch(r"(?:classe|codigo da classe|codigo)\s+([0-9]{1,2})",normalize(ref.mention))
            resolution=classes.resolve(code=int(numeric[1])) if numeric else classes.resolve(term=ref.mention)
        if resolution.status!="resolvido":raise NeedClarification("classe",resolution.reason,ref.mention,resolution.candidates)
        code=int(resolution.selected_codes[0]);class_refs.append({"code":code});selected.append(code)
    covered=set(classes.expand(selected))
    for m in context["class_mentions"]:
        if bindings.get("classe"):break
        required=set(classes.expand(m["candidate_codes"]))
        if not required<=covered:raise GroundingError("classes","classe_citada_omitida")
    if len(selected)>1 and not re.search(r"\b(uniao|soma|conjunto)\b",normalize(question)):
        raise NeedClarification("classe","uniao_de_classes_nao_confirmada",candidates=[{"code":c,"name":classes.by_code[c].name} for c in selected])
    years=requested_years(question,bindings,operation)
    if candidate.years!=years:raise GroundingError("years","anos_divergem_da_pergunta")
    unit=unit_from_question(question,candidate.unit_mention,metric,bindings)
    expected_unit={Metric.SHARE:Unit.PERCENT,Metric.CHANGE:Unit.PERCENT,Metric.POINTS:Unit.PP}.get(metric)
    if expected_unit and unit!=expected_unit:raise NeedClarification("unidade","unidade_incoerente_com_metrica",candidates=[{"code":expected_unit.value,"name":expected_unit.value}])
    denominator={Metric.SHARE:"area_observada",Metric.CHANGE:"area_inicial",Metric.POINTS:"participacao_por_ano"}.get(metric)
    if candidate.denominator not in {None,denominator}:raise GroundingError("denominator","denominador_diverge_da_metrica")
    if any(y<2015 or y>2025 for y in years):raise PolicyStop("dados_indisponiveis","periodo_fora_do_catalogo","O período solicitado não está materializado neste projeto.")
    return QueryIntent(operation=operation,territories=references,scope_uf=scope,classes=class_refs,years=years,
        metric=metric,unit=unit,denominator=denominator,direction=direction,limit=limit)
