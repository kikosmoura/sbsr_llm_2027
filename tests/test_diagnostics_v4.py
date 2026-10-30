"""Mocks: metadados preservados mesmo quando o cliente rejeita texto vazio."""
import json,sys
from pathlib import Path
import pytest,requests
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from science.gateway_diagnostics_v4 import response_metadata,ObservedSession,ObservedResponse
from consultas_ambientais.llm.client import GatewayClient,GatewayError
from consultas_ambientais.settings import LLMSettings

@pytest.mark.parametrize('content,state',[(None,'null'),('','vazio_ou_espacos'),('  ','vazio_ou_espacos'),('OK','texto')])
def test_safe_metadata_never_contains_reasoning(content,state):
    raw={'choices':[{'finish_reason':'length','message':{'content':content,'reasoning_content':'NAO_PERSISTIR'}}],
         'usage':{'prompt_tokens':200,'completion_tokens':2048,'total_tokens':2248,'completion_tokens_details':{'reasoning_tokens':2048}}}
    v=response_metadata(raw)
    assert v['content_state']==state and v['finish_reason']=='length' and v['reasoning_tokens']==2048
    assert 'NAO_PERSISTIR' not in json.dumps(v)

def test_malformed_metadata_is_sanitized():
    v=response_metadata({'choices':[{'finish_reason':{'secret':'NAO_PERSISTIR'},'message':{}}],
                         'usage':{'prompt_tokens':True,'completion_tokens':-1,'total_tokens':'secret'}})
    assert v['finish_reason']=='outro' and v['usage']=={} and 'secret' not in json.dumps(v)

class FakeResponse:
    status_code=200;headers={}
    def iter_content(self,chunk_size):
        yield json.dumps({'choices':[{'finish_reason':'length','message':{'content':None,'reasoning':'NAO_PERSISTIR'}}],
                          'usage':{'completion_tokens':2048}}).encode()
    def close(self):pass

def test_response_records_empty_final_json_but_drops_body():
    event={'endpoint':'chat','bytes_read':0,'_started':0}
    r=ObservedResponse(FakeResponse(),event,clock=lambda:1)
    b''.join(r.iter_content(8192));r.close();r.close()
    assert event['response_metadata']['finish_reason']=='length' and event['body_complete']
    assert not r.body and 'NAO_PERSISTIR' not in json.dumps(event) and '_started' not in event

def test_transport_timeout_records_only_kind():
    class Fake:
        def post(self,*a,**kw):raise requests.Timeout('NAO_PERSISTIR')
        def close(self):pass
    s=ObservedSession(Fake())
    with pytest.raises(requests.Timeout):s.post('https://example.invalid/chat/completions')
    assert s.events[0]['transport_error']=='timeout' and 'NAO_PERSISTIR' not in json.dumps(s.events)

def test_observer_keeps_http_history_and_usage_after_empty_exception():
    def response(status,payload):
        r=requests.Response();r.status_code=status;r._content=json.dumps(payload).encode();r._content_consumed=True;return r
    class Fake:
        def __init__(self):self.responses=[response(200,{'access_token':'FAKE_ACCESS','expires_in':60}),response(429,{}),
            response(200,{'choices':[{'finish_reason':'length','message':{'content':None,'reasoning':'NAO_PERSISTIR'}}],
                          'usage':{'completion_tokens':2048}})]
        def post(self,*a,**kw):return self.responses.pop(0)
        def close(self):pass
    config=LLMSettings(base_url='https://example.invalid',token_url='https://example.invalid/token',
                       client_id='fake-id',client_secret='FAKE_SECRET',model='fake-model',max_attempts=2)
    session=ObservedSession(Fake());client=GatewayClient(config,session=session,sleeper=lambda _:None)
    with pytest.raises(GatewayError,match='texto_final_ausente'):client.chat([{'role':'user','content':'OK'}])
    client.close()
    assert [e['http_status'] for e in session.events]==[200,429,200]
    assert session.events[-1]['response_metadata']['usage']=={'completion_tokens':2048}
    assert session.events[-1]['response_metadata']['finish_reason']=='length'
    assert all(s not in json.dumps(session.events) for s in ['FAKE_ACCESS','FAKE_SECRET','NAO_PERSISTIR'])
