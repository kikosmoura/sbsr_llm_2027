import json
from pathlib import Path
from ..answers.models import QueryAnswer
from ..answers.export import write_outputs,json_text
from ..contracts import ResponseStatus
from .models import MAX_PLAN_BYTES


def add_parsers(sub):
    p=sub.add_parser("query",help="Executar plano JSON validado sobre Parquets locais; sem LLM/rede.")
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--run-id",required=True,help="Execucao geoespacial explicita; nunca mistura execucoes.")
    p.add_argument("--territories",type=Path,default=Path("data/territories_v1.json"))
    p.add_argument("--capabilities",type=Path,default=Path("data/capabilities_stage3.json"))
    p.add_argument("--json-output",type=Path)
    p.add_argument("--csv-output",type=Path)
    p.add_argument("--capabilities-output",type=Path,help="Opcional: exportar capacidades com executor disponivel, sem alterar o manifesto original.")
    p.add_argument("--format",choices=["text","json"],default="text")


def run(args,project):
    engine=None
    try:
        if any(p.name.startswith(".env") for p in [args.plan,args.territories,args.capabilities]):raise ValueError("arquivo_protegido")
        inputs={p.resolve() for p in [args.plan,args.territories,args.capabilities]}
        outputs=[p for p in [args.json_output,args.csv_output,args.capabilities_output] if p]
        protected=[(Path.cwd()/project.data_dir/"processed").resolve(),(Path.cwd()/project.artifacts_dir/"processing").resolve()]
        if (len({p.resolve() for p in outputs})!=len(outputs) or
            any(p.resolve() in inputs or any(p.resolve().is_relative_to(d) for d in protected)
                or any(part.startswith(".env") or part=="script_exemplo" for part in p.parts) for p in outputs)):
            raise ValueError("exportacao_sobre_entrada_ou_fonte")
        if args.plan.stat().st_size>MAX_PLAN_BYTES:
            answer=QueryAnswer(status="precisa_esclarecimento",reason="plano_excede_limite_de_bytes",message="O plano excede o limite de tamanho.")
        else:
            try:raw=json.loads(args.plan.read_text())
            except (json.JSONDecodeError,UnicodeError):raw=None
            from .engine import QueryEngine
            engine=QueryEngine(Path.cwd(),project,args.run_id,args.territories,args.capabilities)
            answer=engine.answer(raw)
        write_outputs(answer,args.json_output,args.csv_output,Path(project.artifacts_dir)/"queries")
        if args.capabilities_output and engine and engine.store:
            from ..processing.common import atomic_json
            atomic_json(args.capabilities_output,engine.store.capabilities.model_dump(mode="json"))
    except Exception:
        answer=QueryAnswer(status="erro_tecnico",reason="falha_de_entrada_ou_exportacao",message="Nao foi possivel ler o plano ou exportar a consulta; detalhes locais omitidos.")
    print(json_text(answer) if args.format=="json" else f"{answer.status.value}: {answer.message}",end="" if args.format=="json" else "\n")
    return 0 if answer.status==ResponseStatus.ANSWERED else 2
