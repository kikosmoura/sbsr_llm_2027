from pathlib import Path
import json
from ..settings import DatabaseSettings
from .models import ProcessingError


def add_parsers(sub):
    p=sub.add_parser("process",help="Snapshot, piloto pequeno e processamento completo da UF configurada.")
    modes=p.add_subparsers(dest="process_action",required=True)
    snapshot=modes.add_parser("snapshot",help="OPT-IN: SELECTs PostGIS, transacao somente leitura.")
    snapshot.add_argument("--output",type=Path,default=Path("data/mesh_RN_v1.json"))
    for name in ["pilot","full"]:
        run=modes.add_parser(name,help="Poucos municipios e validacao independente." if name=="pilot" else "UF apos gate aprovado e estimativa dentro dos limites.")
        run.add_argument("--snapshot",type=Path,required=True)
        run.add_argument("--territories",type=Path,default=Path("data/territories_v1.json"))
        if name=="pilot":run.add_argument("--codes",nargs="+",required=True)


def run(args,config):
    try:
        from .snapshot import export_snapshot
        from .runner import run_processing
    except ImportError:
        raise ProcessingError("dependencias_processing_ausentes") from None
    if args.process_action=="snapshot":
        value=export_snapshot(DatabaseSettings.from_env(),config,config.processing,args.output)
        print(json.dumps({"state":"verificado","features":len(value["features"]),"mesh_sha256":value["mesh_sha256"]}))
        return 0
    m=run_processing(config,args.snapshot,args.territories,Path.cwd(),
        codes=getattr(args,"codes",None),full=args.process_action=="full")
    print(json.dumps({k:m[k] for k in ["state","run_id","territory_count","complete_municipality_universe","ranking_eligible","resources"]},ensure_ascii=False))
    return 0
