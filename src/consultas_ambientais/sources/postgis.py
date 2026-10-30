"""Consultas fixas ao cadastro. Nenhum SQL recebido do usuario e executado."""
import re
from ..contracts import Check, CheckState
from ..errors import network_issue
from ..settings import DatabaseSettings


TABLES={"municipios":{"code":"cd_mun","name":"nm_mun","digits":7},
        "uf":{"code":"cd_uf","name":"nm_uf","digits":2}}


def suspicious_encoding(text):
    return isinstance(text,str) and any(s in text for s in ("Ã", "Â", "�"))


def diagnose_database(settings: DatabaseSettings, sample_size=5, connect=None):
    if not settings.configured:
        return Check(component="postgis",state=CheckState.PENDING,outcome="configuracao_ausente")
    if connect is None:
        try:
            import psycopg2
        except ImportError:
            return Check(component="postgis",state=CheckState.PENDING,outcome="dependencia_psycopg2_ausente")
        connect=psycopg2.connect
    conn=None
    details={"territorial_edition":None,"edition_status":"desconhecida","tables":{}}
    try:
        conn=connect(host=settings.host.get_secret_value(),port=settings.port,
                     dbname=settings.database.get_secret_value(),user=settings.user.get_secret_value(),
                     password=settings.password.get_secret_value(),sslmode=settings.sslmode,
                     connect_timeout=settings.connect_timeout,
                     options=f"-c default_transaction_read_only=on -c statement_timeout={settings.statement_timeout_ms} -c lock_timeout={settings.lock_timeout_ms}")
        conn.set_session(readonly=True,autocommit=False,isolation_level="REPEATABLE READ")
        cur=conn.cursor()
        try:
            cur.execute("SHOW transaction_read_only")
            if cur.fetchone()[0]!="on":
                return Check(component="postgis",state=CheckState.UNAVAILABLE,outcome="transacao_nao_somente_leitura")
            cur.execute("SELECT current_setting('server_encoding'), current_setting('client_encoding')")
            details["encodings"]=list(cur.fetchone())
            for table,spec in TABLES.items():
                cur.execute("SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",("sbsr",table))
                columns=[{"name":a,"type":b,"udt":c} for a,b,c in cur.fetchall()]
                required={spec["code"],spec["name"],"cd_uf","geom"}
                if not required<={c["name"] for c in columns}:
                    details["tables"][table]={"columns":columns,"state":"colunas_ausentes"}
                    continue
                # Identificadores abaixo sao constantes deste modulo, nunca entrada livre.
                code,name=spec["code"],spec["name"]
                query=f"""SELECT count(*), count({code})-count(DISTINCT {code}),
                    count(*) FILTER (WHERE {code} IS NULL OR {code}::text !~ %s),
                    count(*) FILTER (WHERE geom IS NULL),
                    count(*) FILTER (WHERE ST_IsEmpty(geom)),
                    count(*) FILTER (WHERE NOT ST_IsValid(geom))
                    FROM sbsr.{table}"""
                cur.execute(query,("^[0-9]{"+str(spec["digits"])+"}$",))
                n,dup,bad,nullgeom,empty,invalid=cur.fetchone()
                cur.execute(f"SELECT ST_SRID(geom), GeometryType(geom), count(*) FROM sbsr.{table} WHERE geom IS NOT NULL GROUP BY 1,2 ORDER BY 1,2")
                geometries=[{"srid":r[0],"geometry_type":r[1],"rows":r[2]} for r in cur.fetchall()]
                cur.execute(f"SELECT {code}::text, {name}, cd_uf::text FROM sbsr.{table} ORDER BY {code} LIMIT %s",(sample_size,))
                samples=[{"code":r[0],"name":r[1],"uf_code":r[2],"encoding_suspect":suspicious_encoding(r[1])} for r in cur.fetchall()]
                suspect=None
                for c in columns:
                    if c["name"].startswith("nm_") and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",c["name"]):
                        cur.execute(f"SELECT count(*) FROM sbsr.{table} WHERE {c['name']} ~ %s",("[ÃÂ�]",))
                        count=cur.fetchone()[0]
                        if suspect is None:suspect={}
                        suspect[c["name"]]=count
                details["tables"][table]={"columns":columns,"rows":n,"duplicate_codes":dup,
                    "invalid_codes":bad,"null_geometries":nullgeom,"empty_geometries":empty,
                    "invalid_geometries":invalid,"geometry_groups":geometries,"samples":samples,
                    "encoding_suspect_counts":suspect,"encoding_repair_applied":False}
                if table=="municipios" and "nm_rgi" in {c["name"] for c in columns}:
                    cur.execute("SELECT nm_rgi, encode(convert_to(nm_rgi, 'UTF8'), 'hex') FROM sbsr.municipios WHERE cd_mun::text=%s LIMIT 1",("2410900",))
                    observation=cur.fetchone()
                    if observation and isinstance(observation[0],str):
                        value,server_hex=observation
                        candidate=None
                        try:
                            decoded=value.encode("latin1").decode("utf8")
                            if decoded!=value and decoded.encode("utf8").decode("latin1")==value:
                                candidate=decoded
                        except (UnicodeError,ValueError):pass
                        details["tables"][table]["encoding_observation"]={
                            "field":"nm_rgi","municipality_code":"2410900",
                            "suspect_in_returned_unicode":suspicious_encoding(value),
                            "server_utf8_matches_returned_string":server_hex==value.encode("utf8").hex(),
                            "reversible_candidate":candidate,"repair_applied":False}
            if all(details["tables"].get(t,{}).get("rows") is not None for t in TABLES):
                cur.execute("""SELECT count(*) FROM sbsr.municipios m LEFT JOIN sbsr.uf u
                    ON m.cd_uf::text=u.cd_uf::text WHERE u.cd_uf IS NULL""")
                details["municipalities_without_uf"]=cur.fetchone()[0]
                cur.execute("""SELECT count(*) FROM sbsr.municipios WHERE
                    left(cd_mun::text,2) IS DISTINCT FROM cd_uf::text""")
                details["municipality_prefix_mismatches"]=cur.fetchone()[0]
            details["read_only_confirmed"]=True
            details["encoding_note"]="Heuristica identifica suspeitas; nao comprova causa nem corrige valores."
            return Check(component="postgis",state=CheckState.VERIFIED,
                         outcome="consultas_executadas",details=details)
        finally:
            cur.close()
    except Exception as e:
        # Mensagens libpq incluem host/usuario. Nunca propagadas.
        state=CheckState.UNAVAILABLE
        category=network_issue(e) if conn is None else "falha_consulta"
        if type(e).__name__=="QueryCanceled":category="timeout_consulta"
        if getattr(e,"pgcode",None)=="42P01":category="tabela_ausente"
        if getattr(e,"pgcode",None)=="42883":category="funcao_postgis_indisponivel"
        return Check(component="postgis",state=state,outcome=category,details=details)
    finally:
        if conn is not None:
            for cleanup in (conn.rollback,conn.close):
                try:cleanup()
                except Exception:pass  # Falhas libpq no encerramento tambem nao expõem conexao.
