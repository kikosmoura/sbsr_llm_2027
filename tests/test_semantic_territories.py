import pytest

from consultas_ambientais.semantics.catalog import CatalogError
from consultas_ambientais.semantics.models import TerritoryCatalogData,TerritoryEntry,TerritoryReference
from consultas_ambientais.semantics.normalization import encoding_search_alias,normalize
from consultas_ambientais.semantics.territories import TerritoryCatalog,territory_digest


@pytest.fixture
def territories():
    # Fixture sintetica: codigos com formato valido, sem afirmar cadastro oficial.
    rows=[('uf','24','Rio Grande do Norte','RN','24'),('uf','35','São Paulo','SP','35'),
          ('municipio','2410900','Riachuelo','RN','24'),('municipio','2408102','Natal','RN','24'),
          ('municipio','2411205','Santa Cruz','RN','24'),('municipio','3500001','Santa Cruz','SP','35'),
          ('municipio','3500002','SÃ£o Miguel','SP','35')]
    entries=[]
    for kind,code,name,uf,uf_code in rows:
        alias=encoding_search_alias(name)
        entries.append(TerritoryEntry(kind=kind,code=code,name_original=name,uf=uf,uf_code=uf_code,
                                     search_aliases=[alias] if alias else [],alias_notes=['candidato_reversivel'] if alias else []))
    data=TerritoryCatalogData(read_only_confirmed=False,entries=entries,content_sha256='0'*64)
    data.content_sha256=territory_digest(data)
    return TerritoryCatalog(data)


def test_normalization_preserves_original(territories):
    result=territories.resolve(TerritoryReference(name='sao miguel',uf='SP'))
    assert result.status=='resolvido' and result.selected_codes==['3500002']
    assert result.candidates[0]['name_original']=='SÃ£o Miguel'
    assert result.notes
    assert normalize('São-Paulo')==normalize('sao paulo')


def test_homonyms_require_uf(territories):
    ambiguous=territories.resolve(TerritoryReference(name='Santa Cruz',kind='municipio'))
    assert ambiguous.status=='precisa_esclarecimento' and len(ambiguous.candidates)==2
    assert territories.resolve(TerritoryReference(name='Santa Cruz/RN',kind='municipio')).selected_codes==['2411205']


def test_code_uf_and_name_must_agree(territories):
    assert territories.resolve(TerritoryReference(code='2410900',uf='SP')).status=='precisa_esclarecimento'
    assert territories.resolve(TerritoryReference(code='2410900',name='Natal')).status=='precisa_esclarecimento'
    assert territories.resolve(TerritoryReference(name='Natal/SP')).status=='precisa_esclarecimento'
    assert territories.resolve(TerritoryReference(name='Natal/RN',uf='SP')).reason=='ufs_informadas_divergentes'


def test_approximate_matches_never_autoselect(territories):
    result=territories.resolve(TerritoryReference(name='Nata',uf='RN'))
    assert result.status=='precisa_esclarecimento' and result.match_kind=='aproximado'
    assert result.selected_codes==[]


def test_unknown_and_uf_sigla(territories):
    assert territories.resolve(TerritoryReference(code='9999999')).status=='nao_encontrado'
    assert territories.resolve(TerritoryReference(kind='uf',uf='RN')).selected_codes==['24']
    assert territories.municipality_universe('RN')=={'2410900','2408102','2411205'}


def test_repair_candidate_is_conservative():
    assert encoding_search_alias('São Paulo') is None
    assert encoding_search_alias('SÃ£o Paulo')=='São Paulo'
    assert encoding_search_alias('NOME Ã') is None


def test_changed_snapshot_hash_is_rejected(territories):
    data=territories.data.model_copy(deep=True)
    data.entries[0].name_original='changed'
    with pytest.raises(CatalogError,match='hash_catalogo'):TerritoryCatalog(data)
