from pathlib import Path

import pytest

from consultas_ambientais.contracts import Operation
from consultas_ambientais.semantics.catalog import ClassCatalog
from consultas_ambientais.semantics.models import Capabilities,Materialization
from consultas_ambientais.semantics.validation import validate_intent
from test_semantic_territories import territories

DATA=Path(__file__).parents[1]/'src/consultas_ambientais/semantics/data/mapbiomas_col11_v1/catalog.json'


@pytest.fixture
def classes():return ClassCatalog.load(DATA)


@pytest.fixture
def capabilities(classes,territories):
    # Manifesto SINTETICO para testar contratos; nao declara areas reais calculadas.
    leaves=[c.code for c in classes.data.classes if c.kind=='classe_folha']
    records=[]
    for code in territories.by_code:
        for years in [[2015],[2025],[2015,2025]]:
            records.append(Materialization(territory_code=code,years=years,class_codes=leaves,complete=True,
                common_support_id='synthetic-common' if len(years)==2 else None,run_id='synthetic-test-only'))
    return Capabilities(class_catalog_sha256=classes.sha256,territory_catalog_sha256=territories.sha256,
                        available_raster_years=[2015,2025],materializations=records,engine_ready=True)


def intent(**updates):
    return {'operation':'area','metric':'area','unit':'ha','territories':[{'code':'2410900'}],
            'classes':[{'term':'Pastagem'}],'years':[2015],**updates}


def check(classes,territories,capabilities,/,**updates):
    return validate_intent(intent(**updates),classes,territories,capabilities)


def test_validated_plan_is_not_environmental_answer(classes,territories,capabilities):
    result=check(classes,territories,capabilities)
    assert result.status=='plano_validado' and result.normalized_plan.class_codes==[15]
    assert not hasattr(result,'values')


@pytest.mark.parametrize('concept',['ganho_bruto','evento_inundacao','desmatamento','vegetacao_nativa','causa','ilegalidade','projecao'])
def test_unsupported_concepts(classes,territories,capabilities,concept):
    assert check(classes,territories,capabilities,requested_concept=concept).status=='fora_do_escopo'


@pytest.mark.parametrize('term',['percentual','perda','mudança'])
def test_metric_ambiguity_is_not_guessed(classes,territories,capabilities,term):
    result=check(classes,territories,capabilities,metric_term=term)
    assert result.status=='precisa_esclarecimento'


def test_nodata_and_native_vegetation_have_no_invented_code(classes,territories,capabilities):
    for term in ['vegetação nativa','NoData','não observado']:
        result=check(classes,territories,capabilities,classes=[{'term':term}])
        assert result.status=='fora_do_escopo' and result.normalized_plan is None


def test_missing_year_is_checked_against_manifest(classes,territories,capabilities):
    result=check(classes,territories,capabilities,years=[2016])
    assert result.status=='dados_indisponiveis' and result.reason=='ano_sem_fonte_verificada'


def test_group_expansion_and_overlaps(classes,territories,capabilities):
    result=check(classes,territories,capabilities,classes=[{'code':1},{'code':3}])
    assert result.status=='plano_validado'
    assert result.normalized_plan.class_codes==[3,4,5,6,7,49]


def test_ambiguous_class_returns_candidates(classes,territories,capabilities):
    result=check(classes,territories,capabilities,classes=[{'term':'floresta'}])
    assert result.status=='precisa_esclarecimento'
    assert {r['code'] for r in result.class_candidates}=={1,3}


def test_homonym_and_scope_mismatch(classes,territories,capabilities):
    result=check(classes,territories,capabilities,territories=[{'name':'Santa Cruz'}])
    assert result.status=='precisa_esclarecimento' and len(result.territory_candidates)==2
    assert check(classes,territories,capabilities,scope_uf='SP').reason=='territorio_e_escopo_incoerentes'


def test_area_share_percent_change_and_points(classes,territories,capabilities):
    share=check(classes,territories,capabilities,operation='participacao',metric='participacao',unit='percentual')
    assert share.status=='plano_validado' and share.normalized_plan.denominator=='area_observada'
    change=check(classes,territories,capabilities,operation='comparacao_temporal',metric='variacao_percentual',unit='percentual',years=[2015,2025])
    assert change.status=='plano_validado' and change.normalized_plan.denominator=='area_inicial'
    points=check(classes,territories,capabilities,operation='comparacao_temporal',metric='diferenca_pontos_percentuais',unit='pontos_percentuais',years=[2015,2025])
    assert points.status=='plano_validado' and points.normalized_plan.denominator=='participacao_por_ano'
    assert check(classes,territories,capabilities,unit='percentual').status=='precisa_esclarecimento'
    assert check(classes,territories,capabilities,unit_term='km²',unit=None).status=='plano_validado'


def test_missing_common_support_and_partial_coverage(classes,territories,capabilities):
    caps=capabilities.model_copy(deep=True)
    caps.materializations=[m for m in caps.materializations if len(m.years)==1]
    result=check(classes,territories,caps,operation='comparacao_temporal',metric='diferenca_liquida',years=[2015,2025])
    assert result.status=='dados_indisponiveis' and result.reason=='estatisticas_nao_materializadas'


def test_rank_requires_complete_universe(classes,territories,capabilities):
    args={'operation':'ranking_delimitado','metric':'reducao_liquida','scope_uf':'RN','limit':2,'territories':[],'years':[2015,2025]}
    assert check(classes,territories,capabilities,**args).status=='plano_validado'
    caps=capabilities.model_copy(deep=True)
    caps.materializations=[m for m in caps.materializations if m.territory_code!='2408102']
    result=check(classes,territories,caps,**args)
    assert result.status=='dados_indisponiveis' and result.reason=='ranking_com_cobertura_incompleta'


def test_wrong_catalog_version_is_technical_failure(classes,territories,capabilities):
    caps=capabilities.model_copy(update={'class_catalog_sha256':'0'*64})
    assert check(classes,territories,caps).status=='erro_tecnico'


def test_syntactic_extra_fields_not_executable(classes,territories,capabilities):
    assert check(classes,territories,capabilities,sql='SELECT 1').status=='precisa_esclarecimento'


def test_engine_not_ready_is_not_a_success(classes,territories,capabilities):
    caps=capabilities.model_copy(update={'engine_ready':False})
    result=check(classes,territories,caps)
    assert result.status=='dados_indisponiveis' and result.reason=='executor_indisponivel'


def test_boolean_is_not_a_class_code_year_or_rank_limit(classes,territories,capabilities):
    for updates in [{'classes':[{'code':True}]},{'years':[True]},
                    {'operation':'ranking_delimitado','territories':[],'scope_uf':'RN','limit':True}]:
        result=check(classes,territories,capabilities,**updates)
        assert result.status=='precisa_esclarecimento' and result.normalized_plan is None


def test_gross_loss_needs_transition_matrix(classes,territories,capabilities):
    assert check(classes,territories,capabilities,requested_concept='perda_bruta').status=='dados_indisponiveis'
