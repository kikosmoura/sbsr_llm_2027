"""Contrato comum das respostas A/B e da pontuacao; nenhum campo de raciocinio."""
from typing import Literal
from pydantic import Field, model_validator, StrictInt
from ..contracts import Contract, QueryPlan, ResponseStatus, Unit


class NumericValue(Contract):
    territory_code: str = Field(pattern=r'^(?:[0-9]{2}|[0-9]{7})$')
    years: list[StrictInt] = Field(min_length=1, max_length=2)
    value: float | None
    unit: Unit
    undefined_reason: str | None = None
    denominators_ha: list[float] = Field(default_factory=list)
    rank: StrictInt | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def undefined(self):
        if self.value is None and not self.undefined_reason:
            raise ValueError('null_exige_motivo')
        return self


class BaselineAnswer(Contract):
    status: ResponseStatus
    plan: QueryPlan | None = None
    values: list[NumericValue] = Field(default_factory=list, max_length=200)
    clarification_field: Literal['territorio', 'classe', 'metrica', 'unidade', 'periodo',
                                 'escopo', 'limite', 'ordenacao', 'operacao'] | None = None
    reason: str = Field(max_length=160, pattern=r'^[a-z][a-z0-9_]*$')

    @model_validator(mode='after')
    def coherent(self):
        if self.status == ResponseStatus.ANSWERED and (self.plan is None or not self.values):
            raise ValueError('resposta_exige_plano_e_valores')
        if self.status != ResponseStatus.ANSWERED and self.values:
            raise ValueError('recusa_nao_publica_valores')
        if self.status == ResponseStatus.CLARIFY and not self.clarification_field:
            raise ValueError('esclarecimento_exige_campo')
        return self
