"""Capacidades da execucao derivada, verificando arquivos, hashes e cobertura."""
from datetime import datetime, timezone
from ..semantics.catalog import ClassCatalog, digest
from ..semantics.territories import TerritoryCatalog
from ..storage.derived import DerivedStore
from ..contracts import Operation


def capabilities(root, project, config, territory_code=None):
    classes = ClassCatalog.load()
    territories = TerritoryCatalog.load(root / config.territories)
    store = DerivedStore(root, project, config.run_id, classes, territories, root / config.capabilities)
    verified = set()
    # Nao anunciar estatisticas a partir apenas de URLs ou do manifesto de indice.
    for code in store.parts:
        store._partition(code)
        verified.add(code)
    records = [r for r in store.capabilities.materializations if r.territory_code in verified]
    scope = store.identity['config'].get('pilot_uf', project.pilot_uf)
    entries = []
    for code in sorted(verified):
        e = territories.by_code[code]
        rows = [r for r in records if r.territory_code == code]
        annual = sorted(r.years[0] for r in rows if len(r.years) == 1)
        usable = sorted(r.years[0] for r in rows if len(r.years) == 1 and r.complete)
        pairs = [{'years': r.years, 'usable': r.complete,
                  'common_support_id': r.common_support_id} for r in rows if len(r.years) == 2]
        entries.append({'code': code, 'name_original': e.name_original, 'uf': e.uf, 'kind': e.kind,
                        'materialized_years': annual, 'usable_years': usable, 'comparable_pairs': pairs,
                        'quality_diagnostics': [{'year': q['year'], 'support': q['support'],
                            'unknown_codes': sorted(q['unknown_codes_m2']), 'unknown_area_m2': q['unknown_area_m2'],
                            'nodata_area_m2': q['nodata_area_m2'], 'outside_raster_area_m2': q['outside_raster_area_m2']}
                            for (territory, _, _), q in store.quality.items() if territory == code],
                        'quality': 'completo' if annual and annual == usable and all(p['usable'] for p in pairs) else 'parcial'})
    universe = territories.municipality_universe(scope)
    pairs = sorted({tuple(r.years) for r in records if len(r.years) == 2})
    ranking = []
    for pair in pairs:
        complete = {r.territory_code for r in records if tuple(r.years) == pair and r.complete}
        ok = bool(universe) and universe <= complete
        ranking.append({'uf': scope, 'years': list(pair), 'status': 'disponivel' if ok else 'dados_indisponiveis',
                        'universe_count': len(universe), 'usable_count': len(universe & complete),
                        'missing_or_partial_codes': sorted(universe - complete),
                        'reason': 'universo_completo' if ok else 'ranking_com_cobertura_incompleta'})
    selected_records = [r for r in records if territory_code is None or r.territory_code == territory_code]
    annual_ok = any(r.complete and len(r.years) == 1 for r in selected_records)
    common_ok = any(r.complete and len(r.years) == 2 for r in selected_records)
    operations = []
    for op in store.capabilities.supported_operations:
        ok = (any(p['status'] == 'disponivel' for p in ranking) if op == Operation.RANKING
              else common_ok if op == Operation.TEMPORAL
              else any(len({r.territory_code for r in selected_records if r.complete and r.years == [year]}) >= 2
                       for year in {r.years[0] for r in selected_records if len(r.years)==1})
              if op == Operation.TERRITORIAL else annual_ok)
        operations.append({'operation': op.value, 'status': 'disponivel' if ok else 'dados_indisponiveis',
                           'restriction': 'cobertura_completa_do_universo_da_uf' if op == Operation.RANKING
                           else 'suporte_valido_comum_materializado' if op == Operation.TEMPORAL else 'territorio_ano_com_cobertura_completa'})
    materialized_codes = set(c for r in selected_records for c in r.class_codes)
    class_rows = [{'code': c.code, 'name': c.name, 'kind': c.kind, 'beta': c.beta,
                   'leaf_codes': c.leaf_codes, 'raster_observation_asserted': False,
                   'materialized': set(c.leaf_codes) <= materialized_codes}
                  for c in classes.data.classes if set(c.leaf_codes) <= materialized_codes]
    all_entries = entries
    if territory_code is not None:
        entries = [e for e in entries if e['code'] == territory_code]
    years = sorted({y for e in entries for y in e['materialized_years']})
    return {'schema_version': 'capacidades-locais-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'data_kind': config.data_kind, 'run_id': config.run_id, 'scope_uf': scope,
            'run_manifest_sha256': store.manifest_sha256, 'class_catalog_sha256': classes.sha256,
            'territory_catalog_sha256': territories.sha256, 'collection': 11,
            'source_revision': store.identity['config']['source_revision'],
            'territorial_edition': store.identity['config']['territorial_edition'],
            'materialized_years': years, 'usable_years': sorted({y for e in entries for y in e['usable_years']}),
            'territories': entries, 'territory_count_in_run': len(all_entries), 'classes': class_rows,
            'operations': operations, 'ranking': ranking, 'materialized_pairs': [list(p) for p in pairs],
            'usable_pairs': sorted({tuple(r.years) for r in selected_records if len(r.years)==2 and r.complete}),
            'limitations': ['Disponibilidade depende da cobertura do território e do suporte solicitado.',
                            'Sem matriz de transição, inferência causal ou validação temática.',
                            'Revisão oficial e edição territorial são desconhecidas quando null.'],
            'verification': 'hashes_das_particoes_e_qualidade_da_execucao'}
