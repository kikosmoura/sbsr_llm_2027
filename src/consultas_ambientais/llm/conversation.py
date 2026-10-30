"""Pergunta -> proposta ancorada -> semantica -> executor -> template do servidor."""
import json
import time
from pathlib import Path
from uuid import uuid4
from ..contracts import ResponseStatus
from ..semantics.catalog import ClassCatalog,digest
from ..semantics.territories import TerritoryCatalog
from ..semantics.validation import validate_intent
from ..storage.derived import DerivedStore
from ..storage.dialogues import DialogueStore,SessionError
from ..queries.engine import QueryEngine
from .dialogue_models import AskAnswer,InterpretationConfig
from .prompting import PromptBundle,interpreter_digest
from .context import build_context
from .privacy import Redactor
from .grounding import policy,PolicyStop,NeedClarification
from .clarifying import clarification,apply_reply
from .interpreting import interpret

CAUTION="Mudança observada na classificação não comprova mudança real específica no terreno, causas ou ilegalidade."

class ConversationService:
    def __init__(self,root,project,run_id,territories,capabilities,client,settings,config=None,integration_kind="gateway_real"):
        self.root=Path(root);self.project=project;self.run_id=run_id;self.territory_path=Path(territories);self.capability_path=Path(capabilities)
        self.client=client;self.settings=settings;self.config=config or InterpretationConfig();self.integration_kind=integration_kind
        self.prompts=PromptBundle();self.redactor=Redactor.from_environment(settings);self.dialogues=DialogueStore(root,project)

    def ask(self,question,session_id=None,reply_to=None):
        start=time.monotonic();safe,redactions=self.redactor.clean(question if isinstance(question,str) else "")
        if redactions:safe="[Pergunta redigida: dados de acesso]"
        answer=AskAnswer(session_id=session_id if isinstance(session_id,str) and len(session_id)==32 and all(c in '0123456789abcdef' for c in session_id) else uuid4().hex,
            turn_id=uuid4().hex,question=safe[:self.config.max_question_chars],original_question=safe[:self.config.max_question_chars],
            status="erro_tecnico",reason="falha_interpretacao",message="Não foi possível interpretar a pergunta com segurança.",
            integration_kind=self.integration_kind,requested_model=self.redactor.model_name(self.settings.model),
            safe_configuration={"max_tokens":self.settings.max_tokens,"temperature":self.settings.temperature,"timeout":self.settings.timeout,
                "http_max_attempts":self.settings.max_attempts,"token_auth_mode":self.settings.token_auth_mode,"max_repairs":self.config.max_repairs,"tls_verified":True,
                "custom_ca":bool(self.settings.ca_bundle),"native_tools":False,"native_response_format":False,
                "interpretation":self.config.model_dump(mode="json"),"prompt_version":self.prompts.version},
            prompt_hashes=self.prompts.hashes,interpreter_sha256=interpreter_digest(),redactions=redactions)
        try:
            if not isinstance(question,str) or not safe.strip() or len(safe)>self.config.max_question_chars:
                answer.status="precisa_esclarecimento";answer.reason="pergunta_vazia_ou_excede_limite";answer.message="Envie uma pergunta ambiental curta em português."
                answer.latency_seconds=time.monotonic()-start
                self.dialogues.reject(answer)
                return answer
            if redactions:
                answer.status="fora_do_escopo";answer.reason="entrada_contem_dados_de_acesso";answer.message="Envie somente a pergunta ambiental, sem dados de acesso."
                answer.latency_seconds=time.monotonic()-start
                self.dialogues.reject(answer)
                return answer
            classes=ClassCatalog.load();territories=TerritoryCatalog.load(self.territory_path)
            store=DerivedStore(self.root,self.project,self.run_id,classes,territories,self.capability_path)
            answer.source_context={"run_id":self.run_id,"run_manifest_sha256":store.manifest_sha256,"class_catalog_sha256":classes.sha256,"territory_catalog_sha256":territories.sha256}
            identity={"run_id":self.run_id,"run_manifest_sha256":store.manifest_sha256,"classes":classes.sha256,
                "territories":territories.sha256,"prompts":digest(self.prompts.hashes),"protocol":"pergunta-verificavel-v1","interpreter":answer.interpreter_sha256,"configuration":digest(answer.safe_configuration),"requested_model":answer.requested_model}
            with self.dialogues.open(session_id,reply_to,identity,self.config.max_turns) as (state,path):
                answer.session_id=state["session_id"];answer.parent_turn_id=state.get("parent_turn_id")
                state["original_question"]=state["original_question"] or safe
                answer.original_question=state["original_question"]
                try:
                    policy(safe);policy(answer.original_question)
                    if reply_to:
                        state["bindings"]=apply_reply(state["pending"],safe,state["bindings"],classes,territories)
                    context=build_context(answer.original_question,state["bindings"],classes,territories,store,self.config)
                    if len(json.dumps(context,ensure_ascii=False).encode())>self.config.max_context_bytes:raise ValueError("contexto_excede_limite")
                    answer.context=context;answer.context_sha256=digest(context)
                    if self.client is None:
                        answer.reason="configuracao_llm_ausente";answer.message="Configuração LLM ausente nas variáveis exportadas; o .env não foi lido."
                    else:
                        intent,proposal,need,attempts,fallback,error=interpret(self.client,self.prompts,answer.original_question,state["bindings"],context,classes,territories,self.config,self.redactor,store.capabilities)
                        answer.attempts=attempts;answer.gateway_called=bool(attempts);answer.explanation_fallback=fallback
                        if need:raise need
                        if error:
                            answer.reason=error
                            if error=="saida_modelo_invalida_apos_limite":
                                answer.status="erro_tecnico";answer.message="O modelo não produziu um plano válido após o limite de reparo; nenhum número foi publicado."
                            else:answer.message="Falha técnica no gateway; nenhum resultado numérico foi publicado."
                        else:
                            answer.intent=intent
                            decision=validate_intent(intent,classes,territories,store.capabilities);answer.decision=decision
                            if decision.normalized_plan:
                                norm=decision.normalized_plan
                                answer.entities={"territory_codes":norm.territory_codes,"scope_uf":norm.scope_uf,"class_codes":norm.class_codes,"years":norm.years}
                            if decision.status=="precisa_esclarecimento":
                                field="territorio" if decision.territory_candidates else "classe" if decision.class_candidates else "operacao"
                                raise NeedClarification(field,decision.reason,candidates=decision.territory_candidates or decision.class_candidates)
                            if decision.status!="plano_validado":
                                answer.status=decision.status;answer.reason=decision.reason;answer.message=decision.message
                            elif proposal.action=="esclarecer":
                                field=proposal.clarification_fields[0] if proposal.clarification_fields else "operacao"
                                raise NeedClarification(field,"esclarecimento_solicitado_pelo_modelo")
                            else:
                                engine=QueryEngine(self.root,self.project,self.run_id,self.territory_path,self.capability_path)
                                result=engine.answer(decision.normalized_plan)
                                answer=AskAnswer.model_validate({**answer.model_dump(mode="json"),"query":result.model_dump(mode="json"),"status":result.status.value,
                                    "reason":result.reason,"message":result.message+("\n"+CAUTION if result.status==ResponseStatus.ANSWERED else ""),
                                    "entities":{"territory_codes":result.plan.territory_codes,"scope_uf":result.plan.scope_uf,"class_codes":result.plan.class_codes,"years":result.plan.years} if result.plan else answer.entities})
                except NeedClarification as need:
                    answer.status="precisa_esclarecimento";answer.reason=need.reason;answer.clarification=clarification(need)
                    answer.message=answer.clarification.question
                except PolicyStop as stop:
                    answer.status=stop.status;answer.reason=stop.reason;answer.message=stop.message
                answer.latency_seconds=time.monotonic()-start
                self.dialogues.commit(state,path,answer)
                return answer
        except SessionError as e:
            answer.status="precisa_esclarecimento";answer.reason=str(e);answer.message="A resposta exige uma sessão e um esclarecimento pendente correspondentes; inicie outra pergunta sem IDs para um novo contexto."
        except Exception:
            answer=AskAnswer.model_validate({**answer.model_dump(mode="json"),"status":"erro_tecnico","reason":"falha_tecnica_interpretacao", "message":"Falha técnica local; nenhum resultado numérico foi publicado.","query":None})
        finally:
            if not answer.latency_seconds:answer.latency_seconds=time.monotonic()-start
        try:self.dialogues.reject(answer)
        except OSError:pass
        return answer
