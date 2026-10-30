"""Execucao pareada auditavel. Gold e lido somente apos obter a resposta de cada caso."""
from pathlib import Path
import concurrent.futures
import time
from uuid import uuid4
from .common import read, lines, save, now, sha, digest
from .protocol import verify
from .baselines import run_baseline, failure
from .scoring import score
from ..llm.client import GatewayClient
from ..llm.conversation import ConversationService
from ..llm.dialogue_models import InterpretationConfig
from ..llm.privacy import Redactor
from ..delivery.settings import load_environment


def public_configuration(local, environment):
    s=environment.settings
    redactor=Redactor.from_environment(s)
    return {'requested_model':redactor.model_name(s.model),'temperature':s.temperature,'max_tokens':s.max_tokens,
            'timeout_seconds':s.timeout,'http_max_attempts':s.max_attempts,'max_repairs':1,
            'stream':False,'tls_verified':True,'custom_ca':bool(s.ca_bundle),
            'native_tools':False,'native_response_format':False,'llm_seed_sent':False,
            'workers':3,'C_interpretation':InterpretationConfig(max_output_tokens=2048).model_dump(mode='json')}


def normalized_C(answer):
    raw=answer.model_dump(mode='json')
    plan=raw['query']['plan'] if raw.get('query') else None
    if plan is None and raw.get('decision'):
        plan=raw['decision'].get('normalized_plan')
    values=[]
    if raw.get('query'):
        evidences={e['evidence_id']:e for e in raw['query']['evidence']}
        for v in raw['query']['values']:
            e=evidences[v['evidence_id']]
            values.append({'territory_code':e['territory']['code'],'years':e['years'], 'value':v['value'],
                           'unit':v['unit'],'undefined_reason':v['undefined_reason'],
                           'denominators_ha':e['denominator_values_ha'],'rank':v['rank']})
    return {'status':raw['status'],'plan':plan,'values':values,
            'clarification_field':raw['clarification']['field'] if raw['clarification'] else None,'reason':raw['reason']},raw


def execute(root, benchmark, output, split, project, local, environment, smoke=False, repeat=False):
    root,benchmark,output=map(Path,(root,benchmark,output))
    config=public_configuration(local,environment)
    frozen=verify(benchmark,root,config)
    protocol=read(benchmark/'protocol.json')
    cases=[c for c in lines(benchmark/'cases.jsonl') if c['split']==split]
    if smoke:
        if split!='dev':raise ValueError('smoke_apenas_desenvolvimento')
        cases=[c for c in cases if c['case_id'] in protocol['dev_smoke_case_ids']]
    output.mkdir(parents=True,exist_ok=True)
    manifest={'run_id':uuid4().hex,'created_at':now(),'split':split,'case_ids':[c['case_id'] for c in cases],
              'integration_kind':'gateway_real','configuration':config,'freeze_sha256':frozen,
              'repeat_requested':repeat,'data_run_id':local.run_id,'state':'em_execucao'}
    if (output/'run.json').exists():
        previous=read(output/'run.json')
        for key in ['split','case_ids','freeze_sha256','configuration','repeat_requested']:
            if previous[key]!=manifest[key]:raise ValueError('retomada_divergente')
        manifest=previous
    else:save(output/'run.json',manifest)
    facts=read(benchmark/'facts.json')
    leaves=read(benchmark/'classes.json')
    gold_path=benchmark/'gold.json'
    tasks=[]
    for index,case in enumerate(cases):
        order=['A','B','C'];order=order[index%3:]+order[:index%3]
        for condition in order:tasks.append((case,condition,0))
    if repeat:
        tasks.extend((c,k,1) for c in cases if c['case_id'] in protocol['repeat_case_ids'] for k in ['A','B','C'])
    def work(task):
        case,condition,repetition=task
        path=output/'individual'/f"{case['case_id']}_{condition}_{repetition}.json"
        if path.exists():
            existing=read(path)
            if existing['freeze_sha256']!=frozen or existing['run_id']!=manifest['run_id']:
                raise ValueError('registro_individual_divergente')
            return case['case_id'],condition,'retomado'
        client=GatewayClient(environment.settings)
        redactor=Redactor.from_environment(environment.settings)
        redactor=Redactor([*redactor.secrets,*environment.redaction_secrets])
        start=time.monotonic();raw=None;attempts=[];messages_hash=None
        try:
            if condition=='C':
                service=ConversationService(root,project,local.run_id,root/local.territories,root/local.capabilities,
                                            client,environment.settings,InterpretationConfig(max_output_tokens=2048))
                service.redactor=redactor
                result=service.ask(case['question'])
                observed,raw=normalized_C(result)
                attempts=raw['attempts'];latency=raw['latency_seconds']
            else:
                observed,attempts,latency,messages_hash=run_baseline(condition,case['question'],facts[case['case_id']],client,redactor,protocol['max_context_bytes_B'])
        except Exception:
            # Nao imprimir traceback/corpo remoto. A falha permanece no denominador.
            observed=failure('falha_tecnica_runner');latency=time.monotonic()-start
        finally:client.close()
        # Nunca enviar gabarito ou case_id ao modelo. Escores somente depois da resposta.
        expected=read(gold_path)[case['case_id']]
        scored=score(observed,expected,protocol,leaves)
        final=raw['message'] if raw else __import__('json').dumps(observed,ensure_ascii=False)
        record={'schema_version':'avaliacao-caso-v1','run_id':manifest['run_id'],'case_id':case['case_id'],
                'family_id':case['family_id'],'territory_codes':case['territory_codes'],'condition':condition,'repeat':repetition,
                'created_at':now(),'integration_kind':'gateway_real','question':case['question'],
                'freeze_sha256':frozen,'configuration':config,'facts_sha256':digest(facts[case['case_id']]) if condition=='B' else None,
                'messages_sha256':messages_hash,'model':config['requested_model'],'observed':observed,
                'final_answer':final,'plan':observed['plan'],'result':raw['query'] if raw else observed['values'],
                'attempts':attempts,'latency_seconds':latency,'scores':scored,'cost':None,
                'source_context':raw.get('source_context') if raw else {'data_run_id':local.run_id},
                'C_session_id':raw.get('session_id') if raw else None,'C_turn_id':raw.get('turn_id') if raw else None,
                'C_candidate_intent':raw.get('intent') if raw else None,'C_decision':raw.get('decision') if raw else None}
        # So dados tipados e campos explicitamente selecionados; nunca reasoning.
        serialized=__import__('json').dumps(record,ensure_ascii=False)
        safe,redactions=redactor.clean(serialized)
        if redactions:
            raise ValueError('registro_avaliacao_contem_valor_privado')
        save(path,record)
        return case['case_id'],condition,'registrado'
    completed=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=config['workers']) as pool:
        futures=[pool.submit(work,t) for t in tasks]
        for future in concurrent.futures.as_completed(futures):
            cid,condition,state=future.result();completed+=1
            # Progresso sem acertos/gold: nao observar teste para ajustar o sistema.
            print(f'{split}: {completed}/{len(tasks)} {cid} {condition} {state}',flush=True)
    verify(benchmark,root,config)
    manifest.update(state='concluida',completed_at=now(),individual_hashes={p.name:sha(p) for p in sorted((output/'individual').glob('*.json'))})
    save(output/'run.json',manifest)
    return manifest
