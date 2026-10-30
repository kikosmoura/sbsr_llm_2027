"""Experimento de disponibilidade de calculo, com planos fixos e finalizadores iguais."""
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


class EquivalentAnswer(Contract):
    status: Literal['respondida','dados_indisponiveis','erro_tecnico']
    values: list[NumericValue]=Field(default_factory=list,max_length=200)
    reason: str=Field(default='consulta_executada',pattern=r'^[a-z][a-z0-9_]*$',max_length=160)

    @model_validator(mode='after')
    def coherent(self):
        if (self.status=='respondida')!=bool(self.values):raise ValueError('status_e_valores_incoerentes')
        return self


def runtime_files(code):
    package=Path(__import__('consultas_ambientais').__file__).parent
    return {'runner':sha(code/'science/equivalent_v3.py'),
            'entrypoint':sha(code/'executar_controle_v3.py'),
            'scorer':sha(package/'evaluation/scoring.py'),'client':sha(package/'llm/client.py'),
            'executor':executor_digest(),'schema':digest(EquivalentAnswer.model_json_schema())}


def prepare(root,target,code):
    root,target,code=map(Path,(root,target,code));require(not target.exists(),'congelamento_destino_existente')
    original=root/'benchmarks/pt_rn_v1';original_hash=verify_original(original,root)
    protocol=read(code.parent/'configs/science/equivalent_v3/protocol.json')
    allcases=list(lines(original/'cases.jsonl'));gold=read(original/'gold.json');facts=read(original/'facts.json')
    numeric=sorted([c for c in allcases if gold[c['case_id']]['status']=='respondida'],key=lambda c:c['case_id'])
    dev=[c for c in numeric if c['split']=='dev'];test=[c for c in numeric if c['split']=='test']
    first={}
    for c in dev:first.setdefault(gold[c['case_id']]['plan']['metric'],c)
    selected=list(first.values())
    selected+= [c for c in dev if c not in selected][:max(0,8-len(selected))]
    selected=sorted(selected[:8],key=lambda c:c['case_id'])
    require(len(selected)==8 and len(test)*2<=protocol['max_primary_records'],'universo_fora_do_orcamento')
    target.mkdir(parents=True)
    classes=ClassCatalog.load();territories=TerritoryCatalog.load(root/'data/territories_v1.json')
    inputs={};reference={}
    for c in selected+test:
        cid=c['case_id'];bundle=facts[cid]
        require(bundle['complete'] and not bundle['truncated'],'fatos_insuficientes')
        _,plan,_=preflight(gold[cid]['plan'],classes,territories)
        inputs[cid]={'question':c['question'],'validated_plan':plan.model_dump(mode='json'),
            'documentation':(Path(__import__('consultas_ambientais.evaluation.baselines',fromlist=['x']).__file__).parent/'prompts/documentation.txt').read_text(),
            'catalog_and_scope':bundle['context'],'tables':bundle['tables'],'table_columns':bundle['table_columns']}
        reference[cid]=gold[cid]
    repeat={}
    for c in test:repeat.setdefault(gold[c['case_id']]['plan']['metric'],c['case_id'])
    protocol.update(repeat_case_ids=[repeat[k] for k in sorted(repeat)[:4]],development_cases=len(selected),test_cases=len(test),
        source_freeze_sha256=original_hash,source_geo_run_id=read(root/'configs/local.json')['run_id'],
        llm_model=read(original/'freeze.json')['configuration']['requested_model'])
    target.joinpath('cases.jsonl').write_text(''.join(canonical(c)+'\n' for c in selected+test))
    for name,value in [('inputs.json',inputs),('reference.json',reference),('classes.json',read(original/'classes.json')),
                       ('scoring_protocol.json',read(original/'protocol.json')),('protocol.json',protocol),('output_schema.json',EquivalentAnswer.model_json_schema())]:save(target/name,value)
    target.joinpath('system.txt').write_text((code.parent/'configs/science/equivalent_v3/system.txt').read_text())
    frozen={'created_at':now(),'kind':'exploratory_reused_questions_fixed_plan','runtime':runtime_files(code),
        'files':{p.name:sha(p) for p in sorted(target.iterdir()) if p.is_file()},'original_freeze_sha256':original_hash}
    save(target/'freeze.json',frozen)
    return frozen


def verify(target,root,code):
    target,root,code=map(Path,(target,root,code));f=read(target/'freeze.json')
    require(all(sha(target/n)==h for n,h in f['files'].items()),'entradas_controle_alteradas')
    require(runtime_files(code)==f['runtime'],'runtime_controle_alterado')
    require(verify_original(root/'benchmarks/pt_rn_v1',root)==f['original_freeze_sha256'],'teste_original_alterado')
    return sha(target/'freeze.json')


def model_messages(common,observations,schema,system):
    # Nao transmitir rotulo da condicao, case_id, escores ou referencias esperadas.
    payload={**common,'execution_observations':observations,'output_contract':schema}
    return [{'role':'system','content':system},{'role':'user','content':canonical(payload)}]


def complete(messages,client,redactor,limit):
    attempts=[];initial=messages;start=time.monotonic()
    if len(canonical(messages).encode())>limit:return failure('contexto_excede_limite'),[],time.monotonic()-start
    for n in range(2):
        a={'number':n+1,'messages_sha256':digest(messages),'usage':None,'issues':[]}
        try:
            result=client.chat(messages);clean,redactions=redactor.clean(result.text)
            a.update(latency_seconds=result.elapsed_seconds,usage=result.usage,returned_model=redactor.model_name(result.model),
                chat_requests=result.chat_requests,output_sha256=hashlib.sha256(result.text.encode()).hexdigest(),output_chars=len(result.text))
            if redactions:raise ValueError('saida_redigida')
            parsed=EquivalentAnswer.model_validate(strict_json(clean))
            a['state']='valida';attempts.append(a)
            return parsed.model_dump(mode='json'),attempts,time.monotonic()-start
        except GatewayError as e:
            a.update(state='falha_gateway',gateway_error=e.code,http_status=e.status);attempts.append(a)
            return failure('falha_gateway'),attempts,time.monotonic()-start
        except (ValueError,TypeError,ValidationError) as e:
            issues=[{'path':list(x['loc']),'code':x['type']} for x in e.errors(include_input=False,include_url=False)] if isinstance(e,ValidationError) else [{'path':[],'code':'json_invalido_ou_redigido'}]
            a.update(state='invalida',issues=issues);attempts.append(a)
            messages=initial+[{'role':'user','content':canonical({'repair':'Reenvie somente JSON no mesmo contrato.','validation_issues':issues})}]
    return failure('saida_invalida_apos_reparo'),attempts,time.monotonic()-start


def failure(reason):return {'status':'erro_tecnico','values':[],'reason':reason}


def executor_observation(answer):
    raw=answer.model_dump(mode='json');evidences={e['evidence_id']:e for e in raw['evidence']};values=[]
    for v in raw['values']:
        e=evidences[v['evidence_id']]
        values.append({'territory_code':e['territory']['code'],'years':e['years'],'value':v['value'],'unit':v['unit'],
            'undefined_reason':v['undefined_reason'],'denominators_ha':e['denominator_values_ha'],'rank':v['rank']})
    return {'status':raw['status'],'values':values,'reason':raw['reason']},raw


def run(root,benchmark,output,code,split,env_file,repeats=False):
    root,benchmark,output,code=map(Path,(root,benchmark,output,code));frozen=verify(benchmark,root,code)
    protocol=read(benchmark/'protocol.json');cases=[c for c in lines(benchmark/'cases.jsonl') if c['split']==split]
    local=LocalSettings.load(root/'configs/local.json');local.llm_timeout_seconds=protocol['llm_timeout_seconds']
    local.llm_max_tokens=protocol['llm_max_tokens'];local.llm_max_attempts=protocol['http_max_attempts'];local.temperature=protocol['temperature']
    environment=load_environment(local,env_file);require(environment.settings.model==protocol['llm_model'],'modelo_divergente')
    require(environment.settings.verify is True or isinstance(environment.settings.verify,str),'TLS_nao_verificado')
    inputs=read(benchmark/'inputs.json');schema=read(benchmark/'output_schema.json');system=(benchmark/'system.txt').read_text()
    project=ProjectConfig.load(root/'configs/project.json');output.mkdir(parents=True,exist_ok=True)
    config={'requested_model':protocol['llm_model'],'temperature':local.temperature,'max_tokens':local.llm_max_tokens,
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
        redactor=Redactor([*Redactor.from_environment(environment.settings).secrets,*environment.redaction_secrets]);client=GatewayClient(environment.settings)
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
            'executor_seconds':engine_seconds,'scores':scored,'cost':None,'source_geo_run_id':local.run_id}
        require(not redactor.clean(canonical(record))[1],'registro_contem_segredo')
        save(path,record);return cid,condition,'registrado'
    with concurrent.futures.ThreadPoolExecutor(max_workers=protocol['workers']) as pool:
        futures=[pool.submit(work,t) for t in tasks]
        for n,future in enumerate(concurrent.futures.as_completed(futures),1):
            cid,condition,state=future.result();print(f'{split}: {n}/{len(tasks)} {cid} {condition} {state}',flush=True)
    verify(benchmark,root,code)
    manifest.update(state='concluida',completed_at=now(),individual_hashes={p.name:sha(p) for p in sorted((output/'individual').glob('*.json'))})
    save(output/'run.json',manifest);return manifest
