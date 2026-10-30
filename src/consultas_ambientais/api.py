"""FastAPI local. Rotas sincronas usam o thread pool; I/O do LLM roda em processo limitado."""
import json
import asyncio
import logging
import time
from pathlib import Path
from uuid import uuid4
from typing import Annotated
from fastapi import FastAPI, Header, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException
from .delivery.models import UUID, HASH, QuestionRequest, ClarificationRequest, LocalResponse, SessionCreated, DeliveryError, ErrorResponse, error_payload
from .delivery.settings import LocalSettings, load_environment
from .delivery.runtime import LocalRuntime
from .delivery.export import export
from .settings import ProjectConfig

TOKEN = Annotated[str | None, Header(alias='X-Session-Token')]
logger = logging.getLogger('consultas_ambientais.http')


class LocalBoundary:
    """Limite real de bytes inclusive em chunked; sem logs de URL, corpo ou cabecalhos."""
    def __init__(self, app, config):
        self.app, self.config = app, config

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request_id, start = uuid4().hex, time.monotonic()
        headers = {k.lower(): v for k, v in scope['headers']}
        status, started = 500, False

        async def wrapped(message):
            nonlocal status, started
            if message['type'] == 'http.response.start':
                status = message['status']
                started = True
                message['headers'] = [*message.get('headers', []), (b'x-request-id', request_id.encode()),
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'), (b'content-security-policy', b"default-src 'none'; frame-ancestors 'none'")]
            await send(message)

        async def reject(code, reason):
            await JSONResponse(error_payload(reason), status_code=code)(scope, receive, wrapped)
        try:
            raw_host = headers.get(b'host', b'').decode('latin1').lower()
            hosts = {'127.0.0.1', 'localhost', '[::1]'}
            if raw_host not in hosts | {h+':'+str(self.config.port) for h in hosts}:
                return await reject(400, 'host_nao_permitido')
            origin = headers.get(b'origin')
            allowed = {f'http://127.0.0.1:{self.config.port}', f'http://localhost:{self.config.port}', f'http://[::1]:{self.config.port}'}
            if origin is not None and origin.decode('latin1') not in allowed:
                return await reject(403, 'origem_nao_permitida')
            if headers.get(b'content-encoding', b'identity').lower() != b'identity':
                return await reject(415, 'codificacao_nao_suportada')
            chunks, size = [], 0
            body_deadline = time.monotonic() + self.config.body_timeout_seconds
            while True:
                remaining = body_deadline - time.monotonic()
                if remaining <= 0:
                    return await reject(408, "timeout_requisicao")
                message = await asyncio.wait_for(receive(), remaining)
                if message['type'] == 'http.disconnect':
                    return
                data = message.get('body', b'')
                size += len(data)
                if size > self.config.max_body_bytes:
                    return await reject(413, 'requisicao_excede_limite')
                chunks.append(data)
                if not message.get('more_body', False):
                    break
            body = b''.join(chunks)
            sent = False
            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                return await receive()
            await self.app(scope, replay, wrapped)
        except asyncio.TimeoutError:
            if not started:
                await reject(408, 'timeout_requisicao')
        except Exception:
            if not started:
                await reject(503, 'falha_tecnica_local')
        finally:
            logger.info('request_id=%s status=%s duration_ms=%.1f', request_id, status, (time.monotonic()-start)*1000)


def create_app(root=None, project=None, config=None, environment=None, runner=None):
    root = Path(root or Path.cwd()).resolve()
    project = project or ProjectConfig.load(root/'configs/project.json')
    config = config or LocalSettings.load(root/'configs/local.json')
    environment = environment or load_environment(config)
    runtime = LocalRuntime(root, project, config, environment, runner)
    app = FastAPI(title='Consultas ambientais locais', version='0.6.0', docs_url=None, redoc_url=None, debug=False,
                  responses={code: {'model': LocalResponse | ErrorResponse if code in {503,504} else ErrorResponse}
                             for code in (400,404,408,409,413,415,422,429,503,504)})
    app.state.runtime = runtime
    app.add_middleware(LocalBoundary, config=config)

    @app.exception_handler(DeliveryError)
    async def delivery_error(request, error):
        return JSONResponse(error_payload(error.reason, error.status), status_code=error.http_status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse(error_payload('requisicao_invalida', 'precisa_esclarecimento'), status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse(error_payload('rota_ou_metodo_nao_disponivel'), status_code=error.status_code)

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        return JSONResponse(error_payload('falha_tecnica_local'), status_code=503)

    def returned(value):
        status = 504 if value.reason == 'consulta_timeout' else 503 if value.status.value == 'erro_tecnico' else 200
        return JSONResponse(value.model_dump(mode='json'), status_code=status)

    @app.get('/healthz')
    def health():
        return {'state': 'ok', 'service': 'consultas_ambientais_local'}

    @app.get('/v1/capabilities')
    def available(territory_code: Annotated[str | None, Query(pattern=r'^(?:[0-9]{2}|[0-9]{7})$')] = None):
        return runtime.get_capabilities(territory_code)

    @app.post('/v1/sessions', response_model=SessionCreated, status_code=201)
    def new_session():
        return runtime.create_session()

    @app.post('/v1/sessions/{session_id}/questions', response_model=LocalResponse)
    def ask(session_id: UUID, body: QuestionRequest, x_session_token: TOKEN = None):
        return returned(runtime.ask(session_id, x_session_token, body.question))

    @app.post('/v1/sessions/{session_id}/results/{result_id}/clarifications', response_model=LocalResponse)
    def clarify(session_id: UUID, result_id: UUID, body: ClarificationRequest, x_session_token: TOKEN = None):
        return returned(runtime.ask(session_id, x_session_token, body.reply, result_id, body.clarification_id))

    @app.get('/v1/sessions/{session_id}/results/{result_id}', response_model=LocalResponse)
    def result(session_id: UUID, result_id: UUID, x_session_token: TOKEN = None):
        return runtime.get(session_id, x_session_token, result_id)

    @app.get('/v1/sessions/{session_id}/answers/{answer_id}')
    def answer(session_id: UUID, answer_id: HASH, x_session_token: TOKEN = None):
        return runtime.registry.answer(session_id, x_session_token, answer_id)

    @app.get('/v1/sessions/{session_id}/results/{result_id}/evidence')
    def evidence(session_id: UUID, result_id: UUID, x_session_token: TOKEN = None):
        response = runtime.get(session_id, x_session_token, result_id)
        q = response.result
        return {'status': response.status, 'result_id': result_id,
                'evidence': q.evidence if q else [], 'execution': q.execution if q else None,
                'source_context': response.source_context, 'limitations': response.limitations}

    @app.get('/v1/sessions/{session_id}/results/{result_id}/evidence/{evidence_id}')
    def one_evidence(session_id: UUID, result_id: UUID, evidence_id: HASH, x_session_token: TOKEN = None):
        q = runtime.get(session_id, x_session_token, result_id).result
        for e in q.evidence if q else []:
            if e.evidence_id == evidence_id:
                return e
        raise DeliveryError('evidencia_nao_encontrada', 404)

    @app.get('/v1/sessions/{session_id}/results/{result_id}/export/{format}')
    def exported(session_id: UUID, result_id: UUID, format: str, x_session_token: TOKEN = None):
        if format not in {'json', 'csv', 'html'}:
            raise DeliveryError('formato_nao_suportado', 404)
        content, mime = export(runtime.get(session_id, x_session_token, result_id), format, config.max_result_bytes)
        return Response(content, media_type=mime,
                        headers={'Content-Disposition': f'attachment; filename="resultado-{result_id}.{format}"'})
    return app
