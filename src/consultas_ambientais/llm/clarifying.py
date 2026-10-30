"""Perguntas fixas e escolhas confirmadas, sem texto livre do modelo."""
import re
from uuid import uuid4
from ..contracts import Metric,Operation
from ..semantics.normalization import normalize
from ..semantics.models import TerritoryReference
from .dialogue_models import Clarification
from .grounding import NeedClarification,uf_code,metric_from_question,UNITS,UNIT_CHOICES,METRIC_CHOICES

QUESTIONS={"territorio":"Qual território? Informe código IBGE ou nome e UF, escolhendo um dos candidatos quando houver.",
    "classe":"Qual classe ou grupo da legenda você pretende consultar? Confirme nome ou código.",
    "metrica":"Você deseja área, participação na área observada, diferença líquida, redução líquida, variação percentual em relação à área inicial ou pontos percentuais?",
    "unidade":"Em qual unidade: ha, km² ou m²? Para participações/variações percentuais, confirme percentual; para diferenças de participação, pontos percentuais.",
    "periodo":"Quais anos? Informe um ano ou o par desejado; uma série deve especificar os anos.",
    "escopo":"Qual UF deve definir o universo completo do ranking?",
    "limite":"Quantos municípios devem aparecer no ranking (1 a 100)?",
    "ordenacao":"Deseja ordem crescente (asc) ou decrescente (desc)?",
    "operacao":"Qual operação: área, participação, comparação temporal, série disponível, comparação territorial ou ranking completo de uma UF?"}


def clarification(need):
    return Clarification(clarification_id=uuid4().hex,field=need.field,reason=need.reason,
        question=QUESTIONS[need.field],mention=need.mention,candidates=need.candidates)


def apply_reply(pending,reply,bindings,classes,territories):
    field=pending["field"];candidates=pending["candidates"];mention=pending.get("mention")
    result=dict(bindings);q=normalize(reply)
    def invalid():raise NeedClarification(field,"resposta_nao_resolve_esclarecimento",mention,candidates)
    if field=="territorio":
        codes={str(c["code"]) for c in candidates}
        matched=[c for c in candidates if reply.strip()==str(c["code"]) or q==normalize(c.get("name_original",c.get("name","")))]
        uf=uf_code(reply.strip(),territories)
        if uf and candidates:matched=[c for c in candidates if c["uf"]==uf]
        if not matched:
            raw=reply.strip();suffix=re.fullmatch(r"(.+?)/\s*([A-Za-z]{2})",raw)
            ref=TerritoryReference(code=raw) if re.fullmatch(r"[0-9]{7}|[0-9]{2}",raw) else TerritoryReference(name=suffix[1] if suffix else raw,uf=suffix[2].upper() if suffix else None)
            resolution=territories.resolve(ref)
            if resolution.status!="resolvido":invalid()
            code=str(resolution.selected_codes[0])
            if codes and code not in codes:invalid()
            e=territories.by_code[code];matched=[{"code":code,"name_original":e.name_original,"uf":e.uf}]
        if len(matched)!=1:invalid()
        chosen=matched[0];entry=territories.by_code[str(chosen["code"])]
        result[field]={"code":entry.code,"name":entry.name_original,"uf":entry.uf,"mention":mention or entry.name_original}
    elif field=="classe":
        resolution=classes.resolve(code=int(reply.strip())) if re.fullmatch(r"[0-9]{1,2}",reply.strip()) else classes.resolve(term=reply)
        if resolution.status!="resolvido":invalid()
        code=int(resolution.selected_codes[0])
        if candidates and code not in {int(c["code"]) for c in candidates}:invalid()
        result[field]={"code":code,"name":classes.by_code[code].name,"mention":mention or classes.by_code[code].name}
    elif field=="metrica":
        aliases={normalize(m.value):m for m in Metric}
        metric=aliases.get(q)
        if metric is None:
            try:metric=metric_from_question(reply,{})
            except NeedClarification:invalid()
        result[field]={"code":metric.value,"label":next(c["name"] for c in METRIC_CHOICES if c["code"]==metric.value)}
    elif field=="unidade":
        unit="percentual" if reply.strip()=="%" else UNITS.get(q)
        if unit is None:invalid()
        if candidates and unit not in {c["code"] for c in candidates}:invalid()
        result[field]={"code":unit,"label":reply.strip()}
    elif field=="periodo":
        if not re.fullmatch(r"\s*[0-9]{4}(?:\s*(?:,|e|a|ate|-|–)\s*[0-9]{4})*\s*",q):invalid()
        years=sorted({int(y) for y in re.findall(r"[0-9]{4}",q)})
        if not 1<=len(years)<=11:invalid()
        result[field]={"years":years}
    elif field=="escopo":
        uf=uf_code(reply,territories)
        if not uf:invalid()
        result[field]={"uf":uf}
    elif field=="limite":
        if not reply.strip().isdigit() or not 1<=int(reply.strip())<=100:invalid()
        result[field]={"limit":int(reply.strip())}
    elif field=="ordenacao":
        direction={"asc":"asc","crescente":"asc","menores":"asc","desc":"desc","decrescente":"desc","maiores":"desc"}.get(q)
        if not direction:invalid()
        result[field]={"direction":direction}
    elif field=="operacao":
        choices={normalize(o.value):o.value for o in Operation}
        if q not in choices:invalid()
        result[field]={"code":choices[q]}
    return result
