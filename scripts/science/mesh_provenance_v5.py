"""Auditoria de RN/IBGE 2025, sem substituir o snapshot ou reprocessar areas."""
from pathlib import Path
from datetime import datetime,timezone
from zipfile import ZipFile
import json,hashlib
import requests,shapely
from osgeo import ogr,gdal
from shapely.geometry import shape,mapping
from consultas_ambientais.evaluation.common import read,save,sha,digest
from .audit import require

BASE='https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2025/UFs/RN/'

def bounded_get(url,path,limit):
    try:
        with requests.get(url,timeout=(15,25),stream=True,verify=True,allow_redirects=False) as r:
            if r.status_code!=200:return {'url':url,'state':'indisponivel','http_status':r.status_code}
            data=bytearray()
            for chunk in r.iter_content(65536):
                data.extend(chunk);require(len(data)<=limit,'limite_download_malha')
            path.write_bytes(data)
            return {'url':url,'state':'verificado','http_status':r.status_code,'bytes':len(data),'sha256':sha(path),
                    'last_modified_http':r.headers.get('Last-Modified'),'etag':r.headers.get('ETag'),
                    'http_last_modified_is_publication_date':False}
    except requests.RequestException as e:
        return {'url':url,'state':'indisponivel','http_status':None,
                'reason':'timeout' if isinstance(e,requests.Timeout) else 'rede_ou_TLS','error_body_stored':False}

def all_equal(files):
    return len(files)==2 and all(f.get('state')=='verificado' and f.get('comparison',{}).get('features',0)>0 and
        f['comparison']['normalized_exact_matches']==f['comparison']['features'] for f in files)

def read_official(path,kind):
    ds=ogr.Open('/vsizip/'+str(path.resolve()),0);require(ds is not None,'arquivo_oficial_ilegivel')
    layer=ds.GetLayer(0);definition=layer.GetLayerDefn();names={definition.GetFieldDefn(i).GetName() for i in range(definition.GetFieldCount())}
    column=next((k for k in (['CD_MUN','CD_GEOCMU'] if kind=='municipio' else ['CD_UF','CD_GEOCUF']) if k in names),None)
    require(column is not None,'codigo_IBGE_ausente')
    crs=layer.GetSpatialRef();crs_wkt=crs.ExportToWkt();official={}
    for f in layer:official[str(f.GetField(column))]=shape(json.loads(f.GetGeometryRef().ExportToJson()))
    ds=None;return official,crs_wkt

def compare(snapshot,official,official_crs,kind):
    rows=[]
    for f in snapshot['features']:
        if f['kind']!=kind:continue
        g=shape(f['geometry']);other=official.get(f['code'])
        ng=shapely.normalize(g);norm_sha=hashlib.sha256(ng.wkb).hexdigest()
        no=shapely.normalize(other) if other is not None else None
        rows.append({'code':f['code'],'kind':kind,'name_original':f['name_original'],
            'snapshot_geometry_sha256':f['geometry_sha256'],'snapshot_ewkb_sha256':f['source_ewkb_sha256'],
            'normalized_2d_wkb_sha256':norm_sha,'official_normalized_2d_wkb_sha256':hashlib.sha256(no.wkb).hexdigest() if no is not None else None,
            'normalized_wkb_equal':ng.wkb==no.wkb if no is not None else False,
            'topologically_equal':g.equals(other) if other is not None else False,
            'coordinate_count_snapshot':int(shapely.get_num_coordinates(g)),
            'coordinate_count_official':int(shapely.get_num_coordinates(other)) if other is not None else None,
            'valid':g.is_valid,'empty':g.is_empty,'bounds':list(g.bounds)})
    return {'features':len(rows),'official_features':len(official),'codes_equal':{r['code'] for r in rows}==set(official),
        'normalized_exact_matches':sum(r['normalized_wkb_equal'] for r in rows),
        'topological_exact_matches':sum(r['topologically_equal'] for r in rows),'rows':rows,
        'comparison_space':'coordenadas numericas originais; sem transformacao de datum ou tolerancia',
        'official_crs':official_crs,'snapshot_crs':snapshot['crs']}

def acquire(root,output,offline=False):
    root,output=map(Path,(root,output));output.mkdir(exist_ok=True,parents=True)
    mesh_path=root/'data/mesh_RN_v1.json';mesh=read(mesh_path)
    previous=read(output/'proveniencia_malha.json') if offline else None
    report={'schema_version':'proveniencia-malha-v5','checked_at':datetime.now(timezone.utc).isoformat(),
        'author_declaration':{'received_on':'2026-10-21','provider':'IBGE','edition':2025,'scope':['municipios','uf'],
            'basis':'usuario confirmou origem IBGE e respondeu 2025 ao esclarecimento de ano para municipios/UF',
            'original_archive_or_import_log_supplied':False},
        'raster_provider_reported':'MapBiomas; verificacao dos intervalos utilizados permanece na V2',
        'snapshot_file_sha256':sha(mesh_path),'mesh_logical_sha256':mesh['mesh_sha256'],'snapshot_created_at':mesh['created_at'],
        'snapshot_source_tables':mesh['source_tables'],'snapshot_crs':mesh['crs'],'snapshot_changed':False,'areas_reprocessed':False,
        'official_files':[],'limits':['Edicao declarada e comparacao geometrica nao recuperam o historico de importacao.',
            'SRID 4326 do snapshot difere do CRS SIRGAS 2000 descrito pelo IBGE; comparar coordenadas nao prova transformacao de datum.']}
    if previous:
        if not (output/'aquisicao_ibge_2025.json').exists():save(output/'aquisicao_ibge_2025.json',previous)
        report['acquisition_checked_at']=previous['checked_at'];report['recorded_acquisition_sha256']=sha(output/'aquisicao_ibge_2025.json')
    report['official_product_documentation']={'url':'https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-mlhas.html',
        'checked_on':'2026-10-21','crs_described':'SIRGAS 2000, coordenadas geograficas; documentacao do produto, nao leitura do arquivo historico',
        'license_of_imported_archive_verified':False,'original_publication_date_verified':False}
    report['snapshot_geometry_inventory']=[{'code':f['code'],'kind':f['kind'],'srid':f['srid'],
        'geometry_sha256':f['geometry_sha256'],'source_ewkb_sha256':f['source_ewkb_sha256'],
        'normalized_2d_wkb_sha256':hashlib.sha256(shapely.normalize(shape(f['geometry'])).wkb).hexdigest(),
        'geometry_type':f['geometry']['type'],'coordinates':int(shapely.get_num_coordinates(shape(f['geometry']))),
        'bounds':list(shape(f['geometry']).bounds),'valid':shape(f['geometry']).is_valid,'empty':shape(f['geometry']).is_empty,
        'repair':f['repair']} for f in mesh['features']]
    for name,kind in [('RN_Municipios_2025.zip','municipio'),('RN_UF_2025.zip','uf')]:
        path=output/name
        meta=next(f for f in previous['official_files'] if f['url']==BASE+name) if previous else bounded_get(BASE+name,path,4*1024*1024)
        if meta['state']=='verificado':
            with ZipFile(path) as z:
                require(sum(i.file_size for i in z.infolist())<=32*1024*1024,'zip_malha_grande')
                meta['archive_members']={i.filename:hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist() if not i.is_dir()}
                meta['prj_text']={i.filename:z.read(i).decode('utf-8',errors='replace') for i in z.infolist() if i.filename.lower().endswith('.prj')}
            official,crs=read_official(path,kind)
            meta['comparison']=compare(mesh,official,crs,kind)
        report['official_files'].append(meta)
    report['all_numeric_geometries_equal']=all_equal(report['official_files'])
    report['comparison_state']='pendente_aquisicao' if any(f['state']!='verificado' for f in report['official_files']) else 'coincidente' if report['all_numeric_geometries_equal'] else 'diferencas_a_investigar'
    report['software']={'gdal':gdal.VersionInfo(),'shapely':shapely.__version__}
    # Copia GeoJSON dos numeros utilizados: nao e uma nova edicao do produto IBGE.
    geojson={'type':'FeatureCollection','name':'limites_RN_utilizados_no_experimento',
        'metadata':{'mesh_logical_sha256':mesh['mesh_sha256'],'source_snapshot_sha256':sha(mesh_path),'snapshot_crs':mesh['crs'],
                    'provider_and_edition_reported':'IBGE 2025; declaracao do autor','reprojected':False,'repaired':False},
        'features':[{'type':'Feature','id':f['code'],'properties':{k:f[k] for k in ['code','kind','name_original','uf','srid','geometry_sha256','source_ewkb_sha256']},
                     'geometry':f['geometry']} for f in mesh['features']]}
    save(output/'limites_RN_utilizados.geojson',geojson);report['derived_geojson_sha256']=sha(output/'limites_RN_utilizados.geojson')
    save(output/'proveniencia_malha.json',report);return report
