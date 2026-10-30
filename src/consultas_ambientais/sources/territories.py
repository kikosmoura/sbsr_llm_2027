"""Extracao somente leitura de codigos e nomes; nao consulta geometria ou segredos."""
from ..errors import network_issue
from ..semantics.catalog import CatalogError
from ..semantics.models import TerritoryCatalogData, TerritoryEntry
from ..semantics.normalization import encoding_search_alias
from ..semantics.territories import TerritoryCatalog, territory_digest


def export_territory_catalog(settings,connect=None,max_rows=20000):
    if not settings.configured:raise CatalogError("configuracao_postgis_ausente")
    if connect is None:
        try:import psycopg2
        except ImportError:raise CatalogError("dependencia_psycopg2_ausente") from None
        connect=psycopg2.connect
    conn=None
    try:
        conn=connect(host=settings.host.get_secret_value(),port=settings.port,
                     dbname=settings.database.get_secret_value(),user=settings.user.get_secret_value(),
                     password=settings.password.get_secret_value(),sslmode=settings.sslmode,
                     connect_timeout=settings.connect_timeout,
                     options=f"-c default_transaction_read_only=on -c statement_timeout={settings.statement_timeout_ms} -c lock_timeout={settings.lock_timeout_ms}")
        conn.set_session(readonly=True,autocommit=False,isolation_level="REPEATABLE READ")
        entries=[]
        with conn.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            if cur.fetchone()[0]!="on":raise CatalogError("transacao_nao_somente_leitura")
            for kind,query in [
                ("uf","SELECT cd_uf::text, nm_uf, sigla_uf, cd_uf::text FROM sbsr.uf ORDER BY cd_uf"),
                ("municipio","SELECT cd_mun::text, nm_mun, sigla_uf, cd_uf::text FROM sbsr.municipios ORDER BY cd_mun"),
            ]:
                cur.execute(query)
                while True:
                    rows=cur.fetchmany(512)
                    if not rows:break
                    for code,name,uf,uf_code in rows:
                        candidate=encoding_search_alias(name)
                        entries.append(TerritoryEntry(kind=kind,code=code,name_original=name,uf=uf,uf_code=uf_code,
                            search_aliases=[candidate] if candidate else [],
                            alias_notes=["Alias de busca candidato por conversao reversivel Latin-1/UTF8; nao altera nome_original nem a origem."] if candidate else []))
                        if len(entries)>max_rows:raise CatalogError("limite_de_atributos_territoriais")
        data=TerritoryCatalogData(read_only_confirmed=True,entries=entries,content_sha256="0"*64)
        data.content_sha256=territory_digest(data)
        TerritoryCatalog(data)
        return data
    except CatalogError:raise
    except Exception as e:
        raise CatalogError(network_issue(e) if conn is None else "falha_leitura_catalogo_territorial") from None
    finally:
        if conn:
            for action in (conn.rollback,conn.close):
                try:action()
                except Exception:pass
