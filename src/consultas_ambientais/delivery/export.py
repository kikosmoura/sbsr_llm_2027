"""Exportar valores do servidor: nenhuma metrica ou arredondamento novo."""
import json
from html import escape
from ..answers.export import csv_text
from ..answers.models import QueryAnswer
from .models import DeliveryError


def bounded_csv(query, limit):
    chunks, size = [], 0
    # Projecao de uma linha para o serializador existente; nenhuma formula nova.
    for i, value in enumerate(query.values or [None]):
        view = query.model_copy(update={'values': [value]}) if value is not None else query
        text = csv_text(view)
        chunk = text if i == 0 else text.partition('\n')[2]
        size += len(chunk.encode())
        if size > limit:
            raise DeliveryError('exportacao_excede_limite_local', 413)
        chunks.append(chunk)
    return ''.join(chunks)


def checked(text, limit):
    if len(text.encode()) > limit:
        raise DeliveryError('exportacao_excede_limite_local', 413)
    return text


def export(response, format, max_bytes=4194304):
    if format == 'json':
        return checked(response.model_dump_json(indent=2), max_bytes), 'application/json'
    query = response.result or QueryAnswer(status=response.status, reason=response.reason, message=response.message)
    if format == 'csv':
        return bounded_csv(query, max_bytes), 'text/csv; charset=utf-8'
    if format != 'html':
        raise ValueError('formato_nao_suportado')
    rows = []
    evidence = {e.evidence_id: e for e in query.evidence}
    for v in query.values:
        e = evidence[v.evidence_id]
        # repr(float) e reversivel para o valor interno, sem novas formulas.
        value = repr(v.value) if v.value is not None else 'null: ' + str(v.undefined_reason)
        cells = [e.territory.name, ','.join(map(str, e.class_codes)), ','.join(map(str, e.years)),
                 v.metric.value, value, v.unit.value,
                 '' if v.denominator_value is None else repr(v.denominator_value), v.evidence_id]
        rows.append('<tr>' + ''.join('<td>' + escape(str(c)) + '</td>' for c in cells) + '</tr>')
    body = ('<!doctype html><html lang="pt-br"><meta charset="utf-8"><title>Resultado verificável</title>'
            '<h1>Resultado verificável</h1><p>' + escape(response.message) + '</p>'
            '<p>Dados: ' + escape(response.data_kind) + ' | Resultado: ' + response.result_id + '</p>'
            '<table><thead><tr>' + ''.join('<th>' + c + '</th>' for c in
             ['Território', 'Classes', 'Anos', 'Métrica', 'Valor integral', 'Unidade', 'Denominador', 'Evidência']) +
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table><pre>' +
            escape(json.dumps({'execution': query.execution.model_dump(mode='json') if query.execution else None,
                              'source_context': response.source_context,
                              'limitations': response.limitations}, ensure_ascii=False, indent=2)) + '</pre></html>')
    return checked(body, max_bytes), 'text/html; charset=utf-8'
