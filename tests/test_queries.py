"""Referencias de algebra/seletores SINTETICAS, calculadas com Decimal e valores literais.

Estas tabelas nao simulam pixels nem validam a fisica/mascaras da etapa 3.
Valores anuais e comparaveis deliberadamente distintos detectam a leitura do
suporte errado. Nenhuma chamada externa participa desta suite.
"""
import csv
import io
import json
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import Mock
import pytest
from consultas_ambientais.contracts import QueryPlan
from consultas_ambientais.queries.engine import QueryEngine
from consultas_ambientais.queries.models import QueryFailure
from consultas_ambientais.answers.models import QueryAnswer
from consultas_ambientais.answers.export import csv_text,json_text
from consultas_ambientais.processing.models import ProcessingConfig
from consultas_ambientais.processing.common import atomic_json
from consultas_ambientais.storage.areas import AreaStore
from consultas_ambientais.semantics.catalog import ClassCatalog,digest
from consultas_ambientais.semantics.territories import TerritoryCatalog,territory_digest
from consultas_ambientais.semantics.models import TerritoryCatalogData,TerritoryEntry,Capabilities,Materialization
from consultas_ambientais.settings import ProjectConfig

CODES=['2400109','2400208','2400307','2400406']


def plan(**updates):
    return {'operation':'area','metric':'area','unit':'ha','territory_codes':[CODES[0]],'class_codes':[3],'years':[2015],**updates}


def temporal(**updates):
    return plan(operation='comparacao_temporal',metric='diferenca_liquida',years=[2015,2025],**updates)


@pytest.fixture
def materialized(tmp_path):
    classes=ClassCatalog.load();leaves=classes.expand(list(classes.by_code))
    entries=[TerritoryEntry(kind='municipio',code=c,name_original=name,uf='RN',uf_code='24') for c,name in zip(CODES,['Alfa','Beta','Gama','Delta'])]
    entries.append(TerritoryEntry(kind='uf',code='24',name_original='UF sintetica',uf='RN',uf_code='24'))
    tdata=TerritoryCatalogData(read_only_confirmed=True,entries=entries,content_sha256='0'*64)
    tdata.content_sha256=territory_digest(tdata);territories=TerritoryCatalog(tdata)
    territory_path=tmp_path/'data/territories.json';atomic_json(territory_path,tdata.model_dump(mode='json'))
    identity={'catalog_sha256':classes.sha256,'mesh_sha256':'b'*64,'method':'ellipsoid-linear-lonlat-fractional-v1',
        'software':{'synthetic_fixture_only':True},'staging_id':'c'*64,'years':[2015,2025],
        'territory_codes':sorted([*CODES,'24']),'config':{'collection':11,'source_revision':'synthetic-only','territorial_edition':None}}
    run=digest(identity);store=AreaStore(tmp_path/'data/processed',ProcessingConfig());parts=[];quality_all=[];mats=[]
    raw_refs={}
    for code in [*CODES,'24']:
        records=[];qs=[]
        for support in ['anual','comum']:
            for year in [2015,2025]:
                before=year==2015
                initial_final={CODES[0]:(D('100'),D('60')),CODES[1]:(D('100'),D('60')),CODES[2]:(D('0'),D('10')),CODES[3]:(D('50'),D('50')),'24':(D('321'),D('300'))}
                area=initial_final[code][0 if before else 1]
                second=D('20') if before else D('10')
                if code!=CODES[0]:second=D('0')
                if support=='anual' and code==CODES[0]:area=D('120.123456') if before else D('100.123456');second=D('10')
                total=D('1234.5') if code=='24' else D('200')
                values={3:area,4:second,15:total-area-second}
                common=digest({'synthetic':code}) if support=='comum' else None
                q={'run_id':run,'territory_code':code,'territory_kind':'uf' if code=='24' else 'municipio','year':year,'support':support,'common_support_id':common,
                    'total_area_m2':float(total*10000),'inside_raster_area_m2':float(total*10000),'outside_raster_area_m2':0.,
                    'observed_area_m2':float(total*10000),'nodata_area_m2':0.,'unknown_area_m2':0.,'unknown_codes_m2':{},
                    'processing_status':'completo','quality_status':'completo','eligible_complete':True,
                    'conservation_error_m2':0.,'conservation_tolerance_m2':.01+1e-9*float(total*10000)}
                qs.append(q)
                for leaf in leaves:
                    m2=float(values.get(leaf,D(0))*D(10000));raw_refs[(code,support,year,leaf)]=D(str(m2))
                    records.append({'schema_version':'areas-geoespaciais-v1','run_id':run,'territory_code':code,
                        'territory_kind':q['territory_kind'],'provenance':'uf_direta' if code=='24' else 'municipio_direto',
                        'mesh_sha256':identity['mesh_sha256'],'geometry_sha256':digest(code),'territorial_edition':None,
                        'collection':11,'source_revision':'synthetic-only','source_fingerprint':identity['staging_id'],
                        'catalog_sha256':classes.sha256,'method':identity['method'],'support':support,'common_support_id':common,
                        'year':year,'pair_start':2015 if common else None,'pair_end':2025 if common else None,'class_code':leaf,
                        'area_m2':m2,'value_status':'zero_real' if m2==0 else 'observado','unit':'m2'})
        part=store.commit(run,code,records,qs,{'synthetic_only':True});parts.append({'territory_code':code,'files':part['files'],'resources':{}});quality_all.extend(qs)
        for years in [[2015],[2025],[2015,2025]]:
            mats.append(Materialization(territory_code=code,years=years,class_codes=leaves,complete=True,
                common_support_id=digest({'synthetic':code}) if len(years)==2 else None,run_id=run))
    store.close()
    manifest={'schema_version':'execucao-geoespacial-v1','state':'verificado','run_id':run,'identity':identity,
        'partitions':parts,'quality_summary':quality_all,'territory_count':5,'expected_municipalities':4,
        'complete_municipality_universe':True,'ranking_eligible':True,
        'sources':[{'url':f'https://example.test/synthetic_{year}.tif','etag':'synthetic-only'} for year in [2015,2025]],
        'input_crop_hashes':['d'*64,'e'*64]}
    manifest_path=tmp_path/'artifacts/processing'/run/'manifest.json';atomic_json(manifest_path,manifest)
    caps=Capabilities(class_catalog_sha256=classes.sha256,territory_catalog_sha256=territories.sha256,
        available_raster_years=[2015,2025],materializations=mats,engine_ready=False)
    cap_path=tmp_path/'data/caps.json';atomic_json(cap_path,caps.model_dump(mode='json'))
    def engine():return QueryEngine(tmp_path,ProjectConfig(),run,territory_path,cap_path)
    return {'root':tmp_path,'run':run,'engine':engine,'raw':raw_refs,'manifest':manifest,'manifest_path':manifest_path,'cap_path':cap_path,'caps':caps}


def reference(fixture,code,support,year,codes):
    # Somente Decimal/literais: nao chama metricas, validadores ou SQL do executor.
    return sum((fixture['raw'][code,support,year,c] for c in set(codes)),D(0))/D(10000)


@pytest.mark.parametrize('unit,factor',[('ha',D(1)),('km2',D('0.01')),('m2',D(10000))])
def test_area_conversions_independent_reference(materialized,unit,factor):
    a=materialized['engine']().answer(plan(unit=unit))
    expected=reference(materialized,CODES[0],'anual',2015,[3])*factor
    assert a.status=='respondida' and a.values[0].value==pytest.approx(float(expected),rel=1e-14)
    assert a.values[0].area_value_ha==pytest.approx(120.123456)
    assert a.evidence[0].observations[0].class_area_ha==pytest.approx(120.123456)


def test_share_and_no_rounding_before_calculation(materialized):
    a=materialized['engine']().answer(plan(operation='participacao',metric='participacao',unit='percentual',denominator='area_observada'))
    expected=D('120.123456')/D(200)*100
    assert a.values[0].value==pytest.approx(float(expected),abs=1e-12)
    assert a.values[0].denominator_value==200 and a.values[0].denominator_unit=='ha'
    assert '60,06 %' in a.message
    raw=json.loads(json_text(a));assert raw['values'][0]['value']!=60.06


def test_hierarchy_union_not_parent_plus_children(materialized):
    a=materialized['engine']().answer(plan(class_codes=[1,3]))
    assert a.status=='respondida'
    assert a.plan.class_codes==[3,4,5,6,7,49]
    assert a.values[0].value==pytest.approx(130.123456)
    assert a.evidence[0].requested_class_codes==[1,3]


@pytest.mark.parametrize('metric,unit,denominator,expected',[
    ('diferenca_liquida','ha',None,-40),('diferenca_liquida','m2',None,-400000),
    ('reducao_liquida','km2',None,.4),('variacao_percentual','percentual','area_inicial',-40),
    ('diferenca_pontos_percentuais','pontos_percentuais','participacao_por_ano',-20)])
def test_temporal_uses_materialized_common_support(materialized,metric,unit,denominator,expected):
    p=temporal();p.update(metric=metric,unit=unit,denominator=denominator)
    a=materialized['engine']().answer(p)
    assert a.status=='respondida' and a.values[0].value==pytest.approx(expected)
    e=a.evidence[0]
    assert all(o.support=='comum' for o in e.observations)
    assert e.observations[0].class_area_ha==100 and e.observations[1].class_area_ha==60
    assert e.quality.common_support_id and e.denominator_values_ha==([100] if metric=='variacao_percentual' else [200,200] if metric=='diferenca_pontos_percentuais' else [])


def test_base_zero_is_null_with_reason(materialized):
    p=temporal();p.update(metric='variacao_percentual',unit='percentual',denominator='area_inicial',territory_codes=[CODES[2]])
    a=materialized['engine']().answer(p)
    assert a.status=='respondida' and a.values[0].value is None
    assert a.values[0].undefined_reason=='base_inicial_zero' and a.values[0].denominator_value==0
    assert 'indefinida' in a.message and 'base_inicial_zero' in a.message


def test_absent_class_is_real_zero(materialized):
    a=materialized['engine']().answer(plan(class_codes=[24]))
    assert a.status=='respondida' and a.values[0].value==0 and a.values[0].undefined_reason is None


def test_series_is_available_years_without_interpolation(materialized):
    a=materialized['engine']().answer(plan(operation='serie_disponivel',years=[2025,2015]))
    assert a.status=='respondida' and a.plan.years==[2015,2025]
    assert [v.value for v in a.values]==pytest.approx([120.123456,100.123456])
    assert 'sem interpolação' in a.message


def test_territory_comparison_and_uf_direct_not_sum(materialized):
    a=materialized['engine']().answer(plan(operation='comparacao_territorial',territory_codes=[CODES[0],CODES[1]]))
    assert [v.value for v in a.values]==pytest.approx([120.123456,100])
    uf=materialized['engine']().answer(plan(territory_codes=['24']))
    assert uf.values[0].value==321 and uf.evidence[0].provenance=='uf_direta'


def ranking(**updates):
    return plan(operation='ranking_delimitado',metric='reducao_liquida',years=[2015,2025],territory_codes=[],scope_uf='RN',limit=3,**updates)


def test_ranking_reductions_filter_increases_and_tie_by_code(materialized):
    a=materialized['engine']().answer(ranking())
    assert a.status=='respondida' and [v.value for v in a.values]==[40,40]
    assert [e.territory.code for e in a.evidence]==CODES[:2]
    assert [v.rank for v in a.values]==[1,2]
    r=a.ranking
    assert r.candidate_codes==CODES and r.verified_count==4 and r.filtered_non_reductions==2
    assert r.coverage=='completa' and r.returned_count==2 and r.scope_uf=='RN'
    assert 'Brasil' not in a.message


def test_signed_ranking_and_undefined_base_zero(materialized):
    p=ranking();p.update(metric='diferenca_liquida',direction='asc')
    a=materialized['engine']().answer(p)
    assert [v.value for v in a.values]==[-40,-40,0]
    p.update(metric='variacao_percentual',unit='percentual',denominator='area_inicial')
    a=materialized['engine']().answer(p)
    assert a.ranking.undefined_codes==[CODES[2]]
    assert [v.value for v in a.values]==[-40,-40,0]


def test_empty_ranking_is_not_missing_data(materialized):
    a=materialized['engine']().answer(ranking(class_codes=[24]))
    assert a.status=='respondida' and not a.values and not a.evidence
    assert a.ranking.qualifying_count==0 and a.ranking.filtered_non_reductions==4
    assert 'Nenhum município apresentou redução líquida' in a.message


def test_ranking_does_not_round_before_ordering(materialized,monkeypatch):
    import consultas_ambientais.queries.engine as module
    original=module._calculate
    counter=iter([1.001,1.002,0.,0.])
    def calculate(metric,unit,observations):
        # Valores de ordenacao com mesma apresentacao; aritmetica ja testada por referencias.
        v=next(counter);return v,v,None,None
    monkeypatch.setattr(module,'_calculate',calculate)
    a=materialized['engine']().answer(ranking())
    assert [e.territory.code for e in a.evidence]==[CODES[1],CODES[0]]
    assert a.values[0].value==1.002


@pytest.mark.parametrize('updates,expected',[
    ({'years':[2016]},'dados_indisponiveis'),({'class_codes':[999]},'precisa_esclarecimento'),
    ({'territory_codes':['3550308']},'precisa_esclarecimento'),({'scope_uf':'SP'},'precisa_esclarecimento'),
    ({'class_codes':[True]},'precisa_esclarecimento'),({'class_codes':['3']},'precisa_esclarecimento'),
    ({'sql':'SELECT * FROM secrets'},'precisa_esclarecimento'),({'metric':'perda_bruta'},'dados_indisponiveis'),
    ({'scope_uf':'BR'},'fora_do_escopo')])
def test_refusals_have_no_quantitative_payload(materialized,updates,expected):
    a=materialized['engine']().answer(plan(**updates))
    assert a.status==expected and not a.values and not a.evidence and not a.answer_id
    assert 'secrets' not in a.model_dump_json()


def test_limits_validated_before_any_sql(materialized,monkeypatch):
    import consultas_ambientais.storage.derived as module
    spy=Mock(side_effect=AssertionError('SQL nao deveria ser chamado'))
    monkeypatch.setattr(module.duckdb,'connect',spy)
    p=ranking();p['limit']=True
    assert materialized['engine']().answer(p).status=='precisa_esclarecimento'
    p['limit']=101
    assert materialized['engine']().answer(p).status=='precisa_esclarecimento'
    spy.assert_not_called()


def test_missing_pair_never_falls_back_to_annual(materialized):
    caps=materialized['caps'].model_copy(deep=True)
    caps.materializations=[m for m in caps.materializations if len(m.years)==1]
    atomic_json(materialized['cap_path'],caps.model_dump(mode='json'))
    a=materialized['engine']().answer(temporal())
    assert a.status=='dados_indisponiveis' and not a.values


def test_rank_requires_every_candidate(materialized):
    caps=materialized['caps'].model_copy(deep=True)
    caps.materializations=[m for m in caps.materializations if m.territory_code!=CODES[-1]]
    atomic_json(materialized['cap_path'],caps.model_dump(mode='json'))
    a=materialized['engine']().answer(ranking())
    assert a.status=='dados_indisponiveis' and a.reason=='ranking_com_cobertura_incompleta'


def test_bad_hash_and_sql_failure_are_technical_not_numbers(materialized,monkeypatch):
    import consultas_ambientais.storage.derived as module
    monkeypatch.setattr(module.duckdb,'connect',Mock(side_effect=RuntimeError('sensitive-error-body')))
    a=materialized['engine']().answer(plan())
    assert a.status=='erro_tecnico' and not a.values and 'sensitive-error-body' not in a.model_dump_json()
    monkeypatch.undo()
    path=materialized['root']/'data/processed'/materialized['run']/CODES[0]/'areas.parquet'
    path.write_bytes(b'corrupted')
    a=materialized['engine']().answer(plan())
    assert a.status=='erro_tecnico' and a.reason=='hash_da_particao_divergente' and not a.values


def test_stable_ids_export_and_no_input_mutation(materialized):
    p=plan(class_codes=[1,3]);before=json.dumps(p,sort_keys=True)
    a=materialized['engine']().answer(p);b=materialized['engine']().answer(p)
    assert a.answer_id==b.answer_id and a.plan_id==b.plan_id
    assert [e.evidence_id for e in a.evidence]==[e.evidence_id for e in b.evidence]
    assert json.dumps(p,sort_keys=True)==before
    assert QueryAnswer.model_validate_json(json_text(a))==a
    rows=list(csv.DictReader(io.StringIO(csv_text(a))))
    assert D(rows[0]['value'])==D(str(a.values[0].value))
    assert json.loads(rows[0]['class_codes'])==a.plan.class_codes
    assert json.loads(rows[0]['sources'])[0]['sha256']==a.evidence[0].run_manifest_sha256
    for e in a.evidence:
        assert e.observations and e.sources and e.source_ids and e.area_method and e.mesh_sha256
    assert materialized['caps'].engine_ready is False


def test_executor_rejects_unvalidated_object(materialized):
    engine=materialized['engine']()
    with pytest.raises(QueryFailure,match='plano_nao_validado'):engine.execute(QueryPlan.model_validate(plan()))


def test_query_needs_no_network_or_source_database(materialized,monkeypatch):
    import requests,psycopg2
    http=Mock(side_effect=AssertionError('rede proibida'))
    database=Mock(side_effect=AssertionError('origem proibida'))
    monkeypatch.setattr(requests.sessions.Session,'request',http);monkeypatch.setattr(psycopg2,'connect',database)
    assert materialized['engine']().answer(plan()).status=='respondida'
    http.assert_not_called();database.assert_not_called()


def test_json_csv_null_and_undefined_reason(materialized):
    p=temporal();p.update(metric='variacao_percentual',unit='percentual',denominator='area_inicial',territory_codes=[CODES[2]])
    a=materialized['engine']().answer(p)
    row=next(csv.DictReader(io.StringIO(csv_text(a))))
    assert row['value']=='' and row['undefined_reason']=='base_inicial_zero'
    assert json.loads(row['executed_plan'])==a.plan.model_dump(mode='json')


def test_cli_json_csv_audit_and_capabilities(materialized,monkeypatch,capsys):
    from consultas_ambientais.cli import main
    root=materialized['root'];monkeypatch.chdir(root)
    p=root/'plan.json';atomic_json(p,plan())
    args=['query','--plan',str(p),'--run-id',materialized['run'],'--territories','data/territories.json','--capabilities','data/caps.json',
        '--json-output','reports/answer.json','--csv-output','reports/answer.csv','--capabilities-output','data/caps4.json','--format','json']
    assert main(args)==0
    a=QueryAnswer.model_validate_json(capsys.readouterr().out)
    assert a.status=='respondida'
    assert (root/'artifacts/queries'/f'{a.answer_id}.json').exists()
    assert json.loads((root/'data/caps4.json').read_text())['engine_ready'] is True
    assert json.loads((root/'data/caps.json').read_text())['engine_ready'] is False
    assert next(csv.DictReader((root/'reports/answer.csv').open()))['value']=='120.123456'
    assert a.model_dump(mode='json')==json.loads((root/'reports/answer.json').read_text())


def test_cli_does_not_overwrite_source_files(materialized,monkeypatch,capsys):
    from consultas_ambientais.cli import main
    root=materialized['root'];monkeypatch.chdir(root);p=root/'plan.json';atomic_json(p,plan());before=p.read_bytes()
    assert main(['query','--plan',str(p),'--run-id',materialized['run'],'--json-output',str(p),'--format','json'])==2
    a=json.loads(capsys.readouterr().out)
    assert a['status']=='erro_tecnico' and not a['values'] and p.read_bytes()==before


def test_inconsistent_common_support_is_technical(materialized):
    # Aumentar o suporte de um ano mantendo hash da particao antigo e detectado antes de calcular.
    import duckdb
    root=materialized['root'];run=materialized['run'];path=root/'data/processed'/run/CODES[0]/'quality.parquet'
    c=duckdb.connect();rows=c.execute('SELECT * FROM read_parquet(?)',[str(path)]).fetchall();c.close()
    assert rows
    m=materialized['manifest'];q=next(q for q in m['quality_summary'] if q['territory_code']==CODES[0] and q['support']=='comum' and q['year']==2025)
    q['common_support_id']='different-common-mask'
    atomic_json(materialized['manifest_path'],m)
    a=materialized['engine']().answer(temporal())
    assert a.status=='erro_tecnico' and not a.values


def test_duplicate_or_mismatched_quality_is_not_missing_data(materialized):
    m=materialized['manifest'];m['quality_summary'].append(m['quality_summary'][0])
    atomic_json(materialized['manifest_path'],m)
    a=materialized['engine']().answer(plan())
    assert a.status=='erro_tecnico' and a.reason=='qualidade_duplicada_ou_fora_da_execucao'


def test_missing_requested_year_of_series_is_not_silently_dropped(materialized):
    a=materialized['engine']().answer(plan(operation='serie_disponivel',years=[2015,2016,2025]))
    assert a.status=='dados_indisponiveis' and not a.values
