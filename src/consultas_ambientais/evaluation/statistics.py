"""Bootstrap pareado de familias; IC de acerto, nunca IC de area ambiental."""
import numpy as np
from .common import save, lines, read


def paired_bootstrap(pairs, group_key='family_id', replicas=10000, seed=20271019):
    groups = sorted({p[group_key] for p in pairs})
    if len(groups) < 2:
        return {'state':'pendente','reason':'menos_de_dois_grupos','groups':len(groups),'cases':len(pairs)}
    totals = np.array([sum(p['C']-p['B'] for p in pairs if p[group_key]==g) for g in groups],dtype=float)
    sizes = np.array([sum(p[group_key]==g for p in pairs) for g in groups],dtype=float)
    rng = np.random.default_rng(seed)
    # Uma familia sorteada leva todos os casos e as duas condicoes juntos.
    samples = rng.integers(0,len(groups),size=(replicas,len(groups)))
    deltas = totals[samples].sum(axis=1)/sizes[samples].sum(axis=1)
    low,high=np.quantile(deltas,[.025,.975],method='linear')
    return {'state':'verificado','estimator':'diferenca de proporcoes por caso; clusters reamostrados',
            'difference_C_minus_B':float(totals.sum()/sizes.sum()),'ci95':[float(low),float(high)],
            'groups':len(groups),'cases':len(pairs),'replicas':replicas,'seed':seed,
            'method':'percentil; numpy PCG64; quantile linear','group_key':group_key}


def aggregate(directory, benchmark):
    directory, benchmark = __import__('pathlib').Path(directory), __import__('pathlib').Path(benchmark)
    manifest=read(directory/'run.json'); protocol=read(benchmark/'protocol.json')
    if manifest['integration_kind']=='gateway_real':
        from .protocol import verify
        from .common import sha
        if verify(benchmark)!=manifest['freeze_sha256']:
            raise ValueError('congelamento_divergente_no_relatorio')
        if manifest['state']!='concluida':raise ValueError('execucao_incompleta')
        if {p.name:sha(p) for p in sorted((directory/'individual').glob('*.json'))}!=manifest['individual_hashes']:
            raise ValueError('resultados_individuais_alterados')
    records=[read(p) for p in sorted((directory/'individual').glob('*.json'))]
    primary=[r for r in records if r['repeat']==0]
    by_condition={}
    expected=manifest['case_ids']
    for condition in ['A','B','C']:
        subset=[r for r in primary if r['condition']==condition]
        correct=sum(r['scores']['correct'] for r in subset)
        answered=[r for r in subset if r['observed']['status']=='respondida']
        total=len(expected)
        usage={key:sum(a.get('usage',{}).get(key,0) for r in subset for a in r['attempts'] if a.get('usage')) for key in ['prompt_tokens','completion_tokens','total_tokens']}
        observed_tokens=sum(bool(a.get('usage')) for r in subset for a in r['attempts'])
        statuses={s:sum(r['observed']['status']==s for r in subset) for s in ['respondida','precisa_esclarecimento','fora_do_escopo','dados_indisponiveis','erro_tecnico']}
        by_condition[condition]={'expected':total,'completed':len(subset),'missing':total-len(subset),
            'correct':correct,'accuracy_including_technical_and_missing':correct/total if total else None,
            'coverage_answered':len(answered)/total if total else None,
            'precision_emitted':sum(r['scores']['correct'] for r in answered)/len(answered) if answered else None,
            'statuses':statuses,'abstention_or_clarification':sum(r['observed']['status']!='respondida' for r in subset)/total if total else None,
            'json_failures':sum(any('json' in str(a.get('issues','')) for a in r['attempts']) for r in subset),
            'semantic_or_contract_failures':sum(any(a.get('issues') for a in r['attempts']) for r in subset),
            'latency_mean_seconds':float(np.mean([r['latency_seconds'] for r in subset])) if subset else None,
            'latency_p50_seconds':float(np.median([r['latency_seconds'] for r in subset])) if subset else None,
            'latency_p95_seconds':float(np.quantile([r['latency_seconds'] for r in subset],.95)) if subset else None,
            'usage_observed_sum':usage if observed_tokens else None,'usage_missing_attempts':sum(not a.get('usage') for r in subset for a in r['attempts']),
            'cost':None,'cost_reason':'preco_nao_fornecido'}
    index={(r['case_id'],r['condition']):r for r in primary}
    cases={c['case_id']:c for c in lines(benchmark/'cases.jsonl')}
    pairs=[]
    for cid in expected:
        if (cid,'B') not in index or (cid,'C') not in index:continue
        case=cases[cid]
        codes=case['territory_codes']
        pairs.append({'case_id':cid,'family_id':case['family_id'],
                      'territory':codes[0] if len(codes)==1 and len(codes[0])==7 and 'universo_RN' not in case['dependencies'] else None,
                      'B':int(index[cid,'B']['scores']['correct']),'C':int(index[cid,'C']['scores']['correct'])})
    complete=len(pairs)==len(expected)
    paired=paired_bootstrap(pairs,replicas=protocol['bootstrap_replicas'],seed=protocol['seed']) if complete else {'state':'pendente','reason':'pares_incompletos'}
    numeric_pairs=[p for p in pairs if cases[p['case_id']]['expected_decision']=='respondida']
    numeric=paired_bootstrap(numeric_pairs,replicas=protocol['bootstrap_replicas'],seed=protocol['seed']) if complete else {'state':'pendente'}
    territory_pairs=[p for p in pairs if p['territory']]
    enough=len({p['territory'] for p in territory_pairs})>=protocol['minimum_territory_groups']
    sensitivity=paired_bootstrap(territory_pairs,'territory',protocol['bootstrap_replicas'],protocol['seed']) if complete and enough else {'state':'pendente','reason':'grupos_territoriais_insuficientes_ou_execucao_incompleta'}
    repeat_records=[r for r in records if r['repeat']>0]
    repeat_checks=[]
    for r in repeat_records:
        first=index.get((r['case_id'],r['condition']))
        if first:repeat_checks.append({'case_id':r['case_id'],'condition':r['condition'],
            'same_normalized_answer':{k:v for k,v in first['observed'].items() if k!='reason'}=={k:v for k,v in r['observed'].items() if k!='reason'},'same_correctness':first['scores']['correct']==r['scores']['correct']})
    report={'schema_version':'avaliacao-cientifica-v1','run_id':manifest['run_id'],'split':manifest['split'],
            'integration_kind':manifest['integration_kind'],'freeze_sha256':manifest['freeze_sha256'],
            'metrics':by_condition,'paired_C_minus_B':paired,'paired_numeric_subset':numeric,
            'territory_sensitivity':sensitivity,'territory_sensitivity_excluded_cases':len(pairs)-len(territory_pairs),
            'repeatability':repeat_checks or 'execucao_unica; temperature zero nao garante determinismo',
            'limitations':['Familias compartilham malha, revisao e uma UF; independencia territorial nao garantida.',
                          'Rankings reais positivos indisponiveis por cobertura RN incompleta.',
                          'IC descreve acerto de consulta, nao incerteza de area ou acuracia tematica.',
                          'Gabaritos independentes no calculo compartilham os derivados geoespaciais.',
                          'Sem revisao humana; amostra revisada por IA e invariantes deterministas.']}
    import csv
    with (directory/'individual.csv').open('w',newline='') as stream:
        fields=['run_id','case_id','family_id','condition','repeat','status','correct','latency_seconds','prompt_tokens','completion_tokens','total_tokens','cost']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for record in records:
            usage={key:sum(a.get('usage',{}).get(key,0) for a in record['attempts'] if a.get('usage')) for key in ['prompt_tokens','completion_tokens','total_tokens']}
            if not any(a.get('usage') for a in record['attempts']):usage={key:None for key in usage}
            writer.writerow({**{k:record.get(k) for k in ['run_id','case_id','family_id','condition','repeat','latency_seconds','cost']},
                             **usage,'status':record['observed']['status'],'correct':record['scores']['correct']})
    save(directory/'metrics.json',report)
    return report
