import json

import pytest
import requests

from consultas_ambientais.llm.client import GatewayClient,GatewayError,diagnose_llm
from consultas_ambientais.settings import LLMSettings


def response(status=200,payload=None,headers=None):
    r=requests.Response();r.status_code=status;r.headers.update(headers or {})
    r._content=json.dumps(payload or {}).encode();r._content_consumed=True
    return r


class Session:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def post(self,url,**kwargs):
        self.calls.append((url,kwargs))
        value=self.responses.pop(0)
        if isinstance(value,Exception):raise value
        return value
    def close(self):pass


def settings(**updates):
    return LLMSettings(base_url="https://gateway.example.test/v1",token_url="https://auth.example.test/token",
        client_id="test-client",client_secret="test-only-secret",model="test-model",**updates)


def token(**updates):return response(payload={"access_token":"test-only-access","expires_in":100,**updates})
def chat(**updates):return response(payload={"choices":[{"message":{"content":"OK","reasoning":"never-include-reasoning"}}],
                                          "model":"test-model",**updates})
MESSAGES=[{"role":"user","content":"Responda OK."}]


def test_basic_auth_cache_and_text_payload():
    session=Session([token(),chat(),chat()]);client=GatewayClient(settings(),session)
    assert client.chat(MESSAGES).text=="OK"
    assert client.chat(MESSAGES).text=="OK"
    assert len(session.calls)==3
    auth_call=session.calls[0][1]
    assert auth_call["data"]["grant_type"]=="client_credentials"
    assert auth_call["auth"].username=="test-client"
    call=session.calls[1][1]
    assert call["verify"] is True and call["allow_redirects"] is False
    assert call["json"]=={"model":"test-model","messages":MESSAGES,"stream":False,"max_tokens":128}
    assert "response_format" not in call["json"] and "tools" not in call["json"]


def test_body_auth_optional_parameters():
    session=Session([token(),chat()])
    GatewayClient(settings(token_auth_mode="body",scope="test-scope",audience="test-audience"),session).chat(MESSAGES)
    data=session.calls[0][1]["data"]
    assert data["client_secret"]=="test-only-secret" and data["scope"]=="test-scope"
    assert session.calls[0][1]["auth"] is None


def test_auto_only_falls_back_on_auth_failure():
    session=Session([response(401),token(),chat()])
    GatewayClient(settings(token_auth_mode="auto"),session).chat(MESSAGES)
    assert "client_secret" in session.calls[1][1]["data"]


def test_expiry_refreshes_before_deadline():
    now=[0.0];session=Session([token(),chat(),token(),chat()])
    client=GatewayClient(settings(),session,clock=lambda:now[0])
    client.chat(MESSAGES);now[0]=91;client.chat(MESSAGES)
    assert len(session.calls)==4


def test_one_401_renewal_only():
    session=Session([token(),response(401),token(),response(401,payload={"secret":"do-not-echo"})])
    with pytest.raises(GatewayError) as exc:GatewayClient(settings(),session).chat(MESSAGES)
    assert len(session.calls)==4 and str(exc.value)=="falha_chat"
    assert "do-not-echo" not in str(exc.value)


def test_retry_bounded_for_429():
    session=Session([token(),response(429,headers={"Retry-After":"1000"}),chat()]);delays=[]
    result=GatewayClient(settings(),session,sleeper=delays.append).chat(MESSAGES)
    assert result.text=="OK" and delays==[5.0]


def test_error_does_not_include_http_body_or_request_exception():
    session=Session([requests.ConnectionError("private-host test-only-secret")])
    with pytest.raises(GatewayError) as exc:GatewayClient(settings(),session).chat(MESSAGES)
    assert str(exc.value)=="falha_conexao"


def test_reasoning_only_is_not_final_text():
    session=Session([token(),response(payload={"choices":[{"message":{"reasoning_content":"private-reasoning"}}]})])
    with pytest.raises(GatewayError):GatewayClient(settings(),session).chat(MESSAGES)


def test_reasoning_blocks_and_usage_details_are_discarded():
    session=Session([token(),response(payload={"choices":[{"message":{"content":[
        {"type":"reasoning","text":"private-reasoning"},{"type":"text","text":"OK"}]}}],
        "usage":{"total_tokens":10,"details":{"secret":"bad"}}})])
    result=GatewayClient(settings(),session).chat(MESSAGES)
    assert result.text=="OK" and result.usage=={"total_tokens":10}


def test_probe_makes_only_one_chat_request_even_on_401():
    session=Session([token(),response(401)])
    result=diagnose_llm(settings(),session)
    assert result.state.value=="indisponivel" and len(session.calls)==2


def test_probe_no_config_no_network():
    session=Session([])
    assert diagnose_llm(LLMSettings(),session).state.value=="pendente"
    assert not session.calls


def test_non_text_input_rejected_before_network():
    session=Session([])
    with pytest.raises(GatewayError):GatewayClient(settings(),session).chat([{"role":"user","content":[]}])
    assert not session.calls
