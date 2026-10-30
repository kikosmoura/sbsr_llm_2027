"""CLI textual; nenhuma leitura automatica de .env, sem modo mock na producao."""
import json
from pathlib import Path
from uuid import uuid4
from .dialogue_models import InterpretationConfig,AskAnswer
from ..contracts import ResponseStatus


def add_parsers(sub):
    p=sub.add_parser("ask",help="Pergunta em portugues -> plano validado -> resultado com evidencias; usa LLM.")
    p.add_argument("--question",required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--territories",type=Path,default=Path("data/territories_v1.json"))
    p.add_argument("--capabilities",type=Path,default=Path("data/capabilities_stage3.json"))
    p.add_argument("--session-id",help="Somente para responder a esclarecimento pendente desta sessao.")
    p.add_argument("--reply-to",help="clarification_id retornado, da mesma sessao.")
    p.add_argument("--json-output",type=Path)
    p.add_argument("--csv-output",type=Path,help="Exporta os valores produzidos pelo servidor, quando houver.")
    p.add_argument("--max-output-tokens",type=int,default=None)
    p.add_argument("--no-repair",action="store_true",help="Desativar a unica tentativa de reparo.")
    p.add_argument("--format",choices=["text","json"],default="text")


def run(args,project):
    from .client import GatewayClient
    from .conversation import ConversationService
    from .prompting import PromptBundle,interpreter_digest
    from ..settings import LLMSettings
    from ..storage.dialogues import private_json,private_text
    from ..answers.models import QueryAnswer
    from ..answers.export import csv_text
    client=None;answer=None
    try:
        inputs={args.territories.resolve(),args.capabilities.resolve()}
        protected=[(Path.cwd()/project.data_dir/"processed").resolve(),(Path.cwd()/project.artifacts_dir/"processing").resolve(),(Path.cwd()/project.data_dir/"dialogues").resolve()]
        outputs=[p for p in [args.json_output,args.csv_output] if p]
        if (len({p.resolve() for p in outputs})!=len(outputs) or any(p.resolve() in inputs or any(p.resolve().is_relative_to(d) for d in protected)
            or any(part.startswith(".env") or part=="script_exemplo" for part in p.parts) for p in outputs)
            or any(p.name.startswith(".env") for p in [args.territories,args.capabilities])):raise ValueError("caminho_protegido")
        import os
        settings=LLMSettings.from_env()
        maximum=args.max_output_tokens if args.max_output_tokens is not None else settings.max_tokens if os.environ.get("LLM_MAX_TOKENS") else 768
        config=InterpretationConfig(max_output_tokens=maximum,max_repairs=0 if args.no_repair else 1)
        settings=settings.model_copy(update={"max_tokens":config.max_output_tokens})
        if settings.configured:client=GatewayClient(settings)
        service=ConversationService(Path.cwd(),project,args.run_id,args.territories,args.capabilities,client,settings,config)
        answer=service.ask(args.question,args.session_id,args.reply_to)
        if args.json_output:private_json(args.json_output,answer.model_dump(mode="json"))
        if args.csv_output:
            result=answer.query or QueryAnswer(status=answer.status,reason=answer.reason,message=answer.message)
            private_text(args.csv_output,csv_text(result))
    except Exception:
        if answer:
            answer=AskAnswer.model_validate({**answer.model_dump(mode="json"),"status":"erro_tecnico","reason":"falha_configuracao_ou_exportacao","message":"Falha ao configurar o cliente ou exportar a resposta; detalhes omitidos.","query":None})
        else:
            # Nao ecoar a pergunta antes de redigir credenciais, inclusive em erros de configuracao.
            from .privacy import Redactor
            safe="[Pergunta omitida por falha de configuração]";redactions=["entrada_omitida_no_erro"]
            answer=AskAnswer(session_id=uuid4().hex,turn_id=uuid4().hex,question=safe[:4000],original_question=safe[:4000],
                status="erro_tecnico",reason="falha_configuracao_ou_exportacao",message="Falha ao configurar a consulta; detalhes omitidos.",
                integration_kind="gateway_real",requested_model=None,safe_configuration={},prompt_hashes=PromptBundle().hashes,
                interpreter_sha256=interpreter_digest(),redactions=redactions)
    finally:
        if client:client.close()
    print(json.dumps(answer.model_dump(mode="json"),ensure_ascii=False,indent=2,allow_nan=False) if args.format=="json" else f"{answer.status.value}: {answer.message}")
    if args.format=="text":
        print("session_id: "+answer.session_id)
        if answer.clarification:
            for candidate in answer.clarification.candidates:
                name=candidate.get("name_original",candidate.get("name",""))
                suffix="/"+candidate["uf"] if candidate.get("uf") else ""
                print(f"  {candidate.get('code','')}: {name}{suffix}")
            print("reply_to: "+answer.clarification.clarification_id)
    return 0 if answer.status==ResponseStatus.ANSWERED else 2
