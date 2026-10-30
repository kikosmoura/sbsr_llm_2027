"""Resume diagnostico novo sem preencher lacunas dos logs historicos."""
from pathlib import Path
from collections import Counter
from statistics import mean,median
from consultas_ambientais.evaluation.common import read,save,sha
from .audit import require
from .gateway_diagnostics_v4 import verify

def summarize(root,protocol,directory,code):
    root,protocol,directory,code=map(Path,(root,protocol,directory,code))
    frozen=verify(root,protocol,code);p=read(protocol/'protocol.json');run=read(directory/'run.json')
    require(run['state']=='concluida' and run['freeze_sha256']==frozen,'diagnostico_incompleto')
    paths=sorted((directory/'individual').glob('*.json'));require({f.name:sha(f) for f in paths}==run['individual_hashes'],'diagnostico_alterado')
    records=[read(f) for f in paths];historical=read(protocol/'historical.json');old={r['case_id']:r for r in historical}
    require({(r['case_id'],r['max_tokens']) for r in records}=={(cid,n) for cid in p['case_ids'] for n in p['budgets']},'grade_diagnostica_incompleta')
    groups=[];rows=[]
    from .equivalent_v3 import model_messages
    from consultas_ambientais.evaluation.common import digest
    bench=root/'benchmarks/controle_contrato_v1';inputs=read(bench/'inputs.json');schema=read(bench/'output_schema.json');system=(bench/'system.txt').read_text()
    for r in records:
        cid=r['case_id'];require(r['messages_sha256']==digest(model_messages(inputs[cid],[],schema,system)),'prompt_de_replay_alterado')
        old_record=read(root/'artifacts/evaluation/controle_contrato_v1/test/individual'/f'{cid}_B_eq_0.json')
        require(r['messages_sha256']==old_record['attempts'][0]['messages_sha256'],'replay_nao_repete_mensagem_original')
        chats=[e for e in r['events'] if e['endpoint']=='chat'];last=chats[-1] if chats else {};meta=last.get('response_metadata') or {}
        rows.append({'case_id':cid,'family_id':old[cid]['family_id'],'old_empty':old[cid]['empty_final_text'],'max_tokens':r['max_tokens'],
                     'error':r['error'],'http_status':last.get('http_status'),'http_attempts':len(chats),'finish_reason':meta.get('finish_reason'),
                     'content_state':meta.get('content_state'),'final_content_chars':meta.get('final_content_chars'),
                     'prompt_tokens':(meta.get('usage') or {}).get('prompt_tokens'),
                     'completion_tokens':(meta.get('usage') or {}).get('completion_tokens'),
                     'total_tokens':(meta.get('usage') or {}).get('total_tokens'),'reasoning_tokens':meta.get('reasoning_tokens'),
                     'reasoning_field_present':meta.get('reasoning_field_present'),'latency_seconds':r['latency_seconds']})
    for empty in [True,False]:
        for budget in p['budgets']:
            selected=[r for r in rows if r['old_empty']==empty and r['max_tokens']==budget]
            n=len(selected);require(n>0,'grupo_vazio')
            groups.append({'selected_on':'old_empty' if empty else 'positive_control','max_tokens':budget,'cases':n,
                'nonempty_final_text':sum(r['content_state']=='texto' for r in selected),'valid_contract':sum(r['error'] is None for r in selected),
                'empty_final_text':sum(r['error']=='texto_final_ausente' for r in selected),
                'finish_reason_counts':dict(Counter(r['finish_reason'] if r['finish_reason'] is not None else 'nao_informado' for r in selected)),
                'completion_equals_requested_limit':sum(r['completion_tokens']==budget for r in selected),
                'empty_and_length':sum(r['error']=='texto_final_ausente' and r['finish_reason']=='length' for r in selected),
                'missing_usage':sum(r['total_tokens'] is None for r in selected),
                'prompt_tokens_sum_observed':sum(r['prompt_tokens'] or 0 for r in selected),'completion_tokens_sum_observed':sum(r['completion_tokens'] or 0 for r in selected),
                'latency_mean_seconds':mean(r['latency_seconds'] for r in selected),'latency_median_seconds':median(r['latency_seconds'] for r in selected)})
    events=[e for r in records for e in r['events']];empty_old=[r for r in historical if r['empty_final_text']]
    report={'schema_version':'diagnostico-retornos-resumo-v1','state':'verificado','run_id':run['run_id'],'freeze_sha256':frozen,
        'records':len(records),'groups':groups,'individual_rows':rows,
        'http_status_counts':{kind:dict(Counter(str(e['http_status']) for e in events if e['endpoint']==kind)) for kind in ['oauth','chat']},
        'transport_error_counts':dict(Counter(e['transport_error'] for e in events if e.get('transport_error'))),
        'reasoning_token_counter_missing':sum(r['reasoning_tokens'] is None for r in rows),
        'reasoning_field_present':sum(r['reasoning_field_present'] is True for r in rows),
        'input_tokens_min':min(r['prompt_tokens'] for r in rows if r['prompt_tokens'] is not None),
        'input_tokens_max':max(r['prompt_tokens'] for r in rows if r['prompt_tokens'] is not None),
        'input_tokens_same_within_case':all(len({r['prompt_tokens'] for r in rows if r['case_id']==cid})==1 for cid in p['case_ids']),
        'historical':{'empty_cases':len(empty_old),'families':dict(Counter(r['family_id'] for r in empty_old)),
            'http_status_captured':sum(r['http_status_logged'] is not None for r in empty_old),'finish_reason_captured':0,'usage_captured':0,
            'max_tokens_configured':2048,'timeout_seconds_configured':60,
            'latency_min_seconds':min(r['latency_seconds'] for r in empty_old),'latency_max_seconds':max(r['latency_seconds'] for r in empty_old),
            'latency_mean_seconds':mean(r['latency_seconds'] for r in empty_old),'client_path_inference':'texto_final_ausente so e emitido apos resposta 2xx com JSON objeto; codigo nao informa qual 2xx nem historico de retries HTTP'},
        'limitations':['Replays novos e selecionados pelas falhas antigas; nao substituem o experimento V3.',
            'Logs originais nao capturaram finish_reason/usage quando nao houve texto; a causa historica individual nao e recuperavel.',
            'Somente o limite de saida difere entre replays; mesmo modelo identificado nao garante pesos/infraestrutura remota identicos.',
            'length identifica encerramento por limite reportado pelo servico; nao prova a causa interna do gateway.',
            'Sem texto de raciocinio, corpos HTTP, credenciais ou precos estimados nos registros.'],
        'V3_records_replaced':False,'raw_response_stored':False,'reasoning_text_stored':False}
    return report

def narrative(report):
    g={(r['selected_on'],r['max_tokens']):r for r in report['groups']};a=g['old_empty',2048];b=g['old_empty',4096]
    return (f'Os logs historicos dos 26 casos nao preservaram finish_reason, usage ou status HTTP final. '
        f'Em replays novos selecionados por falha, com as mesmas mensagens, houve {a["empty_final_text"]}/26 retornos vazios a 2.048 tokens '
        f'e {b["empty_final_text"]}/26 a 4.096. No primeiro limite, {a["empty_and_length"]} casos combinaram texto ausente e finish_reason=length; '
        f'{a["completion_equals_requested_limit"]}/26 consumiram exatamente o limite de saida informado. '
        'Esses dados diagnosticam as novas chamadas, sem reconstruir a causa das antigas nem substituir os seus escores.')
