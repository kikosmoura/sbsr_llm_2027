"""Observabilidade restrita: nunca persiste corpo HTTP nem texto de raciocinio."""
import concurrent.futures,json,random,time,hashlib
from collections import Counter
from pathlib import Path
from uuid import uuid4
import requests
from pydantic import ValidationError
from consultas_ambientais.evaluation.common import read,save,sha,digest,canonical,now
from consultas_ambientais.delivery.settings import LocalSettings,load_environment
from consultas_ambientais.llm.client import GatewayClient,GatewayError
from consultas_ambientais.llm.privacy import Redactor
from consultas_ambientais.llm.interpreting import strict_json
from .equivalent_v3 import EquivalentAnswer,model_messages,verify as verify_v3
from .audit import require


def counters(value):
    return {k:v for k,v in value.items() if k in {'prompt_tokens','completion_tokens','total_tokens'}
            and type(v) is int and v>=0} if isinstance(value,dict) else None


def response_metadata(raw):
    """Whitelist de estados e contadores; nao exporta texto ou chaves arbitrarias."""
    if not isinstance(raw,dict):return {'json_object':False}
    choices=raw.get('choices');choice=choices[0] if isinstance(choices,list) and choices and isinstance(choices[0],dict) else {}
    message=choice.get('message');message=message if isinstance(message,dict) else {}
    content=message.get('content')
    if isinstance(content,list):
        content=''.join(b['text'] for b in content if isinstance(b,dict) and b.get('type')=='text' and isinstance(b.get('text'),str))
    state='ausente' if 'content' not in message else 'null' if content is None else 'nao_textual'
    if isinstance(content,str):state='texto' if content.strip() else 'vazio_ou_espacos'
    finish=choice.get('finish_reason')
    finish=finish if finish is None or isinstance(finish,str) and finish in {'stop','length','content_filter','tool_calls','function_call','eos_token','max_tokens'} else 'outro'
    usage=raw.get('usage');details=usage.get('completion_tokens_details') if isinstance(usage,dict) else None
    reason_tokens=details.get('reasoning_tokens') if isinstance(details,dict) else None
    return {'json_object':True,'choices_count':len(choices) if isinstance(choices,list) else None,
            'finish_reason':finish,'content_state':state,'final_content_chars':len(content) if isinstance(content,str) else None,
            'reasoning_field_present':any(k in message for k in ['reasoning','reasoning_content']),
            'usage':counters(usage),'reasoning_tokens':reason_tokens if type(reason_tokens) is int and reason_tokens>=0 else None}


class ObservedResponse:
    def __init__(self,response,event,clock=time.monotonic):
        self.response=response;self.event=event;self.clock=clock;self.body=bytearray();self.closed=False
    @property
    def status_code(self):return self.response.status_code
    @property
    def headers(self):return self.response.headers
    def iter_content(self,chunk_size):
        try:
            for chunk in self.response.iter_content(chunk_size=chunk_size):
                self.event['bytes_read']+=len(chunk)
                if self.event['endpoint']=='chat' and len(self.body)+len(chunk)<=1048576:self.body.extend(chunk)
                yield chunk
            self.event['body_complete']=True
        except requests.RequestException as e:
            self.event['read_error']='timeout' if isinstance(e,requests.Timeout) else 'falha_leitura'
            raise
    def close(self):
        if self.closed:return
        self.closed=True
        try:
            if self.event['endpoint']=='chat' and self.event.get('body_complete') and self.event['bytes_read']<=1048576:
                try:self.event['response_metadata']=response_metadata(json.loads(self.body))
                except (ValueError,TypeError):self.event['response_metadata']={'json_object':False}
        finally:
            self.body.clear();self.event['elapsed_seconds']=self.clock()-self.event.pop('_started')
            self.response.close()


class ObservedSession:
    def __init__(self,session=None,clock=time.monotonic):
        self.session=session or requests.Session();self.clock=clock;self.events=[]
    def post(self,url,**kwargs):
        event={'endpoint':'chat' if url.endswith('/chat/completions') else 'oauth',
               'http_status':None,'bytes_read':0,'body_complete':False,'response_metadata':None,'_started':self.clock()}
        self.events.append(event)
        try:
            response=self.session.post(url,**kwargs);event['http_status']=response.status_code
            return ObservedResponse(response,event,self.clock)
        except requests.RequestException as e:
            event['transport_error']='timeout' if isinstance(e,requests.Timeout) else 'tls' if isinstance(e,requests.exceptions.SSLError) else 'conexao'
            event['elapsed_seconds']=self.clock()-event.pop('_started');raise
    def close(self):self.session.close()


def historical(root):
    """Campos ausentes continuam null; inferencias do caminho de codigo sao marcadas."""
    directory=Path(root)/'artifacts/evaluation/controle_contrato_v1/test'
    run=read(directory/'run.json');require(run['state']=='concluida','V3_incompleta')
    require(all(sha(directory/'individual'/n)==h for n,h in run['individual_hashes'].items()),'V3_alterada')
    rows=[]
    for p in sorted((directory/'individual').glob('*B_eq_0.json')):
        r=read(p);a=r['attempts'][-1]
        rows.append({'case_id':r['case_id'],'family_id':r['family_id'],'original_record_sha256':sha(p),
            'original_correct':r['scores']['correct'],'original_status':r['observed']['status'],
            'gateway_error':a.get('gateway_error'),'http_status_logged':a.get('http_status'),
            'finish_reason':None,'usage':a.get('usage'),'latency_seconds':r['latency_seconds'],
            'empty_final_text':a.get('gateway_error')=='texto_final_ausente',
            'http_inference':'2xx e JSON objeto decodificado; inferido do cliente congelado, nao status HTTP capturado' if a.get('gateway_error')=='texto_final_ausente' else None})
    require(len(rows)==88 and sum(r['empty_final_text'] for r in rows)==26,'universo_historico_inesperado')
    return rows


def prepare(root,target,code):
    root,target,code=map(Path,(root,target,code));require(not target.exists(),'destino_existente')
    old=root/'benchmarks/controle_contrato_v1';verify_v3(old,root,code)
    rows=historical(root);selected=[r for r in rows if r['empty_final_text']]
    selected += [next(r for r in rows if r['case_id']==cid) for cid in ['t01_1','t16_2']]
    protocol={'kind':'diagnostico_exploratorio_selecionado_por_falha_historica','created_at':now(),
        'budgets':[2048,4096],'timeout_seconds':60,'http_attempts':2,'workers':3,'seed':202610214,
        'case_ids':[r['case_id'] for r in selected],'selected_old_empty':26,'positive_controls':2,'max_records':56,
        'repairs':0,'same_messages_as_initial_B_eq':True,'changes_only':'max_tokens; metadados observados por wrapper de transporte',
        'not_main_accuracy_experiment':True,'replace_V3_records':False,'reasoning_text_stored':False,'raw_response_stored':False,
        'limits':'amostra selecionada por resultado anterior; outro momento do gateway; sem atribuicao retroativa de causa'}
    target.mkdir(parents=True);save(target/'protocol.json',protocol);save(target/'historical.json',rows)
    frozen={'created_at':now(),'files':{p.name:sha(p) for p in target.iterdir()},'V3_freeze_sha256':sha(old/'freeze.json'),
            'runtime':{'observer':sha(code/'science/gateway_diagnostics_v4.py'),'entrypoint':sha(code/'diagnosticar_retornos_v4.py'),
                       'client':read(old/'freeze.json')['runtime']['client']}}
    save(target/'freeze.json',frozen);return frozen


def verify(root,target,code):
    root,target,code=map(Path,(root,target,code));f=read(target/'freeze.json')
    require(all(sha(target/n)==h for n,h in f['files'].items()),'diagnostico_entradas_alteradas')
    require(sha(code/'science/gateway_diagnostics_v4.py')==f['runtime']['observer'] and sha(code/'diagnosticar_retornos_v4.py')==f['runtime']['entrypoint'],'diagnostico_runtime_alterado')
    require(verify_v3(root/'benchmarks/controle_contrato_v1',root,code)==f['V3_freeze_sha256'],'fonte_V3_alterada')
    return sha(target/'freeze.json')


def run(root,target,output,code,env_file):
    root,target,output,code=map(Path,(root,target,output,code));frozen=verify(root,target,code);p=read(target/'protocol.json')
    settings=LocalSettings.load(root/'configs/local.json');settings.llm_timeout_seconds=p['timeout_seconds'];settings.llm_max_attempts=p['http_attempts']
    environment=load_environment(settings,env_file);old=root/'benchmarks/controle_contrato_v1'
    require(environment.settings.model==read(old/'protocol.json')['llm_model'],'modelo_divergente')
    require(environment.settings.verify is True or isinstance(environment.settings.verify,str),'TLS_nao_verificado')
    inputs=read(old/'inputs.json');schema=read(old/'output_schema.json');system=(old/'system.txt').read_text()
    tasks=[(cid,n) for cid in p['case_ids'] for n in p['budgets']];random.Random(p['seed']).shuffle(tasks)
    output.mkdir(parents=True,exist_ok=True)
    manifest={'run_id':uuid4().hex,'created_at':now(),'freeze_sha256':frozen,'state':'em_execucao','integration_kind':'gateway_real',
              'tasks':tasks,'model':environment.settings.model}
    if (output/'run.json').exists():
        previous=read(output/'run.json');require(previous['freeze_sha256']==frozen,'retomada_divergente');manifest=previous
    else:save(output/'run.json',manifest)
    def work(task):
        cid,budget=task;path=output/'individual'/f'{cid}_{budget}.json'
        if path.exists():return
        require(budget in {2048,4096},'orcamento_fora_do_protocolo')
        config=environment.settings.model_copy(update={'max_tokens':budget})
        redactor=Redactor([*Redactor.from_environment(config).secrets,*environment.redaction_secrets])
        messages=model_messages(inputs[cid],[],schema,system);require(not redactor.clean(canonical(messages))[1],'mensagem_sensivel')
        session=ObservedSession();client=GatewayClient(config,session=session);start=time.monotonic();observed=None;error=None;issues=[]
        try:
            result=client.chat(messages);clean,redactions=redactor.clean(result.text)
            require(not redactions,'resposta_sensivel')
            observed=EquivalentAnswer.model_validate(strict_json(clean)).model_dump(mode='json')
        except GatewayError as e:error=e.code
        except (ValueError,TypeError,ValidationError):error='contrato_invalido'
        finally:client.close()
        record={'case_id':cid,'run_id':manifest['run_id'],'max_tokens':budget,'freeze_sha256':frozen,'created_at':now(),
                'messages_sha256':digest(messages),'error':error,'observed':observed,'events':session.events,
                'latency_seconds':time.monotonic()-start,'reasoning_text_stored':False,'raw_response_stored':False}
        require(not redactor.clean(canonical(record))[1],'registro_sensivel');save(path,record)
    with concurrent.futures.ThreadPoolExecutor(max_workers=p['workers']) as pool:
        for i,_ in enumerate(pool.map(work,tasks),1):print(f'diagnostico: {i}/{len(tasks)}',flush=True)
    verify(root,target,code);manifest.update(state='concluida',completed_at=now(),individual_hashes={f.name:sha(f) for f in sorted((output/'individual').glob('*.json'))})
    require(len(manifest['individual_hashes'])==p['max_records'],'diagnostico_incompleto');save(output/'run.json',manifest)
    return manifest
