"""Interpretacoes e declaracao humana nao podem extrapolar a evidencia."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from science.writing_v3 import interpretation,require_review,renumber


@pytest.mark.parametrize('ci,expected',[([.01,.5],'aumentou'),([-.5,-.01],'reduziu'),([-.1,.2],'inclui zero')])
def test_interpretation_follows_interval_without_claiming_equivalence(ci,expected):
    text=interpretation({'ci95':ci})
    assert expected in text
    if ci[0]<=0<=ci[1]:assert 'não demonstra equivalência' in text


def test_question_review_does_not_become_reference_validation():
    review={'question_count':120,'corrections_reported':False,'reference_answer_review_confirmed':False}
    require_review(review)
    with pytest.raises(ValueError):require_review({**review,'reference_answer_review_confirmed':True})


def test_citation_renumbering_keeps_numeric_json_arrays_unchanged():
    draft={'blocks':[{'kind':'paragraph','text':'Antecedente [geogpt2023], método [1].'},
        {'kind':'paragraph','text':'{"class_codes":[1]}','citation_exempt':True},
        {'kind':'reference','text':'[1] Metodo.'}]}
    extra=[{'id':'geogpt2023','title':'Titulo sintetico','version':'mock','year':2023,'doi':'mock'}]
    renumber(draft,extra)
    assert draft['blocks'][0]['text']=='Antecedente [1], método [2].'
    assert draft['blocks'][1]['text']=='{"class_codes":[1]}'
