"""Resposta verificavel v1: estende as evidencias basicas sem alterar o envelope historico."""
from typing import Literal
from pydantic import Field,model_validator
from ..contracts import Contract,Evidence,ResultValue,QueryPlan,ResponseStatus,Metric,Unit

class Observation(Contract):
    year: int
    class_area_ha: float = Field(ge=0)
    observed_area_ha: float = Field(ge=0)
    support: Literal["anual","comum"]
    nodata_area_ha: float = Field(default=0,ge=0)
    unknown_area_ha: float = Field(default=0,ge=0)
    outside_raster_area_ha: float = Field(default=0,ge=0)

class SourceReference(Contract):
    source_id: str
    kind: Literal["execucao","malha","catalogo","raster_espelho","recorte","particao_areas","particao_qualidade"]
    sha256: str | None = Field(default=None,pattern=r"^[0-9a-f]{64}$")
    year: int | None = None
    public_url: str | None = None
    etag: str | None = None

class QueryEvidence(Evidence):
    plan_id: str
    metric: Metric
    requested_class_codes: list[int]
    class_names: list[str]
    observations: list[Observation] = Field(min_length=1)
    denominator_definition: str | None
    denominator_values_ha: list[float] = Field(default_factory=list)
    provenance: Literal["municipio_direto","uf_direta"]
    mesh_sha256: str
    catalog_sha256: str
    run_manifest_sha256: str
    sources: list[SourceReference] = Field(min_length=1)

class QueryValue(ResultValue):
    metric: Metric
    area_value_ha: float | None = None
    denominator_unit: Unit | None = None
    rank: int | None = Field(default=None,ge=1)

class RankingInfo(Contract):
    scope_uf: str
    universe: Literal["municipios_da_uf"] = "municipios_da_uf"
    candidate_codes: list[str]
    candidate_count: int = Field(ge=1)
    verified_count: int = Field(ge=1)
    coverage: Literal["completa"] = "completa"
    metric: Metric
    sign_convention: str
    direction: Literal["asc","desc"]
    tie_break: Literal["codigo_ibge_asc"] = "codigo_ibge_asc"
    limit: int = Field(ge=1,le=100)
    filtered_non_reductions: int = Field(default=0,ge=0)
    undefined_codes: list[str] = Field(default_factory=list)
    qualifying_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)

    @model_validator(mode="after")
    def complete(self):
        if (self.candidate_codes!=sorted(set(self.candidate_codes)) or
            len(self.candidate_codes)!=self.candidate_count or self.verified_count!=self.candidate_count or
            self.returned_count!=min(self.limit,self.qualifying_count)):
            raise ValueError("universo ou ordenacao do ranking incoerente")
        return self

class ExecutionContext(Contract):
    run_id: str
    run_manifest_sha256: str
    collection: int
    source_revision: str | None
    territorial_edition: str | None
    method: str
    mesh_sha256: str
    catalog_sha256: str
    years: list[int]
    class_names: list[str]
    sources: list[SourceReference] = Field(min_length=1)

class QueryAnswer(Contract):
    schema_version: Literal["resposta-consulta-v1"] = "resposta-consulta-v1"
    status: ResponseStatus
    reason: str
    message: str
    answer_id: str | None = None
    plan_id: str | None = None
    executor_sha256: str | None = None
    requested_plan: QueryPlan | None = None
    plan: QueryPlan | None = None
    evidence: list[QueryEvidence] = Field(default_factory=list)
    values: list[QueryValue] = Field(default_factory=list)
    execution: ExecutionContext | None = None
    ranking: RankingInfo | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def proven(self):
        if self.status==ResponseStatus.ANSWERED:
            if not all([self.answer_id,self.plan_id,self.executor_sha256,self.plan,self.requested_plan,self.execution]):
                raise ValueError("resposta exige registro do plano e da execucao")
            empty_rank=self.ranking is not None and self.ranking.returned_count==0
            if not empty_rank and (not self.evidence or not self.values):
                raise ValueError("resposta numerica exige evidencias e valores")
            ids={e.evidence_id for e in self.evidence}
            if len(ids)!=len(self.evidence) or any(v.evidence_id not in ids for v in self.values):
                raise ValueError("referencia de evidencia invalida")
            if self.ranking and (len(self.values)!=self.ranking.returned_count or self.plan.operation.value!="ranking_delimitado"):
                raise ValueError("resultado de ranking incoerente")
        elif self.evidence or self.values or self.ranking:
            raise ValueError("falha nao pode publicar valores ou evidencias numericas")
        return self
