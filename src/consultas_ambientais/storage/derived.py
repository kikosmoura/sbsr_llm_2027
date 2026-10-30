"""Leitura de Parquets autoritativos, com hashes e linhagem; indice global nao e confiado.

DuckDB usa somente memoria e SQL interno. O arquivo areas.duckdb da etapa 3,
os Parquets, manifests e capacidades de origem nunca sao alterados.
"""
import hashlib
import json
import math
import re
from pathlib import Path
import duckdb
from ..contracts import QueryPlan
from ..processing.models import AreaRecord
from ..semantics.catalog import digest
from ..semantics.capabilities import load_capabilities
from ..queries.models import technical,unavailable

SHA=re.compile(r"^[0-9a-f]{64}$")


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""):h.update(chunk)
    return h.hexdigest()


def read_json(path,limit=16777216):
    if Path(path).stat().st_size>limit:raise technical("manifest_excede_limite")
    return json.loads(Path(path).read_text())


def finite(value):
    if type(value) not in {int,float} or not math.isfinite(value) or value<0:raise technical("area_derivada_invalida")
    return float(value)


def check_quality(q):
    for name in ["total_area_m2","inside_raster_area_m2","outside_raster_area_m2","observed_area_m2","nodata_area_m2","unknown_area_m2",
                 "conservation_error_m2","conservation_tolerance_m2"]:finite(q[name])
    tolerance=q["conservation_tolerance_m2"]
    # Limite do metodo da etapa 3; o arquivo nao pode ampliar arbitrariamente a tolerancia.
    expected_tolerance=.01+1e-9*q["total_area_m2"]
    if not math.isclose(tolerance,expected_tolerance,rel_tol=1e-12,abs_tol=1e-12):raise technical("tolerancia_do_artefato_incoerente")
    if (abs(q["inside_raster_area_m2"]+q["outside_raster_area_m2"]-q["total_area_m2"])>tolerance or
        abs(q["observed_area_m2"]+q["nodata_area_m2"]+q["unknown_area_m2"]-q["inside_raster_area_m2"])>tolerance or
        q["conservation_error_m2"]>tolerance or q["processing_status"]!="completo"):
        raise technical("particao_de_qualidade_incoerente")
    complete=(q["observed_area_m2"]>0 and q["nodata_area_m2"]+q["unknown_area_m2"]+q["outside_raster_area_m2"]<=tolerance)
    if type(q["eligible_complete"]) is not bool or q["eligible_complete"]!=complete or q["quality_status"]!=("completo" if complete else "parcial"):
        raise technical("elegibilidade_incoerente")
    unknown=q["unknown_codes_m2"]
    if not isinstance(unknown,dict):raise technical("diagnostico_de_codigos_invalido")
    for area in unknown.values():finite(area)
    return complete


class DerivedStore:
    def __init__(self,root,project,run_id,classes,territories,capabilities_path):
        self.root=Path(root).resolve();self.project=project;self.run_id=run_id
        if not SHA.fullmatch(run_id):raise technical("identificador_de_execucao_invalido")
        self.path=self.root/project.artifacts_dir/"processing"/run_id/"manifest.json"
        if not self.path.exists():raise unavailable("execucao_nao_disponivel")
        self.manifest=read_json(self.path);self.manifest_sha256=file_sha(self.path)
        m=self.manifest;identity=m["identity"]
        if (m["schema_version"]!="execucao-geoespacial-v1" or m["state"]!="verificado" or
            m["run_id"]!=run_id or digest(identity)!=run_id):raise technical("identidade_da_execucao_invalida")
        if identity["catalog_sha256"]!=classes.sha256:raise technical("catalogo_da_execucao_divergente")
        self.identity=identity;self.classes=classes
        self.leaves=classes.expand(list(classes.by_code));self.parts={}
        for part in m["partitions"]:
            code=part["territory_code"]
            if not re.fullmatch(r"(?:[0-9]{2}|[0-9]{7})",code) or code in self.parts:raise technical("particao_territorial_invalida")
            if code not in territories.by_code:raise technical("territorio_fora_do_catalogo")
            self.parts[code]=part
        if sorted(self.parts)!=identity["territory_codes"] or m["territory_count"]!=len(self.parts):raise technical("universo_da_execucao_incoerente")
        self.quality={}
        for q in m["quality_summary"]:
            key=(q["territory_code"],q["support"],q["year"])
            if key in self.quality or q["territory_code"] not in self.parts or q["run_id"]!=run_id:raise technical("qualidade_duplicada_ou_fora_da_execucao")
            check_quality(q);self.quality[key]=q
        caps=load_capabilities(Path(capabilities_path))
        if caps.class_catalog_sha256!=classes.sha256 or caps.territory_catalog_sha256!=territories.sha256:
            raise technical("capacidades_e_catalogos_divergentes")
        self.capabilities=caps.model_copy(deep=True)
        self.capabilities.engine_ready=True
        self.capabilities.materializations=[r for r in caps.materializations if r.run_id==run_id]
        # O manifesto upstream e apenas um indice; conferir seus compromissos contra a execucao escolhida.
        for record in self.capabilities.materializations:
            support="comum" if len(record.years)==2 else "anual"
            rows=[self.quality.get((record.territory_code,support,y)) for y in record.years]
            if not all(rows):raise technical("capacidade_sem_qualidade_materializada")
            if record.complete!=all(check_quality(q) for q in rows):raise technical("capacidade_e_qualidade_divergem")
            if set(record.class_codes)!=set(self.leaves):raise technical("classes_materializadas_incoerentes")
            if support=="comum" and any(q["common_support_id"]!=record.common_support_id for q in rows):
                raise technical("capacidade_com_suporte_comum_divergente")
        self.base=self.root/project.data_dir/"processed"/run_id

    def _partition(self,code):
        part=self.parts.get(code)
        if part is None:raise unavailable("territorio_nao_materializado")
        directory=self.base/code
        if not directory.resolve().is_relative_to(self.base.resolve()):raise technical("caminho_derivado_fora_do_escopo")
        value=read_json(directory/"manifest.json")
        if value["run_id"]!=self.run_id or value["territory_code"]!=code or value["status"]!="completo" or value["files"]!=part["files"]:
            raise technical("manifest_de_particao_divergente")
        files={}
        for f in part["files"]:
            name=f["name"]
            if name not in {"areas.parquet","quality.parquet"} or name in files or not SHA.fullmatch(f["sha256"]):raise technical("arquivo_de_particao_invalido")
            path=directory/name
            if not path.resolve().is_relative_to(self.base.resolve()) or path.stat().st_size>67108864 or file_sha(path)!=f["sha256"]:
                raise technical("hash_da_particao_divergente")
            files[name]=path
        if len(files)!=2:raise technical("particao_sem_areas_ou_qualidade")
        return files

    def read(self,validated):
        codes=list(validated.candidate_codes);plan=validated.executed
        files=[self._partition(code) for code in codes]
        if file_sha(self.path)!=self.manifest_sha256:raise technical("manifest_alterado_durante_consulta")
        with duckdb.connect(":memory:") as c:
            c.execute("SET threads=1");c.execute("SET memory_limit='256MB'")
            c.execute("SET allowed_directories=?",[[str(self.base.resolve())]])
            c.execute("SET enable_external_access=false")
            # Nenhuma parcela de SQL, identificador, ordenacao ou expressao vem do plano.
            parameters=[codes,validated.support,plan.years]
            sql="SELECT * FROM read_parquet(?) WHERE territory_code IN (SELECT unnest(?)) AND support=? AND year IN (SELECT unnest(?)) ORDER BY territory_code,year"
            def fetch(name):
                cursor=c.execute(sql,[[str(f[name]) for f in files],*parameters])
                names=[d[0] for d in cursor.description]
                return [dict(zip(names,r)) for r in cursor.fetchall()]
            raw=fetch("areas.parquet");quality=fetch("quality.parquet")
        if len(raw)>150000:raise technical("resultado_intermediario_excede_limite")
        qs={}
        for q in quality:
            q["unknown_codes_m2"]=json.loads(q["unknown_codes_m2"])
            key=(q["territory_code"],q["support"],q["year"])
            if key in qs or q!=self.quality.get(key):raise technical("qualidade_parquet_diverge_do_manifest")
            if not check_quality(q):raise unavailable("cobertura_derivada_parcial")
            qs[key]=q
        grouped={}
        for raw_row in raw:
            row=AreaRecord.model_validate(raw_row)
            config=self.identity["config"]
            if (row.run_id!=self.run_id or row.mesh_sha256!=self.identity["mesh_sha256"] or row.catalog_sha256!=self.classes.sha256 or
                row.method!=self.identity["method"] or row.collection!=config["collection"] or row.source_revision!=config["source_revision"] or
                row.source_fingerprint!=self.identity["staging_id"] or row.territorial_edition!=config["territorial_edition"]):
                raise technical("linhagem_das_areas_divergente")
            key=(row.territory_code,row.year);grouped.setdefault(key,{})
            if row.class_code in grouped[key]:raise technical("classe_materializada_duplicada")
            if (row.support!=validated.support or row.class_code not in self.leaves or row.area_m2 is None or
                row.value_status not in {"observado","zero_real"} or (row.area_m2==0)!=(row.value_status=="zero_real")):
                raise technical("valor_materializado_incoerente")
            grouped[key][row.class_code]=row
        result={}
        for code in codes:
            geometries=set();common_ids=set();common_supports=set();observations=[]
            for year in plan.years:
                rows=grouped.get((code,year),{});q=qs.get((code,validated.support,year))
                if q is None or set(rows)!=set(self.leaves):raise unavailable("classes_ou_anos_nao_materializados")
                if abs(math.fsum(r.area_m2 for r in rows.values())-q["observed_area_m2"])>q["conservation_tolerance_m2"]:
                    raise technical("soma_de_classes_diverge_do_suporte")
                for row in rows.values():
                    geometries.add((row.geometry_sha256,row.territory_kind,row.provenance))
                    expected_kind="municipio" if len(code)==7 else "uf"
                    if row.territory_kind!=expected_kind or row.provenance!=("municipio_direto" if expected_kind=="municipio" else "uf_direta"):
                        raise technical("proveniencia_territorial_incoerente")
                    if validated.support=="comum":
                        if (row.common_support_id!=q["common_support_id"] or not row.common_support_id or
                            [row.pair_start,row.pair_end]!=plan.years):raise technical("par_comparavel_divergente")
                    elif row.common_support_id is not None or row.pair_start is not None or row.pair_end is not None:
                        raise technical("suporte_anual_incoerente")
                common_ids.add(q["common_support_id"]);common_supports.add(q["observed_area_m2"])
                # A partir daqui todos os calculos sao em hectares, inclusive a agregacao de classes.
                area=math.fsum(rows[c].area_m2/10000.0 for c in plan.class_codes)
                support=q["observed_area_m2"]/10000.0
                if area>support and not math.isclose(area,support,rel_tol=1e-12,abs_tol=1e-9):raise technical("classe_excede_denominador")
                observations.append({"year":year,"class_area_ha":area,"observed_area_ha":support,"support":validated.support,"nodata_area_ha":q["nodata_area_m2"]/10000.0,
                    "unknown_area_ha":q["unknown_area_m2"]/10000.0,"outside_raster_area_ha":q["outside_raster_area_m2"]/10000.0})
            if len(geometries)!=1:raise technical("malhas_ou_proveniencias_misturadas")
            if validated.support=="comum" and (len(common_ids)!=1 or len(common_supports)!=1):raise technical("suporte_temporal_nao_identico")
            geometry,kind,provenance=next(iter(geometries))
            result[code]={"observations":observations,"geometry_sha256":geometry,"kind":kind,"provenance":provenance,
                "common_support_id":next(iter(common_ids)) if validated.support=="comum" else None}
        return result
