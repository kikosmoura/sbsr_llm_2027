"""OAuth2 e chat textual. Nunca inclui o corpo de erros em excecoes."""
import json
import math
import threading
import time
from dataclasses import dataclass

import requests
from requests.auth import HTTPBasicAuth

from ..contracts import Check, CheckState
from ..errors import network_issue
from ..settings import LLMSettings


class GatewayError(RuntimeError):
    def __init__(self, code, status=None):
        self.code = code
        self.status = status
        super().__init__(code)


@dataclass(frozen=True)
class ChatResult:
    text: str
    model: str | None
    usage: dict | None
    elapsed_seconds: float
    chat_requests: int


def limited_json(response, limit=1048576):
    chunks = []
    size = 0
    try:
        for chunk in response.iter_content(chunk_size=8192):
            size += len(chunk)
            if size > limit:
                raise GatewayError("resposta_excede_limite")
            chunks.append(chunk)
        value = json.loads(b"".join(chunks))
        if not isinstance(value, dict):
            raise GatewayError("resposta_json_invalida")
        return value
    except (ValueError, requests.RequestException):
        raise GatewayError("resposta_json_invalida") from None
    finally:
        response.close()


class GatewayClient:
    def __init__(self, settings: LLMSettings, session=None, clock=time.monotonic,
                 sleeper=time.sleep):
        if not settings.configured:
            raise GatewayError("configuracao_llm_ausente")
        self.settings = settings
        self.session = session or requests.Session()
        self.clock = clock
        self.sleeper = sleeper
        self._token = None
        self._expires = 0.0
        self._lock = threading.RLock()
        self._chat_requests = 0

    @property
    def chat_requests(self):
        return self._chat_requests

    def close(self):
        self._token = None
        self.session.close()

    def _post(self, url, **kwargs):
        for attempt in range(self.settings.max_attempts):
            try:
                if url.endswith("/chat/completions"):self._chat_requests+=1
                response = self.session.post(url, timeout=self.settings.timeout,
                                             verify=self.settings.verify, stream=True,
                                             allow_redirects=False, **kwargs)
            except requests.exceptions.SSLError:
                raise GatewayError("falha_tls") from None
            except requests.Timeout:
                raise GatewayError("timeout") from None
            except requests.RequestException as e:
                raise GatewayError(network_issue(e)) from None
            if response.status_code not in {429,500,502,503,504}:
                return response
            if attempt + 1 == self.settings.max_attempts:
                return response
            retry = response.headers.get("Retry-After", "")
            response.close()
            try:
                delay = min(5.0, max(0.0, float(retry))) if retry else min(2**attempt, 5)
                if not math.isfinite(delay):delay=1.0
            except (ValueError, OverflowError):
                delay=1.0
            self.sleeper(delay)
        raise GatewayError("tentativas_esgotadas")

    def _get_token(self, invalidate=False):
        with self._lock:
            if invalidate:
                self._token = None
            if self._token and self.clock() < self._expires:
                return self._token
            s = self.settings
            form = {"grant_type":"client_credentials"}
            if s.scope:form["scope"] = s.scope.get_secret_value()
            if s.audience:form["audience"] = s.audience.get_secret_value()
            modes = ["basic", "body"] if s.token_auth_mode == "auto" else [s.token_auth_mode]
            for index,mode in enumerate(modes):
                data = dict(form)
                auth = None
                if mode == "basic":
                    auth = HTTPBasicAuth(s.client_id.get_secret_value(), s.client_secret.get_secret_value())
                else:
                    data.update(client_id=s.client_id.get_secret_value(), client_secret=s.client_secret.get_secret_value())
                r = self._post(s.token_url.get_secret_value(), data=data, auth=auth,
                               headers={"Accept":"application/json"})
                if not 200 <= r.status_code < 300:
                    status = r.status_code
                    r.close()
                    if index + 1 < len(modes) and status in {400,401,403}:
                        continue
                    raise GatewayError("falha_autenticacao", status)
                payload = limited_json(r)
                token = payload.get("access_token")
                if not isinstance(token,str) or not token or "\n" in token or "\r" in token:
                    raise GatewayError("token_ausente_ou_invalido")
                token_type = payload.get("token_type", "Bearer")
                if not isinstance(token_type,str) or token_type.lower() != "bearer":
                    raise GatewayError("tipo_token_nao_suportado")
                try:
                    ttl = float(payload.get("expires_in", 0))
                    if not math.isfinite(ttl) or ttl < 0:raise ValueError
                except (ValueError, TypeError, OverflowError):
                    raise GatewayError("expiracao_token_invalida") from None
                self._token = token
                self._expires = self.clock() + max(0.0, ttl - min(30,ttl * 0.1))
                return token
            raise GatewayError("falha_autenticacao")

    def chat(self, messages, *, allow_401_refresh=True):
        if (not isinstance(messages,list) or not messages or
                any(not isinstance(m,dict) or set(m) != {"role","content"} or
                    m["role"] not in {"system","user","assistant"} or
                    not isinstance(m["content"],str) for m in messages)):
            raise GatewayError("mensagens_textuais_invalidas")
        s=self.settings
        payload={"model":s.model,"messages":messages,"stream":False,"max_tokens":s.max_tokens}
        if s.temperature is not None:payload["temperature"]=s.temperature
        start=self.clock()
        initial_requests=self._chat_requests
        token=self._get_token()
        for attempt in range(2 if allow_401_refresh else 1):
            r=self._post(s.base_url.get_secret_value().rstrip("/")+"/chat/completions",
                         json=payload,headers={"Accept":"application/json","Content-Type":"application/json",
                                               "Authorization":"Bearer "+token})
            if r.status_code==401 and attempt==0 and allow_401_refresh:
                r.close()
                token=self._get_token(invalidate=True)
                continue
            if not 200 <= r.status_code < 300:
                status=r.status_code
                r.close()
                raise GatewayError("falha_chat",status)
            raw=limited_json(r)
            choices=raw.get("choices")
            if not isinstance(choices,list) or not choices or not isinstance(choices[0],dict):
                raise GatewayError("texto_final_ausente")
            message=choices[0].get("message")
            content=message.get("content") if isinstance(message,dict) else None
            if isinstance(content,list):
                content="".join(b["text"] for b in content if isinstance(b,dict)
                                and b.get("type")=="text" and isinstance(b.get("text"),str))
            if not isinstance(content,str) or not content.strip():
                raise GatewayError("texto_final_ausente")
            # Campos reasoning/reasoning_content e detalhes de usage nunca sao retornados.
            usage=raw.get("usage")
            usage={k:v for k,v in usage.items() if k in {"prompt_tokens","completion_tokens","total_tokens"}
                   and type(v) is int and v>=0} if isinstance(usage,dict) else None
            model=raw.get("model")
            model=model if isinstance(model,str) and len(model)<=128 else None
            return ChatResult(content,model,usage,self.clock()-start,self._chat_requests-initial_requests)
        raise GatewayError("falha_chat")


def diagnose_llm(settings: LLMSettings, session=None):
    if not settings.configured:
        return Check(component="llm",state=CheckState.PENDING,outcome="configuracao_ausente")
    # Exatamente uma requisicao de chat: sem retry ou renovacao de 401 no diagnostico.
    probe=settings.model_copy(update={"max_attempts":1,"max_tokens":min(settings.max_tokens,64)})
    client=GatewayClient(probe,session=session)
    try:
        result=client.chat([{"role":"user","content":"Responda apenas OK."}],allow_401_refresh=False)
        return Check(component="llm",state=CheckState.VERIFIED,outcome="chat_textual_executado",
                     details={"requested_model":settings.model,"returned_model":result.model,
                              "latency_seconds":result.elapsed_seconds,"usage":result.usage,
                              "chat_requests":result.chat_requests,"nonempty_final_text":True,
                              "tested_payload_fields":["model","messages","stream","max_tokens"],
                              "native_tools":"nao_testado","json_schema":"nao_testado"})
    except GatewayError as e:
        return Check(component="llm",state=CheckState.UNAVAILABLE,outcome=e.code,
                     details={"http_status":e.status})
    finally:
        client.close()
