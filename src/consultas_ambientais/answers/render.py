"""Frases quantitativas determinadas por template; arredondamento somente aqui."""
from ..contracts import Metric

LABELS={Metric.AREA:"área mapeada",Metric.SHARE:"participação na área observada",
    Metric.DELTA:"diferença líquida (final menos inicial)",Metric.REDUCTION:"redução líquida",
    Metric.CHANGE:"variação percentual em relação à área inicial",Metric.POINTS:"diferença de participação"}
UNITS={"ha":"ha","km2":"km²","m2":"m²","percentual":"%","pontos_percentuais":"pontos percentuais"}

def number(value):
    text=f"{value:,.2f}".replace(",","_").replace(".",",").replace("_",".")
    # Evitar -0,00 no texto, sem alterar o valor exportado.
    return "0,00" if text=="-0,00" else text

def render(answer):
    lines=[];evidence={e.evidence_id:e for e in answer.evidence}
    if answer.ranking:
        r=answer.ranking
        lines.append("Classes: "+"; ".join(answer.execution.class_names)+"; anos: "+", ".join(str(y) for y in answer.plan.years)+".")
        lines.append(f"Ranking de municípios de {r.scope_uf}: {LABELS[r.metric]}, ordem {r.direction}; universo completo de {r.candidate_count} municípios, desempate por código IBGE crescente.")
        if r.filtered_non_reductions:lines.append(f"Foram excluidos {r.filtered_non_reductions} municípios sem redução líquida.")
        if r.undefined_codes:lines.append(f"{len(r.undefined_codes)} municípios possuem metrica indefinida e nao foram ordenados.")
        if not answer.values:lines.append("Nenhum município apresentou redução líquida no periodo solicitado." if r.metric==Metric.REDUCTION else "Nenhum município possui valor definido para a métrica solicitada.")
    if answer.plan.operation.value=="serie_disponivel":lines.append("Série restrita aos anos solicitados e materializados; sem interpolação de anos ausentes.")
    for value in answer.values:
        e=evidence[value.evidence_id];t=e.territory
        territory=f"{t.name}/{t.uf} (IBGE {t.code})"
        years=str(e.years[0]) if len(e.years)==1 else f"{e.years[0]}–{e.years[-1]}"
        classes="; ".join(e.class_names)
        prefix=f"{value.rank}. " if value.rank else ""
        if value.value is None:
            result=f"indefinida ({value.undefined_reason})"
        else:result=f"{number(value.value)} {UNITS[value.unit.value]}"
        line=f"{prefix}{territory}: {LABELS[value.metric]} de {classes}, em {years}: {result}."
        if e.denominator_definition:
            denominators=", ".join(number(v)+" ha" for v in e.denominator_values_ha)
            line+=f" Denominador: {e.denominator_definition} ({denominators})."
        if e.observations[0].support=="comum":line+=" Calculada no suporte válido comum dos dois anos."
        lines.append(line)
    if answer.execution:
        context=answer.execution
        lines.append(f"Coleção {context.collection}; revisão {context.source_revision or 'desconhecida'}; malha {context.territorial_edition or 'edição desconhecida'}; método {context.method}; execução {context.run_id}.")
    return "\n".join(lines)
