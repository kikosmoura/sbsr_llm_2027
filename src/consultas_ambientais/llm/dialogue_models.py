"""Contrato textual conservador; superficie citada nao equivale a entidade resolvida."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import Field,StrictInt,model_validator
from ..contracts import Contract,Metric,Operation,ResponseStatus
from ..semantics.models import SemanticDecision,QueryIntent
from ..answers.models import QueryAnswer

FieldName=Literal["territorio","classe","metrica","unidade","periodo","escopo","limite","ordenacao","operacao"]

class TerritoryMention(Contract):
    mention: str = Field(min_length=1,max_length=120)
    uf_mention: str | None = Field(default=None,max_length=80)
    kind: Literal["municipio","uf"] | None = None

class ClassMention(Contract):
    mention: str = Field(min_length=1,max_length=120)

class CandidateIntent(Contract):
    operation: Operation | None = None
    territories: list[TerritoryMention] = Field(default_factory=list,max_length=10)
    scope_uf_mention: str | None = Field(default=None,max_length=80)
    classes: list[ClassMention] = Field(default_factory=list,max_length=10)
    years: list[StrictInt] = Field(default_factory=list,max_length=11)
    metric: Metric | None = None
    metric_mention: str | None = Field(default=None,max_length=120)
    unit_mention: str | None = Field(default=None,max_length=80)
    denominator: Literal["area_observada","area_inicial","participacao_por_ano"] | None = None
    direction: Literal["asc","desc"] | None = None
    limit: StrictInt | None = Field(default=None,ge=1,le=100)

class ModelProposal(Contract):
    action: Literal["consultar","esclarecer"]
    intent: CandidateIntent
    clarification_fields: list[FieldName] = Field(default_factory=list,max_length=3)
    # Campo defensivo: nunca publicado, mesmo quando o restante do objeto e valido.
    explanation: str | None = Field(default=None,max_length=2000)

class InterpretationConfig(Contract):
    max_repairs: StrictInt = Field(default=1,ge=0,le=1)
    max_output_tokens: StrictInt = Field(default=768,ge=256,le=2048)
    max_question_chars: StrictInt = Field(default=4000,ge=200,le=8000)
    max_candidates: StrictInt = Field(default=40,ge=5,le=60)
    max_context_bytes: StrictInt = Field(default=65536,ge=16384,le=131072)
    max_turns: StrictInt = Field(default=10,ge=1,le=20)

class ValidationIssue(Contract):
    path: list[str | int]
    code: str

class Attempt(Contract):
    number: StrictInt
    kind: Literal["inicial","reparo"]
    state: Literal["valida","precisa_esclarecimento","invalida","falha_gateway"]
    latency_seconds: float = Field(ge=0)
    usage: dict[str,int] | None = None
    chat_requests: int | None = None
    returned_model: str | None = None
    output_sha256: str | None = None
    output_chars: int | None = None
    candidate: dict | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    gateway_error: str | None = None
    http_status: int | None = None
    messages_sha256: str
    explanation_fallback: str | None = None

class Clarification(Contract):
    clarification_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    field: FieldName
    reason: str
    question: str
    mention: str | None = None
    candidates: list[dict] = Field(default_factory=list)

class AskAnswer(Contract):
    schema_version: Literal["pergunta-verificavel-v1"] = "pergunta-verificavel-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    turn_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    parent_turn_id: str | None = None
    question: str
    original_question: str
    status: ResponseStatus
    reason: str
    message: str
    integration_kind: Literal["gateway_real","mock_contrato"]
    gateway_called: bool = False
    requested_model: str | None
    safe_configuration: dict
    prompt_hashes: dict[str,str]
    interpreter_sha256: str
    context_sha256: str | None = None
    context: dict | None = None
    attempts: list[Attempt] = Field(default_factory=list)
    intent: QueryIntent | None = None
    decision: SemanticDecision | None = None
    query: QueryAnswer | None = None
    clarification: Clarification | None = None
    source_context: dict = Field(default_factory=dict)
    entities: dict = Field(default_factory=dict)
    explanation_fallback: str | None = None
    latency_seconds: float = Field(default=0,ge=0)
    redactions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def proven(self):
        if self.status==ResponseStatus.ANSWERED and (not self.query or self.query.status!=ResponseStatus.ANSWERED):
            raise ValueError("pergunta respondida exige resultado deterministico")
        if self.status!=ResponseStatus.ANSWERED and self.query and self.query.values:
            raise ValueError("falha nao publica valores")
        if len(self.attempts)>2:raise ValueError("limite de uma tentativa de reparo")
        return self
