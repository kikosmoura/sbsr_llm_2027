import json
import subprocess
import shutil
from pathlib import Path

import pytest

from consultas_ambientais.cli import main
from consultas_ambientais.contracts import Check,CheckState,DiagnosticReport
from consultas_ambientais.semantics.catalog import ClassCatalog,CatalogError
from consultas_ambientais.semantics.capabilities import from_diagnostic
from consultas_ambientais.semantics.models import TerritoryReference
from consultas_ambientais.sources.territories import export_territory_catalog
from consultas_ambientais.settings import DatabaseSettings
from test_semantic_territories import territories


def test_real_diagnostic_contract_does_not_invent_statistics(tmp_path,territories):
    catalog=ClassCatalog.load()
    checks=[Check(component='raster_2015',state=CheckState.VERIFIED,outcome='executado',details={
        'year':2015,'range_verified':True,'metadata':{'year':2015,'collection':11,'nodata':None},
        'window':{'state':'verificado','value':0}}),
        Check(component='raster_2016',state=CheckState.PENDING,outcome='nao_executado')]
    path=tmp_path/'report.json';path.write_text(DiagnosticReport(checks=checks).model_dump_json())
    caps=from_diagnostic(path,catalog,territories)
    assert caps.available_raster_years==[2015]
    assert caps.engine_ready is False and caps.materializations==[]
    assert caps.observed_samples[0]['diagnostic']['unknown_codes']==[0]
    assert caps.observed_samples[0]['inventory_complete'] is False


def test_exporter_never_updates_or_reads_geometry():
    events=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):events.append('cursor_closed')
        def execute(self,query):
            assert events[0]=='read_only'
            assert query.startswith(('SELECT','SHOW'))
            assert 'geom' not in query.lower()
            self.query=query;self.done=False
        def fetchone(self):return ('on',)
        def fetchmany(self,size):
            if self.done:return []
            self.done=True
            return [('24','Rio Grande do Norte','RN','24')] if 'FROM sbsr.uf' in self.query else [('2410900','Riachuelo','RN','24')]
    class Connection:
        def set_session(self,**kwargs):
            assert kwargs['readonly'] is True and kwargs['isolation_level']=='REPEATABLE READ'
            events.append('read_only')
        def cursor(self):return Cursor()
        def rollback(self):events.append('rollback')
        def close(self):events.append('closed')
    config=DatabaseSettings(host='private.example.test',database='test-db',user='test-user',password='test-only-secret')
    result=export_territory_catalog(config,connect=lambda **kwargs:Connection())
    assert result.read_only_confirmed is True and len(result.entries)==2
    assert events[-2:]==['rollback','closed']
    assert 'test-only-secret' not in result.model_dump_json()


def test_exporter_error_is_redacted():
    def fail(**kwargs):raise RuntimeError('private.example.test test-only-secret')
    config=DatabaseSettings(host='private.example.test',database='test-db',user='test-user',password='test-only-secret')
    with pytest.raises(CatalogError) as exc:export_territory_catalog(config,connect=fail)
    assert str(exc.value)=='falha_conexao'


def test_cli_catalog_schema_and_ambiguity(capsys):
    assert main(['schema','intent'])==0
    schema=json.loads(capsys.readouterr().out)
    assert schema['additionalProperties'] is False
    assert 'territories' in schema['properties'] and 'classes' in schema['properties']
    assert main(['catalog','resolve','--term','floresta'])==2
    assert json.loads(capsys.readouterr().out)['status']=='precisa_esclarecimento'
    assert main(['catalog','audit-codes','0','3'])==2
    assert json.loads(capsys.readouterr().out)['unknown_codes']==[0]


def test_lowercase_uf_is_normalized(territories):
    result=territories.resolve(TerritoryReference(name='Santa Cruz',uf=' rn '))
    assert result.selected_codes==['2411205']


def test_missing_catalog_is_technical_error_not_ambiguous_request(tmp_path,capsys):
    path=tmp_path/'nonexistent.json'
    assert main(['territories','resolve','--catalog',str(path),'--name','Santa Cruz'])==2
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='erro_tecnico'
    assert str(path) not in json.dumps(result)


def test_runtime_data_ignored_but_packaged_catalog_is_versionable(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    shutil.copyfile(Path(__file__).parents[1]/'.gitignore',tmp_path/'.gitignore')
    def ignored(name):
        return subprocess.run(['git','-c','core.excludesFile=/dev/null','check-ignore','--no-index',name],
                              cwd=tmp_path,capture_output=True).returncode==0
    assert ignored('data/territories_v1.json')
    assert ignored('reports/diagnostico_rede.json')
    assert ignored('.env')
    assert not ignored('.env.example')
    assert not ignored('src/consultas_ambientais/semantics/data/mapbiomas_col11_v1/catalog.json')


def test_invalid_territorial_selector_is_clarification(tmp_path,capsys,territories):
    path=tmp_path/'territories.json';path.write_text(territories.data.model_dump_json())
    assert main(['territories','resolve','--catalog',str(path),'--code','invalid'])==2
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='precisa_esclarecimento' and result['reason']=='seletor_territorial_invalido'
