"""Criterios deterministas pre-registrados; nenhum juiz LLM ou ajuste ao teste."""
import math
from .reference import D


def normalize_plan(plan, leaves):
    if plan is None:
        return None
    p = dict(plan)
    p['class_codes'] = sorted(set().union(*(set(leaves[str(c)]) for c in p['class_codes'])))
    p['territory_codes'] = sorted(p['territory_codes'])
    p['years'] = sorted(p['years'])
    # Uma UF implicita nos codigos nao altera a semantica fora de rankings.
    if p['operation'] != 'ranking_delimitado':
        p['scope_uf'] = None
        p['direction'] = 'desc'
        p['limit'] = None
    return p


def near(actual, expected, unit, protocol):
    if actual is None or expected is None:
        return actual is None and expected is None
    try:
        return math.isfinite(float(actual)) and abs(D(actual)-D(expected)) <= (
            D(protocol['absolute_tolerance'][unit]) + D(protocol['relative_tolerance'])*abs(D(expected)))
    except (ValueError, TypeError, ArithmeticError):
        return False


def score(observed, gold, protocol, leaves):
    result = {'status': observed.get('status') == gold['status'], 'plan': None,
              'values': None, 'clarification': None, 'correct': False}
    if not result['status']:
        return result
    if gold['status'] == 'precisa_esclarecimento':
        result['clarification'] = observed.get('clarification_field') == gold['clarification_field']
        result['correct'] = result['clarification'] and not observed.get('values')
        return result
    if gold['status'] != 'respondida':
        # Planos podem faltar quando uma politica interrompe antes do gateway.
        # Se ambos informarem plano, divergencias sao penalizadas.
        if observed.get('plan') and gold.get('plan'):
            try:result['plan'] = normalize_plan(observed['plan'],leaves)==normalize_plan(gold['plan'],leaves)
            except (KeyError,TypeError):result['plan']=False
        result['correct'] = not observed.get('values') and result['plan'] is not False
        return result
    try:
        result['plan'] = normalize_plan(observed.get('plan'),leaves)==normalize_plan(gold['plan'],leaves)
    except (KeyError, TypeError):
        result['plan'] = False
    expected, actual = gold['values'], observed.get('values', [])
    if gold['plan']['operation'] != 'ranking_delimitado':
        key=lambda r: (r['territory_code'], tuple(r['years']))
        try:actual,expected=sorted(actual,key=key),sorted(expected,key=key)
        except (KeyError,TypeError):actual=[]
    result['values'] = len(actual)==len(expected)
    for a,b in zip(actual,expected):
        match = all(a.get(k)==b.get(k) for k in ('territory_code','years','unit','undefined_reason','rank'))
        match = match and near(a.get('value'),b['value'],b['unit'],protocol)
        da, db = a.get('denominators_ha',[]), b.get('denominators_ha',[])
        match = match and len(da)==len(db) and all(near(x,y,'ha',protocol) for x,y in zip(da,db))
        result['values'] = result['values'] and match
    result['correct'] = bool(result['status'] and result['plan'] and result['values'])
    return result
