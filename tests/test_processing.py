"""Sinteticos/mocks: nunca validam integracao de rede ou estatisticas oficiais."""
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock
import numpy as np
import pytest
import rasterio
import shapely
from rasterio.transform import from_origin
from shapely.geometry import box,Polygon,mapping
from consultas_ambientais.processing.area import EllipsoidArea
from consultas_ambientais.processing.models import ProcessingConfig,ProcessingError
from consultas_ambientais.processing.common import atomic_json,sha_file
from consultas_ambientais.processing.snapshot import prepare_feature,load_snapshot_value
from consultas_ambientais.processing.engine import compute_feature,summarize
from consultas_ambientais.processing.raster_io import Budget,CachedSource
from consultas_ambientais.processing.runner import select_features,run_processing
from consultas_ambientais.processing.validation import geodesic_reference_area
from consultas_ambientais.storage.areas import AreaStore
from consultas_ambientais.semantics.catalog import digest
from consultas_ambientais.settings import ProjectConfig

@pytest.mark.parametrize('latitude',[0,60,-6])
def test_ellipsoid_full_fractional_and_latitudes(latitude):
    m=EllipsoidArea('EPSG:4326');t=from_origin(-36,latitude,.001,.001)
    g=box(-36+.5*t.a,latitude+2*t.e,-36+2.5*t.a,latitude)
    weights=m.weights(g,t,(2,3));row=m.row_areas(t,2)
    assert weights==pytest.approx(row[:,None]*np.array([[.5,1,.5]]),rel=1e-8,abs=.01)
    reference=geodesic_reference_area(g,.001/8)
    assert weights.sum()==pytest.approx(reference,rel=1e-6,abs=.05)
    assert weights.sum()==pytest.approx(m.area(g),rel=1e-9,abs=.01)
    if latitude==60:
        equator=m.row_areas(from_origin(-36,0,.001,.001),1)[0]
        assert .49<row[0]/equator<.51


def test_holes_oblique_border_and_window_conservation():
    m=EllipsoidArea(4326);t=from_origin(-36,-5,.001,.001)
    g=Polygon([(-36,-5),(-35.9923,-5.0012),(-35.994,-5.0077),(-36,-5.006)],
        holes=[[(-35.998,-5.002),(-35.996,-5.002),(-35.996,-5.004),(-35.998,-5.004)]])
    weights=m.weights(g,t,(10,10))
    assert weights.sum()==pytest.approx(m.area(g),rel=1e-9,abs=.01)
    assert np.all(weights>=0)
    assert weights.sum()==pytest.approx(geodesic_reference_area(g,.001/8),rel=1e-6,abs=.05)
    partition=0.
    from rasterio.windows import Window,transform
    for row in range(0,10,2):
        for col in range(0,10,2):
            partition+=m.weights(g,transform(Window(col,row,2,2),t),(2,2)).sum()
    assert partition==pytest.approx(weights.sum(),rel=1e-9,abs=.01)

@pytest.mark.parametrize('transform',[from_origin(0,0,.1,.1),rasterio.Affine(.001,.01,0,0,-.001,0)])
def test_grid_rejected_without_implicit_alignment(transform):
    with pytest.raises(ProcessingError):EllipsoidArea(4326).row_areas(transform,2)
    with pytest.raises(ProcessingError):EllipsoidArea(3857)


def synthetic_pair(tmp_path,latitude=-6,mask_all=False):
    t=from_origin(-36,latitude,.001,.001)
    arrays=[np.array([[3,3,15],[24,255,15]],dtype='uint8'),np.array([[15,3,15],[24,3,99]],dtype='uint8')]
    paths=[]
    for year,a in zip([2015,2025],arrays):
        path=tmp_path/f'{year}.tif'
        with rasterio.open(path,'w',driver='GTiff',height=2,width=3,count=1,dtype='uint8',crs='EPSG:4326',transform=t,nodata=255) as ds:
            ds.write(a,1)
            if mask_all:ds.write_mask(np.zeros((2,3),dtype='uint8'))
        paths.append(path)
    geom=box(-36+.5*t.a,latitude+2*t.e,-36+2.5*t.a,latitude)
    f=prepare_feature('2410900','Nome','RN','municipio',4326,shapely.to_wkb(geom),None)
    return paths,f,t


def context():
    return {'run_id':'a'*64,'mesh_sha256':'b'*64,'territorial_edition':None,'source_revision':None,
        'source_fingerprint':'c'*64,'catalog_sha256':'d'*64}


def calculate(tmp_path,mask_all=False):
    paths,f,t=synthetic_pair(tmp_path,mask_all=mask_all);config=ProcessingConfig()
    with rasterio.open(paths[0]) as a,rasterio.open(paths[1]) as b:
        records,quality,resources=compute_feature(f,[a,b],[2015,2025],[3,15,24,33],context(),config,Budget(config))
    return records,quality,resources,t


def test_annual_and_same_common_valid_support(tmp_path):
    records,qs,resources,t=calculate(tmp_path);row=EllipsoidArea(4326).row_areas(t,2)
    get=lambda support,year:next(q for q in qs if q['support']==support and q['year']==year)
    a=get('anual',2015);b=get('anual',2025);ca=get('comum',2015);cb=get('comum',2025)
    assert a['nodata_area_m2']==pytest.approx(row[1],rel=1e-8)
    assert a['unknown_area_m2']==0
    assert b['unknown_codes_m2']['99']==pytest.approx(row[1]*.5,rel=1e-8)
    assert b['nodata_area_m2']==0
    assert ca['observed_area_m2']==cb['observed_area_m2']
    assert ca['observed_area_m2']==pytest.approx(2*row[0]+.5*row[1],rel=1e-8)
    assert ca['common_support_id']==cb['common_support_id']
    assert all(r['value_status']=='zero_real' and r['area_m2']==0 for r in records if r['class_code']==33)
    assert next(r for r in records if r['support']=='comum' and r['year']==2015 and r['class_code']==15)['area_m2']==pytest.approx(.5*row[0],rel=1e-8)
    assert all(q['processing_status']=='completo' and q['quality_status']=='parcial' for q in qs)


def test_no_observation_is_null_not_zero(tmp_path):
    records,quality,_,_=calculate(tmp_path,mask_all=True)
    assert all(r['area_m2'] is None and r['value_status']=='sem_suporte_valido' for r in records)
    assert all(q['observed_area_m2']==0 and not q['eligible_complete'] for q in quality)


def test_zero_not_invented_as_nodata_and_group_not_counted():
    _,valid,q=summarize(np.array([[0,1,3]],dtype='uint8'),np.ones((1,3),bool),np.ones((1,3)),[3,15,24,33])
    assert q['unknown_codes_m2']=={'0':1.,'1':1.}
    assert q['nodata_area_m2']==0
    assert valid.tolist()==[[False,False,True]]


def test_outside_raster_separate(tmp_path):
    paths,f,t=synthetic_pair(tmp_path)
    geom=box(-36-.001,-6-.002,-36+.003,-6)
    f=prepare_feature('2410900','Nome','RN','municipio',4326,shapely.to_wkb(geom),None)
    config=ProcessingConfig()
    with rasterio.open(paths[0]) as a,rasterio.open(paths[1]) as b:
        _,qs,_=compute_feature(f,[a,b],[2015,2025],[3,15,24,33],context(),config,Budget(config))
    assert all(q['outside_raster_area_m2']>0 and not q['eligible_complete'] for q in qs)


def test_repair_explicit_and_not_automatically_accepted():
    invalid=Polygon([(0,0),(.001,.001),(0,.001),(.001,0),(0,0)])
    f=prepare_feature('2410900','Nome','RN','municipio',4326,shapely.to_wkb(invalid),None)
    assert f['repair']['repaired'] and not f['repair']['accepted']
    assert f['repair']['original_area_m2'] is None
    assert f['repair']['derived_area_m2']>0


def test_parquet_duckdb_resume_and_hashes(tmp_path):
    records,quality,resources,_=calculate(tmp_path);config=ProcessingConfig();root=tmp_path/'processed'
    store=AreaStore(root,config)
    assert store.complete('a'*64,'2410900') is None
    store.commit('a'*64,'2410900',records,quality,resources)
    for _ in range(2):assert store.complete('a'*64,'2410900')['status']=='completo'
    assert store.conn.execute('SELECT count(*) FROM areas').fetchone()[0]==16
    assert store.conn.execute('SELECT count(*) FROM quality').fetchone()[0]==4
    store.close()
    # Recriar o indice DuckDB a partir das particoes verificadas.
    (root/'areas.duckdb').unlink();store=AreaStore(root,config)
    store.complete('a'*64,'2410900')
    assert store.conn.execute('SELECT sum(area_m2) FROM areas').fetchone()[0]>0
    parquet=root/('a'*64)/'2410900/areas.parquet';parquet.write_bytes(b'corrupt')
    with pytest.raises(ProcessingError,match='corrompida'):store.complete('a'*64,'2410900')
    store.close()


def test_budgets_no_network_and_full_gate(tmp_path):
    config=ProcessingConfig(max_seconds=30);budget=Budget(config);budget.started-=31
    with pytest.raises(ProcessingError,match='tempo'):budget.check()
    with pytest.raises(ProcessingError,match='cinco'):select_features({'features':[]},['1']*6,False)
    with pytest.raises(ProcessingError,match='fora_da_uf'):select_features({'features':[]},['3550308'],False)


def test_persistent_range_cache_integrity(tmp_path):
    cfg=ProcessingConfig();budget=Budget(cfg);session=Mock()
    source=CachedSource('https://example.org/a.tif',cfg,session,tmp_path,budget)
    source.size=100000;source.directory=tmp_path;source.inventory={}
    source.fetch=Mock(return_value=b'x'*cfg.range_block_bytes)
    assert source.read_at(20,40)==b'x'*40
    assert source.read_at(100,4)==b'x'*4
    source.fetch.assert_called_once()
    source.memory.clear();assert source.read_at(0,4)==b'x'*4
    source.memory.clear();(tmp_path/'0.bin').write_bytes(b'bad')
    with pytest.raises(ProcessingError,match='corrompido'):source.read_at(0,4)


def test_snapshot_readonly_parameterized_and_rollback(tmp_path):
    from consultas_ambientais.processing.snapshot import export_snapshot,load_snapshot
    from consultas_ambientais.settings import DatabaseSettings
    geom=shapely.to_wkb(box(-36,-6.001,-35.999,-6))
    cur=Mock();cur.__enter__=Mock(return_value=cur);cur.__exit__=Mock(return_value=False)
    cur.fetchone.return_value=('on',)
    cur.fetchall.side_effect=[[('2410900','Nome','RN',4326,geom)],[('24','UF','RN',4326,geom)]]
    conn=Mock();conn.cursor.return_value=cur;connect=Mock(return_value=conn)
    settings=DatabaseSettings(host='placeholder',database='placeholder',user='placeholder',password='placeholder')
    path=tmp_path/'mesh.json';value=export_snapshot(settings,ProjectConfig(),ProcessingConfig(),path,connect)
    conn.set_session.assert_called_once_with(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
    conn.rollback.assert_called_once();conn.close.assert_called_once()
    for call in cur.execute.call_args_list:
        query=call.args[0]
        assert query.startswith(('SELECT','SHOW'))
        if query.startswith('SELECT'):
            assert call.args[1]==('RN',) and '%s' in query
    assert load_snapshot(path)['mesh_sha256']==value['mesh_sha256']
    value['features'][0]['name_original']='changed';atomic_json(path,value)
    with pytest.raises(ProcessingError,match='hash_snapshot'):load_snapshot(path)


def test_snapshot_rejects_unknown_srid():
    with pytest.raises(ProcessingError,match='srid'):
        prepare_feature('2410900','Nome','RN','municipio',0,shapely.to_wkb(box(0,0,1,1)),None)


def test_full_universe_requires_real_pilot_gate(tmp_path,monkeypatch):
    import consultas_ambientais.processing.runner as runner
    mesh={'features':[{'kind':'municipio','code':'2410900'}],'uf':'RN','mesh_sha256':'a'*64}
    monkeypatch.setattr(runner,'load_snapshot',lambda _:mesh)
    monkeypatch.setattr(runner.TerritoryCatalog,'load',lambda _:object())
    monkeypatch.setattr(runner,'validate_lineage',lambda *_:None)
    with pytest.raises(ProcessingError,match='piloto_validado_obrigatorio'):
        runner.run_processing(ProjectConfig(),'unused','unused',tmp_path,full=True)
    assert not (tmp_path/'data/processed').exists()


def test_no_implicit_fractional_overlap_for_mismatched_grids(tmp_path):
    paths,f,t=synthetic_pair(tmp_path);cfg=ProcessingConfig()
    with rasterio.open(paths[1],'r+') as ds:ds.transform=from_origin(-35.999,-6,.001,.001)
    with rasterio.open(paths[0]) as a,rasterio.open(paths[1]) as b:
        with pytest.raises(ProcessingError,match='grades_locais'):
            compute_feature(f,[a,b],[2015,2025],[3,15,24,33],context(),cfg,Budget(cfg))


def test_resume_preserves_prior_unit_after_interruption(tmp_path):
    records,quality,resources,_=calculate(tmp_path);cfg=ProcessingConfig();store=AreaStore(tmp_path/'processed',cfg)
    first=store.commit('a'*64,'2410900',records,quality,resources)
    # Arquivo temporario nao cria marcador de conclusao para outra unidade.
    pending=store.root/('a'*64)/'2408102';pending.mkdir();(pending/'areas.parquet.tmp').write_bytes(b'partial')
    assert store.complete('a'*64,'2408102') is None
    assert store.complete('a'*64,'2410900')['files']==first['files']
    store.close()


def test_store_rejects_mismatched_identity(tmp_path):
    records,quality,resources,_=calculate(tmp_path);store=AreaStore(tmp_path/'processed',ProcessingConfig())
    with pytest.raises(ProcessingError,match='identidade_das_linhas'):
        store.commit('other','2410900',records,quality,resources)
    store.close()


def test_common_unknown_code_union_across_years(tmp_path):
    paths,f,t=synthetic_pair(tmp_path)
    for path,values in zip(paths,[np.array([[0,3,15],[24,3,15]],dtype='uint8'),np.array([[3,3,0],[24,3,15]],dtype='uint8')]):
        with rasterio.open(path,'r+') as ds:ds.write(values,1)
    cfg=ProcessingConfig()
    with rasterio.open(paths[0]) as a,rasterio.open(paths[1]) as b:
        _,quality,_=compute_feature(f,[a,b],[2015,2025],[3,15,24,33],context(),cfg,Budget(cfg))
    q=next(q for q in quality if q['support']=='comum')
    assert q['unknown_codes_m2']['0']==pytest.approx(EllipsoidArea(4326).row_areas(t,2)[0],rel=1e-8)


def test_repeated_real_shape_batches_remain_within_memory_budget(tmp_path):
    """Regressao da retencao detectada no piloto: 33 classes x 4 suportes/anos."""
    from consultas_ambientais.semantics.catalog import ClassCatalog
    paths,feature,_=synthetic_pair(tmp_path);cfg=ProcessingConfig();budget=Budget(cfg)
    catalog=ClassCatalog.load()
    with rasterio.open(paths[0]) as a,rasterio.open(paths[1]) as b:
        records,quality,resources=compute_feature(feature,[a,b],[2015,2025],catalog.expand(list(catalog.by_code)),context(),cfg,budget)
    assert len(records)==132
    store=AreaStore(tmp_path/'batches',cfg)
    try:
        for _ in range(12):
            store.commit(context()['run_id'],feature['code'],records,quality,resources)
            budget.check()
        assert store.conn.execute('SELECT count(*) FROM areas').fetchone()[0]==132
    finally:store.close()
