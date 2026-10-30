"""Verificacoes sinteticas do protocolo/runner, sem executar gateway real."""
import json
from pathlib import Path
import pytest
from consultas_ambientais.evaluation.common import save, read, write_lines, sha
from consultas_ambientais.evaluation import protocol as frozen
from consultas_ambientais.evaluation.protocol import default_protocol
from consultas_ambientais.evaluation.statistics import aggregate
from consultas_ambientais.evaluation.scoring import score
from consultas_ambientais.evaluation.runner import normalized_C
from consultas_ambientais.evaluation.benchmark import plan, cluster_family


def test_freeze_detects_gold_prompt_code_configuration_and_source_mutations(tmp_path,monkeypatch):
    b=tmp_path/'benchmarks';b.mkdir();save(b/'questions.json',{'q':'consulta sintetica'})
    save(b/'sources.json',{'input_hashes':{}})
    monkeypatch.setattr(frozen,'executor_digest',lambda:'executor')
    monkeypatch.setattr(frozen,'interpreter_digest',lambda:'interpreter')
    cfg={'temperature':0}
    frozen.freeze(b,cfg);assert frozen.verify(b,tmp_path,cfg)==sha(b/'freeze.json')
    with pytest.raises(ValueError):frozen.freeze(b,cfg)
    with pytest.raises(ValueError):frozen.verify(b,configuration={'temperature':1})
    save(b/'questions.json',{'q':'modificada'})
    with pytest.raises(ValueError):frozen.verify(b)


def test_bootstrap_report_counts_technical_errors_and_missing(tmp_path):
    benchmark=tmp_path/'b';benchmark.mkdir();output=tmp_path/'r';output.mkdir()
    save(benchmark/'protocol.json',default_protocol())
    cases=[{'case_id':str(i),'family_id':str(i),'territory_codes':['2400109'],'dependencies':[],
            'expected_decision':'respondida'} for i in range(3)]
    write_lines(benchmark/'cases.jsonl',cases)
    save(output/'run.json',{'case_ids':['0','1','2'],'run_id':'synthetic','split':'dev',
                           'integration_kind':'mock_contrato','freeze_sha256':'synthetic'})
    for i in range(3):
        for condition in ['A','B','C']:
            if i==2 and condition=='A':continue
            save(output/'individual'/f'{i}_{condition}.json',{
                'case_id':str(i),'condition':condition,'repeat':0,'observed':{'status':'erro_tecnico'},
                'scores':{'correct':condition=='C' and i!=2},'latency_seconds':1,'attempts':[]})
    report=aggregate(output,benchmark)
    assert report['metrics']['A']['missing']==1
    assert report['metrics']['C']['accuracy_including_technical_and_missing']==2/3
    assert report['paired_C_minus_B']['cases']==3
    assert report['metrics']['C']['cost'] is None
    # C par ausente impede um IC enganoso em subconjunto selecionado.
    (output/'individual/2_C.json').unlink()
    assert aggregate(output,benchmark)['paired_C_minus_B']['state']=='pendente'


def test_family_groups_combine_reused_frames():
    assert cluster_family('t01')==cluster_family('t05')
    assert cluster_family('t11')==cluster_family('t14')
    assert cluster_family('t25')==cluster_family('t26')
    assert cluster_family('t01')!=cluster_family('t11')


def test_ranking_score_checks_order_before_rounding():
    p=plan([],15,(2025,),operation='ranking_delimitado')
    rows=[{'territory_code':c,'years':[2025],'unit':'ha','value':10,'undefined_reason':None,
           'denominators_ha':[],'rank':i+1} for i,c in enumerate(['2400109','2400208'])]
    gold={'status':'respondida','plan':p,'values':rows,'clarification_field':None}
    wrong={**gold,'values':list(reversed(rows))}
    assert score(gold,gold,default_protocol(),{'15':[15]})['correct']
    assert not score(wrong,gold,default_protocol(),{'15':[15]})['correct']


def test_reference_reader_synthetic_parquet_and_conservation(tmp_path):
    import duckdb
    from consultas_ambientais.evaluation.reference import ReferenceReader
    from consultas_ambientais.semantics.catalog import ClassCatalog
    run='synthetic';base=tmp_path/'data/processed'/run/'2400109';base.mkdir(parents=True)
    with duckdb.connect(':memory:') as db:
        db.execute("CREATE TABLE a(support VARCHAR, year INTEGER, class_code INTEGER, area_m2 DOUBLE)")
        db.execute("INSERT INTO a VALUES ('anual',2015,15,30000),('comum',2015,15,20000),('comum',2025,15,50000)")
        db.execute('COPY a TO ? (FORMAT PARQUET)',[str(base/'areas.parquet')])
        db.execute("CREATE TABLE q(support VARCHAR, year INTEGER, observed_area_m2 DOUBLE,total_area_m2 DOUBLE, common_support_id VARCHAR, eligible_complete BOOLEAN)")
        db.execute("INSERT INTO q VALUES ('anual',2015,30000,30000,NULL,true),('comum',2015,20000,20000,'pair',true),('comum',2025,50000,50000,'pair',true)")
        db.execute('COPY q TO ? (FORMAT PARQUET)',[str(base/'quality.parquet')])
    save(tmp_path/'artifacts/processing'/run/'manifest.json',{'partitions':[{'territory_code':'2400109',
         'files':[{'name':p.name,'sha256':sha(p)} for p in base.glob('*.parquet')]}]})
    reader=ReferenceReader(tmp_path,run,ClassCatalog.load())
    status,values=reader.answer(plan('2400109',15,(2015,2025),'diferenca_liquida'))
    assert status=='respondida' and float(values[0]['value'])==3
    assert reader.answer(plan('2400109',15,(2024,)))[0]=='dados_indisponiveis'
    (base/'areas.parquet').write_text('tampered')
    with pytest.raises(ValueError):ReferenceReader(tmp_path,run,ClassCatalog.load()).partition('2400109')
