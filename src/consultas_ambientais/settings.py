"""Configuracao sem leitura automatica de arquivos locais de credenciais."""
import json
import os
from pathlib import Path
from string import Formatter
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator

from .contracts import Contract
from .processing.models import ProcessingConfig


def https_url(value: str) -> str:
    try:
        p = urlsplit(value)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment:
            raise ValueError
        _ = p.port
    except ValueError:
        raise ValueError("URL HTTPS sem credenciais, query ou fragmento exigida") from None
    return value.rstrip("/")


class ProjectConfig(Contract):
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    collection: int = Field(default=11, ge=11, le=11)
    candidate_years: list[int] = Field(default_factory=lambda: list(range(2015, 2026)))
    base_url: str = "https://storage.example.invalid/BUCKET_NAME"
    filename_template: str = "brazil_coverage-col{colecao}_{ano}.tif"
    catalog_schema: str = "mapbiomas-catalogo-v1"
    pilot_uf: str = Field(default="RN", pattern=r"^[A-Z]{2}$")
    pilot_years: list[int] = Field(default_factory=lambda: [2015, 2025])
    source_revision: str | None = None
    territorial_edition: str | None = None
    data_dir: str = "data"
    cache_dir: str = "cache"
    artifacts_dir: str = "artifacts"
    http_timeout_seconds: float = Field(default=10, gt=0, le=120)
    max_bytes_per_raster: int = Field(default=4194304, ge=16384, le=16777216)
    max_range_requests: int = Field(default=64, ge=1, le=256)
    sample_size: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def coherent(self):
        https_url(self.base_url)
        if (not self.candidate_years or self.candidate_years != sorted(set(self.candidate_years))
                or any(y not in range(2015, 2026) for y in self.candidate_years)):
            raise ValueError("anos candidatos invalidos")
        if len(self.pilot_years) != 2 or self.pilot_years != sorted(set(self.pilot_years)):
            raise ValueError("piloto exige par distinto de anos em ordem")
        if not set(self.pilot_years) <= set(self.candidate_years):
            raise ValueError("anos piloto fora do catalogo candidato")
        fields = [n for _, n, _, _ in Formatter().parse(self.filename_template) if n]
        if set(fields) != {"colecao", "ano"}:
            raise ValueError("template de arquivo invalido")
        filename = self.filename_template.format(colecao=11, ano=2015)
        if "/" in filename or "\\" in filename or not filename.endswith(".tif"):
            raise ValueError("template deve formar nome GeoTIFF simples")
        for directory in (self.data_dir, self.cache_dir, self.artifacts_dir):
            if Path(directory).is_absolute() or ".." in Path(directory).parts:
                raise ValueError("diretorios devem ser relativos ao projeto")
        return self

    def raster_url(self, year: int) -> str:
        if year not in self.candidate_years:
            raise ValueError("ano nao candidato")
        return self.base_url.rstrip("/") + "/" + self.filename_template.format(colecao=self.collection, ano=year)

    @classmethod
    def load(cls, path: Path | None = None):
        return cls.model_validate(json.loads(path.read_text()) if path else {})


class DatabaseSettings(Contract):
    host: SecretStr | None = Field(default=None, exclude=True, repr=False)
    port: int = Field(default=5432, ge=1, le=65535)
    database: SecretStr | None = Field(default=None, exclude=True, repr=False)
    user: SecretStr | None = Field(default=None, exclude=True, repr=False)
    password: SecretStr | None = Field(default=None, exclude=True, repr=False)
    sslmode: str = Field(default="prefer", pattern=r"^(prefer|require|verify-ca|verify-full|disable|allow)$")
    connect_timeout: int = Field(default=5, ge=1, le=30)
    statement_timeout_ms: int = Field(default=10000, ge=100, le=60000)
    lock_timeout_ms: int = Field(default=1000, ge=100, le=10000)

    @model_validator(mode="after")
    def complete(self):
        values = [self.host, self.database, self.user, self.password]
        if any(values) and not all(values):
            raise ValueError("configuracao SOURCE_PG incompleta")
        return self

    @property
    def configured(self):
        return bool(self.host and self.database and self.user and self.password)

    @classmethod
    def from_env(cls, env=None):
        e = os.environ if env is None else env
        mapping = {"HOST":"host", "PORT":"port", "DATABASE":"database", "USER":"user",
                   "PASSWORD":"password", "SSLMODE":"sslmode", "CONNECT_TIMEOUT":"connect_timeout",
                   "STATEMENT_TIMEOUT_MS":"statement_timeout_ms", "LOCK_TIMEOUT_MS":"lock_timeout_ms"}
        return cls.model_validate({v:e["SOURCE_PG_"+k] for k,v in mapping.items() if e.get("SOURCE_PG_"+k)})


class LLMSettings(Contract):
    base_url: SecretStr | None = Field(default=None, exclude=True, repr=False)
    token_url: SecretStr | None = Field(default=None, exclude=True, repr=False)
    client_id: SecretStr | None = Field(default=None, exclude=True, repr=False)
    client_secret: SecretStr | None = Field(default=None, exclude=True, repr=False)
    scope: SecretStr | None = Field(default=None, exclude=True, repr=False)
    audience: SecretStr | None = Field(default=None, exclude=True, repr=False)
    model: str | None = None
    token_auth_mode: str = Field(default="basic", pattern=r"^(basic|body|auto)$")
    timeout: float = Field(default=30, gt=0, le=120)
    max_attempts: int = Field(default=3, ge=1, le=5)
    max_tokens: int = Field(default=128, ge=1, le=4096)
    temperature: float | None = Field(default=None, ge=0, le=2)
    ca_bundle: SecretStr | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def coherent(self):
        values = [self.base_url, self.token_url, self.client_id, self.client_secret, self.model]
        if any(values) and not all(values):
            raise ValueError("configuracao LLM incompleta")
        for v in [self.base_url,self.token_url]:
            if v:https_url(v.get_secret_value())
        if self.ca_bundle and not Path(self.ca_bundle.get_secret_value()).is_file():
            raise ValueError("arquivo CA configurado indisponivel")
        return self

    @property
    def configured(self):
        return bool(self.base_url and self.token_url and self.client_id and self.client_secret and self.model)

    @property
    def verify(self):
        return self.ca_bundle.get_secret_value() if self.ca_bundle else True

    @classmethod
    def from_env(cls, env=None):
        e = os.environ if env is None else env
        names = ["base_url","token_url","client_id","client_secret","scope","audience","model",
                 "token_auth_mode","timeout","max_attempts","max_tokens","temperature","ca_bundle"]
        return cls.model_validate({n:e["LLM_"+n.upper()] for n in names if e.get("LLM_"+n.upper())})
