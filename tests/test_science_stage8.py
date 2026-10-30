"""Consolidacao: algebra sintetica e privacidade; nao sao dados cientificos reais."""
import sys,json,copy
from pathlib import Path
from zipfile import ZipFile
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from science.metrics import derive,crosscheck,error_type
from science.publication import scan_text
from science.writing import export_tables
from science.audit import require
from obter_template_etapa8 import obtain


def samples():
    records=[];cases={}
    for i in range(4):
        cid=str(i);cases[cid]={'case_id':cid,'family_id':'f'+str(i//2),'territory_codes':['2400109'],'dependencies':[],'expected_decision':'respondida'}
        for condition in 'ABC':
            correct=condition=='C' or (condition=='B' and i==0)
            scores={'correct':correct,'status':correct,'plan':None,'values':None,'clarification':None}
            records.append({'case_id':cid,'family_id':cases[cid]['family_id'],'condition':condition,'repeat':0,'scores':scores,
                'observed':{'status':'respondida' if correct else 'erro_tecnico','reason':'sintetico'},'latency_seconds':float(i+1),
                'attempts':[{'number':1,'state':'valida','usage':{'prompt_tokens':3,'completion_tokens':2,'total_tokens':5},'latency_seconds':1}]})
    return records,cases,{'bootstrap_replicas':10000,'seed':20271019,'minimum_territory_groups':10}


def test_consolidation_uses_case_denominator_and_excludes_repeats():
    rs,c,p=samples();rep=copy.deepcopy(rs[0]);rep['repeat']=1;rs.append(rep)
    m=derive(rs,c,p)
    assert [r['correct'] for r in m['conditions']]==[0,1,4]
    assert m['paired_C_minus_B']['difference_C_minus_B']==.75
    assert m['paired_C_minus_B']['groups']==2 and m['paired_C_minus_B']['cases']==4
    assert len(m['repeats'])==1 and m['repeats'][0]['same_answer']
    assert all(r['tokens_observed']['total_tokens']==20 for r in m['conditions'])


def test_technical_errors_are_separate_from_deliberate_abstention():
    rs,c,p=samples();rs[0]['observed']['status']='dados_indisponiveis'
    row=derive(rs,c,p)['conditions'][0]
    assert row['abstention_nontechnical']==1 and row['technical_errors']==3
    assert row['nonanswer_including_technical']==4 and row['cases']==4


def test_error_taxonomy_no_unfounded_gateway_cause():
    rs,_,_=samples();r=rs[0];r['attempts'][0]['gateway_error']='texto_final_ausente'
    assert error_type(r)=='texto_final_ausente'
    r['attempts'][0]['gateway_error']=None;r['attempts'][0]['issues']=[{'code':'json_invalido'}]
    assert error_type(r)=='json_invalido_apos_limite'
    r['scores'].update(status=True,clarification=False);r['observed']['status']='precisa_esclarecimento'
    assert error_type(r)=='esclarecimento_incorreto'


def test_empty_usage_not_estimated_and_csv_keeps_raw_values(tmp_path):
    rs,c,p=samples();rs[0]['attempts'][0]['usage']=None
    m=derive(rs,c,p);export_tables(tmp_path,m)
    assert m['conditions'][0]['usage_missing_attempts']==1
    assert m['conditions'][0]['tokens_observed']['total_tokens']==15
    import csv
    row=next(csv.DictReader((tmp_path/'intervals.csv').open()))
    assert float(row['difference_pp'])==100*m['paired_C_minus_B']['difference_C_minus_B']
    assert m['conditions'][0]['cost'] is None


@pytest.mark.parametrize('kind',['path','ip','secret','signed','file_uri'])
def test_scanner_rejects_private_material_without_echoing_values(kind):
    value={'path':'/'.join(['','home','simulacao','arquivo']),
           'ip':'.'.join(['10','9','8','7']), 'secret':'somente_mock_de_teste',
           'signed':'https://exemplo.invalid/a?X-Amz-'+'Signature=simulado',
           'file_uri':'file:'+'///tmp/material_local'}[kind]
    hits=scan_text(value,[value] if kind=='secret' else [])
    assert hits and value not in json.dumps(hits)


def test_scanner_allows_public_urls_and_loopback():
    assert not scan_text('https://brasil.mapbiomas.org/faq/ '+'.'.join(['127','0','0','1']))


def test_consistency_guard_fails_closed():
    with pytest.raises(ValueError,match='hash_incoerente'):require(False,'hash_incoerente')


def test_template_cache_does_not_make_network_call_or_overwrite(tmp_path):
    import hashlib
    output=tmp_path/'official.odt';output.write_bytes(b'synthetic template')
    template={'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
    assert obtain(template,output,None)=='cache_verificado'
    with pytest.raises(ValueError,match='arquivo_existente_divergente'):
        obtain({'sha256':'0'*64},output,None)
    assert output.read_bytes()==b'synthetic template'


@pytest.mark.parametrize('content,reason',[(b'changed','revisao_diferente'),(b'x'*(1024*1024+1),'limite_de_bytes')])
def test_template_download_rejects_other_revision_and_large_body(tmp_path,content,reason):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
        def iter_content(self,size):yield content
    class Session:
        def get(self,url,**kwargs):
            assert kwargs['verify'] is True and kwargs['stream'] is True
            return Response()
    target=tmp_path/'official.odt'
    with pytest.raises(ValueError,match=reason):obtain({'url':'https://exemplo.invalid/template','sha256':'0'*64},target,Session())
    assert not target.exists()


def test_odt_drops_original_metadata_and_settings(tmp_path):
    from science.documents import make,NS,node,serialize
    from lxml import etree as E
    template=tmp_path/'model.odt';content=node('office:document-content');content.append(node('office:automatic-styles'));content.append(node('office:font-face-decls'));body=node('office:body');body.append(node('office:text'));content.append(body)
    styles=node('office:document-styles');master=node('style:master-page');master.append(node('text:p',text='MODELO SINTETICO'));styles.append(master)
    with ZipFile(template,'w') as z:
        z.writestr('content.xml',serialize(content));z.writestr('styles.xml',serialize(styles));z.writestr('meta.xml','AUTORIA SINTETICA');z.writestr('settings.xml','PREFERENCIA PRIVADA SINTETICA')
    draft={'title':'TITULO','authors':'[A PREENCHER]','draft_notice':'RASCUNHO','abstract_pt':'Resumo de teste','abstract_en':'Test abstract','keywords_pt':'teste','keywords_en':'test','blocks':[{'kind':'heading','text':'1. TESTE'},{'kind':'paragraph','text':'Conteudo sintetico sem pessoas.'}]}
    output=tmp_path/'result.odt';make(draft,template,tmp_path,output)
    with ZipFile(output) as z:
        text=''.join(z.read(n).decode() for n in z.namelist() if n.endswith('.xml'))
        assert 'AUTORIA SINTETICA' not in text and 'MODELO SINTETICO' not in text
        assert 'settings.xml' not in z.namelist() and '[A PREENCHER]' in text
        meta=E.fromstring(z.read('meta.xml'));assert meta.find('.//dc:creator',NS) is None
