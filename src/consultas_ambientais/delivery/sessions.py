"""Chave aleatoria por sessao; somente seu hash e persistido. Sem listar sessoes."""
import hashlib
import hmac
import json
import secrets
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from ..storage.dialogues import private_json
from .models import SessionCreated, LocalResponse, DeliveryError

ID = re.compile(r'^[0-9a-f]{32}$')
SHA = re.compile(r'^[0-9a-f]{64}$')


class SessionRegistry:
    def __init__(self, root, config):
        self.base = Path(root) / config.storage_dir / 'sessions'
        self.config = config

    def read(self, path):
        if path.stat().st_size > self.config.max_result_bytes:
            raise DeliveryError('registro_local_excede_limite')
        return json.loads(path.read_text())

    def ensure_capacity(self, extra=4096):
        used = sum(p.stat().st_size for p in self.base.rglob('*') if p.is_file()) if self.base.exists() else 0
        if used + extra > self.config.max_storage_bytes:
            raise DeliveryError('limite_de_armazenamento_local', 429)

    def create(self):
        self.ensure_capacity()
        self.base.mkdir(parents=True, exist_ok=True)
        if sum(1 for _ in self.base.glob('*/session.json')) >= self.config.max_sessions:
            raise DeliveryError('limite_de_sessoes_locais', 429)
        sid = uuid4().hex
        token = secrets.token_urlsafe(32)
        expiry = time.time() + self.config.session_ttl_seconds
        private_json(self.base / sid / 'session.json',
                     {'session_id': sid, 'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
                      'expires_at': expiry, 'results': {}, 'answers': {}})
        return SessionCreated(session_id=sid, session_token=token,
                              expires_at=datetime.fromtimestamp(expiry, timezone.utc))

    def authorize(self, sid, token):
        if not isinstance(sid, str) or not ID.fullmatch(sid) or not isinstance(token, str) or not 20 <= len(token) <= 128:
            raise DeliveryError('sessao_ou_recurso_nao_encontrado', 404)
        path = self.base / sid / 'session.json'
        if not path.is_file():
            raise DeliveryError('sessao_ou_recurso_nao_encontrado', 404)
        state = self.read(path)
        if state['expires_at'] <= time.time() or not hmac.compare_digest(
                state['token_sha256'], hashlib.sha256(token.encode()).hexdigest()):
            raise DeliveryError('sessao_ou_recurso_nao_encontrado', 404)
        return state

    def get(self, sid, token, rid):
        state = self.authorize(sid, token)
        if not ID.fullmatch(rid) or rid not in state['results']:
            raise DeliveryError('sessao_ou_recurso_nao_encontrado', 404)
        path = self.base / sid / (rid + '.json')
        if path.stat().st_size > self.config.max_result_bytes:
            raise DeliveryError('registro_local_excede_limite')
        if hashlib.sha256(path.read_bytes()).hexdigest() != state['results'][rid]:
            raise DeliveryError('registro_local_divergente')
        return self.read(path)

    def save(self, sid, token, public, internal):
        state = self.authorize(sid, token)
        if len(state['results']) >= self.config.max_results_per_session:
            raise DeliveryError('limite_de_resultados_da_sessao', 429)
        value = {'public': public.model_dump(mode='json'), 'internal': internal}
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode()
        self.ensure_capacity(len(encoded)+4096)
        if len(encoded) > self.config.max_result_bytes:
            raise DeliveryError('resultado_excede_limite_local')
        path = self.base / sid / (public.result_id + '.json')
        private_json(path, value)
        state['results'][public.result_id] = hashlib.sha256(path.read_bytes()).hexdigest()
        if public.result and public.result.answer_id:
            state['answers'][public.result.answer_id] = public.result_id
        private_json(self.base / sid / 'session.json', state)

    def answer(self, sid, token, answer_id):
        state = self.authorize(sid, token)
        rid = state['answers'].get(answer_id) if SHA.fullmatch(answer_id) else None
        if rid is None:
            raise DeliveryError('sessao_ou_recurso_nao_encontrado', 404)
        return LocalResponse.model_validate(self.get(sid, token, rid)['public']).result
