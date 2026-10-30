"""Snapshot derivado: transacao repetivel somente leitura; nenhuma escrita PostGIS."""
import hashlib
from pathlib import Path
import shapely
from shapely.geometry import mapping,shape
from ..semantics.catalog import digest
from ..errors import network_issue
from .area import EllipsoidArea
from .common import atomic_json,now
from .models import ProcessingError


def prepare_feature(code,name,uf,kind,srid,ewkb,edition):
    if srid!=4326:raise ProcessingError("srid_fonte_nao_validado")
    if not isinstance(code,str) or len(code)!=(7 if kind=="municipio" else 2) or not code.isascii() or not code.isdigit():
        raise ProcessingError("codigo_territorial_invalido")
    raw=bytes(ewkb);geom=shapely.from_wkb(raw)
    if geom.is_empty or geom.geom_type not in {"Polygon","MultiPolygon"}:
        raise ProcessingError("geometria_territorial_ausente_ou_incompativel")
    method=EllipsoidArea("EPSG:4326")
    valid=geom.is_valid;before=method.area(geom) if valid else None
    diagnostic={"original_valid":bool(valid),"validity_reason":shapely.is_valid_reason(geom),
                "repaired":False,"original_area_m2":before,"derived_area_m2":before,
                "relative_area_change":0.0 if valid else None,"accepted":True}
    if not valid:
        # Area algébrica da geometria inválida não é uma área territorial de referência.
        derived=shapely.make_valid(geom)
        parts=[x for x in shapely.get_parts(derived) if x.geom_type in {"Polygon","MultiPolygon"}]
        if not parts:raise ProcessingError("reparo_sem_componente_poligonal")
        derived=shapely.union_all(parts)
        after=method.area(derived)
        diagnostic.update(repaired=True,derived_area_m2=after,accepted=False,
                          decision="requer_revisao_reparo_sem_area_original_valida")
        # Não aceitar silenciosamente reparos com área de referência indefinida.
        geom=derived
    derived_wkb=shapely.to_wkb(geom,byte_order=1)
    return {"code":code,"name_original":name,"uf":uf,"kind":kind,"srid":srid,
            "territorial_edition":edition,"source_ewkb_sha256":hashlib.sha256(raw).hexdigest(),
            "geometry_sha256":hashlib.sha256(derived_wkb).hexdigest(),"geometry":mapping(geom),
            "repair":diagnostic,
            "original_ewkb_hex_if_repaired":raw.hex() if not valid else None}


def export_snapshot(settings,project,processing,path,connect=None):
    if not settings.configured:raise ProcessingError("configuracao_postgis_ausente")
    if connect is None:
        import psycopg2
        connect=psycopg2.connect
    conn=None
    try:
        conn=connect(host=settings.host.get_secret_value(),port=settings.port,
            dbname=settings.database.get_secret_value(),user=settings.user.get_secret_value(),
            password=settings.password.get_secret_value(),sslmode=settings.sslmode,
            connect_timeout=settings.connect_timeout,
            options=f"-c default_transaction_read_only=on -c statement_timeout={settings.statement_timeout_ms} -c lock_timeout={settings.lock_timeout_ms}")
        conn.set_session(readonly=True,autocommit=False,isolation_level="REPEATABLE READ")
        features=[]
        with conn.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            if cur.fetchone()[0]!="on":raise ProcessingError("transacao_nao_somente_leitura")
            for kind,query in [
                ("municipio","SELECT cd_mun::text,nm_mun,sigla_uf,ST_SRID(geom),ST_AsEWKB(geom) FROM sbsr.municipios WHERE sigla_uf=%s ORDER BY cd_mun"),
                ("uf","SELECT cd_uf::text,nm_uf,sigla_uf,ST_SRID(geom),ST_AsEWKB(geom) FROM sbsr.uf WHERE sigla_uf=%s ORDER BY cd_uf")]:
                cur.execute(query,(project.pilot_uf,))
                for code,name,uf,srid,wkb in cur.fetchall():
                    features.append(prepare_feature(code,name,uf,kind,srid,wkb,project.territorial_edition))
        value={"schema_version":"malha-snapshot-v1","created_at":now(),"uf":project.pilot_uf,
            "read_only_confirmed":True,"source_tables":["sbsr.municipios","sbsr.uf"],
            "territorial_edition":project.territorial_edition,"crs":"EPSG:4326","features":features}
        value["mesh_sha256"]=digest({k:v for k,v in value.items() if k!="created_at"})
        load_snapshot_value(value)
        atomic_json(path,value)
        return value
    except ProcessingError:raise
    except Exception as e:
        raise ProcessingError(network_issue(e) if conn is None else "falha_snapshot_somente_leitura") from None
    finally:
        if conn:
            for action in (conn.rollback,conn.close):
                try:action()
                except Exception:pass


def load_snapshot_value(value):
    if value.get("schema_version")!="malha-snapshot-v1" or value.get("crs")!="EPSG:4326" or not value.get("read_only_confirmed"):
        raise ProcessingError("contrato_snapshot_invalido")
    if digest({k:v for k,v in value.items() if k not in {"mesh_sha256","created_at"}})!=value.get("mesh_sha256"):
        raise ProcessingError("hash_snapshot_divergente")
    codes=[f["code"] for f in value["features"]]
    if len(codes)!=len(set(codes)) or sum(f["kind"]=="uf" for f in value["features"])!=1:
        raise ProcessingError("universo_snapshot_incoerente")
    uf_code=next(f["code"] for f in value["features"] if f["kind"]=="uf")
    for f in value["features"]:
        geom=shape(f["geometry"])
        if (f["srid"]!=4326 or f["uf"]!=value["uf"] or not f["code"].startswith(uf_code)
                or hashlib.sha256(shapely.to_wkb(geom,byte_order=1)).hexdigest()!=f["geometry_sha256"]):
            raise ProcessingError("geometria_snapshot_divergente")
    return value


def load_snapshot(path):
    import json
    return load_snapshot_value(json.loads(Path(path).read_text()))
