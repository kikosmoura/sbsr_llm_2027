"""Etapa 7: testes sinteticos e HTTP mocks; nao sao resultados cientificos."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from consultas_ambientais.evaluation.reference import calculate, order_ranking
from consultas_ambientais.evaluation.protocol import default_protocol
from consultas_ambientais.evaluation.scoring import score
from consultas_ambientais.evaluation.statistics import paired_bootstrap
from consultas_ambientais.evaluation.models import BaselineAnswer
from consultas_ambientais.evaluation.baselines import run_baseline
from consultas_ambientais.evaluation.benchmark import DEV, test_families as make_test_families, plan
from consultas_ambientais.llm.privacy import Redactor
from consultas_ambientais.llm.client import GatewayError


@pytest.mark.parametrize('metric,unit,obs,expected,den',[
 ('area','km2',[(200,500)],'2.00',[]),
 ('area','m2',[(2,10)],'20000',[]),
 ('participacao','percentual',[(2,8)],'25',['8']),
 ('diferenca_liquida','ha',[(40,100),(10,100)],'-30',[]),
 ('reducao_liquida','ha',[(10,100),(40,100)],'0',[]),
 ('variacao_percentual','percentual',[(40,100),(10,100)],'-75',['40']),
 ('variacao_percentual','percentual',[(0,100),(10,100)],None,['0']),
 ('diferenca_pontos_percentuais','pontos_percentuais',[(20,100),(60,200)],'10',['100','200']),
])
def test_independent_formulas(metric,unit,obs,expected,den):
    r=calculate(metric,unit,obs)
    assert r['value']==expected and r['denominators_ha']==den
    if expected is None:assert r['undefined_reason']=='base_inicial_zero'


def test_ranking_ties_and_sign():
    rows=[{'territory_code':c,'value':v} for c,v in [('2400208','3'),('2400109','3'),('2400307','0'),('2400406','-5')]]
    assert [r['territory_code'] for r in order_ranking(rows,'reducao_liquida','desc',5)]==['2400109','2400208']


def test_cluster_bootstrap_pairs_preserved_reproducible():
    p=[{'family_id':'a','B':0,'C':1},{'family_id':'a','B':1,'C':0},{'family_id':'b','B':0,'C':1}]
    a=paired_bootstrap(p);b=paired_bootstrap(p)
    assert a==b and a['groups']==2 and a['replicas']==10000
    assert a['difference_C_minus_B']==pytest.approx(1/3) and a['ci95']==[0,1]
    assert paired_bootstrap(p[:1])['state']=='pendente'


def test_identical_conditions_zero_interval():
    p=[{'family_id':str(i),'B':i%2,'C':i%2} for i in range(10)]
    assert paired_bootstrap(p)['ci95']==[0,0]


def fixture_answer():
    p=plan('2400109')
    v={'territory_code':'2400109','years':[2015],'value':20.0,'unit':'ha','undefined_reason':None,'denominators_ha':[],'rank':None}
    a={'status':'respondida','plan':p,'values':[v],'clarification_field':None,'reason':'ok'}
    return a


def test_score_demands_semantics_not_only_numbers():
    a=fixture_answer();g=json.loads(json.dumps(a));leaves={'15':[15],'1':[3,4],'3':[3]};protocol=default_protocol()
    assert score(a,g,protocol,leaves)['correct']
    for field,val in [('unit','km2'),('years',[2025]),('territory_codes',['2400208']),('metric','diferenca_liquida')]:
        bad=json.loads(json.dumps(a));bad['plan'][field]=val
        assert not score(bad,g,protocol,leaves)['correct']
    a['values'][0]['value']=None
    assert not score(a,g,protocol,leaves)['correct']


def test_hierarchy_union_equivalence_and_no_duplicates():
    a=fixture_answer();g=json.loads(json.dumps(a))
    a['plan']['class_codes']=[1,3];g['plan']['class_codes']=[3,4]
    assert score(a,g,default_protocol(),{'1':[3,4],'3':[3],'4':[4]})['correct']


def test_clarification_field_and_technical_failure():
    g={'status':'precisa_esclarecimento','plan':None,'values':[],'clarification_field':'territorio'}
    a={**g,'clarification_field':'classe'}
    assert not score(a,g,default_protocol(),{})['correct']
    assert not score({'status':'erro_tecnico'},g,default_protocol(),{})['correct']


class MockClient:
    def __init__(self,outputs):self.outputs=list(outputs);self.messages=[]
    def chat(self,messages):
        self.messages.append(messages)
        text=self.outputs.pop(0)
        if isinstance(text,Exception):raise text
        return SimpleNamespace(text=text,elapsed_seconds=.01,usage={'total_tokens':5},model='mock_model',chat_requests=1)


def bundle():
    return {'context':{'available_scope':{'uf':'RN'}},'tables':[{'raw_area_ha':'4321.987'}],
            'table_columns':['raw_area_ha'],'truncated':False}


def test_AB_context_and_no_gold_in_repair():
    client=MockClient(['NOT JSON',json.dumps(fixture_answer())]);r=Redactor([])
    answer,attempts,_,_=run_baseline('B','area ambiental',bundle(),client,r)
    assert answer['status']=='respondida' and len(attempts)==2
    assert attempts[0]['state']=='invalida' and attempts[0]['output_sha256']
    assert '4321.987' in client.messages[0][1]['content']
    assert '20.0' not in client.messages[1][-1]['content']
    client=MockClient([json.dumps(fixture_answer())]);run_baseline('A','area ambiental',bundle(),client,r)
    assert '4321.987' not in json.dumps(client.messages)


def test_invalid_extra_field_and_gateway_no_body():
    a=fixture_answer();a['SQL']='secret_text'
    client=MockClient([json.dumps(a),json.dumps(a)])
    answer,attempts,_,_=run_baseline('B','area ambiental',bundle(),client,Redactor([]))
    assert answer['status']=='erro_tecnico' and len(attempts)==2
    assert 'secret_text' not in json.dumps(attempts) and 'extra_forbidden' in json.dumps(attempts)
    client=MockClient([GatewayError('falha_chat',503)])
    assert run_baseline('B','area ambiental',bundle(),client,Redactor([]))[0]['status']=='erro_tecnico'


def test_context_cannot_silently_truncate():
    client=MockClient([])
    assert run_baseline('B','area ambiental',bundle(),client,Redactor([]),max_context_bytes=1)[0]['status']=='erro_tecnico'
    assert not client.messages


def test_benchmark_families_split_and_counts():
    test=make_test_families()
    assert sum(len(x[3]) for x in DEV)==40 and sum(len(x[3]) for x in test)==120
    assert not {x[0] for x in DEV}&{x[0] for x in test}
    dev_codes={c for _,_,p,_ in DEV if isinstance(p,dict) for c in p['territory_codes']}
    test_codes={c for _,_,p,_ in test if isinstance(p,dict) for c in p['territory_codes']}
    assert not dev_codes&test_codes
    assert len({q for f in DEV+test for q in f[3]})==160


def test_reference_has_no_production_calculation_imports():
    p=Path(__file__).parents[1]/'src/consultas_ambientais/evaluation/reference.py'
    assert not any(s in p.read_text() for s in ['from ..queries','from ..storage','import QueryEngine','validate_intent('])
