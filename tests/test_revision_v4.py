"""Referencias pequenas conhecidas e limites da declaracao humana (sinteticos)."""
import sys
from pathlib import Path
from decimal import Decimal
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from science.reference_review_v4 import arithmetic
from science.writing_v4 import require_human

@pytest.mark.parametrize('metric,unit,operands,expected',[
 ('area','km2',[(250,500)],'2.50'),('area','m2',[(2,500)],'20000'),
 ('participacao','percentual',[(25,200)],'12.5'),
 ('diferenca_liquida','ha',[(12,100),(7,100)],'-5'),
 ('variacao_percentual','percentual',[(40,200),(50,200)],'25'),
 ('diferenca_pontos_percentuais','pontos_percentuais',[(40,200),(50,200)],'5'),
 ('reducao_liquida','ha',[(40,200),(50,200)],'0')])
def test_hand_calculated_reference(metric,unit,operands,expected):
    assert Decimal(arithmetic(metric,unit,operands)['value'])==Decimal(expected)

def test_zero_base_is_undefined_instead_of_invented_percent():
    r=arithmetic('variacao_percentual','percentual',[(0,100),(10,100)])
    assert r['value'] is None and r['undefined_reason']=='base_inicial_zero'

def test_global_review_does_not_fabricate_individual_annotations():
    h={'quantitative_references_reviewed':88,'corrections_reported':False,'individual_annotations_supplied':False}
    require_human(h)
    with pytest.raises(ValueError):require_human({**h,'individual_annotations_supplied':True})
