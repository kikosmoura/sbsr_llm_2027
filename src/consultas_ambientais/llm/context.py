"""Candidatos por superficie literal; malha, conexao e fatos de area nao entram no prompt."""
import re
from ..semantics.normalization import normalize
from ..semantics.models import TerritoryReference


def mentions(index,question):
    q=normalize(question);hits=[]
    for alias,codes in index.items():
        if not alias or len(alias)<3:continue
        wrapped=" "+q+" ";needle=" "+alias+" ";pos=wrapped.find(needle)
        while pos>=0:
            hits.append({"mention":alias,"codes":sorted(codes),"start":pos,"end":pos+len(alias)})
            pos=wrapped.find(needle,pos+1)
    selected=[]
    for hit in sorted(hits,key=lambda x:(-(x["end"]-x["start"]),x["start"])):
        if not any(hit["start"]<h["end"] and h["start"]<hit["end"] for h in selected):selected.append(hit)
    return sorted(selected,key=lambda x:x["start"])


def class_composition_word(mention, question):
    """'uniao da classe' e uma operacao, preservando municipio Uniao explicito."""
    if mention['mention']!='uniao':return False
    q=normalize(question)
    before=q[:mention['start']];after=q[mention['end']:]
    explicit_city=bool(re.search(r'\b(?:municipio|cidade)(?: de)?\s*$',before))
    return not explicit_city and bool(re.match(r'\s+(?:da|das|de)\s+classes?\b',after))


def build_context(question,bindings,classes,territories,store,config):
    class_mentions=mentions(classes.index,question)
    territory_mentions=[m for m in mentions(territories.index,question)
        if not class_composition_word(m,question) and not any(m["start"]<c["end"] and c["start"]<m["end"] for c in class_mentions)]
    codes={c for m in territory_mentions for c in m["codes"]}
    for code in re.findall(r"(?<![0-9])(?:[0-9]{7})(?![0-9])",question):
        if code in territories.by_code:codes.add(code)
    selected=bindings.get("territorio")
    if selected:codes.add(selected["code"])
    # Siglas explicitas e nomes de UF servem como candidatos, nao filtros de disponibilidade.
    for entry in territories.data.entries:
        if entry.kind=="uf" and re.search(r"(?<![A-Za-z])"+entry.uf+r"(?![A-Za-z])",question):codes.add(entry.code)
    all_codes=sorted(codes);candidates=[]
    for code in all_codes[:config.max_candidates]:
        entry=territories.by_code[code]
        annual=[r.years[0] for r in store.capabilities.materializations if r.territory_code==code and len(r.years)==1 and r.complete]
        candidates.append({"code":code,"name":entry.name_original,"aliases":entry.search_aliases,"kind":entry.kind,"uf":entry.uf,"materialized_complete_years":sorted(annual)})
    years=sorted({y for r in store.capabilities.materializations for y in r.years})
    pairs=sorted({tuple(r.years) for r in store.capabilities.materializations if len(r.years)==2})
    pilot=store.identity["config"]["pilot_uf"] if "pilot_uf" in store.identity["config"] else store.project.pilot_uf
    context={"schema_version":"contexto-textual-v1","collection":11,
        "class_catalog":[{"code":c.code,"name":c.name,"parent_code":c.parent_code,"leaf_codes":c.leaf_codes,
            "aliases":c.aliases,"beta":c.beta,"kind":c.kind} for c in classes.data.classes],
        "available_scope":{"uf":pilot,"materialized_years":years,"comparable_pairs":[list(p) for p in pairs],
            "ranking_eligible":store.manifest.get("ranking_eligible",False),"scope_is_not_national":True},
        "territory_candidates":candidates,"candidate_count":len(all_codes),"candidates_truncated":len(all_codes)>len(candidates),
        "class_mentions":[{"mention":m["mention"],"candidate_codes":m["codes"]} for m in class_mentions],
        "territory_mentions":[{"mention":m["mention"],"candidate_codes":m["codes"]} for m in territory_mentions],
        "confirmed_choices":bindings}
    return context
