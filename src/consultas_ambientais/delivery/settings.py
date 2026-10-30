"""Configuracao publica e leitura opt-in de .env, sem executar shell."""
from dataclasses import dataclass, field
from pathlib import Path
import json
import os
from typing import Literal
from pydantic import Field, model_validator
from ..contracts import Contract
from ..settings import LLMSettings


class LocalSettings(Contract):
    run_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    territories: str = 'data/territories_v1.json'
    capabilities: str = 'data/capabilities_stage3.json'
    storage_dir: str = 'artifacts/local_service'
    bind_host: Literal['127.0.0.1', '::1'] = '127.0.0.1'
    port: int = Field(default=8765, ge=1024, le=65535)
    max_body_bytes: int = Field(default=32768, ge=1024, le=65536)
    body_timeout_seconds: float = Field(default=10, gt=0, le=30)
    max_query_seconds: float = Field(default=90, gt=0, le=300)
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    llm_max_tokens: int = Field(default=2048, ge=256, le=2048)
    llm_max_attempts: int = Field(default=2, ge=1, le=3)
    temperature: float = Field(default=0, ge=0, le=2)
    max_sessions: int = Field(default=32, ge=1, le=4096)
    max_results_per_session: int = Field(default=25, ge=1, le=500)
    session_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    max_storage_bytes: int = Field(default=134217728, ge=65536, le=1073741824)
    max_result_bytes: int = Field(default=4194304, ge=65536, le=8388608)
    data_kind: Literal['real', 'synthetic'] = 'real'

    @model_validator(mode='after')
    def relative_paths(self):
        for name in ('territories', 'capabilities', 'storage_dir'):
            p = Path(getattr(self, name))
            if p.is_absolute() or '..' in p.parts or any(v.startswith('.env') for v in p.parts):
                raise ValueError('caminho_local_invalido')
        if self.storage_dir.split('/')[0] not in {'artifacts', 'data'}:
            raise ValueError('armazenamento_privado_exige_data_ou_artifacts')
        return self

    @classmethod
    def load(cls, path):
        return cls.model_validate_json(Path(path).read_text())


@dataclass(repr=False)
class LocalEnvironment:
    settings: LLMSettings
    redaction_secrets: tuple = field(default=(), repr=False)


def load_environment(config, env_file=None):
    values = dict(os.environ)
    if env_file is not None:
        from dotenv import dotenv_values
        p = Path(env_file)
        if not p.is_file():
            raise ValueError('arquivo_env_ausente')
        # Valores interpolados nao executam comandos ou referencias de shell.
        values.update({k: v for k, v in dotenv_values(p, interpolate=False).items()
                       if v is not None and k.startswith(('LLM_', 'SOURCE_PG_'))})
    values.update(LLM_TIMEOUT=str(config.llm_timeout_seconds),
                  LLM_MAX_TOKENS=str(config.llm_max_tokens),
                  LLM_MAX_ATTEMPTS=str(config.llm_max_attempts),
                  LLM_TEMPERATURE=str(config.temperature))
    settings = LLMSettings.from_env(values)
    extras = tuple(values[k] for k in ('SOURCE_PG_HOST', 'SOURCE_PG_DATABASE',
                   'SOURCE_PG_USER', 'SOURCE_PG_PASSWORD') if values.get(k))
    return LocalEnvironment(settings, extras)
