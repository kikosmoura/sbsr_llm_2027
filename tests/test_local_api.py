"""API local com HTTP LLM MOCK e areas SINTETICAS. Sem rede externa."""
import csv
import io
import json
import multiprocessing
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from consultas_ambientais.api import create_app
from consultas_ambientais.delivery.settings import LocalSettings, LocalEnvironment
from consultas_ambientais.delivery.models import DeliveryError, LocalResponse
from consultas_ambientais.delivery.runtime import LocalRuntime
from consultas_ambientais.delivery.worker import ProcessRunner
from consultas_ambientais.settings import ProjectConfig
from consultas_ambientais.storage.dialogues import private_json
from test_queries import materialized, CODES
from test_interpretation import nl, proposal, output, QUESTION
from test_llm import settings, response


@pytest.fixture
def local(nl):
    cfg = LocalSettings(run_id=nl['run'], territories='data/territories.json', capabilities='data/caps.json', data_kind='synthetic')
    def factory(outputs=None, runner=None, config=None):
        service, http = nl['factory'](outputs or [])
        if runner is None:
            def runner(root, project, config, environment, question, session, clarification):
                return service.ask(question, session, clarification)
        app = create_app(nl['root'], ProjectConfig(), config or cfg, LocalEnvironment(settings(max_tokens=768)), runner)
        return TestClient(app, base_url='http://127.0.0.1:8765'), http
    return {**nl, 'cfg':cfg, 'app_factory':factory}


def session(client):
    r = client.post('/v1/sessions')
    assert r.status_code == 201
    data = r.json()
    return data['session_id'], {'X-Session-Token': data['session_token']}


def ask(client, sid, headers, question=QUESTION):
    return client.post(f'/v1/sessions/{sid}/questions', headers=headers, json={'question':question})


def test_real_contract_mock_gateway_api_trace_exports(local):
    client, _ = local['app_factory']([output(proposal())])
    sid, headers = session(client)
    r = ask(client, sid, headers)
    assert r.status_code == 200
    a = LocalResponse.model_validate(r.json())
    assert a.status == 'respondida' and a.data_kind == 'synthetic'
    assert a.result.values[0].value == pytest.approx(69.876544)
    assert a.trace['integration_kind'] == 'mock_contrato'
    assert a.source_context['run_id'] == local['run'] and a.result.execution.run_id == local['run']
    url = f'/v1/sessions/{sid}/results/{a.result_id}'
    assert client.get(url, headers=headers).json() == r.json()
    by_answer = client.get(f'/v1/sessions/{sid}/answers/{a.result.answer_id}', headers=headers)
    assert by_answer.json() == a.result.model_dump(mode='json')
    evidence = client.get(url+'/evidence', headers=headers).json()
    assert evidence['evidence'][0]['evidence_id'] == a.result.values[0].evidence_id
    assert client.get(url+'/evidence/'+a.result.values[0].evidence_id, headers=headers).status_code == 200
    assert client.get(url+'/evidence/'+'f'*64, headers=headers).status_code == 404
    assert client.get(url+'/export/json', headers=headers).json() == r.json()
    rows = list(csv.DictReader(io.StringIO(client.get(url+'/export/csv', headers=headers).text)))
    assert float(rows[0]['value']) == a.result.values[0].value
    assert rows[0]['evidence_id'] == a.result.values[0].evidence_id
    html = client.get(url+'/export/html', headers=headers)
    assert repr(a.result.values[0].value) in html.text and 'synthetic' in html.text
    assert "default-src 'none'" in html.headers['content-security-policy']
    assert r.headers['cache-control'] == 'no-store'
    registry = client.app.state.runtime.registry
    state = registry.read(registry.base/sid/'session.json')
    assert headers['X-Session-Token'] not in json.dumps(state)
    assert (registry.base/sid/'session.json').stat().st_mode&0o777 == 0o600


def test_session_isolation_retrieval_and_tokens(local):
    client, _ = local['app_factory']([output(proposal())])
    sid, headers = session(client)
    other, h2 = session(client)
    a = ask(client, sid, headers).json()
    url = f'/v1/sessions/{sid}/results/{a["result_id"]}'
    assert client.get(url).status_code == 404
    assert client.get(url, headers=h2).status_code == 404
    assert client.get(url.replace(sid,other), headers=h2).status_code == 404
    assert ask(client,other,headers).status_code == 404
    assert client.get(f'/v1/sessions/{other}/answers/{a["result"]["answer_id"]}', headers=h2).status_code == 404


def test_clarification_bound_to_result_and_same_session(local):
    p = proposal(territories=[{'mention':'Alfa'}])
    client, _ = local['app_factory']([output(p),output(p)])
    sid, headers = session(client)
    a = ask(client,sid,headers,QUESTION.replace('/RN','')).json()
    assert a['status'] == 'precisa_esclarecimento'
    url = f'/v1/sessions/{sid}/results/{a["result_id"]}/clarifications'
    invalid = client.post(url,headers=headers,json={'reply':'RN','clarification_id':'a'*32})
    assert invalid.status_code == 409
    payload = {'reply':'RN','clarification_id':a['clarification']['clarification_id']}
    b = client.post(url,headers=headers,json=payload)
    assert b.status_code == 200 and b.json()['status'] == 'respondida'
    assert b.json()['trace']['parent_turn_id'] == a['trace']['turn_id']
    assert b.json()['result']['plan']['territory_codes'] == [CODES[0]]
    repeat = client.post(url,headers=headers,json=payload)
    assert repeat.json()['status'] == 'precisa_esclarecimento'
    assert repeat.json()['result'] is None


def test_capabilities_only_materialized_not_candidates(local):
    raw = json.loads(local['cap_path'].read_text())
    raw['available_raster_years'] = list(range(2015,2026))
    private_json(local['cap_path'],raw)
    client, _ = local['app_factory']()
    r = client.get('/v1/capabilities')
    assert r.status_code == 200
    c = r.json()
    assert c['materialized_years'] == [2015,2025] and c['usable_years'] == [2015,2025]
    assert len(c['territories']) == 5 and c['data_kind'] == 'synthetic'
    assert c['ranking'][0]['status'] == 'disponivel' and c['ranking'][0]['universe_count'] == 4
    assert all(not row['raster_observation_asserted'] for row in c['classes'])
    group = next(row for row in c['classes'] if row['code']==1)
    assert group['kind']=='grupo' and group['leaf_codes']==[3,4,5,6,7,49]
    assert len(client.get('/v1/capabilities',params={'territory_code':CODES[0]}).json()['territories']) == 1
    assert client.get('/v1/capabilities',params={'territory_code':'../.env'}).status_code == 422


def test_capabilities_fail_closed_on_missing_or_corrupt_partition(local):
    path = local['root']/'data/processed'/local['run']/CODES[0]/'areas.parquet'
    path.write_bytes(b'invalid')
    client, _ = local['app_factory']()
    r = client.get('/v1/capabilities')
    assert r.status_code == 503 and 'materialized_years' not in r.json()


@pytest.mark.parametrize('payload',[
    {'question':QUESTION,'sql':'sensitive-marker-extra'},
    {'question':123}, {'question':'a'*4001}, {'question':''}])
def test_invalid_request_does_not_echo_input(local,payload):
    client, http = local['app_factory']()
    sid, headers = session(client)
    r = client.post(f'/v1/sessions/{sid}/questions',headers=headers,json=payload)
    assert r.status_code == 422 and 'sensitive-marker-extra' not in r.text
    assert r.json()['status']=='precisa_esclarecimento' and not http.calls


def test_bytes_limit_chunked_compression_host_origin_and_logs(local,caplog):
    cfg = local['cfg'].model_copy(update={'max_body_bytes':1024})
    client, _ = local['app_factory'](config=cfg)
    assert client.post('/v1/sessions',content=iter([b'a'*600,b'b'*600])).status_code == 413
    assert client.post('/v1/sessions',headers={'Content-Encoding':'gzip'},content=b'x').status_code == 415
    assert client.get('/healthz',headers={'Host':'evil.example.test'}).status_code == 400
    assert client.get('/healthz',headers={'Host':'[::1]evil'}).status_code == 400
    assert client.post('/v1/sessions',headers={'Origin':'https://evil.example.test'}).status_code == 403
    assert client.get('/healthz').status_code == 200
    with caplog.at_level('INFO',logger='consultas_ambientais.http'):
        client.post('/v1/sessions',json={'secret':'do-not-log-this-body'})
    assert 'do-not-log-this-body' not in caplog.text
    assert client.get('/docs').status_code == 404


def test_session_and_result_limits_and_expiry(local):
    cfg = local['cfg'].model_copy(update={'max_sessions':1,'max_results_per_session':1})
    client, _ = local['app_factory']([output(proposal())],config=cfg)
    sid, headers = session(client)
    assert client.post('/v1/sessions').status_code == 429
    a = ask(client,sid,headers)
    assert a.status_code == 200 and ask(client,sid,headers).status_code == 429
    registry = client.app.state.runtime.registry
    p = registry.base/sid/'session.json'
    state = json.loads(p.read_text());state['expires_at']=0;private_json(p,state)
    assert client.get(f'/v1/sessions/{sid}/results/{a.json()["result_id"]}',headers=headers).status_code == 404


def test_slow_blocking_query_does_not_block_health_and_busy_is_bounded(local):
    started = threading.Event()
    service, _ = local['factory']([output(proposal())])
    def runner(root, project, config, environment, question, session, clarification):
        started.set();time.sleep(.4)
        return service.ask(question,session,clarification)
    client, _ = local['app_factory'](runner=runner)
    with client, ThreadPoolExecutor(max_workers=1) as pool:
        sid, headers = session(client)
        pending = pool.submit(ask,client,sid,headers)
        assert started.wait(2)
        start = time.monotonic()
        assert client.get('/healthz').status_code == 200
        assert time.monotonic()-start < .3
        assert ask(client,sid,headers).status_code == 429
        assert pending.result(timeout=5).status_code == 200


def sleeping_worker(connection,payload):
    time.sleep(10)


def invalid_worker(connection,payload):
    connection.send_bytes(b'{}');connection.close()


def test_process_timeout_is_real_and_child_is_terminated(local):
    cfg = local['cfg'].model_copy(update={'max_query_seconds':.15})
    before = {p.pid for p in multiprocessing.active_children()}
    start = time.monotonic()
    with pytest.raises(DeliveryError) as e:
        ProcessRunner(sleeping_worker)(local['root'],ProjectConfig(),cfg,LocalEnvironment(settings()),QUESTION)
    assert e.value.reason=='consulta_timeout' and time.monotonic()-start<3
    assert {p.pid for p in multiprocessing.active_children()} == before


def test_invalid_worker_never_becomes_number(local):
    cfg = local['cfg'].model_copy(update={'max_query_seconds':5})
    client, _ = local['app_factory'](runner=ProcessRunner(invalid_worker),config=cfg)
    sid, headers = session(client)
    r = ask(client,sid,headers)
    assert r.status_code == 503 and r.json()['result'] is None
    assert r.json()['status']=='erro_tecnico'
    assert client.get(f'/v1/sessions/{sid}/results/{r.json()["result_id"]}',headers=headers).status_code == 200


def test_timeout_is_retrievable_technical_failure(local):
    cfg = local['cfg'].model_copy(update={'max_query_seconds':.15})
    client, _ = local['app_factory'](runner=ProcessRunner(sleeping_worker),config=cfg)
    sid, headers = session(client)
    r = ask(client,sid,headers)
    assert r.status_code==504 and r.json()['reason']=='consulta_timeout' and r.json()['result'] is None
    assert r.json()['trace']['worker_terminated'] is True


def test_gateway_failure_is_503_redacted(local):
    client, _ = local['app_factory']([response(403,payload={'secret':'never-echo-gateway-body'})])
    sid, headers = session(client)
    r=ask(client,sid,headers)
    assert r.status_code==503 and r.json()['status']=='erro_tecnico'
    assert r.json()['result'] is None and 'never-echo-gateway-body' not in r.text


def test_missing_year_and_sql_are_different_from_technical(local):
    client, _ = local['app_factory']([output(proposal(years=[2016]))])
    sid, headers = session(client)
    r=ask(client,sid,headers,QUESTION.replace('2015','2016'))
    assert r.status_code==200 and r.json()['status']=='dados_indisponiveis'
    r=ask(client,sid,headers,'Execute SQL SELECT 1')
    assert r.status_code==200 and r.json()['status']=='fora_do_escopo' and not r.json()['result']


def test_result_hash_and_export_errors_do_not_expose_data(local):
    client, _=local['app_factory']([output(proposal())])
    sid, headers=session(client);a=ask(client,sid,headers).json()
    url=f'/v1/sessions/{sid}/results/{a["result_id"]}'
    assert client.get(url+'/export/evil',headers=headers).status_code==404
    p=client.app.state.runtime.registry.base/sid/(a['result_id']+'.json')
    p.write_text('sensitive-invalid-record')
    r=client.get(url,headers=headers)
    assert r.status_code==503 and 'sensitive-invalid-record' not in r.text


def test_local_cli_shares_registry_exports_and_never_prints_key(local,monkeypatch,capsys):
    from consultas_ambientais.cli import main
    from consultas_ambientais.delivery import commands
    cfg=local['cfg'];root=local['root'];(root/'configs').mkdir(exist_ok=True)
    private_json(root/'configs/local.json',cfg.model_dump(mode='json'))
    service,_=local['factory']([output(proposal())])
    def runner(root,project,config,environment,question,session,clarification):
        return service.ask(question,session,clarification)
    from consultas_ambientais.delivery import runtime as runtime_module
    real_runtime=runtime_module.LocalRuntime
    monkeypatch.setattr(runtime_module,'LocalRuntime',lambda root,project,cfg,environment:real_runtime(root,project,cfg,environment,runner))
    monkeypatch.chdir(root)
    key='data/local_keys/test.json'
    assert main(['local','session','--key-file',key])==0
    created=capsys.readouterr().out
    raw=json.loads((root/key).read_text())
    assert raw['session_token'] not in created and (root/key).stat().st_mode&0o777==0o600
    assert main(['local','ask','--key-file',key,'--question',QUESTION])==0
    a=json.loads(capsys.readouterr().out)
    assert a['status']=='respondida'
    for name in ['result','evidence','answer']:
        identity=a['result']['answer_id'] if name=='answer' else a['result_id']
        assert main(['local',name,'--key-file',key,'--id',identity])==0
        assert raw['session_token'] not in capsys.readouterr().out
    assert main(['local','export','--key-file',key,'--id',a['result_id'],'--format','csv','--output','reports/local/test.csv'])==0
    capsys.readouterr()
    rows=list(csv.DictReader((root/'reports/local/test.csv').open()))
    assert float(rows[0]['value'])==a['result']['values'][0]['value']
    assert main(['local','session','--key-file',key])==2
    assert 'arquivo_chave_ja_existe' in capsys.readouterr().out
    assert main(['local','session','--key-file','data/territories.json'])==2
    assert 'arquivo_chave_fora_do_diretorio_privado' in capsys.readouterr().out


def test_opt_in_env_is_data_and_explicit_limits_apply(local,tmp_path):
    from consultas_ambientais.delivery.settings import load_environment
    p=tmp_path/'.env'
    p.write_text('LLM_BASE_URL=https://gateway.example.test/v1\nLLM_TOKEN_URL=https://auth.example.test/token\nLLM_CLIENT_ID=test-client\nLLM_CLIENT_SECRET="$(touch should-not-exist)"\nLLM_MODEL=test-model\nLLM_TIMEOUT=9999\n')
    original=p.read_bytes()
    environment=load_environment(local['cfg'],p)
    assert environment.settings.configured and environment.settings.timeout==30
    assert environment.settings.verify is True and not (Path.cwd()/'should-not-exist').exists()
    assert p.read_bytes()==original
    assert 'touch' not in repr(environment)


def test_default_worker_without_gateway_is_real_process_contract(local):
    from consultas_ambientais.settings import LLMSettings
    cfg=local['cfg'].model_copy(update={'max_query_seconds':10})
    a=ProcessRunner()(local['root'],ProjectConfig(),cfg,LocalEnvironment(LLMSettings()),QUESTION)
    assert a.status=='erro_tecnico' and a.reason=='configuracao_llm_ausente'
    assert not a.gateway_called and a.query is None


def test_request_body_deadline_is_enforced(local):
    import asyncio
    from consultas_ambientais.api import LocalBoundary
    messages=[]
    async def never_called(scope,receive,send):raise AssertionError('app nao deve receber corpo pendente')
    async def slow_receive():
        await asyncio.sleep(.2)
        return {'type':'http.request','body':b'a','more_body':True}
    async def sent(message):messages.append(message)
    cfg=local['cfg'].model_copy(update={'body_timeout_seconds':.01})
    boundary=LocalBoundary(never_called,cfg)
    asyncio.run(boundary({'type':'http','headers':[(b'host',b'127.0.0.1')]},slow_receive,sent))
    assert messages[0]['status']==408


def test_ranking_capability_requires_every_municipality_pair(local):
    raw=json.loads(local['cap_path'].read_text())
    raw['materializations']=[r for r in raw['materializations'] if not (r['territory_code']==CODES[0] and r['years']==[2015,2025])]
    private_json(local['cap_path'],raw)
    client,_=local['app_factory']()
    c=client.get('/v1/capabilities').json()
    assert c['ranking'][0]['status']=='dados_indisponiveis'
    assert c['ranking'][0]['missing_or_partial_codes']==[CODES[0]]
    assert next(o for o in c['operations'] if o['operation']=='ranking_delimitado')['status']=='dados_indisponiveis'


def test_storage_budget_rejects_before_gateway(local):
    cfg=local['cfg'].model_copy(update={'max_result_bytes':65536,'max_storage_bytes':131072})
    client,http=local['app_factory'](config=cfg)
    sid,headers=session(client)
    registry=client.app.state.runtime.registry
    (registry.base/'padding.bin').write_bytes(b'x'*70000)
    r=ask(client,sid,headers)
    assert r.status_code==429 and r.json()['reason']=='limite_de_armazenamento_local' and not http.calls


def test_null_percentage_export_is_not_zero(local):
    p=proposal(operation='comparacao_temporal',territories=[{'mention':'Gama','uf_mention':'RN'}],
        classes=[{'mention':'Formação Florestal'}],years=[2015,2025],metric='variacao_percentual',
        metric_mention='variação percentual',denominator='area_inicial',unit_mention=None)
    client,_=local['app_factory']([output(p)])
    sid,headers=session(client)
    a=ask(client,sid,headers,'Qual a variação percentual de Formação Florestal de Gama/RN de 2015 a 2025 em relação à área inicial?').json()
    assert a['status']=='respondida' and a['result']['values'][0]['value'] is None
    url=f'/v1/sessions/{sid}/results/{a["result_id"]}/export/csv'
    row=list(csv.DictReader(io.StringIO(client.get(url,headers=headers).text)))[0]
    assert row['value']=='' and row['undefined_reason']=='base_inicial_zero'


def test_unexpected_storage_exception_never_echoes_details(local,monkeypatch):
    client,_=local['app_factory']()
    def failure():raise OSError('secret-host-and-password')
    monkeypatch.setattr(client.app.state.runtime,'create_session',failure)
    r=client.post('/v1/sessions')
    assert r.status_code==503 and 'secret-host-and-password' not in r.text
    assert r.headers['cache-control']=='no-store'


def test_export_budget_and_csv_matches_original_serializer(local):
    from consultas_ambientais.delivery.export import export
    from consultas_ambientais.answers.export import csv_text
    client,_=local['app_factory']([output(proposal(operation='serie_disponivel',years=[2015,2025]))])
    sid,headers=session(client)
    a=ask(client,sid,headers,'Mostre a série da área de pastagem de Alfa/RN nos anos 2015 e 2025, em hectares.').json()
    response=LocalResponse.model_validate(a)
    assert export(response,'csv')[0]==csv_text(response.result)
    for format in ['json','csv','html']:
        with pytest.raises(DeliveryError) as e:export(response,format,max_bytes=1)
        assert e.value.reason=='exportacao_excede_limite_local'


def test_known_synthetic_source_cannot_be_labeled_real(local):
    cfg=local['cfg'].model_copy(update={'data_kind':'real'})
    with pytest.raises(DeliveryError) as e:
        LocalRuntime(local['root'],ProjectConfig(),cfg,LocalEnvironment(settings()))
    assert e.value.reason=='dados_sinteticos_exigem_rotulo_sintetico'
