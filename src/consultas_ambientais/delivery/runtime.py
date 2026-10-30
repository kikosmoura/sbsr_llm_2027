"""Servico comum a CLI e API. Persistencia local, sem consulta ao PostGIS/raster."""
import fcntl
import hashlib
import json
from .. import __version__
from ..semantics.catalog import digest
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from ..contracts import ResponseStatus
from .capabilities import capabilities
from .models import LocalResponse, DeliveryError
from .sessions import SessionRegistry
from .worker import ProcessRunner


def interface_digest():
    base = Path(__file__).parents[1]
    files = sorted([*base.joinpath('delivery').glob('*.py'), base/'api.py', base/'cli.py', base/'__init__.py'])
    return digest({str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


class LocalRuntime:
    def __init__(self, root, project, config, environment, runner=None):
        self.root = Path(root).resolve()
        self.project, self.config, self.environment = project, config, environment
        manifest = self.root / project.artifacts_dir / 'processing' / config.run_id / 'manifest.json'
        if manifest.is_file() and manifest.stat().st_size <= 16777216:
            identity = json.loads(manifest.read_text()).get('identity', {})
            if identity.get('software', {}).get('synthetic_fixture_only') and config.data_kind != 'synthetic':
                raise DeliveryError('dados_sinteticos_exigem_rotulo_sintetico')
        self.registry = SessionRegistry(self.root, config)
        base = (self.root / config.storage_dir).resolve()
        if not base.is_relative_to(self.root) or any(base.is_relative_to((self.root / p).resolve())
                for p in (project.data_dir + '/processed', project.artifacts_dir + '/processing')):
            raise DeliveryError('armazenamento_local_fora_do_escopo')
        self.runner = runner or ProcessRunner()

    @contextmanager
    def mutation(self):
        base = self.root / self.config.storage_dir
        base.mkdir(parents=True, exist_ok=True)
        with (base / 'operation.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DeliveryError('servico_ocupado', 429) from None
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def create_session(self):
        with self.mutation():
            return self.registry.create()

    def get_capabilities(self, territory_code=None):
        try:
            return capabilities(self.root, self.project, self.config, territory_code)
        except Exception:
            raise DeliveryError('falha_na_verificacao_de_capacidades') from None

    def get(self, sid, token, rid):
        try:
            return LocalResponse.model_validate(self.registry.get(sid, token, rid)['public'])
        except DeliveryError:
            raise
        except Exception:
            raise DeliveryError('falha_na_leitura_do_resultado') from None

    def ask(self, sid, token, question, parent_id=None, clarification_id=None):
        with self.mutation():
            state = self.registry.authorize(sid, token)
            if len(state['results']) >= self.config.max_results_per_session:
                raise DeliveryError('limite_de_resultados_da_sessao', 429)
            self.registry.ensure_capacity(self.config.max_result_bytes + 4096)
            if not isinstance(question, str) or not 1 <= len(question) <= 4000:
                raise DeliveryError('pergunta_fora_do_limite', 422, 'precisa_esclarecimento')
            dialogue, internal = None, {}
            if parent_id is not None:
                previous = self.registry.get(sid, token, parent_id)
                parent = LocalResponse.model_validate(previous['public'])
                if not parent.clarification or parent.clarification.clarification_id != clarification_id:
                    raise DeliveryError('esclarecimento_incompativel', 409, 'precisa_esclarecimento')
                dialogue = previous['internal'].get('dialogue_session_id')
                if not dialogue:
                    raise DeliveryError('esclarecimento_indisponivel', 409, 'precisa_esclarecimento')
            try:
                answer = self.runner(self.root, self.project, self.config, self.environment,
                                     question, dialogue, clarification_id)
                public = LocalResponse(session_id=sid, result_id=answer.turn_id,
                    created_at=answer.created_at, status=answer.status, reason=answer.reason,
                    message=('Configuração LLM indisponível no processo local.' if answer.reason=='configuracao_llm_ausente' else answer.message), data_kind=self.config.data_kind,
                    result=answer.query, clarification=answer.clarification,
                    source_context=answer.source_context,
                    trace={'dialogue_session_id': answer.session_id, 'turn_id': answer.turn_id,
                           'parent_turn_id': answer.parent_turn_id, 'prompt_hashes': answer.prompt_hashes,
                           'interpreter_sha256': answer.interpreter_sha256, 'model': answer.requested_model,
                           'integration_kind': answer.integration_kind,
                           'returned_models': sorted({a.returned_model for a in answer.attempts if a.returned_model}),
                           'usage': [a.usage for a in answer.attempts], 'attempt_count': len(answer.attempts),
                           'latency_seconds': answer.latency_seconds},
                    limitations=['Classificação mapeada não comprova causas ou mudança real específica no terreno.',
                                 'Perda bruta exige matriz de transição.',
                                 'Revisão oficial e edição territorial podem permanecer desconhecidas.'])
                internal = {'dialogue_session_id': answer.session_id, 'turn_id': answer.turn_id}
            except DeliveryError as error:
                public = LocalResponse(session_id=sid, result_id=uuid4().hex,
                    status=ResponseStatus.ERROR, reason=error.reason,
                    message='Falha técnica ou limite de tempo; nenhum resultado numérico foi publicado.',
                    data_kind=self.config.data_kind,
                    source_context={'run_id': self.config.run_id},
                    trace={'parent_result_id': parent_id, 'worker_terminated': error.reason == 'consulta_timeout'},
                    limitations=['O processo local foi encerrado em caso de timeout; inicie outra pergunta.'])
            public.trace.update(interface_version=__version__, interface_sha256=interface_digest(),
                                local_config_sha256=digest(self.config))
            self.registry.save(sid, token, public, internal)
            return public
