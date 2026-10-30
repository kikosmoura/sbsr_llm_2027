"""Auditar identidade de mensagens/configuracao e resumir transporte sem corpos."""
from collections import Counter
from consultas_ambientais.evaluation.common import read
from consultas_ambientais.evaluation.scoring import near
from .audit import require

def summarize(root,records):
    rows=[];groups=[];discrepancies=[]
    gold=read(root/'benchmarks/controle_contrato_v1/reference.json');policy=read(root/'benchmarks/controle_contrato_v1/scoring_protocol.json')
    for r in records:
        old=read(root/'artifacts/evaluation/controle_contrato_v1/test/individual'/f'{r["case_id"]}_{r["condition"]}_0.json')
        require(r['messages_sha256']==old['messages_sha256'],'mensagens_iniciais_alteradas')
        expected={**old['configuration'],'max_tokens':4096}
        require(r['configuration']==expected,'outros_parametros_alterados')
        events=[e for e in r['http_events'] if e['endpoint']=='chat'];last=(events[-1].get('response_metadata') or {}) if events else {}
        rows.append({'case_id':r['case_id'],'family_id':r['family_id'],'condition':r['condition'],'repeat':r['repeat'],
            'status':r['observed']['status'],'correct':r['scores']['correct'],'latency_seconds':r['latency_seconds'],
            'http_statuses':[e['http_status'] for e in events],'finish_reasons':[(e.get('response_metadata') or {}).get('finish_reason') for e in events],
            'last_content_state':last.get('content_state'),'last_completion_tokens':(last.get('usage') or {}).get('completion_tokens'),
            'last_prompt_tokens':(last.get('usage') or {}).get('prompt_tokens')})
        if r['repeat']==0 and not r['scores']['correct'] and r['observed']['status']=='respondida':
            expected=gold[r['case_id']]['values'];actual=r['observed']['values']
            discrepancies.append({'case_id':r['case_id'],'condition':r['condition'],'observed_values':actual,'reference_values':expected,
                'value_outside_frozen_tolerance':any(not near(a['value'],b['value'],b['unit'],policy) for a,b in zip(actual,expected)),
                'interpretation':'discrepancia observada; nao se infere processo cognitivo ou causa interna'})
    for condition in ['B_eq','C_eq']:
        rs=[r for r in records if r['repeat']==0 and r['condition']==condition]
        ev=[e for r in rs for e in r['http_events'] if e['endpoint']=='chat'];metas=[e.get('response_metadata') or {} for e in ev]
        groups.append({'condition':condition,'cases':len(rs),'http_chat_requests':len(ev),
            'http_status_counts':dict(Counter(str(e['http_status']) for e in ev)),
            'transport_error_counts':dict(Counter(e['transport_error'] for e in ev if e.get('transport_error'))),
            'finish_reason_counts':dict(Counter(str(m.get('finish_reason')) for m in metas)),
            'usage_missing_responses':sum(m.get('usage') is None for m in metas),
            'usage_sum_observed_in_transport':{k:sum((m.get('usage') or {}).get(k,0) for m in metas) for k in ['prompt_tokens','completion_tokens','total_tokens']},
            'completion_equals_4096':sum((m.get('usage') or {}).get('completion_tokens')==4096 for m in metas),
            'reasoning_tokens_missing':sum(m.get('reasoning_tokens') is None for m in metas),'cost':None})
    return {'source':'http_events das 176 observacoes principais; repeticoes separadas','groups':groups,'individual_rows':rows,'nontechnical_discrepancies':discrepancies,
        'all_initial_messages_match_V3':True,'only_payload_parameter_changed':'max_tokens de 2048 para 4096',
        'reasoning_text_stored':False,'raw_response_stored':False,'earlier_records_replaced':False}
