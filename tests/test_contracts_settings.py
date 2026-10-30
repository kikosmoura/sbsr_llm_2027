import json
import math

import pytest
from pydantic import ValidationError

from consultas_ambientais.contracts import Answer, QueryPlan
from consultas_ambientais.queries.metrics import convert_area,temporal_change,share_percent,percentage_point_change
from consultas_ambientais.settings import DatabaseSettings,LLMSettings,ProjectConfig


def plan(**updates):
    return {"operation":"area","metric":"area","unit":"ha","territory_codes":["2410900"],
            "class_codes":[15],"years":[2015],**updates}


def test_defaults_are_candidates_not_available():
    cfg=ProjectConfig()
    assert cfg.pilot_uf=="RN" and cfg.pilot_years==[2015,2025]
    assert len(cfg.candidate_years)==11
    assert cfg.raster_url(2018).endswith("brazil_coverage-col11_2018.tif")
    assert not hasattr(cfg,"available_years")


@pytest.mark.parametrize("updates",[
    {"candidate_years":[2015,2015]}, {"candidate_years":[2014,2025]},
    {"filename_template":"../x{ano}{colecao}.tif"}, {"base_url":"https://example.test/?token=x"},
    {"data_dir":"../shared"}, {"pilot_years":[2025,2015]},
])
def test_invalid_public_config(updates):
    with pytest.raises(ValidationError):ProjectConfig(**updates)


def test_credentials_do_not_serialize():
    cfg=DatabaseSettings.from_env({"SOURCE_PG_HOST":"private.example.test","SOURCE_PG_DATABASE":"private-db",
                                   "SOURCE_PG_USER":"private-user","SOURCE_PG_PASSWORD":"test-only-secret"})
    assert cfg.configured
    for text in [repr(cfg),str(cfg),cfg.model_dump_json()]:
        assert "private.example.test" not in text and "test-only-secret" not in text and "private-user" not in text


def test_partial_credentials_are_rejected_without_values():
    with pytest.raises(ValidationError) as exc:
        DatabaseSettings.from_env({"SOURCE_PG_HOST":"never-show-this.test"})
    assert "never-show-this" not in str(exc.value)


def test_llm_url_security():
    env={"LLM_BASE_URL":"http://unsafe.test","LLM_TOKEN_URL":"https://example.test/token",
         "LLM_CLIENT_ID":"test-client","LLM_CLIENT_SECRET":"test-secret","LLM_MODEL":"test-model"}
    with pytest.raises(ValidationError):LLMSettings.from_env(env)


def test_extra_query_fields_cannot_carry_sql():
    with pytest.raises(ValidationError):QueryPlan(**plan(sql="SELECT 1"))


@pytest.mark.parametrize("updates",[
    {"metric":"participacao"}, {"years":[2014]}, {"years":[2015,2015]},
    {"territory_codes":[]}, {"territory_codes":["1; SELECT 1"]},
    {"operation":"comparacao_temporal","metric":"variacao_percentual","unit":"percentual",
     "years":[2015,2025]},
    {"operation":"ranking_delimitado","scope_uf":"RN","limit":5},
])
def test_invalid_plans(updates):
    with pytest.raises(ValidationError):QueryPlan(**plan(**updates))


def test_valid_temporal_and_ranking():
    QueryPlan(**plan(operation="comparacao_temporal",metric="variacao_percentual",unit="percentual",
                     denominator="area_inicial",years=[2015,2025]))
    QueryPlan(**plan(operation="ranking_delimitado",metric="reducao_liquida",territory_codes=[],
                     scope_uf="RN",limit=5,years=[2015,2025]))


def test_unproven_answer_rejected():
    with pytest.raises(ValidationError):Answer(status="respondida",message="100 hectares")


def test_numerical_contract():
    assert convert_area(100,"km2")==1
    assert convert_area(1,"m2")==10000
    assert temporal_change(100,75)=={"delta_ha":-25,"reduction_ha":25,"change_percent":-25,"undefined_reason":None}
    assert temporal_change(0,10)["change_percent"] is None
    assert share_percent(20,100)==20
    assert percentage_point_change(20,100,30,100)==10
    assert temporal_change(20,30)["change_percent"]==50
    with pytest.raises(ValueError):share_percent(3,2)
    with pytest.raises(ValueError):convert_area(math.nan,"ha")
