"""Oraculo independente: DuckDB apenas desserializa; formulas em Decimal/Python.

Nao importa executor, metrics, DerivedStore, render ou validate_intent de producao.
A independencia e de calculo sobre os derivados, nao da geracao geoespacial destes.
"""
from decimal import Decimal, localcontext
from pathlib import Path
import duckdb
from .common import read, sha

D = lambda x: Decimal(str(x))
TEMPORAL = {'diferenca_liquida', 'reducao_liquida', 'variacao_percentual', 'diferenca_pontos_percentuais'}


def calculate(metric, unit, observations):
    with localcontext() as context:
        context.prec = 40
        a, d0 = map(D, observations[0])
        den = []
        reason = None
        if metric == 'area':
            result = a
        elif metric == 'participacao':
            den = [d0]
            result = 100 * a / d0 if d0 else None
            reason = 'suporte_observado_zero' if result is None else None
        else:
            b, d1 = map(D, observations[1])
            if metric == 'diferenca_liquida':
                result = b - a
            elif metric == 'reducao_liquida':
                result = max(D(0), a - b)
            elif metric == 'variacao_percentual':
                den = [a]
                result = 100 * (b - a) / a if a else None
                reason = 'base_inicial_zero' if result is None else None
            elif metric == 'diferenca_pontos_percentuais':
                den = [d0, d1]
                result = 100 * b / d1 - 100 * a / d0 if d0 and d1 else None
                reason = 'suporte_observado_zero' if result is None else None
            else:
                raise ValueError('metrica_desconhecida')
        if result is not None and unit in {'ha', 'km2', 'm2'}:
            result *= {'ha': D(1), 'km2': D('.01'), 'm2': D(10000)}[unit]
        return {'value': str(result) if result is not None else None,
                'undefined_reason': reason, 'denominators_ha': list(map(str, den))}


def order_ranking(rows, metric, direction, limit):
    defined = [r for r in rows if r['value'] is not None
               and (metric != 'reducao_liquida' or D(r['value']) > 0)]
    ordered = sorted(defined, key=lambda r: (D(r['value']) * (1 if direction == 'asc' else -1), r['territory_code']))
    return [{**r, 'rank': n + 1} for n, r in enumerate(ordered[:limit])]


class ReferenceReader:
    def __init__(self, root, run_id, classes):
        self.root = Path(root)
        self.run_id = run_id
        self.manifest_path = self.root / 'artifacts/processing' / run_id / 'manifest.json'
        self.manifest = read(self.manifest_path)
        self.parts = {p['territory_code']: p for p in self.manifest['partitions']}
        self.leaves = {c.code: set(c.leaf_codes) for c in classes.data.classes}
        self.cache = {}
        self.input_hashes = {str(self.manifest_path.relative_to(root)): sha(self.manifest_path)}
        self.invariants = []

    def expand(self, codes):
        return sorted(set().union(*(self.leaves[c] for c in codes)))

    def partition(self, code):
        if code in self.cache:
            return self.cache[code]
        base = self.root / 'data/processed' / self.run_id / code
        tables = {}
        with duckdb.connect(':memory:') as db:
            db.execute('SET threads=1')
            for file in self.parts[code]['files']:
                path = base / file['name']
                if sha(path) != file['sha256']:
                    raise ValueError('hash_fonte_divergente')
                self.input_hashes[str(path.relative_to(self.root))] = sha(path)
                cursor = db.execute('SELECT * FROM read_parquet(?)', [str(path)])
                names = [v[0] for v in cursor.description]
                tables[file['name']] = [dict(zip(names, row)) for row in cursor.fetchall()]
        areas = tables['areas.parquet']
        quality = tables['quality.parquet']
        keys = [(r['support'], r['year'], r['class_code']) for r in areas]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicatas_no_oraculo')
        for q in quality:
            selected = [r for r in areas if (r['support'], r['year']) == (q['support'], q['year'])]
            total = sum((D(r['area_m2']) for r in selected), D(0))
            error = abs(total - D(q['observed_area_m2']))
            tolerance = D('.01') + D('1e-9') * D(q['total_area_m2'])
            if error > tolerance or any(r['area_m2'] is None or r['area_m2'] < 0 for r in selected):
                raise ValueError('conservacao_independente_falhou')
            self.invariants.append({'territory_code': code, 'support': q['support'], 'year': q['year'],
                                    'area_sum_error_m2': str(error), 'tolerance_m2': str(tolerance), 'passed': True})
        common = [q for q in quality if q['support'] == 'comum']
        if len({q['common_support_id'] for q in common}) != 1:
            raise ValueError('suportes_comuns_divergentes')
        self.cache[code] = areas, quality
        return areas, quality

    def facts(self, codes):
        """Todas as folhas/anos/suportes dos candidatos, sem respostas calculadas."""
        facts = []
        for code in sorted(set(codes)):
            if code not in self.parts:
                facts.append({'territory_code': code, 'materialized': False})
                continue
            areas, quality = self.partition(code)
            facts.append({'territory_code': code, 'materialized': True, 'unit': 'ha',
                          'areas': [[r['support'], r['year'], r['class_code'], str(D(r['area_m2']) / 10000)] for r in areas],
                          'quality': [{'support': q['support'], 'year': q['year'],
                                       'observed_ha': str(D(q['observed_area_m2']) / 10000),
                                       'complete': q['eligible_complete'],
                                       'common_support_id': q['common_support_id']} for q in quality]})
        return facts

    def answer(self, plan):
        support = 'comum' if plan['metric'] in TEMPORAL else 'anual'
        leaves = self.expand(plan['class_codes'])
        codes = plan['territory_codes'] or sorted(c for c in self.parts if len(c) == 7)
        output = []
        for code in sorted(codes):
            if code not in self.parts:
                return 'dados_indisponiveis', []
            areas, quality = self.partition(code)
            observations = []
            for year in plan['years']:
                qs = [q for q in quality if (q['support'], q['year']) == (support, year)]
                if len(qs) != 1 or not qs[0]['eligible_complete']:
                    return 'dados_indisponiveis', []
                rows = [r for r in areas if (r['support'], r['year']) == (support, year) and r['class_code'] in leaves]
                if len(rows) != len(leaves):
                    return 'dados_indisponiveis', []
                observations.append((sum((D(r['area_m2']) for r in rows), D(0)) / 10000,
                                     D(qs[0]['observed_area_m2']) / 10000))
            groups = [(plan['years'], observations)] if support == 'comum' else [([y], [o]) for y, o in zip(plan['years'], observations)]
            for years, obs in groups:
                output.append({'territory_code': code, 'years': years, 'unit': plan['unit'], 'rank': None,
                               **calculate(plan['metric'], plan['unit'], obs)})
        if plan['operation'] == 'ranking_delimitado':
            output = order_ranking(output, plan['metric'], plan.get('direction', 'desc'), plan['limit'])
        return 'respondida', output
