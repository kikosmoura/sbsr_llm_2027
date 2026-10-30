"""Exportacao sem arredondar os dados; texto e gerado separadamente."""
import csv
import io
import json
import os
from pathlib import Path
from ..contracts import ResponseStatus

FIELDS=["status","reason","message","answer_id","plan_id","execution","executed_plan","requested_plan","evidence_id","run_id","territory_code","territory_name","uf",
    "class_codes","class_names","years","metric","value","undefined_reason","unit","area_value_ha","denominator_definition","denominator_value","denominator_unit",
    "denominator_values_ha","observations","common_support_id","method","collection","source_revision","mesh_sha256","territorial_edition",
    "provenance","source_ids","sources","rank","ranking"]

def json_text(answer):return json.dumps(answer.model_dump(mode="json"),ensure_ascii=False,indent=2,allow_nan=False)+"\n"

def csv_text(answer):
    output=io.StringIO(newline="");writer=csv.DictWriter(output,fieldnames=FIELDS);writer.writeheader()
    base={"status":answer.status.value,"reason":answer.reason,"message":answer.message,"answer_id":answer.answer_id,"plan_id":answer.plan_id,"execution":answer.execution.model_dump(mode="json") if answer.execution else None,
        "executed_plan":answer.plan.model_dump(mode="json") if answer.plan else None,
        "requested_plan":answer.requested_plan.model_dump(mode="json") if answer.requested_plan else None}
    if answer.ranking:base["ranking"]=answer.ranking.model_dump(mode="json")
    evidence={e.evidence_id:e for e in answer.evidence};rows=[]
    for v in answer.values:
        e=evidence[v.evidence_id]
        rows.append({**base,"evidence_id":e.evidence_id,"run_id":e.run_id,"territory_code":e.territory.code,"territory_name":e.territory.name,"uf":e.territory.uf,
            "class_codes":e.class_codes,"class_names":e.class_names,"years":e.years,"metric":v.metric.value,"value":v.value,"undefined_reason":v.undefined_reason,"unit":v.unit.value,"area_value_ha":v.area_value_ha,
            "denominator_definition":e.denominator_definition,"denominator_value":v.denominator_value,"denominator_unit":v.denominator_unit.value if v.denominator_unit else None,
            "denominator_values_ha":e.denominator_values_ha,"observations":[o.model_dump() for o in e.observations],
            "common_support_id":e.quality.common_support_id,"method":e.area_method,"collection":e.collection,"source_revision":e.source_revision,
            "mesh_sha256":e.mesh_sha256,"territorial_edition":e.territory.edition,"provenance":e.provenance,
            "source_ids":e.source_ids,"sources":[s.model_dump() for s in e.sources],"rank":v.rank})
    for row in rows or [base]:
        clean={}
        for k,v in row.items():
            if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False,separators=(",",":"),allow_nan=False)
            # Textos de fonte nunca viram formulas de planilha; valores numericos mantem o sinal.
            if isinstance(v,str) and v.lstrip().startswith(("=","+","-","@")):v="'"+v
            clean[k]=v
        writer.writerow(clean)
    return output.getvalue()


def write_outputs(answer,json_path=None,csv_path=None,audit_dir=None):
    files=[]
    if json_path:files.append((Path(json_path),json_text(answer)))
    if csv_path:files.append((Path(csv_path),csv_text(answer)))
    if audit_dir and answer.status==ResponseStatus.ANSWERED:
        files.append((Path(audit_dir)/(answer.answer_id+".json"),json_text(answer)))
    if len({p.resolve() for p,_ in files})!=len(files):raise ValueError("destinos_de_exportacao_repetidos")
    temporary=[]
    try:
        for path,content in files:
            path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+".tmp")
            temp.write_text(content,encoding="utf-8");temporary.append((temp,path))
        for temp,path in temporary:os.replace(temp,path)
    finally:
        for temp,_ in temporary:
            if temp.exists():temp.unlink()
