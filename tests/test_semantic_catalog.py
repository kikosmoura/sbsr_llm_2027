from pathlib import Path
import shutil

import pytest

from consultas_ambientais.semantics.catalog import ClassCatalog,CatalogError,build_catalog

DATA=Path(__file__).parents[1]/"src/consultas_ambientais/semantics/data/mapbiomas_col11_v1"


@pytest.fixture
def classes():return ClassCatalog.load(DATA/"catalog.json")


def test_sources_are_actual_collection_11_and_rebuild_matches(classes):
    rebuilt=ClassCatalog(build_catalog(DATA/"sources"))
    assert rebuilt.sha256==classes.sha256
    assert len(classes.by_code)==41
    assert sum(c.kind=="classe_folha" for c in classes.data.classes)==33
    assert classes.by_code[3].name=="Formação Florestal"
    assert classes.by_code[15].name=="Pastagem"
    assert classes.by_code[24].name=="Área Urbanizada"
    assert classes.by_code[33].name=="Rio, Lago e Oceano"


def test_groups_do_not_double_count_parent_and_children(classes):
    expected=[3,4,5,6,7,49]
    assert classes.expand([1])==expected
    assert classes.expand([1,3,4,1])==expected
    assert classes.expand([18,19,39])==classes.expand([18])
    assert 18 not in classes.expand([18]) and 19 not in classes.expand([18])


def test_parent_48_correction_has_provenance(classes):
    assert classes.by_code[48].parent_code==36
    assert classes.by_code[48].printed_path=="3.2.1.4"
    assert classes.by_code[48].canonical_path=="3.2.2.4"
    discrepancy=next(r for r in classes.data.discrepancies if r['code']==48)
    assert discrepancy['corroborating_source']=='official_page.html'
    assert classes.by_code[84].name=="Marisma (beta)"
    assert classes.resolve("Marismas (beta)").selected_codes==[84]


def test_beta_markers_and_hierarchy(classes):
    assert {c.code for c in classes.data.classes if c.beta}=={7,62,84,91}
    assert classes.by_code[1].kind=="grupo" and classes.by_code[3].kind=="classe_folha"
    assert classes.by_code[39].parent_code==19


@pytest.mark.parametrize('term',['floresta','Floresta','área florestal','água','superfície de água'])
def test_generic_class_terms_are_ambiguous(classes,term):
    assert classes.resolve(term).status=='precisa_esclarecimento'


def test_explicit_selection_and_name_code_inconsistency(classes):
    assert classes.resolve('Formacao Florestal').selected_codes==[3]
    assert classes.resolve('grupo Floresta').selected_codes==[1]
    assert classes.resolve('rio/lago/oceano').selected_codes==[33]
    assert classes.resolve('floresta',3).selected_codes==[3]
    assert classes.resolve('pastagem',24).status=='precisa_esclarecimento'


def test_unknown_pixels_are_not_assumed_nodata(classes):
    report=classes.audit_codes([0,1,3,255])
    assert report['unknown_codes']==[0,255] and report['group_codes_observed']==[1]
    assert report['declared_nodata_observed']==[]
    assert classes.audit_codes([0,3],declared_nodata=0)['unknown_codes']==[]
    assert classes.audit_codes([3])['inventory_complete'] is False
    with pytest.raises(CatalogError):classes.expand([255])


def test_hierarchy_cycle_is_rejected(classes):
    data=classes.data.model_copy(deep=True)
    next(c for c in data.classes if c.code==1).parent_code=3
    with pytest.raises(CatalogError,match='ciclo'):ClassCatalog(data)


def test_changed_source_is_rejected(tmp_path):
    shutil.copytree(DATA/'sources',tmp_path/'sources')
    (tmp_path/'sources/legend.csv').write_text('altered')
    with pytest.raises(CatalogError,match='hash_de_fonte'):build_catalog(tmp_path/'sources')


def test_text_without_corresponding_pdf_is_rejected(tmp_path):
    shutil.copytree(DATA/'sources',tmp_path/'sources')
    p=tmp_path/'sources/legend.txt';p.write_text(p.read_text().replace('Formação Florestal','Nome modificado'))
    with pytest.raises(CatalogError,match='texto_extraido'):build_catalog(tmp_path/'sources')
