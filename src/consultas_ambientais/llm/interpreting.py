"""JSON estrito, uma reparacao no maximo e diagnosticos sem texto bruto do modelo."""
import hashlib
import json
import time
from pydantic import ValidationError
from .client import GatewayError
from .dialogue_models import ModelProposal,ValidationIssue,Attempt
from .grounding import ground,GroundingError,NeedClarification,PolicyStop
from ..semantics.catalog import digest
from ..semantics.validation import validate_intent

KNOWN_FIELDS={"action","intent","clarification_fields","explanation","operation","territories","mention","uf_mention","kind",
    "scope_uf_mention","classes","years","metric","metric_mention","unit_mention","denominator","direction","limit"}
GATEWAY_CODES={"configuracao_llm_ausente","falha_autenticacao","token_ausente_ou_invalido","tipo_token_nao_suportado",
    "expiracao_token_invalida","falha_chat","falha_tls","timeout","falha_conexao","falha_dns","resposta_excede_limite",
    "resposta_json_invalida","texto_final_ausente","tentativas_esgotadas","mensagens_textuais_invalidas"}


def strict_json(text):
    if len(text)>20000:raise ValueError("saida_excede_limite")
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError("chave_json_duplicada")
            result[k]=v
        return result
    def constant(_):raise ValueError("constante_json_nao_finita")
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)


def issues_for(error):
    if isinstance(error,GroundingError):return error.issues
    if isinstance(error,ValidationError):
        return [ValidationIssue(path=[v if isinstance(v,int) or v in KNOWN_FIELDS else "campo_extra" for v in e["loc"]],code=e["type"])
            for e in error.errors(include_input=False)[:24]]
    return [ValidationIssue(path=[],code="json_invalido_ou_fora_do_limite")]


def interpret(client,prompts,question,bindings,context,classes,territories,config,redactor,capabilities=None):
    attempts=[];last_issues=None;fallback=None
    for number in range(config.max_repairs+1):
        messages=prompts.messages(question,context,last_issues)
        start=time.monotonic();before=getattr(client,"chat_requests",None)
        request_hash=digest(messages)
        try:response=client.chat(messages)
        except GatewayError as e:
            requests=getattr(client,"chat_requests",None)
            count=requests-before if type(requests) is int and type(before) is int else None
            code=e.code if e.code in GATEWAY_CODES else "falha_gateway"
            attempts.append(Attempt(number=number+1,kind="inicial" if number==0 else "reparo",state="falha_gateway",
                latency_seconds=time.monotonic()-start,chat_requests=count,messages_sha256=request_hash,
                gateway_error=code,http_status=e.status if type(e.status) is int else None))
            return None,None,None,attempts,fallback,code
        text=response.text
        usage={k:v for k,v in (response.usage or {}).items() if k in {"prompt_tokens","completion_tokens","total_tokens"} and type(v) is int and v>=0} if response.usage is not None else None
        attempt=Attempt(number=number+1,kind="inicial" if number==0 else "reparo",state="invalida",latency_seconds=response.elapsed_seconds,
            usage=usage,chat_requests=response.chat_requests,returned_model=redactor.model_name(response.model),
            output_sha256=hashlib.sha256(text.encode()).hexdigest(),output_chars=len(text),messages_sha256=request_hash)
        attempts.append(attempt)
        try:
            proposal=ModelProposal.model_validate(strict_json(text))
            candidate=proposal.model_dump(mode="json",exclude={"explanation"})
            safe,changes=redactor.clean(json.dumps(candidate,ensure_ascii=False))
            attempt.candidate=json.loads(safe)
            if changes:raise GroundingError("intent","saida_contem_credencial_redigida")
            if proposal.explanation:
                fallback="texto_livre_nao_verificado_substituido_pelo_template"
                attempt.explanation_fallback=fallback
            intent=ground(proposal,question,bindings,context,classes,territories)
            if capabilities is not None and proposal.action=='esclarecer':
                decision=validate_intent(intent,classes,territories,capabilities)
                if decision.status=='plano_validado':
                    raise GroundingError('action','esclarecimento_sem_campo_pendente')
            attempt.state="valida"
            return intent,proposal,None,attempts,fallback,None
        except NeedClarification as need:
            attempt.state="precisa_esclarecimento"
            return None,None,need,attempts,fallback,None
        except PolicyStop as stop:
            attempt.state="valida"
            return None,None,stop,attempts,fallback,None
        except (ValueError,ValidationError) as error:
            attempt.issues=issues_for(error)
            last_issues=[i.model_dump(mode="json") for i in attempt.issues]
    return None,None,None,attempts,fallback,"saida_modelo_invalida_apos_limite"
