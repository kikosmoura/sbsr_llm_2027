"""Mesma auditoria/metrica V3 para a sensibilidade completa 4096."""
from collections import Counter
from statistics import mean,median
from pathlib import Path
import json
import numpy as np
from consultas_ambientais.evaluation.common import read,lines,sha,digest,canonical,save
from consultas_ambientais.evaluation.scoring import score
from consultas_ambientais.evaluation.statistics import paired_bootstrap
from .equivalent_v3 import model_messages,executor_observation
from .sensitivity_v5 import verify
from .audit import require


def summarize(root,benchmark,directory,code):
    root,benchmark,directory,code=map(Path,(root,benchmark,directory,code));frozen=verify(benchmark,root,code)
    run=read(directory/'run.json');protocol=read(benchmark/'protocol.json')
    require(run['state']=='concluida' and run['freeze_sha256']==frozen,'controle_incompleto_ou_divergente')
    paths=sorted((directory/'individual').glob('*.json'))
    require({p.name:sha(p) for p in paths}==run['individual_hashes'],'registros_controle_alterados')
    records=[read(p) for p in paths];primary=[r for r in records if r['repeat']==0]
    cases={c['case_id']:c for c in lines(benchmark/'cases.jsonl')};inputs=read(benchmark/'inputs.json')
    reference=read(benchmark/'reference.json');old_protocol=read(benchmark/'scoring_protocol.json');leaves=read(benchmark/'classes.json')
    schema=read(benchmark/'output_schema.json');system=(benchmark/'system.txt').read_text()
    expected={(cid,k) for cid in run['case_ids'] for k in ['B_eq','C_eq']}
    require(len(primary)==len(expected) and {(r['case_id'],r['condition']) for r in primary}==expected,'pares_controle_incompletos')
    keys=[(r['case_id'],r['condition'],r['repeat']) for r in records];require(len(keys)==len(set(keys)),'duplicata_controle')
    expected_keys={(cid,k,0) for cid,k in expected}
    if run['repeat_requested']:
        expected_keys|={(cid,k,1) for cid in run['case_ids'] if cid in protocol['repeat_case_ids'] for k in ['B_eq','C_eq']}
    require(set(keys)==expected_keys,'repeticoes_planejadas_incompletas_ou_excedentes')
    geo=root/'artifacts/processing'/protocol['source_geo_run_id']/'manifest.json';geo_hash=sha(geo)
    model_names=set()
    for r in records:
        cid=r['case_id'];common=inputs[cid]
        require(r['configuration']==run['configuration'] and r['freeze_sha256']==frozen,'configuracao_controle_divergente')
        require(r['common_input_sha256']==digest(common) and r['fixed_plan']==common['validated_plan'],'entrada_fixa_divergente')
        require(r['output_contract_sha256']==digest(schema) and r['system_sha256']==sha(benchmark/'system.txt'),'contrato_ou_prompt_divergente')
        require(r['scores']==score(r['observed'],reference[cid],old_protocol,leaves),'escore_controle_divergente')
        for attempt in r['attempts']:
            if attempt.get('returned_model'):model_names.add(attempt['returned_model'])
        if r['condition']=='B_eq':require(r['execution_observations']==[] and r['executor_result'] is None,'executor_usado_em_B_eq')
        if r['executor_result'] and r['executor_result']['execution']:
            ex=r['executor_result']['execution'];require(ex['run_manifest_sha256']==geo_hash and ex['run_id']==protocol['source_geo_run_id'],'dados_executor_de_outra_execucao')
            from consultas_ambientais.answers.models import QueryAnswer
            normalized,_=executor_observation(QueryAnswer.model_validate(r['executor_result']))
            require(r['execution_observations']==[normalized],'observacao_fornecida_diverge_da_evidencia')
        if r['messages_sha256']:
            messages=model_messages(common,r['execution_observations'],schema,system)
            require(digest(messages)==r['messages_sha256'],'mensagem_controle_divergente')
            require(len(r['attempts'])<=2,'reparos_excedentes')
            for i,attempt in enumerate(r['attempts']):
                actual=messages if i==0 else messages+[{'role':'user','content':canonical({'repair':'Reenvie somente JSON no mesmo contrato.','validation_issues':r['attempts'][0]['issues']})}]
                require(digest(actual)==attempt['messages_sha256'],'mensagem_de_reparo_divergente')
    metrics=[];families=[];error_rows=[]
    for k in ['B_eq','C_eq']:
        rs=[r for r in primary if r['condition']==k];answered=[r for r in rs if r['observed']['status']=='respondida']
        usage={field:sum((a.get('usage') or {}).get(field,0) for r in rs for a in r['attempts']) for field in ['prompt_tokens','completion_tokens','total_tokens']}
        times=[r['latency_seconds'] for r in rs];correct=sum(r['scores']['correct'] for r in rs)
        errors=Counter()
        for r in rs:
            if r['scores']['correct']:typ='acerto'
            elif r['observed']['status']=='erro_tecnico':
                last=r['attempts'][-1] if r['attempts'] else {}
                typ=last.get('gateway_error') or ('contrato_invalido' if last.get('issues') else 'falha_tecnica_local')
            elif not r['scores']['status']:typ='estado_incorreto'
            elif not r['scores']['values']:typ='valores_ou_estrutura_incorretos'
            else:typ='outro'
            errors[typ]+=1
        metrics.append({'condition':k,'cases':len(rs),'correct':correct,'accuracy':correct/len(rs),
            'answered':len(answered),'technical_errors':sum(r['observed']['status']=='erro_tecnico' for r in rs),
            'coverage':len(answered)/len(rs),'precision_emitted':sum(r['scores']['correct'] for r in answered)/len(answered) if answered else None,
            'latency_mean_seconds':mean(times),'latency_median_seconds':median(times),'latency_p95_seconds':float(np.quantile(times,.95)),
            'model_seconds_mean':mean(r['model_seconds'] for r in rs),'executor_seconds_mean':mean(r['executor_seconds'] for r in rs),
            'usage_observed_sum':usage,'usage_missing_attempts':sum(a.get('usage') is None for r in rs for a in r['attempts']),
            'cost':None})
        error_rows.extend({'condition':k,'type':t,'count':n} for t,n in sorted(errors.items()))
        for fid in sorted({r['family_id'] for r in rs}):
            selected=[r for r in rs if r['family_id']==fid]
            families.append({'condition':k,'family_id':fid,'cases':len(selected),'correct':sum(r['scores']['correct'] for r in selected)})
    index={(r['case_id'],r['condition']):r for r in primary}
    pairs=[{'case_id':cid,'family_id':cases[cid]['family_id'],'B':int(index[cid,'B_eq']['scores']['correct']),
            'C':int(index[cid,'C_eq']['scores']['correct'])} for cid in sorted(run['case_ids'])]
    effect=paired_bootstrap(pairs,replicas=protocol['bootstrap_replicas'],seed=protocol['bootstrap_seed'])
    repeated=[]
    for r in records:
        if r['repeat']==0:continue
        initial=index[r['case_id'],r['condition']]
        a={k:v for k,v in r['observed'].items() if k!='reason'};b={k:v for k,v in initial['observed'].items() if k!='reason'}
        repeated.append({'case_id':r['case_id'],'condition':r['condition'],'same_answer':a==b,'same_correctness':r['scores']['correct']==initial['scores']['correct']})
    report={'schema_version':'controle-contrato-estatisticas-v1','state':'verificado','run_id':run['run_id'],'split':run['split'],
        'freeze_sha256':frozen,'integration_kind':'gateway_real','configuration':run['configuration'],'returned_models':sorted(model_names),
        'primary_records':len(primary),'repeat_records':len(repeated),'conditions':metrics,'families':families,'errors':error_rows,
        'paired_cases':pairs,'paired_Ceq_minus_Beq':effect,'repeatability':repeated,
        'input_audit':{'same_common_facts_and_fixed_plan':True,'same_system_prompt':True,'same_output_contract':True,
            'same_model_and_parameters':True,'both_generate_final_json_with_llm':True,'all_scores_recomputed':True,'all_messages_reconstructed':True,
            'treatment_only':'resultado real de executor inserido em execution_observations de C_eq'},
        'limitations':['Planos corretos fornecidos: nao avalia interpretacao nem ambiguidades.',
            'Resultado estima efeito do fornecimento de calculo ao finalizador, incluindo conformidade de saida; nao habilidade cognitiva isolada.',
            'Questões reutilizadas e protocolo complementar definido depois do teste original; nao avaliacao externa independente.',
            'Familias compartilham territorios, classes e dados; bootstrap com poucos grupos.',
            'Pesos/modelo/infraestrutura remota nao versionados de forma observavel; ordem aleatoria reduz mas nao elimina efeitos temporais.',
            'Revisao humana declarada cobre perguntas; gabaritos nao tiveram validacao humana confirmada.']}
    return report,records
