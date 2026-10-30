"""O texto nao pode inferir superioridade/equivalencia quando o IC inclui zero."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from science.writing_v5 import effect_interpretation

@pytest.mark.parametrize('ci,phrase',[([.01,.3],'acima de zero'),([-.3,-.01],'abaixo de zero'),([0,.2],'inclui zero'),([-.1,.2],'inclui zero')])
def test_interpretation_is_conditional(ci,phrase):
    text=effect_interpretation({'ci95':ci});assert phrase in text
    if ci[0]<=0<=ci[1]:assert 'nem demonstra equivalência' in text
