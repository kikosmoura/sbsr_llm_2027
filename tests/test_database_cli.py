import json

from consultas_ambientais.cli import main
from consultas_ambientais.settings import DatabaseSettings
from consultas_ambientais.sources.postgis import diagnose_database,suspicious_encoding


def test_database_error_redacted_and_settings_readonly():
    seen={}
    def broken_connect(**kw):
        seen.update(kw)
        raise RuntimeError("private-host test-only-secret")
    settings=DatabaseSettings(host="private.example.test",database="private-db",user="private-user",password="test-only-secret")
    report=diagnose_database(settings,connect=broken_connect)
    output=report.model_dump_json()
    assert "private-host" not in output and "test-only-secret" not in output
    assert "default_transaction_read_only=on" in seen["options"]
    assert "statement_timeout=" in seen["options"]


def test_missing_db_never_calls_connect():
    def fail(**kwargs):raise AssertionError("must not connect")
    assert diagnose_database(DatabaseSettings(),connect=fail).state.value=="pendente"


def test_encoding_is_only_suspected():
    assert suspicious_encoding("SÃ£o Paulo do Potengi")
    assert not suspicious_encoding("São Paulo do Potengi")


def test_cli_help(capsys):
    try:main(["--help"])
    except SystemExit as e:assert e.code==0
    assert "diagnose" in capsys.readouterr().out


def test_diagnostic_no_flags_has_no_integrations(tmp_path,capsys):
    path=tmp_path/"diagnostic.json"
    assert main(["diagnose","--output",str(path)])==0
    report=json.loads(path.read_text())
    assert all(c["state"]=="pendente" and c["outcome"]=="nao_solicitado" for c in report["checks"])
    assert path.stat().st_mode & 0o777 == 0o600


def test_schema_export(capsys):
    assert main(["schema","plan"])==0
    assert json.loads(capsys.readouterr().out)["additionalProperties"] is False


def test_database_transaction_readonly_and_public_samples():
    events=[]
    class Cursor:
        def execute(self,query,params=None):
            assert events[0]=="readonly"
            assert query.strip().split()[0] in {"SELECT","SHOW"}
            assert not any(x in query.upper() for x in ["UPDATE ","DELETE ","INSERT ","CREATE "])
            self.query=query;events.append("query")
        def fetchone(self):
            q=self.query
            if q.startswith("SHOW"):return ("on",)
            if "server_encoding" in q:return ("UTF8","UTF8")
            if "convert_to" in q:
                name="SÃ£o Paulo do Potengi"
                return (name,name.encode('utf8').hex())
            if "count(DISTINCT" in q:return (1,0,0,0,0,0)
            return (0,)
        def fetchall(self):
            q=self.query
            if "information_schema" in q:
                return [(n,"USER-DEFINED" if n=="geom" else "text","geometry" if n=="geom" else "text")
                        for n in ["cd_mun","nm_mun","nm_rgi","cd_uf","nm_uf","geom"]]
            if "ST_SRID" in q:return [(4674,"MULTIPOLYGON",1)]
            return [("2410900","Riachuelo","24")]
        def close(self):events.append("cursor_closed")
    class Connection:
        def set_session(self,**kwargs):
            assert kwargs=={"readonly":True,"autocommit":False,"isolation_level":"REPEATABLE READ"}
            events.append("readonly")
        def cursor(self):return Cursor()
        def rollback(self):events.append("rollback")
        def close(self):events.append("closed")
    config=DatabaseSettings(host="private.example.test",database="test-db",user="test-user",password="test-only-secret")
    report=diagnose_database(config,connect=lambda **kwargs:Connection())
    assert report.state.value=="verificado"
    assert report.details["read_only_confirmed"] is True
    assert events[-2:]==["rollback","closed"]
    assert report.details["tables"]["municipios"]["geometry_groups"][0]["srid"]==4674
    observation=report.details["tables"]["municipios"]["encoding_observation"]
    assert observation['server_utf8_matches_returned_string'] is True
    assert observation['reversible_candidate']=="São Paulo do Potengi"
    assert observation['repair_applied'] is False
    assert "private.example.test" not in report.model_dump_json()
