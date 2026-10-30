"""Sensibilidade precongelada a 4096 tokens; nao altera o controle V3."""
import argparse,concurrent.futures,hashlib,json,random,time
from pathlib import Path
from uuid import uuid4
from typing import Literal
from pydantic import Field,model_validator,ValidationError
from consultas_ambientais.contracts import Contract
from consultas_ambientais.evaluation.models import NumericValue
from consultas_ambientais.evaluation.common import read,lines,save,sha,digest,canonical,now
from consultas_ambientais.evaluation.protocol import verify as verify_original
from consultas_ambientais.evaluation.scoring import score
from consultas_ambientais.evaluation.statistics import paired_bootstrap
from consultas_ambientais.llm.interpreting import strict_json
from consultas_ambientais.llm.client import GatewayClient,GatewayError
from consultas_ambientais.llm.privacy import Redactor
from consultas_ambientais.delivery.settings import LocalSettings,load_environment
from consultas_ambientais.settings import ProjectConfig
from consultas_ambientais.queries.engine import QueryEngine,preflight,executor_digest
from consultas_ambientais.semantics.catalog import ClassCatalog
from consultas_ambientais.semantics.territories import TerritoryCatalog
from .audit import require


from .equivalent_v3 import complete,executor_observation,model_messages,verify as verify_original_control
from .gateway_diagnostics_v4 import ObservedSession
import shutil


def runtime(code):
    return {'runner':sha(code/'science/sensitivity_v5.py'),'entrypoint':sha(code/'executar_sensibilidade_v5.py'),
            'observer':sha(code/'science/gateway_diagnostics_v4.py')}

def prepare(root,target,code):
    root,target,code=map(Path,(root,target,code));require(not target.exists(),'destino_existente')
    source=root/'benchmarks/controle_contrato_v1';parent=verify_original_control(source,root,code)
    target.mkdir(parents=True)
    for name in read(source/'freeze.json')['files']:shutil.copy2(source/name,target/name)
    protocol=read(target/'protocol.json');protocol.update(llm_max_tokens=4096,version='controle-contrato-4096-v1',
        analysis_role='sensibilidade adicional; casos reutilizados; nao substitui V3',parent_freeze_sha256=parent)
    save(target/'protocol.json',protocol)
    frozen={'created_at':now(),'parent_freeze_sha256':parent,'kind':'sensitivity_full_paired_4096',
        'runtime':runtime(code),'files':{f.name:sha(f) for f in sorted(target.iterdir()) if f.is_file()}}
    save(target/'freeze.json',frozen);return frozen

def verify(target,root,code):
    target,root,code=map(Path,(target,root,code));f=read(target/'freeze.json')
    parent=verify_original_control(root/'benchmarks/controle_contrato_v1',root,code)
    require(f['parent_freeze_sha256']==parent and f['runtime']==runtime(code),'congelamento_sensibilidade_divergente')
    require(all(sha(target/n)==h for n,h in f['files'].items()),'entradas_sensibilidade_alteradas')
    source=root/'benchmarks/controle_contrato_v1'
    require(all(sha(target/n)==sha(source/n) for n in f['files'] if n!='protocol.json'),'contexto_ou_criterios_alterados')
    old=read(source/'protocol.json');new=read(target/'protocol.json')
    require(new['llm_max_tokens']==4096,'orcamento_incorreto')
    require({k:v for k,v in new.items() if k not in {'llm_max_tokens','version','analysis_role','parent_freeze_sha256'}}==
            {k:v for k,v in old.items() if k not in {'llm_max_tokens','version'}},'outros_parametros_alterados')
    return sha(target/'freeze.json')


def run(root,benchmark,output,code,split,env_file,repeats=False):
    root,benchmark,output,code=map(Path,(root,benchmark,output,code));frozen=verify(benchmark,root,code)
    protocol=read(benchmark/'protocol.json');cases=[c for c in lines(benchmark/'cases.jsonl') if c['split']==split]
    local=LocalSettings.load(root/'configs/local.json');local.llm_timeout_seconds=protocol['llm_timeout_seconds']
    local.llm_max_tokens=2048;local.llm_max_attempts=protocol['http_max_attempts'];local.temperature=protocol['temperature']
    environment=load_environment(local,env_file);environment.settings=environment.settings.model_copy(update={'max_tokens':protocol['llm_max_tokens']});require(environment.settings.model==protocol['llm_model'],'modelo_divergente')
    require(environment.settings.verify is True or isinstance(environment.settings.verify,str),'TLS_nao_verificado')
    inputs=read(benchmark/'inputs.json');schema=read(benchmark/'output_schema.json');system=(benchmark/'system.txt').read_text()
    project=ProjectConfig.load(root/'configs/project.json');output.mkdir(parents=True,exist_ok=True)
    config={'requested_model':protocol['llm_model'],'temperature':local.temperature,'max_tokens':protocol['llm_max_tokens'],
        'timeout_seconds':local.llm_timeout_seconds,'http_max_attempts':local.llm_max_attempts,'max_repairs':protocol['max_repairs'],
        'stream':False,'tls_verified':True,'native_tools':False,'native_response_format':False,'workers':protocol['workers']}
    manifest={'run_id':uuid4().hex,'created_at':now(),'split':split,'case_ids':[c['case_id'] for c in cases],
        'configuration':config,'freeze_sha256':frozen,'repeat_requested':repeats,'state':'em_execucao','integration_kind':'gateway_real'}
    if (output/'run.json').exists():
        previous=read(output/'run.json')
        require(all(previous[k]==manifest[k] for k in ['split','case_ids','configuration','freeze_sha256','repeat_requested']),'retomada_divergente');manifest=previous
    else:save(output/'run.json',manifest)
    rng=random.Random(protocol['run_order_seed']);tasks=[];order_records=[]
    for c in cases:
        order=['B_eq','C_eq'];rng.shuffle(order);order_records.append({'case_id':c['case_id'],'order':order})
        tasks.extend((c,k,0) for k in order)
    if repeats:tasks.extend((c,k,1) for c in cases if c['case_id'] in protocol['repeat_case_ids'] for k in ['B_eq','C_eq'])
    save(output/'task_order.json',order_records)
    def work(task):
        case,condition,repetition=task;cid=case['case_id'];path=output/'individual'/f'{cid}_{condition}_{repetition}.json'
        if path.exists():
            previous=read(path);require(previous['freeze_sha256']==frozen and previous['run_id']==manifest['run_id'],'registro_previo_divergente')
            return cid,condition,'retomado'
        common=inputs[cid];observations=[];engine_raw=None;attempts=[];messages=None;engine_seconds=0;model_seconds=0
        redactor=Redactor([*Redactor.from_environment(environment.settings).secrets,*environment.redaction_secrets]);session=ObservedSession();client=GatewayClient(environment.settings,session=session)
        begin=time.monotonic()
        try:
            if condition=='C_eq':
                before=time.monotonic();engine=QueryEngine(root,project,local.run_id,root/local.territories,root/local.capabilities)
                obs,engine_raw=executor_observation(engine.answer(common['validated_plan']));engine_seconds=time.monotonic()-before
                if obs['status']!='respondida':raise ValueError('executor_nao_respondeu')
                observations=[obs]
            messages=model_messages(common,observations,schema,system)
            require(not redactor.clean(canonical(messages))[1],'entrada_contem_segredo')
            result,attempts,model_seconds=complete(messages,client,redactor,protocol['max_context_bytes'])
        except Exception:result=failure('falha_tecnica_runner')
        finally:client.close()
        elapsed=time.monotonic()-begin
        # Referencia numerica e lida exclusivamente depois da resposta remota.
        expected=read(benchmark/'reference.json')[cid]
        observed={**result,'plan':common['validated_plan'],'clarification_field':None}
        scored=score(observed,expected,read(benchmark/'scoring_protocol.json'),read(benchmark/'classes.json'))
        record={'schema_version':'controle-contrato-caso-v1','run_id':manifest['run_id'],'case_id':cid,'family_id':case['family_id'],
            'territory_codes':case['territory_codes'],'condition':condition,'repeat':repetition,'integration_kind':'gateway_real','created_at':now(),
            'freeze_sha256':frozen,'configuration':config,'question':common['question'],'fixed_plan':common['validated_plan'],
            'common_input_sha256':digest(common),'output_contract_sha256':digest(schema),'system_sha256':sha(benchmark/'system.txt'),
            'messages_sha256':digest(messages) if messages else None,'execution_observations':observations,'executor_result':engine_raw,
            'observed':observed,'final_answer':canonical(result),'attempts':attempts,'latency_seconds':elapsed,'model_seconds':model_seconds,
            'http_events':session.events,'executor_seconds':engine_seconds,'scores':scored,'cost':None,'source_geo_run_id':local.run_id}
        require(not redactor.clean(canonical(record))[1],'registro_contem_segredo')
        save(path,record);return cid,condition,'registrado'
    with concurrent.futures.ThreadPoolExecutor(max_workers=protocol['workers']) as pool:
        futures=[pool.submit(work,t) for t in tasks]
        for n,future in enumerate(concurrent.futures.as_completed(futures),1):
            cid,condition,state=future.result();print(f'{split}: {n}/{len(tasks)} {cid} {condition} {state}',flush=True)
    verify(benchmark,root,code)
    manifest.update(state='concluida',completed_at=now(),individual_hashes={p.name:sha(p) for p in sorted((output/'individual').glob('*.json'))})
    save(output/'run.json',manifest);return manifest
