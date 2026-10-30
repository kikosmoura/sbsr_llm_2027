"""Orquestracao local, gate de piloto, retomada e manifests auditaveis."""
import fcntl
import importlib.metadata
import json
import platform
import traceback
from contextlib import ExitStack
from pathlib import Path
import numpy as np
import rasterio
from shapely.geometry import shape
from ..semantics.catalog import ClassCatalog,digest
from ..semantics.territories import TerritoryCatalog
from ..semantics.capabilities import load_capabilities
from ..semantics.models import Materialization
from ..storage.areas import AreaStore
from .models import METHOD,ProcessingError
from .common import atomic_json,sha_file,now
from .snapshot import load_snapshot
from .raster_io import stage_pair,Budget
from .engine import compute_feature
from .validation import validate_real


def software():
    import pyproj
    import shapely
    modules=Path(__file__).parents[1]
    files=sorted(list((modules/"processing").glob("*.py"))+[modules/"storage/areas.py"])
    return {"python":platform.python_version(),"dependencies":{n:importlib.metadata.version(n) for n in
        ["numpy","rasterio","shapely","pyproj","duckdb","psutil","psycopg2-binary"]},
        "implementation_sha256":digest({str(f.relative_to(modules)):sha_file(f) for f in files}),
        "gdal":rasterio.__gdal_version__,"proj":pyproj.proj_version_str,"geos":shapely.geos_version_string}


def select_features(snapshot,codes,full):
    if full:return snapshot["features"]
    if not codes:raise ProcessingError("piloto_exige_codigos_de_municipios_explicitos")
    if len(codes)!=len(set(codes)) or not 1<=len(codes)<=5:raise ProcessingError("piloto_limitado_a_cinco_municipios")
    selected=[f for f in snapshot["features"] if f["code"] in codes and f["kind"]=="municipio"]
    if {f["code"] for f in selected}!=set(codes):raise ProcessingError("municipio_fora_da_uf_ou_ausente")
    return selected


def validate_lineage(snapshot,territories):
    expected=set(territories.municipality_universe(snapshot["uf"]))
    present={f["code"] for f in snapshot["features"] if f["kind"]=="municipio"}
    if expected!=present:raise ProcessingError("catalogo_territorial_e_snapshot_divergem")
    for f in snapshot["features"]:
        entry=territories.by_code.get(f["code"])
        if entry is None or entry.name_original!=f["name_original"] or entry.uf!=f["uf"]:
            raise ProcessingError("atributos_territoriais_divergentes")
        if not f["repair"]["accepted"]:raise ProcessingError("snapshot_contem_reparo_pendente")


def run_processing(project,snapshot_path,territory_path,root,codes=None,full=False):
    root=Path(root);config=project.processing;budget=Budget(config)
    output=root/project.artifacts_dir/"processing";output.mkdir(parents=True,exist_ok=True)
    with (output/".lock").open("a") as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ProcessingError("outro_processamento_local_em_andamento") from None
        snapshot=load_snapshot(snapshot_path);territories=TerritoryCatalog.load(Path(territory_path));classes=ClassCatalog.load()
        if snapshot["uf"]!=project.pilot_uf:raise ProcessingError("uf_snapshot_diverge_da_configuracao")
        validate_lineage(snapshot,territories)
        features=select_features(snapshot,codes,full);versions=software()
        base={"mesh_sha256":snapshot["mesh_sha256"],"catalog_sha256":classes.sha256,
            "method":METHOD,"years":project.pilot_years,"software":versions,"config":project.model_dump(mode="json")}
        gate_path=output/"pilot_gate.json";gate=None
        if full:
            if not gate_path.exists():raise ProcessingError("piloto_validado_obrigatorio_antes_da_uf")
            gate=json.loads(gate_path.read_text())
            if gate["identity"]!=base or not gate.get("passed"):
                raise ProcessingError("gate_piloto_incompativel_ou_reprovado")
            if sha_file(output/gate["run_id"]/"manifest.json")!=gate["run_manifest_sha256"]:
                raise ProcessingError("manifest_piloto_alterado")
            # Extrapolacao conservadora pelo retangulo da UF e tempo de processamento medido.
            u=next(f for f in features if f["kind"]=="uf");ub=shape(u["geometry"]).bounds
            extent_area=(ub[2]-ub[0])*(ub[3]-ub[1])
            ratio=extent_area/gate["crop_bounds_area_degrees2"]
            estimate={"download_bytes":gate["staging_download_bytes"]*ratio*1.5,
                "elapsed_seconds":gate["elapsed_seconds"]*ratio*2}
            if estimate["download_bytes"]>config.max_download_bytes or estimate["elapsed_seconds"]>config.max_seconds:
                raise ProcessingError("estimativa_uf_excede_limites_configurados")
        try:
            staging,paths,budget=stage_pair(project,config,snapshot,features,root,budget)
            if gate and staging["identity"]["sources"]!=gate["source_identities"]:
                raise ProcessingError("fontes_mudaram_desde_o_piloto")
            identity={**base,"staging_id":staging["staging_id"],"territory_codes":sorted(f["code"] for f in features)}
            run_id=digest(identity);run_directory=output/run_id;run_directory.mkdir(parents=True,exist_ok=True)
            atomic_json(run_directory/"progress.json",{"state":"em_processamento","started_at":now(),"identity":identity})
            manifests=[];validation=None
            with ExitStack() as stack:
                stack.enter_context(rasterio.Env(GDAL_CACHEMAX=config.gdal_cache_mb*1048576,GDAL_PAM_ENABLED="NO"))
                datasets=[stack.enter_context(rasterio.open(path)) for path in paths]
                if not full:
                    validation=validate_real(features,datasets,project.pilot_years,classes.expand(list(classes.by_code)),config)
                    atomic_json(run_directory/"independent_validation.json",validation)
                store=AreaStore(root/project.data_dir/"processed",config);stack.callback(store.close)
                context={"run_id":run_id,"mesh_sha256":snapshot["mesh_sha256"],
                    "territorial_edition":snapshot["territorial_edition"],"source_revision":project.source_revision,
                    "source_fingerprint":staging["staging_id"],"catalog_sha256":classes.sha256}
                for feature in features:
                    budget.check();part=store.complete(run_id,feature["code"])
                    if part is None:
                        records,quality,resources=compute_feature(feature,datasets,project.pilot_years,
                            classes.expand(list(classes.by_code)),context,config,budget)
                        part=store.commit(run_id,feature["code"],records,quality,resources)
                    budget.check()
                    manifests.append(part)
                    atomic_json(run_directory/"progress.json",{"state":"em_processamento","run_id":run_id,
                        "completed_codes":[m["territory_code"] for m in manifests],"total_units":len(features),"resources":budget.report()})
            codes_done={m["territory_code"] for m in manifests}
            expected={f["code"] for f in snapshot["features"] if f["kind"]=="municipio"}
            full_universe=expected<=codes_done
            eligible=full_universe and all(q["eligible_complete"] for m in manifests if m["territory_code"] in expected for q in m["quality"])
            manifest={"schema_version":"execucao-geoespacial-v1","state":"verificado","completed_at":now(),
                "run_id":run_id,"identity":identity,"mode":"uf_piloto_completa" if full else "poucos_municipios",
                "resources":budget.report(),"staging_resources":staging["resources"],
                "estimated_before_full":estimate if full else None,
                "staging_manifest_sha256":sha_file(paths[0].parent/"manifest.json"),"sources":staging["identity"]["sources"],
                "input_crop_hashes":[f["sha256"] for f in staging["files"]],
                "territory_count":len(manifests),"expected_municipalities":len(expected),
                "complete_municipality_universe":full_universe,"ranking_eligible":eligible,
                "ranking_produced":False,"uf_provenance":"uf_direta" if full else None,
                "partitions":[{"territory_code":m["territory_code"],"files":m["files"],"resources":m["resources"]} for m in manifests],
                "quality_summary":[q for m in manifests for q in m["quality"]],
                "observed_unknown_codes":sorted({c for m in manifests for q in m["quality"] for c in q["unknown_codes_m2"]}),
                "independent_validation":validation if validation else {"state":"verificado","from_pilot_run":gate["run_id"]},
                "limitations":["edicao_territorial_desconhecida" if snapshot["territorial_edition"] is None else "edicao_informada",
                    "revisao_oficial_do_espelho_nao_comprovada","nao_comparado_a_estatistica_oficial",
                    "engine_de_consultas_etapa_4_nao_implementado"]}
            atomic_json(run_directory/"manifest.json",manifest)
            atomic_json(run_directory/"progress.json",{"state":"completo","run_id":run_id,"resources":budget.report()})
            if not full:
                bounds=staging["identity"]["window"];grid=staging["identity"]["grid"][0]["transform"]
                crop_degree_area=bounds[2]*grid[0]*bounds[3]*(-grid[4])
                gate={"passed":all(q["eligible_complete"] for m in manifests for q in m["quality"]),
                    "identity":base,"run_id":run_id,"run_manifest_sha256":sha_file(run_directory/"manifest.json"),
                    "source_identities":staging["identity"]["sources"],"crop_bounds_area_degrees2":crop_degree_area,
                    "staging_download_bytes":staging["resources"]["download_bytes"],"elapsed_seconds":budget.report()["elapsed_seconds"]}
                atomic_json(gate_path,gate)
            update_capabilities(root/project.data_dir,classes,territories,manifests)
            return manifest
        except Exception as e:
            reason=str(e) if isinstance(e,ProcessingError) else getattr(e,"code","falha_tecnica_processamento")
            if "run_directory" in locals():
                atomic_json(run_directory/"progress.json",{"state":"erro_tecnico","reason":reason,"resources":budget.report()})
            atomic_json(output/"last_failure.json",{"state":"indisponivel","checked_at":now(),"reason":reason,
                "resources":budget.report(),"mode":"uf" if full else "piloto","source_secrets_omitted":True,"error_type":type(e).__name__,
                "frames":[{"module":Path(f.filename).name,"line":f.lineno,"function":f.name} for f in traceback.extract_tb(e.__traceback__)]})
            if isinstance(e,ProcessingError):raise
            raise ProcessingError(reason) from None


def update_capabilities(data_root,classes,territories,manifests):
    path=Path(data_root)/"capabilities_stage2.json"
    if not path.exists():return
    caps=load_capabilities(path)
    if caps.class_catalog_sha256!=classes.sha256 or caps.territory_catalog_sha256!=territories.sha256:
        raise ProcessingError("capacidades_com_linhagem_divergente")
    replacements=[];leaves=classes.expand(list(classes.by_code))
    for m in manifests:
        for support in ["anual","comum"]:
            rows=[q for q in m["quality"] if q["support"]==support]
            if support=="anual":groups=[[q] for q in rows]
            else:groups=[rows]
            for group in groups:
                replacements.append(Materialization(territory_code=m["territory_code"],years=sorted(q["year"] for q in group),
                    class_codes=leaves,complete=all(q["eligible_complete"] for q in group),
                    common_support_id=group[0]["common_support_id"],run_id=m["run_id"]))
    caps.materializations=replacements;caps.engine_ready=False
    atomic_json(Path(data_root)/"capabilities_stage3.json",caps.model_dump(mode="json"))
