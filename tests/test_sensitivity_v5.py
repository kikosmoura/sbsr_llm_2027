"""Contrato da sensibilidade com fonte sintetica; sem gateway."""
import sys,json
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from science import sensitivity_v5 as s
from consultas_ambientais.evaluation.common import save,read,sha

def source(tmp_path,monkeypatch):
    root=tmp_path/'root';base=root/'benchmarks/controle_contrato_v1';base.mkdir(parents=True)
    save(base/'protocol.json',{'version':'mock','llm_max_tokens':2048,'temperature':0,'max_repairs':1})
    save(base/'inputs.json',{'synthetic':True});save(base/'freeze.json',{'files':{n:sha(base/n) for n in ['inputs.json','protocol.json']}})
    monkeypatch.setattr(s,'verify_original_control',lambda *a:'a'*64);monkeypatch.setattr(s,'runtime',lambda *a:{'mock':True})
    target=tmp_path/'new';s.prepare(root,target,tmp_path);return root,target

def test_changes_only_budget_and_analysis_metadata(tmp_path,monkeypatch):
    root,target=source(tmp_path,monkeypatch);s.verify(target,root,tmp_path)
    assert read(target/'protocol.json')['llm_max_tokens']==4096
    assert (target/'inputs.json').read_bytes()==(root/'benchmarks/controle_contrato_v1/inputs.json').read_bytes()

@pytest.mark.parametrize('key,value',[('temperature',1),('max_repairs',2)])
def test_rehashed_other_parameter_change_still_rejected(tmp_path,monkeypatch,key,value):
    root,target=source(tmp_path,monkeypatch);v=read(target/'protocol.json');v[key]=value;save(target/'protocol.json',v)
    f=read(target/'freeze.json');f['files']['protocol.json']=sha(target/'protocol.json');save(target/'freeze.json',f)
    with pytest.raises(ValueError,match='outros_parametros_alterados'):s.verify(target,root,tmp_path)

def test_rehashed_context_change_still_rejected(tmp_path,monkeypatch):
    root,target=source(tmp_path,monkeypatch);save(target/'inputs.json',{'synthetic':'changed'})
    f=read(target/'freeze.json');f['files']['inputs.json']=sha(target/'inputs.json');save(target/'freeze.json',f)
    with pytest.raises(ValueError,match='contexto_ou_criterios_alterados'):s.verify(target,root,tmp_path)
