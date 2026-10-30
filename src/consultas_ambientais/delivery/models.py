from datetime import datetime, timezone
from typing import Annotated, Literal
from pydantic import Field, StrictStr, model_validator
from ..contracts import Contract, ResponseStatus
from ..answers.models import QueryAnswer
from ..llm.dialogue_models import Clarification

UUID = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
HASH = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Question = Annotated[StrictStr, Field(min_length=1, max_length=4000)]


class QuestionRequest(Contract):
    question: Question


class ClarificationRequest(Contract):
    clarification_id: UUID
    reply: Question


class SessionCreated(Contract):
    session_id: UUID
    session_token: str = Field(repr=False)
    expires_at: datetime


class LocalResponse(Contract):
    schema_version: Literal['resposta-local-v1'] = 'resposta-local-v1'
    session_id: UUID
    result_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: ResponseStatus
    reason: str
    message: str
    data_kind: Literal['real', 'synthetic']
    result: QueryAnswer | None = None
    clarification: Clarification | None = None
    source_context: dict = Field(default_factory=dict)
    trace: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


    @model_validator(mode='after')
    def evidence_required(self):
        if self.status==ResponseStatus.ANSWERED and (not self.result or self.result.status!=ResponseStatus.ANSWERED):
            raise ValueError('resultado_local_exige_evidencias')
        if self.status!=ResponseStatus.ANSWERED and self.result and self.result.values:
            raise ValueError('falha_local_nao_publica_numeros')
        return self


class ErrorResponse(Contract):
    status: ResponseStatus = ResponseStatus.ERROR
    reason: str
    message: str


class DeliveryError(Exception):
    def __init__(self, reason, http_status=503, status='erro_tecnico'):
        self.reason = reason
        self.http_status = http_status
        self.status = status
        super().__init__(reason)


def error_payload(reason, status='erro_tecnico'):
    return {'status': status, 'reason': reason,
            'message': 'A operação local não foi concluída; nenhum resultado numérico foi publicado.'}
