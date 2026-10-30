"""Contratos semanticos: intencao nao resolvida, catalogos e capacidades reais."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, StrictInt, model_validator, field_validator
from typing_extensions import TypedDict

from ..contracts import Contract, LandClass, Metric, Operation, QueryPlan, Unit

SHA = r"^[0-9a-f]{64}$"


class SourceDocument(Contract):
    source_id: str
    url: str
    sha256: str = Field(pattern=SHA)
    bytes: int = Field(gt=0)
    retrieved_at: datetime
    content_type: str | None = None
    last_modified: str | None = None
    status: Literal["obtido"] = "obtido"


class CatalogClass(LandClass):
    name_en: str
    printed_path: str
    canonical_path: str
    kind: Literal["grupo", "classe_folha"]
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    descendant_codes: list[int]
    sources: list[str]


class ClassCatalogData(Contract):
    schema_version: Literal["mapbiomas-col11-semantica-v1"] = "mapbiomas-col11-semantica-v1"
    collection: Literal[11] = 11
    published_date: str = "2026-08-13"
    sources: list[SourceDocument]
    extraction: dict
    discrepancies: list[dict]
    classes: list[CatalogClass]
    initial_leaf_codes: list[int] = Field(default_factory=lambda: [3, 15, 24, 33])


class TerritoryEntry(Contract):
    kind: Literal["municipio", "uf"]
    code: str
    name_original: str = Field(min_length=1)
    uf: str = Field(pattern=r"^[A-Z]{2}$")
    uf_code: str = Field(pattern=r"^[0-9]{2}$")
    search_aliases: list[str] = Field(default_factory=list)
    alias_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def codes(self):
        length = 7 if self.kind == "municipio" else 2
        if not self.code.isascii() or not self.code.isdigit() or len(self.code) != length:
            raise ValueError("codigo territorial invalido")
        if self.kind == "municipio" and self.code[:2] != self.uf_code:
            raise ValueError("prefixo municipal incoerente com UF")
        if self.kind == "uf" and self.code != self.uf_code:
            raise ValueError("codigo de UF incoerente")
        return self


class TerritoryCatalogData(Contract):
    schema_version: Literal["territorios-semantica-v1"] = "territorios-semantica-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_tables: list[str] = Field(default_factory=lambda: ["sbsr.municipios", "sbsr.uf"])
    edition: str | None = None
    read_only_confirmed: bool
    entries: list[TerritoryEntry]
    content_sha256: str = Field(pattern=SHA)


class TerritoryReference(Contract):
    code: str | None = Field(default=None, pattern=r"^(?:[0-9]{2}|[0-9]{7})$")
    name: str | None = Field(default=None, min_length=1)
    uf: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    kind: Literal["municipio", "uf"] | None = None

    @field_validator("uf",mode="before")
    @classmethod
    def normalize_uf(cls,value):
        return value.strip().upper() if isinstance(value,str) else value

    @model_validator(mode="after")
    def has_selector(self):
        if self.code is None and not self.name and not (self.kind == "uf" and self.uf):
            raise ValueError("territorio exige codigo, nome ou sigla de UF")
        return self


class ClassReference(Contract):
    code: StrictInt | None = Field(default=None, ge=0)
    term: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def has_selector(self):
        if self.code is None and not self.term:
            raise ValueError("classe exige codigo ou termo")
        return self


class QueryIntent(Contract):
    schema_version: Literal["intencao-semantica-v1"] = "intencao-semantica-v1"
    operation: Operation
    territories: list[TerritoryReference] = Field(default_factory=list)
    scope_uf: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    classes: list[ClassReference] = Field(min_length=1)
    years: list[StrictInt] = Field(min_length=1)
    metric: Metric | None = None
    metric_term: str | None = None
    unit: Unit | None = None
    unit_term: str | None = None
    denominator: Literal["area_observada", "area_inicial", "participacao_por_ano"] | None = None
    direction: Literal["asc", "desc"] = "desc"
    limit: StrictInt | None = Field(default=None, ge=1, le=100)
    requested_concept: Literal["cobertura", "perda_bruta", "ganho_bruto", "evento_inundacao",
                               "desmatamento", "vegetacao_nativa", "causa", "ilegalidade", "projecao"] = "cobertura"

    @field_validator("scope_uf",mode="before")
    @classmethod
    def normalize_uf(cls,value):
        return value.strip().upper() if isinstance(value,str) else value


class TerritoryCandidate(TypedDict):
    code: str
    name_original: str
    kind: Literal["municipio", "uf"]
    uf: str
    alias_notes: list[str]


class ClassCandidate(TypedDict):
    code: int
    name: str
    kind: Literal["grupo", "classe_folha"]


class Resolution(Contract):
    status: Literal["resolvido", "precisa_esclarecimento", "nao_encontrado"]
    reason: str
    selected_codes: list[str | int] = Field(default_factory=list)
    candidates: list[TerritoryCandidate | ClassCandidate] = Field(default_factory=list)
    match_kind: str | None = None
    notes: list[str] = Field(default_factory=list)


class Materialization(Contract):
    territory_code: str = Field(pattern=r"^(?:[0-9]{2}|[0-9]{7})$")
    years: list[int] = Field(min_length=1, max_length=2)
    class_codes: list[int] = Field(min_length=1)
    complete: bool
    common_support_id: str | None = None
    run_id: str

    @model_validator(mode="after")
    def support(self):
        if self.years != sorted(set(self.years)) or len(self.class_codes) != len(set(self.class_codes)):
            raise ValueError("materializacao possui selecoes repetidas ou fora de ordem")
        if len(self.years) == 2 and not self.common_support_id:
            raise ValueError("par temporal exige identificador do suporte comum")
        return self


class Capabilities(Contract):
    schema_version: Literal["capacidades-semantica-v1"] = "capacidades-semantica-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    class_catalog_sha256: str = Field(pattern=SHA)
    territory_catalog_sha256: str = Field(pattern=SHA)
    diagnostic_sha256: str | None = Field(default=None, pattern=SHA)
    available_raster_years: list[int]
    supported_operations: list[Operation] = Field(default_factory=lambda: list(Operation))
    materializations: list[Materialization] = Field(default_factory=list)
    engine_ready: bool = False
    observed_samples: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def years_unique(self):
        if self.available_raster_years != sorted(set(self.available_raster_years)):
            raise ValueError("anos disponiveis devem ser distintos e ordenados")
        keys = [(m.territory_code, tuple(m.years)) for m in self.materializations]
        if len(keys) != len(set(keys)):
            raise ValueError("materializacoes duplicadas")
        if any(not set(m.years) <= set(self.available_raster_years) for m in self.materializations):
            raise ValueError("materializacao aponta para ano indisponivel")
        return self


class SemanticDecision(Contract):
    status: Literal["plano_validado", "precisa_esclarecimento", "fora_do_escopo",
                    "dados_indisponiveis", "erro_tecnico"]
    reason: str
    message: str
    normalized_plan: QueryPlan | None = None
    territory_candidates: list[TerritoryCandidate] = Field(default_factory=list)
    class_candidates: list[ClassCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    class_catalog_sha256: str | None = Field(default=None, pattern=SHA)
    territory_catalog_sha256: str | None = Field(default=None, pattern=SHA)
    capabilities_sha256: str | None = Field(default=None, pattern=SHA)

    @model_validator(mode="after")
    def ready_has_plan(self):
        if self.status == "plano_validado" and self.normalized_plan is None:
            raise ValueError("plano validado exige plano normalizado")
        return self
