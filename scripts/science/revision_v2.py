"""Analises exploratorias versionadas; escores/protocolo de teste permanecem intactos."""
from collections import Counter
from pathlib import Path
import json

from consultas_ambientais.evaluation.common import read,sha,save
from consultas_ambientais.evaluation.scoring import near
from consultas_ambientais.evaluation.statistics import paired_bootstrap
from .audit import require


SEMANTIC_ISSUES={'operacao_diverge_da_pergunta','anos_divergem_da_pergunta','territorio_citado_omitido'}
CATEGORIES=['acerto','retorno_textual_ausente','outra_falha_gateway','rejeicao_semantica',
            'rejeicao_contrato_indeterminada','erro_semantico_decisao','erro_semantico_plano',
            'erro_estrutura_resultado','erro_numerico_isolavel','outro_indeterminado']


def value_diagnosis(observed,gold,protocol):
    """Numerico so depois de comparar entidade/ano/unidade/estrutura; sem novo escore."""
    actual=observed.get('values',[]);expected=gold.get('values',[])
    if len(actual)!=len(expected):return 'erro_estrutura_resultado'
    key=lambda v:(v.get('territory_code',''),tuple(v.get('years',[])))
    if gold['plan']['operation']!='ranking_delimitado':actual,expected=sorted(actual,key=key),sorted(expected,key=key)
    numeric=False
    for a,b in zip(actual,expected):
        if any(a.get(k)!=b.get(k) for k in ['territory_code','years','unit','undefined_reason','rank']):return 'erro_estrutura_resultado'
        da,db=a.get('denominators_ha',[]),b.get('denominators_ha',[])
        if len(da)!=len(db):return 'erro_estrutura_resultado'
        numeric|=not near(a.get('value'),b['value'],b['unit'],protocol)
        numeric|=any(not near(x,y,'ha',protocol) for x,y in zip(da,db))
    return 'erro_numerico_isolavel' if numeric else 'outro_indeterminado'


def diagnose(record,gold,protocol):
    if record['scores']['correct']:return 'acerto'
    if record['observed']['status']=='erro_tecnico':
        # A ultima tentativa determina a causa observavel da falha terminal.
        final=record['attempts'][-1] if record['attempts'] else {}
        if final.get('gateway_error')=='texto_final_ausente':return 'retorno_textual_ausente'
        if final.get('gateway_error'):return 'outra_falha_gateway'
        codes={issue.get('code') for issue in final.get('issues',[])}
        if codes and codes<=SEMANTIC_ISSUES:return 'rejeicao_semantica'
        # value_error nao preserva a causa original; nao tentar reconstruir a resposta descartada.
        return 'rejeicao_contrato_indeterminada'
    if record['scores']['status'] is False or record['scores']['clarification'] is False:return 'erro_semantico_decisao'
    if record['scores']['plan'] is False:return 'erro_semantico_plano'
    if record['scores']['values'] is False:return value_diagnosis(record['observed'],gold,protocol)
    return 'outro_indeterminado'


def sensitivity(records,cases,gold,protocol,policy):
    primary=[r for r in records if r['repeat']==0 and r['condition'] in 'BC']
    index={(r['case_id'],r['condition']):r for r in primary};ids=sorted({r['case_id'] for r in primary})
    require(len(index)==2*len(ids),'pares_BC_incompletos')
    per_case=[];counts=[];condition_rates=[]
    for r in primary:
        final=r['attempts'][-1] if r['attempts'] else {}
        per_case.append({'case_id':r['case_id'],'family_id':r['family_id'],'condition':r['condition'],
            'original_status':r['observed']['status'],'original_technical_flag':r['observed']['status']=='erro_tecnico',
            'original_correct':r['scores']['correct'],'diagnosis':diagnose(r,gold[r['case_id']],protocol),
            'terminal_issue_codes':sorted({i.get('code','') for i in final.get('issues',[])}),
            'terminal_gateway_error':final.get('gateway_error')})
    for k in 'BC':
        rs=[r for r in primary if r['condition']==k];nontechnical=[r for r in rs if r['observed']['status']!='erro_tecnico']
        num_semantics=[r for r in rs if gold[r['case_id']]['status']=='respondida' and r['scores']['status'] and r['scores']['plan']]
        condition_rates.append({'condition':k,'original_cases':len(rs),'original_technical_errors':len(rs)-len(nontechnical),
            'nontechnical_cases':len(nontechnical),'correct':sum(r['scores']['correct'] for r in nontechnical),
            'accuracy_conditional_on_own_success':sum(r['scores']['correct'] for r in nontechnical)/len(nontechnical) if nontechnical else None,
            'numeric_semantics_assessable':len(num_semantics),
            'isolated_numeric_errors':sum(p['diagnosis']=='erro_numerico_isolavel' for p in per_case if p['condition']==k)})
        c=Counter(p['diagnosis'] for p in per_case if p['condition']==k)
        counts.extend({'condition':k,'diagnosis':category,'count':c[category],'denominator':len(rs)} for category in CATEGORIES)
    all_pairs=[{'case_id':cid,'family_id':cases[cid]['family_id'],'B':int(index[cid,'B']['scores']['correct']),
                'C':int(index[cid,'C']['scores']['correct']),
                'B_technical':index[cid,'B']['observed']['status']=='erro_tecnico',
                'C_technical':index[cid,'C']['observed']['status']=='erro_tecnico'} for cid in ids]
    common=[p for p in all_pairs if not p['B_technical'] and not p['C_technical']]
    masks={'ambas_sem_erro_tecnico':common,
           'ambas_sem_erro_tecnico_gabarito_quantitativo':[p for p in common if gold[p['case_id']]['status']=='respondida']}
    analyses=[]
    for name,subset in masks.items():
        boot=paired_bootstrap(subset,replicas=policy['sensitivity']['bootstrap_replicas'],seed=policy['sensitivity']['seed'])
        analyses.append({'analysis':name,'cases':len(subset),'excluded':len(ids)-len(subset),
            'case_ids':[p['case_id'] for p in subset],'B_correct':sum(p['B'] for p in subset),'C_correct':sum(p['C'] for p in subset),
            'B_accuracy':sum(p['B'] for p in subset)/len(subset) if subset else None,
            'C_accuracy':sum(p['C'] for p in subset)/len(subset) if subset else None,'paired':boot,
            'exploratory':True,'conditioned_on_observed_outcome':True})
    # Decomposicao descritiva aditiva: a contribuicao de cada estrato usa o denominador completo.
    strata=[]
    for bt,ct in [(False,False),(True,False),(False,True),(True,True)]:
        subset=[p for p in all_pairs if p['B_technical']==bt and p['C_technical']==ct]
        b=sum(p['B'] for p in subset);c=sum(p['C'] for p in subset)
        strata.append({'B_technical':bt,'C_technical':ct,'cases':len(subset),'B_correct':b,'C_correct':c,
            'net_correct_C_minus_B':c-b,'contribution_to_full_difference':(c-b)/len(ids) if ids else None})
    require(sum(r['cases'] for r in strata)==len(ids),'estratos_nao_conservam_casos')
    return {'schema_version':'sensibilidade-exploratoria-v2','analysis_kind':policy['analysis_kind'],
            'primary_scores_changed':False,'new_condition_executed':False,'new_model_calls':False,
            'primary_cases':len(ids),'per_case':per_case,'diagnostic_counts':counts,'condition_specific_rates':condition_rates,
            'paired_analyses':analyses,'technical_strata':strata,'paired_cases':all_pairs,
            'limitations':['Selecao por sucesso observado pode enviesar os subconjuntos; nao equaliza os contratos.',
                'Taxas por condicao usam denominadores diferentes e nao sao comparacao pareada.',
                'Rejeicoes genericas de B nao permitem distinguir erro JSON, semantico ou numerico.',
                'Ausencia de erro numerico isolavel nao prova capacidade aritmetica: so e avaliavel apos semantica/contrato validos.',
                'Rejeicoes semanticas de C continuam contadas como erro_tecnico na pontuacao original.',
                'Analises exploratorias apos inspecao do teste; o IC principal predefinido e preservado.']}


def real_example(root,records,policy):
    candidates=sorted((r for r in records if r['condition']=='C' and r['repeat']==0 and r['scores']['correct']
        and r['observed']['status']=='respondida' and r['plan']['operation']=='area' and len(r['result']['evidence'])==1),key=lambda r:r['case_id'])
    require(bool(candidates),'exemplo_real_nao_disponivel');r=candidates[0];e=r['result']['evidence'][0]
    source=Path(root)/'artifacts/evaluation/test_v1/individual'/f'{r["case_id"]}_C_0.json'
    require(read(source)==r,'registro_exemplo_divergente')
    plan=r['result']['plan'];value=r['result']['values'][0]
    require(r['plan']==plan==r['observed']['plan'],'planos_do_exemplo_divergentes')
    require(value['evidence_id']==e['evidence_id'],'evidencia_exemplo_divergente')
    return {'schema_version':'exemplo-real-v2','selection_rule':policy['real_example_selection'],'integration_kind':r['integration_kind'],
        'new_inference_performed':False,'source_record':str(source.relative_to(root)),'source_record_sha256':sha(source),
        'case_id':r['case_id'],'evaluation_run_id':r['run_id'],'question':r['question'],'candidate_intent':r.get('C_candidate_intent'),
        'validated_plan':plan,'final_answer':r['final_answer'],'server_message':r['result']['message'],
        'answer_id':r['result']['answer_id'],'plan_id':r['result']['plan_id'],'evidence':e,'value':value,
        'execution':r['result']['execution'],'operation_executed':{'template':'soma das areas anuais das classes folha selecionadas, na particao e territorio solicitados',
            'input_unit':'m2 no Parquet; conversao /10000 para ha','output_unit':value['unit'],'support':'anual','class_codes':e['class_codes']},
        'source_limits':['Revisao oficial do espelho e edicao/licenca da malha nao comprovadas; nova verificacao de proveniencia e separada do registro historico.']}


def provenance_report(root,audit,public_path,comments_path):
    root=Path(root);snapshot=read(root/'data/mesh_RN_v1.json')
    geo=read(root/'artifacts/processing'/audit['data_run_id']/'manifest.json')
    sp=root/'artifacts/staging'/geo['identity']['staging_id']/'manifest.json';staging=read(sp)
    public=read(public_path) if Path(public_path).is_file() else {'state':'pendente','files':[]}
    comments=read(comments_path) if Path(comments_path).is_file() else {'state':'pendente','tables':[]}
    if public.get('source_geo_run_id'):require(public['source_geo_run_id']==audit['data_run_id'] and public['staging_sha256']==sha(sp),'verificacao_publica_de_outro_dado')
    files=[]
    for f in staging['files']:
        year=int(f['name'].split('_')[-1].split('.')[0]);official=next((x for x in public['files'] if x['year']==year),None)
        if official and official.get('state')=='verificado_intervalos_utilizados':
            expected={c['offset']:c for c in f['source_chunks']}
            checked={c['offset']:c for c in official['chunks']}
            require(len(checked)==len(official['chunks']) and set(checked)==set(expected),'intervalos_oficiais_incompletos_ou_duplicados')
            require(all(c['bytes']==expected[offset]['bytes'] and c['historical_sha256']==expected[offset]['sha256']
                and c.get('official_sha256')==c['historical_sha256'] and c.get('match') is True
                for offset,c in checked.items()),'hash_de_intervalo_oficial_incoerente')
            require(official['official_object']['size']==f['source']['size'],'tamanho_nacional_divergente')
        files.append({'year':year,'original_basename':f['source']['url'].split('/')[-1],'mirror':f['source'],
            'native_crop':{'path':str((sp.parent/f['name']).relative_to(root)),'bytes':f['bytes'],'sha256':f['sha256']},
            'source_chunks':f['source_chunks'],'official_verification':official,'full_national_sha256':None})
    return {'schema_version':'dossie-proveniencia-v2','source_geo_run_id':audit['data_run_id'],
        'historical_sources_rewritten':False,'raster_files':files,'staging':{'path':str(sp.relative_to(root)),'sha256':sha(sp),
            'acquired_at':staging['created_at'],'strategy':staging['strategy'],'resampling':staging['resampling'],'overviews_used':staging['overviews_used'],'resources':staging['resources']},
        'territorial_snapshot':{'path':'data/mesh_RN_v1.json','file_sha256':sha(root/'data/mesh_RN_v1.json'),
            'mesh_sha256':snapshot['mesh_sha256'],'acquired_at':snapshot['created_at'],'source_tables':snapshot['source_tables'],
            'source_kind':'copia local de tabelas internas PostgreSQL/PostGIS, transacao somente leitura',
            'read_only_confirmed':snapshot['read_only_confirmed'],'crs':snapshot['crs'],'features':len(snapshot['features']),
            'territorial_edition':snapshot['territorial_edition'],'original_provider':None,'original_file':None,'original_publication_date':None,'license':None,
            'date_note':'data de extracao e conhecida; nao e data de publicacao nem edicao da malha',
            'current_catalog_comments_check':comments},'legend':audit['catalog_sources'],
        'public_verification':{'state':public.get('state'),'checked_at':public.get('checked_at'),'official_page':public.get('official_page'),
            'scope_note':public.get('scope_note'),'elapsed_seconds':public.get('elapsed_seconds')},
        'pending':['Edicao, provedor original, data de publicacao e licenca da malha interna',
            'Vinculo explicito entre revisao tematica oficial e os GeoTIFFs; nao transferir v3 do asset GEE',
            'Igualdade integral dos arquivos nacionais e hash SHA-256 nacional nao verificados']}
