import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from . import __version__
from .contracts import Check,CheckState,DiagnosticReport,QueryPlan,Answer,LandClass,Territory,RasterMetadata,ProcessingQuality
from .settings import DatabaseSettings,LLMSettings,ProjectConfig
from .storage.reports import write_report
from .semantics.catalog import CatalogError
from .processing.models import ProcessingError,AreaRecord,ProcessingConfig


def parser():
    p=argparse.ArgumentParser(prog="consultas-ambientais",description="Contratos, diagnosticos e catalogo semantico — etapas 0 a 7.")
    p.add_argument("--version",action="version",version=__version__)
    p.add_argument("--config",type=Path,help="Configuracao publica JSON; nenhum .env e carregado automaticamente.")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("config",help="Validar configuracao e exibir somente parametros publicos.")
    schema=sub.add_parser("schema",help="Exportar JSON Schema dos contratos.")
    schema.add_argument("name",choices=["plan","answer","class","territory","raster","quality","intent","decision","capabilities","class_catalog","territory_catalog","area_record","processing_config","query_answer","model_proposal","ask_answer","local_response","local_settings"])
    from .semantics.commands import add_parsers
    add_parsers(sub)
    from .processing.commands import add_parsers as add_processing
    add_processing(sub)
    from .queries.commands import add_parsers as add_queries
    add_queries(sub)
    from .llm.commands import add_parsers as add_ask
    add_ask(sub)
    from .delivery.commands import add_parsers as add_local
    add_local(sub)
    from .evaluation.commands import add_parsers as add_evaluation
    add_evaluation(sub)
    diagnostic=sub.add_parser("diagnose",help="Executar verificacoes explicitamente selecionadas.")
    diagnostic.add_argument("--database",action="store_true",help="Consultas PostGIS somente leitura.")
    diagnostic.add_argument("--rasters",action="store_true",help="Metadados e janela pequena nos anos selecionados.")
    diagnostic.add_argument("--llm",action="store_true",help="OPT-IN: uma requisicao textual pequena, sujeita a cobranca.")
    diagnostic.add_argument("--years",nargs="+",type=int,help="Subconjunto dos anos candidatos; padrao: todos.")
    diagnostic.add_argument("--output",type=Path,default=Path("reports/diagnostico.json"))
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        config=ProjectConfig.load(args.config)
        if args.command=="evaluate":
            from .evaluation.commands import run as evaluation_run
            return evaluation_run(args,config)
        if args.command=="local":
            from .delivery.commands import run as local_run
            return local_run(args,config)
        if args.command=="ask":
            from .llm.commands import run as ask_run
            return ask_run(args,config)
        if args.command=="query":
            from .queries.commands import run as query_run
            return query_run(args,config)
        if args.command=="process":
            from .processing.commands import run as process_run
            return process_run(args,config)
        if args.command=="schema":
            from .semantics.models import QueryIntent,SemanticDecision,Capabilities,ClassCatalogData,TerritoryCatalogData
            from .answers.models import QueryAnswer
            from .llm.dialogue_models import ModelProposal,AskAnswer
            from .delivery.models import LocalResponse
            from .delivery.settings import LocalSettings
            models={"plan":QueryPlan,"answer":Answer,"class":LandClass,"territory":Territory,
                    "raster":RasterMetadata,"quality":ProcessingQuality,"intent":QueryIntent,
                    "decision":SemanticDecision,"capabilities":Capabilities,
                    "class_catalog":ClassCatalogData,"territory_catalog":TerritoryCatalogData,
                    "area_record":AreaRecord,"processing_config":ProcessingConfig,"query_answer":QueryAnswer,"model_proposal":ModelProposal,"ask_answer":AskAnswer,"local_response":LocalResponse,"local_settings":LocalSettings}
            print(json.dumps(models[args.name].model_json_schema(),ensure_ascii=False,indent=2))
            return 0
        if args.command in {"catalog","territories","semantic"}:
            from .semantics.commands import run
            return run(args)
        if args.command=="config":
            db=DatabaseSettings.from_env();llm=LLMSettings.from_env()
            print(json.dumps({"project":config.model_dump(),"database_configured":db.configured,
                              "llm_configured":llm.configured,"availability":"ainda_nao_verificada"},indent=2))
            return 0
        checks=[]
        if args.database:
            from .sources.postgis import diagnose_database
            checks.append(diagnose_database(DatabaseSettings.from_env(),config.sample_size))
        else:checks.append(Check(component="postgis",state=CheckState.PENDING,outcome="nao_solicitado"))
        if args.rasters:
            from .sources.rasters import diagnose_raster,compare_pilot_grids
            years=args.years or config.candidate_years
            if len(years)!=len(set(years)) or not set(years)<=set(config.candidate_years):
                raise ValueError("anos invalidos")
            raster_checks=[]
            for year in years:
                # Biblioteca GDAL pode escrever URLs em stderr; isolamento/supressao no diagnostico real.
                raster_checks.append(diagnose_raster(config,year))
            checks.extend(raster_checks)
            checks.append(compare_pilot_grids(raster_checks,config.pilot_years))
        else:checks.append(Check(component="rasters",state=CheckState.PENDING,outcome="nao_solicitado"))
        if args.llm:
            from .llm.client import diagnose_llm
            checks.append(diagnose_llm(LLMSettings.from_env()))
        else:checks.append(Check(component="llm",state=CheckState.PENDING,outcome="nao_solicitado"))
        report=DiagnosticReport(checks=checks)
        write_report(report,args.output)
        # Caminhos e detalhes de conexao nunca sao ecoados.
        for check in checks:print(f"{check.component}: {check.state.value} — {check.outcome}")
        return 0 if all(c.state==CheckState.VERIFIED for c in checks if c.outcome!="nao_solicitado") else 2
    except (CatalogError,ProcessingError) as e:
        print(json.dumps({"status":"erro_tecnico","reason":str(e)},ensure_ascii=False))
        return 2
    except ValidationError as e:
        fields=sorted({".".join(str(x) for x in err["loc"]) or "configuracao" for err in e.errors(include_input=False)})
        if args.command in {"catalog","territories","semantic"}:
            print(json.dumps({"status":"erro_tecnico","reason":"configuracao_ou_catalogo_invalido","fields":fields},ensure_ascii=False))
            return 2
        print("Configuracao/contrato invalido; campos: "+", ".join(fields))
        return 2
    except (OSError,ValueError,json.JSONDecodeError):
        if args.command in {"catalog","territories","semantic"}:
            print(json.dumps({"status":"erro_tecnico","reason":"falha_carregamento_ou_gravacao"},ensure_ascii=False))
            return 2
        print("Falha ao ler/validar configuracao ou gravar relatorio; detalhes locais omitidos.")
        return 2
