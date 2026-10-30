"""Dados sinteticos/mocks da revisao: nao sao novos resultados de modelos."""
import copy,hashlib,json,sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from science.revision_v2 import diagnose,sensitivity,value_diagnosis
from science.provenance_v2 import check_chunk,bounded_body,database_comments
from science.writing_v2 import renumber_references


PROTOCOL={'absolute_tolerance':{'ha':'0.001'},'relative_tolerance':'0.000001'}
POLICY={'analysis_kind':'sintetica','sensitivity':{'bootstrap_replicas':10000,'seed':20271020}}


def row(status='respondida',value=10):
    return {'status':status,'plan':{'operation':'area'},'values':[{'territory_code':'2400109','years':[2015],
        'unit':'ha','value':value,'denominators_ha':[],'undefined_reason':None,'rank':None}] if status=='respondida' else []}


def record(cid,k,correct=True):
    return {'case_id':str(cid),'family_id':'familia_'+str(cid),'condition':k,'repeat':0,'observed':row(),
        'attempts':[{'number':1,'issues':[],'gateway_error':None}],
        'scores':{'correct':correct,'status':correct,'plan':True if correct else None,'values':True if correct else None,'clarification':None}}


def test_common_subset_uses_same_cases_and_strata_conserve_original_effect():
    cases={str(i):{'family_id':'familia_'+str(i)} for i in range(4)}
    rs=[record(i,k) for i in range(4) for k in 'BC'];index={(r['case_id'],r['condition']):r for r in rs}
    for cid,k in [('0','B'),('3','C')]:
        r=index[cid,k];r['observed']=row('erro_tecnico');r['scores'].update(correct=False,status=False,plan=None,values=None)
        r['attempts'][-1]['gateway_error']='texto_final_ausente'
    index['2','B']['observed']=row('dados_indisponiveis');index['2','B']['scores'].update(correct=False,status=False,plan=None,values=None)
    gold={cid:row() for cid in cases};result=sensitivity(rs,cases,gold,PROTOCOL,POLICY)
    common=result['paired_analyses'][0]
    assert common['case_ids']==['1','2'] and (common['B_correct'],common['C_correct'])==(1,2)
    assert common['paired']['difference_C_minus_B']==.5
    assert sum(r['net_correct_C_minus_B'] for r in result['technical_strata'])==1
    assert sum(r['contribution_to_full_difference'] for r in result['technical_strata'])==.25
    assert sum(r['cases'] for r in result['technical_strata'])==4
    assert common['conditioned_on_observed_outcome'] and result['primary_scores_changed'] is False
    repeated=copy.deepcopy(index['0','B']);repeated['repeat']=1
    assert sensitivity(rs+[repeated],cases,gold,PROTOCOL,POLICY)==result


def test_terminal_issue_generic_value_error_remains_unknown():
    r=record(0,'B',False);r['observed']=row('erro_tecnico')
    r['attempts'][0]['issues']=[{'code':'value_error'}]
    assert diagnose(r,row(),PROTOCOL)=='rejeicao_contrato_indeterminada'
    r['attempts'][0]['issues']=[{'code':'anos_divergem_da_pergunta'}]
    assert diagnose(r,row(),PROTOCOL)=='rejeicao_semantica'
    r['attempts'].append({'gateway_error':'texto_final_ausente','issues':[]})
    assert diagnose(r,row(),PROTOCOL)=='retorno_textual_ausente'


def test_number_error_requires_matching_plan_status_and_result_structure():
    r=record(0,'B',False);r['scores'].update(status=True,plan=True,values=False)
    r['observed']=row(value=11)
    assert diagnose(r,row(),PROTOCOL)=='erro_numerico_isolavel'
    r['scores']['plan']=False
    assert diagnose(r,row(),PROTOCOL)=='erro_semantico_plano'
    r['scores']['plan']=True;r['observed']['values'][0]['unit']='km2'
    assert diagnose(r,row(),PROTOCOL)=='erro_estrutura_resultado'
    assert value_diagnosis(row(value=10.00001),row(),PROTOCOL)=='outro_indeterminado'


@pytest.mark.parametrize('problem',['none','status200','wrong_range','wrong_generation','truncated','oversize','hash_mismatch'])
def test_official_range_is_bounded_versioned_and_compared_to_historical_hash(problem):
    raw=b'abcde';expected=hashlib.sha256(raw).hexdigest()
    class Response:
        status_code=200 if problem=='status200' else 206
        headers={'Content-Range':'bytes 0-4/100','x-goog-generation':'123'}
        consumed=False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,size):
            self.consumed=True
            yield {'truncated':b'ab','oversize':b'abcdef','hash_mismatch':b'xxxxx'}.get(problem,raw)
    response=Response();response.headers=dict(response.headers)
    if problem=='wrong_range':response.headers['Content-Range']='bytes 1-5/100'
    if problem=='wrong_generation':response.headers['x-goog-generation']='124'
    class Session:
        def get(self,url,**kwargs):
            assert kwargs['verify'] is True and kwargs['stream'] is True
            assert kwargs['params']['generation']=='123' and kwargs['headers']['If-Match']=='test-etag'
            return response
    result=check_chunk('https://exemplo.invalid/mapa.tif',{'generation':'123','etag':'test-etag','size':100},
        {'offset':0,'bytes':5,'sha256':expected},Session())
    if problem=='none':assert result['match'] is True and result['state']=='verificado'
    elif problem=='hash_mismatch':assert result['match'] is False and result['state']=='divergente'
    else:assert result['state']=='indisponivel'
    if problem in ['status200','wrong_range','wrong_generation']:assert not response.consumed


def test_reference_numbering_is_by_occurrence_before_example_insertion():
    draft={'blocks':[{'kind':'paragraph','text':'Contexto [1], fonte oficial [WEB] e método [2].'},
        {'kind':'reference','text':'[1] Fonte inicial.'},{'kind':'reference','text':'[2] Metodo.'}]}
    renumber_references(draft,'https://exemplo.invalid/portal')
    assert draft['blocks'][0]['text']=='Contexto [1], fonte oficial [2] e método [3].'
    assert draft['blocks'][2]['text'].startswith('[2] Projeto MapBiomas.')
    assert draft['blocks'][3]['text']=='[3] Metodo.'


def test_missing_database_configuration_does_not_attempt_a_connection(tmp_path,monkeypatch):
    import dotenv,psycopg2
    monkeypatch.setattr(dotenv,'dotenv_values',lambda *a,**kw:{})
    def forbidden(**kwargs):raise AssertionError('nao deveria conectar')
    monkeypatch.setattr(psycopg2,'connect',forbidden)
    result=database_comments(tmp_path,tmp_path)
    assert result['reason']=='configuracao_ausente' and not result['read_only_confirmed']
    assert (tmp_path/'metadados_malha.json').is_file()


def test_database_comment_inspection_enforces_readonly_and_rollback(tmp_path,monkeypatch):
    import dotenv,psycopg2
    monkeypatch.setattr(dotenv,'dotenv_values',lambda *a,**kw:{'SOURCE_PG_'+k:'mock' for k in ['HOST','DATABASE','USER','PASSWORD']})
    calls=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,parameters=None):calls.append((sql,parameters))
        def fetchone(self):return ('on',)
        def fetchall(self):return [('municipios',None,'geom',None),('uf',None,'geom',None)]
    class Connection:
        def set_session(self,**kwargs):assert kwargs['readonly'] is True and kwargs['autocommit'] is False
        def cursor(self):return Cursor()
        def rollback(self):calls.append('rollback')
        def close(self):calls.append('close')
    def connect(**kwargs):
        assert 'default_transaction_read_only=on' in kwargs['options'] and 'statement_timeout=10000' in kwargs['options']
        return Connection()
    monkeypatch.setattr(psycopg2,'connect',connect)
    result=database_comments(tmp_path,tmp_path)
    assert result['state']=='verificado' and result['read_only_confirmed']
    assert calls[-2:]==['rollback','close'] and len(calls)==4
    assert calls[1][1]==('sbsr','municipios','uf')
    assert all(t['table_comment'] is None and t['edition_identified'] is False for t in result['tables'])
