"""Plano de execucao e falhas de dominio; SQL e expressoes nao sao campos de entrada."""
from dataclasses import dataclass
from ..contracts import QueryPlan,ResponseStatus

TEMPORAL_METRICS={"diferenca_liquida","reducao_liquida","variacao_percentual","diferenca_pontos_percentuais"}
MAX_TERRITORIES=100
MAX_RANK_CANDIDATES=2000
MAX_PLAN_BYTES=65536

class QueryFailure(Exception):
    def __init__(self,status,reason,message):
        self.status=ResponseStatus(status);self.reason=reason;self.message=message
        super().__init__(reason)

def unavailable(reason,message="Os dados derivados necessarios nao estao disponiveis."):
    return QueryFailure("dados_indisponiveis",reason,message)

def technical(reason="artefato_derivado_inconsistente"):
    return QueryFailure("erro_tecnico",reason,"Falha tecnica ao verificar ou consultar os artefatos locais; nenhum valor foi publicado.")

def clarify(reason,message="Confira territorio, classe, anos, metrica, unidade e escopo do plano."):
    return QueryFailure("precisa_esclarecimento",reason,message)

@dataclass(frozen=True)
class ValidatedPlan:
    requested: QueryPlan
    executed: QueryPlan
    candidate_codes: tuple[str,...]
    support: str
    seal: object
