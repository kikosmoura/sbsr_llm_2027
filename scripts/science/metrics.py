"""Tabelas e estimativas derivadas somente dos registros individuais auditados."""
from collections import Counter,defaultdict
from statistics import mean,median
import numpy as np
from consultas_ambientais.evaluation.statistics import paired_bootstrap
from .audit import STATUSES,require


def error_type(r):
    if r['scores']['correct']:return 'acerto'
    if r['observed']['status']=='erro_tecnico':
        errors={a.get('gateway_error') for a in r['attempts']}
        if 'texto_final_ausente' in errors:return 'texto_final_ausente'
        if any(errors-{None}):return 'outra_falha_gateway'
        if any('json' in str(a.get('issues',[])).lower() for a in r['attempts']):return 'json_invalido_apos_limite'
        return 'validacao_apos_limite'
    if r['scores']['status'] is False:return 'status_incorreto'
    if r['scores']['clarification'] is False:return 'esclarecimento_incorreto'
    if r['scores']['plan'] is False:return 'plano_incorreto'
    if r['scores']['values'] is False:return 'valor_ou_ranking_incorreto'
    return 'outro_erro'


def derive(records,cases,protocol):
    primary=[r for r in records if r['repeat']==0];by_condition=[];families=[];errors=[];statuses=[];latencies=[];attempt_rows=[]
    for k in 'ABC':
        selected=[r for r in primary if r['condition']==k];n=len(selected);answered=[r for r in selected if r['observed']['status']=='respondida']
        usage={x:sum(a.get('usage',{}).get(x,0) for r in selected for a in r['attempts'] if a.get('usage')) for x in ['prompt_tokens','completion_tokens','total_tokens']}
        times=[r['latency_seconds'] for r in selected]
        errors_k=Counter(error_type(r) for r in selected)
        row={'condition':k,'cases':n,'correct':sum(r['scores']['correct'] for r in selected),
             'accuracy':sum(r['scores']['correct'] for r in selected)/n,'answered':len(answered),
             'coverage_answered':len(answered)/n,'precision_emitted':sum(r['scores']['correct'] for r in answered)/len(answered) if answered else None,
             'clarification':sum(r['observed']['status']=='precisa_esclarecimento' for r in selected),
             'abstention_nontechnical':sum(r['observed']['status'] in ['precisa_esclarecimento','fora_do_escopo','dados_indisponiveis'] for r in selected),
             'nonanswer_including_technical':sum(r['observed']['status']!='respondida' for r in selected),
             'technical_errors':sum(r['observed']['status']=='erro_tecnico' for r in selected),
             'latency_mean_seconds':mean(times),'latency_median_seconds':median(times),
             'latency_p95_seconds':float(np.quantile(times,.95)),
             'attempts':sum(len(r['attempts']) for r in selected),
             'tokens_observed':usage,'usage_missing_attempts':sum(not a.get('usage') for r in selected for a in r['attempts']),
             'cost':None,'cost_note':'preco_nao_fornecido'}
        by_condition.append(row)
        for typ,count in sorted(errors_k.items()):errors.append({'condition':k,'type':typ,'count':count,'fraction':count/n})
        for status in STATUSES:statuses.append({'condition':k,'status':status,'count':sum(r['observed']['status']==status for r in selected),'denominator':n})
        for fid in sorted({r['family_id'] for r in selected}):
            rs=[r for r in selected if r['family_id']==fid]
            families.append({'condition':k,'family_id':fid,'cases':len(rs),'correct':sum(r['scores']['correct'] for r in rs),'accuracy':sum(r['scores']['correct'] for r in rs)/len(rs)})
        for r in selected:
            latencies.append({'case_id':r['case_id'],'family_id':r['family_id'],'condition':k,'latency_seconds':r['latency_seconds'],'correct':r['scores']['correct'],'status':r['observed']['status']})
            for a in r['attempts']:
                attempt_rows.append({'condition':k,'case_id':r['case_id'],'attempt':a['number'],'state':a['state'],
                                     'latency_seconds':a.get('latency_seconds'),'gateway_error':a.get('gateway_error'),
                                     **{x:(a.get('usage') or {}).get(x) for x in ['prompt_tokens','completion_tokens','total_tokens']}})
    index={(r['case_id'],r['condition']):r for r in primary};pairs=[]
    for cid in sorted({r['case_id'] for r in primary}):
        c=cases[cid];codes=c['territory_codes']
        pairs.append({'case_id':cid,'family_id':c['family_id'],'territory':codes[0] if len(codes)==1 and len(codes[0])==7 and 'universo_RN' not in c['dependencies'] else None,
                      'B':int(index[cid,'B']['scores']['correct']),'C':int(index[cid,'C']['scores']['correct'])})
    principal=paired_bootstrap(pairs,replicas=protocol['bootstrap_replicas'],seed=protocol['seed'])
    numeric=paired_bootstrap([p for p in pairs if cases[p['case_id']]['expected_decision']=='respondida'],replicas=protocol['bootstrap_replicas'],seed=protocol['seed'])
    territorial=[p for p in pairs if p['territory']]
    sensitivity=paired_bootstrap(territorial,'territory',protocol['bootstrap_replicas'],protocol['seed']) if len({p['territory'] for p in territorial})>=protocol['minimum_territory_groups'] else {'state':'pendente'}
    repeat=[]
    for r in records:
        if not r['repeat']:continue
        base=index[r['case_id'],r['condition']]
        a={k:v for k,v in base['observed'].items() if k!='reason'};b={k:v for k,v in r['observed'].items() if k!='reason'}
        repeat.append({'case_id':r['case_id'],'condition':r['condition'],'same_answer':a==b,'same_correctness':base['scores']['correct']==r['scores']['correct']})
    return {'conditions':by_condition,'families':families,'errors':errors,'statuses':statuses,
            'latencies':latencies,'attempts':attempt_rows,'paired_cases':pairs,'paired_C_minus_B':principal,
            'paired_numeric_subset':numeric,'territory_sensitivity':sensitivity,
            'territory_sensitivity_excluded_cases':len(pairs)-len(territorial),'repeats':repeat,
            'primary_cases':len(pairs),'numeric_cases':sum(cases[p['case_id']]['expected_decision']=='respondida' for p in pairs)}


def crosscheck(metrics,old):
    for row in metrics['conditions']:
        o=old['metrics'][row['condition']]
        require(row['correct']==o['correct'] and row['cases']==o['completed'],'contagem_agregada_divergente')
        for field,oldfield in [('accuracy','accuracy_including_technical_and_missing'),('coverage_answered','coverage_answered'),('precision_emitted','precision_emitted'),('latency_mean_seconds','latency_mean_seconds'),('latency_median_seconds','latency_p50_seconds'),('latency_p95_seconds','latency_p95_seconds')]:
            a,b=row[field],o[oldfield];require(a==b or (a is not None and b is not None and abs(a-b)<1e-12),'metrica_agregada_divergente')
        require(row['tokens_observed']==o['usage_observed_sum'],'tokens_agregados_divergentes')
    for name in ['paired_C_minus_B','paired_numeric_subset','territory_sensitivity']:
        require(metrics[name]==old[name],'bootstrap_divergente')
