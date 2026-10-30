"""Contratos publicos. Dados pessoais e configuracao de conexao nao pertencem aqui."""
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, StrictInt


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True,
                              allow_inf_nan=False, validate_assignment=True)


class ResponseStatus(str, Enum):
    ANSWERED = "respondida"
    CLARIFY = "precisa_esclarecimento"
    OUT_OF_SCOPE = "fora_do_escopo"
    UNAVAILABLE = "dados_indisponiveis"
    ERROR = "erro_tecnico"


class CheckState(str, Enum):
    VERIFIED = "verificado"
    PENDING = "pendente"
    UNAVAILABLE = "indisponivel"


class Operation(str, Enum):
    AREA = "area"
    SHARE = "participacao"
    TEMPORAL = "comparacao_temporal"
    SERIES = "serie_disponivel"
    TERRITORIAL = "comparacao_territorial"
    RANKING = "ranking_delimitado"


class Metric(str, Enum):
    AREA = "area"
    SHARE = "participacao"
    DELTA = "diferenca_liquida"
    REDUCTION = "reducao_liquida"
    CHANGE = "variacao_percentual"
    POINTS = "diferenca_pontos_percentuais"


class Unit(str, Enum):
    HA = "ha"
    KM2 = "km2"
    M2 = "m2"
    PERCENT = "percentual"
    PP = "pontos_percentuais"


class Territory(Contract):
    kind: Literal["municipio", "uf"]
    code: str
    name: str = Field(min_length=1)
    uf: str = Field(pattern=r"^[A-Z]{2}$")
    geometry_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    edition: str | None = None

    @model_validator(mode="after")
    def validate_code(self):
        size = 7 if self.kind == "municipio" else 2
        if len(self.code) != size or not self.code.isascii() or not self.code.isdigit():
            raise ValueError("codigo territorial fora do formato")
        return self


class LandClass(Contract):
    code: int = Field(ge=0)
    name: str = Field(min_length=1)
    parent_code: int | None = Field(default=None, ge=0)
    leaf_codes: list[int] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    beta: bool = False
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def unique_leaves(self):
        if len(self.leaf_codes) != len(set(self.leaf_codes)):
            raise ValueError("codigos de folhas duplicados")
        if self.parent_code == self.code or any(c < 0 for c in self.leaf_codes):
            raise ValueError("hierarquia de classe invalida")
        return self


class RasterMetadata(Contract):
    year: int
    collection: int
    source_revision: str | None = None
    catalog_schema: str = "mapbiomas-catalogo-v1"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    band_count: int = Field(gt=0)
    crs: str | None
    transform: list[float] = Field(min_length=6, max_length=6)
    resolution: list[float] = Field(min_length=2, max_length=2)
    dtypes: list[str]
    nodata: float | str | None
    block_shapes: list[list[int]]
    compression: str | None
    cog_layout: str | None
    size_bytes: int | None = Field(default=None, ge=0)
    etag: str | None = None
    last_modified: str | None = None


class ProcessingQuality(Contract):
    state: Literal["nao_processado", "parcial", "completo"]
    observed_area_ha: float | None = Field(default=None, ge=0)
    nodata_area_ha: float | None = Field(default=None, ge=0)
    unknown_codes: list[int] = Field(default_factory=list)
    common_support_id: str | None = None
    area_method: str | None = None
    notes: list[str] = Field(default_factory=list)


class QueryPlan(Contract):
    operation: Operation
    metric: Metric
    unit: Unit
    territory_codes: list[str] = Field(default_factory=list)
    scope_uf: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    class_codes: list[StrictInt] = Field(min_length=1, max_length=41)
    years: list[StrictInt] = Field(min_length=1, max_length=11)
    denominator: Literal["area_observada", "area_inicial", "participacao_por_ano"] | None = None
    direction: Literal["asc", "desc"] = "desc"
    limit: StrictInt | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def coherent(self):
        for values in [self.territory_codes, self.class_codes, self.years]:
            if len(values) != len(set(values)):
                raise ValueError("campos de selecao duplicados")
        if any(not c.isascii() or not c.isdigit() or len(c) not in (2, 7)
               for c in self.territory_codes):
            raise ValueError("codigo territorial invalido")
        if any(c < 0 for c in self.class_codes) or any(not 2015 <= y <= 2025 for y in self.years):
            raise ValueError("classe ou ano fora do escopo candidato")
        temporal = self.metric in {Metric.DELTA, Metric.REDUCTION, Metric.CHANGE, Metric.POINTS}
        if temporal and (len(self.years) != 2 or self.years != sorted(self.years)):
            raise ValueError("metrica temporal exige dois anos distintos em ordem")
        if self.operation == Operation.TEMPORAL and not temporal:
            raise ValueError("operacao temporal exige metrica temporal")
        if self.operation == Operation.AREA and (self.metric != Metric.AREA or len(self.years) != 1):
            raise ValueError("operacao area exige metrica area e um ano")
        if self.operation == Operation.SHARE and (self.metric != Metric.SHARE or len(self.years) != 1):
            raise ValueError("operacao participacao exige um ano e metrica participacao")
        if self.operation == Operation.SERIES and self.metric not in {Metric.AREA, Metric.SHARE}:
            raise ValueError("serie suporta area ou participacao")
        if not temporal and self.operation != Operation.SERIES and len(self.years) != 1:
            raise ValueError("metrica anual exige um ano")
        expected = {Metric.SHARE: "area_observada", Metric.CHANGE: "area_inicial",
                    Metric.POINTS: "participacao_por_ano"}.get(self.metric)
        if self.denominator != expected:
            raise ValueError("denominador incompatível com a metrica")
        expected_unit = {Metric.SHARE: Unit.PERCENT, Metric.CHANGE: Unit.PERCENT,
                         Metric.POINTS: Unit.PP}.get(self.metric)
        if expected_unit and self.unit != expected_unit:
            raise ValueError("unidade incompatível com a metrica")
        if not expected_unit and self.unit not in {Unit.HA, Unit.KM2, Unit.M2}:
            raise ValueError("metrica de area exige unidade de area")
        if self.operation == Operation.RANKING:
            if not self.scope_uf or self.limit is None or self.territory_codes:
                raise ValueError("ranking exige UF, limite e universo sem selecao parcial")
        elif self.limit is not None or not self.territory_codes:
            raise ValueError("consulta exige territorios e nao aceita limite de ranking")
        if self.operation == Operation.TERRITORIAL and len(self.territory_codes) < 2:
            raise ValueError("comparacao territorial exige ao menos dois territorios")
        return self


class Evidence(Contract):
    evidence_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    territory: Territory
    class_codes: list[int] = Field(min_length=1)
    years: list[int] = Field(min_length=1)
    collection: int = 11
    source_revision: str | None
    source_ids: list[str] = Field(min_length=1)
    area_method: str = Field(min_length=1)
    quality: ProcessingQuality


class ResultValue(Contract):
    evidence_id: str
    value: float | None
    unit: Unit
    denominator_value: float | None = Field(default=None, ge=0)
    undefined_reason: str | None = None

    @model_validator(mode="after")
    def undefined(self):
        if self.value is None and not self.undefined_reason:
            raise ValueError("valor indefinido exige motivo")
        return self


class Answer(Contract):
    status: ResponseStatus
    message: str = Field(min_length=1)
    plan: QueryPlan | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    values: list[ResultValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def provenance(self):
        if self.status == ResponseStatus.ANSWERED:
            if not self.plan or not self.evidence or not self.values:
                raise ValueError("resposta quantitativa exige plano, valores e evidencias")
            ids = {e.evidence_id for e in self.evidence}
            if len(ids) != len(self.evidence) or any(v.evidence_id not in ids for v in self.values):
                raise ValueError("referencia de evidencia invalida")
        elif self.values or self.evidence:
            raise ValueError("resposta nao concluida nao publica valores ou evidencias")
        return self


class Check(Contract):
    component: str
    state: CheckState
    outcome: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict = Field(default_factory=dict)


class DiagnosticReport(Contract):
    schema_version: str = "diagnostico-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    checks: list[Check]
