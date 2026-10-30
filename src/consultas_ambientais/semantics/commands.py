"""Comandos da etapa 2; chamadas de rede e banco somente em subcomandos explicitos."""
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests
from pydantic import ValidationError

from ..settings import DatabaseSettings
from .capabilities import from_diagnostic, load_capabilities
from .catalog import CatalogError, ClassCatalog, build_catalog
from .models import TerritoryReference, Resolution
from .territories import TerritoryCatalog
from .validation import validate_intent


SOURCES = {
    "legend.pdf":"https://brasil.mapbiomas.org/wp-content/uploads/sites/3/2026/08/CodigosDeLegenda_LegendCodes_MapBiomas_Brazil_Collection11_PDF.pdf",
    "legend.csv":"https://brasil.mapbiomas.org/wp-content/uploads/sites/3/2026/08/legend_code_mapbiomas_brazil_collection_11.csv",
    "official_page.html":"https://brasil.mapbiomas.org/iniciativas-e-produtos/cobertura-e-uso-da-terra/cobertura-30m/cobertura/",
}


def fetch_sources(output_dir:Path):
    if output_dir.exists() and any(output_dir.iterdir()):
        raise CatalogError("diretorio_fontes_nao_vazio")
    converter=shutil.which("pdftotext")
    if not converter:raise CatalogError("pdftotext_indisponivel")
    output_dir.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for name,url in SOURCES.items():
        try:
            with requests.get(url,stream=True,timeout=20) as response:
                response.raise_for_status();chunks=[];size=0
                for chunk in response.iter_content(8192):
                    size+=len(chunk)
                    if size>2097152:raise CatalogError("fonte_excede_2mb")
                    chunks.append(chunk)
                raw=b"".join(chunks)
                if name=="legend.pdf" and not raw.startswith(b"%PDF-"):
                    raise CatalogError("fonte_pdf_invalida")
                if name=="legend.csv" and b"class_id,class_name_pt_br" not in raw[:100]:
                    raise CatalogError("fonte_csv_invalida")
                (output_dir/name).write_bytes(raw)
                manifest.append({"source_id":name,"url":url,"sha256":hashlib.sha256(raw).hexdigest(),
                    "bytes":len(raw),"retrieved_at":datetime.now(timezone.utc).isoformat(),
                    "content_type":response.headers.get("Content-Type"),"last_modified":response.headers.get("Last-Modified"),
                    "status":"obtido"})
        except requests.RequestException:
            raise CatalogError("fonte_oficial_indisponivel") from None
    try:
        subprocess.run([converter,"-layout",str(output_dir/"legend.pdf"),str(output_dir/"legend.txt")],
                       check=True,capture_output=True,timeout=20)
    except (subprocess.SubprocessError,OSError):
        raise CatalogError("falha_extracao_pdf") from None
    (output_dir/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    return {"status":"fontes_obtidas","sources":[{"source_id":s["source_id"],"sha256":s["sha256"],"bytes":s["bytes"]} for s in manifest]}


def add_parsers(sub):
    catalog=sub.add_parser("catalog",help="Legenda oficial versionada e resolucao de classes.")
    commands=catalog.add_subparsers(dest="catalog_command",required=True)
    fetch=commands.add_parser("fetch",help="OPT-IN: obter fontes oficiais pequenas e extrair PDF.")
    fetch.add_argument("--output-dir",type=Path,required=True)
    build=commands.add_parser("build",help="Conferir fontes locais e construir catalogo.")
    build.add_argument("--sources-dir",type=Path,required=True);build.add_argument("--output",type=Path,required=True)
    inspect=commands.add_parser("inspect",help="Resumo de classes, grupos e versao.")
    inspect.add_argument("--catalog",type=Path)
    resolve=commands.add_parser("resolve",help="Resolver termo ou codigo de classe.")
    resolve.add_argument("--term");resolve.add_argument("--code",type=int);resolve.add_argument("--catalog",type=Path)
    expand=commands.add_parser("expand",help="Uniao de folhas sem dupla contagem.")
    expand.add_argument("codes",type=int,nargs="+");expand.add_argument("--catalog",type=Path)
    audit=commands.add_parser("audit-codes",help="Diagnosticar codigos observados em amostra.")
    audit.add_argument("codes",type=int,nargs="+");audit.add_argument("--declared-nodata",type=int);audit.add_argument("--catalog",type=Path)
    territories=sub.add_parser("territories",help="Snapshot de atributos e resolucao territorial.")
    tsub=territories.add_subparsers(dest="territories_command",required=True)
    export=tsub.add_parser("export",help="OPT-IN: importar atributos PostGIS em transacao somente leitura.")
    export.add_argument("--output",type=Path,required=True)
    resolve=tsub.add_parser("resolve")
    resolve.add_argument("--catalog",type=Path,required=True)
    resolve.add_argument("--name");resolve.add_argument("--code");resolve.add_argument("--uf")
    resolve.add_argument("--kind",choices=["municipio","uf"])
    semantic=sub.add_parser("semantic",help="Capacidades e validacao deterministica de planos.")
    ssub=semantic.add_subparsers(dest="semantic_command",required=True)
    capabilities=ssub.add_parser("capabilities",help="Separar fontes verificadas de estatisticas materializadas.")
    capabilities.add_argument("--diagnostic",type=Path,required=True)
    capabilities.add_argument("--territories",type=Path,required=True)
    capabilities.add_argument("--classes",type=Path)
    capabilities.add_argument("--output",type=Path,required=True)
    validate=ssub.add_parser("validate")
    validate.add_argument("--intent",type=Path,required=True)
    validate.add_argument("--territories",type=Path,required=True)
    validate.add_argument("--classes",type=Path)
    validate.add_argument("--capabilities",type=Path,required=True)
    validate.add_argument("--output",type=Path)


def save_json(value,path):
    if hasattr(value,"model_dump"):value=value.model_dump(mode="json")
    text=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
    if path:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text)
    return text


def run(args):
    code=0;output=None
    if args.command=="catalog":
        command=args.catalog_command
        if command=="fetch":value=fetch_sources(args.output_dir)
        elif command=="build":
            value=build_catalog(args.sources_dir);ClassCatalog(value)
            save_json(value,args.output)
            value={"status":"catalogo_construido","sha256":ClassCatalog(value).sha256}
        else:
            classes=ClassCatalog.load(args.catalog)
            if command=="inspect":
                value={"schema_version":classes.data.schema_version,"sha256":classes.sha256,
                    "collection":11,"node_count":len(classes.by_code),
                    "leaf_count":sum(c.kind=="classe_folha" for c in classes.data.classes),
                    "initial_leaf_codes":classes.data.initial_leaf_codes,"discrepancies":classes.data.discrepancies}
            elif command=="resolve":
                value=classes.resolve(args.term,args.code)
                code=0 if value.status=="resolvido" else 2
            elif command=="expand":value={"requested_codes":args.codes,"leaf_codes":classes.expand(args.codes),"catalog_sha256":classes.sha256}
            else:
                value=classes.audit_codes(args.codes,args.declared_nodata)
                code=2 if value["unknown_codes"] or value["group_codes_observed"] else 0
    elif args.command=="territories":
        if args.territories_command=="export":
            from ..sources.territories import export_territory_catalog
            value=export_territory_catalog(DatabaseSettings.from_env())
            save_json(value,args.output)
            value={"status":"atributos_importados","entries":len(value.entries),"sha256":value.content_sha256,
                   "edition":value.edition,"read_only_confirmed":value.read_only_confirmed}
        else:
            territories=TerritoryCatalog.load(args.catalog)
            try:
                reference=TerritoryReference(name=args.name,code=args.code,uf=args.uf,kind=args.kind)
            except ValidationError:
                value=Resolution(status="precisa_esclarecimento",reason="seletor_territorial_invalido")
            else:
                value=territories.resolve(reference)
            code=0 if value.status=="resolvido" else 2
    else:
        classes=ClassCatalog.load(args.classes);territories=TerritoryCatalog.load(args.territories)
        if args.semantic_command=="capabilities":
            value=from_diagnostic(args.diagnostic,classes,territories)
            save_json(value,args.output)
            value={"status":"capacidades_registradas","available_raster_years":value.available_raster_years,
                   "materialization_count":len(value.materializations),"engine_ready":value.engine_ready}
        else:
            value=validate_intent(json.loads(args.intent.read_text()),classes,territories,load_capabilities(args.capabilities))
            output=args.output
            code=0 if value.status=="plano_validado" else 2
    print(save_json(value,output),end="")
    return code
