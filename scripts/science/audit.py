"""Audita linhagem e escores sem gravar nas fontes ou chamar banco/LLM."""
from pathlib import Path
from collections import Counter,defaultdict
import json
import hashlib
import numpy as np
import duckdb
from consultas_ambientais.evaluation.common import read,lines,sha,digest,canonical
from consultas_ambientais.evaluation.protocol import verify
from consultas_ambientais.evaluation.scoring import score
from consultas_ambientais.evaluation.statistics import paired_bootstrap
from consultas_ambientais.evaluation.reference import ReferenceReader
from consultas_ambientais.semantics.catalog import ClassCatalog
from consultas_ambientais.processing.snapshot import load_snapshot

STATUSES=['respondida','precisa_esclarecimento','fora_do_escopo','dados_indisponiveis','erro_tecnico']


def require(condition, code):
    if not condition:raise ValueError(code)


def audit(root):
    root=Path(root);b=root/'benchmarks/pt_rn_v1';directory=root/'artifacts/evaluation/test_v1'
    frozen=verify(b,root);freeze=read(b/'freeze.json');run=read(directory/'run.json')
    require(run['state']=='concluida' and run['freeze_sha256']==frozen,'execucao_ou_congelamento_divergente')
    paths=sorted((directory/'individual').glob('*.json'))
    require({p.name:sha(p) for p in paths}==run['individual_hashes'],'saidas_individuais_alteradas')
    records=[read(p) for p in paths];cases={c['case_id']:c for c in lines(b/'cases.jsonl')}
    gold=read(b/'gold.json');leaves=read(b/'classes.json');protocol=read(b/'protocol.json')
    expected=set(run['case_ids']);primary=[r for r in records if r['repeat']==0]
    require(len(primary)==3*len(expected),'numero_de_pares_incompleto')
    keys=[(r['case_id'],r['condition'],r['repeat']) for r in records]
    require(len(keys)==len(set(keys)),'avaliacoes_duplicadas')
    require({(r['case_id'],r['condition']) for r in primary}=={(cid,k) for cid in expected for k in 'ABC'},'universo_de_casos_divergente')
    classes=ClassCatalog.load();rid=run['data_run_id'];manifest_path=root/'artifacts/processing'/rid/'manifest.json'
    manifest=read(manifest_path);identity=manifest['identity'];mesh=load_snapshot(root/'data/mesh_RN_v1.json')
    require(identity['mesh_sha256']==mesh['mesh_sha256'],'malha_divergente')
    require(identity['catalog_sha256']==classes.sha256,'legenda_divergente')
    require(identity['config']['collection']==11 and identity['years']==[2015,2025],'colecao_anos_divergentes')
    require(identity['territory_codes']==sorted(f['code'] for f in mesh['features']),'universo_geoespacial_divergente')
    geometry={f['code']:f['geometry_sha256'] for f in mesh['features']}
    for r in records:
        require(r['run_id']==run['run_id'] and r['freeze_sha256']==frozen,'registro_em_outra_execucao')
        require(r['integration_kind']=='gateway_real' and r['configuration']==freeze['configuration'],'modelo_configuracao_divergentes')
        require(r['family_id']==cases[r['case_id']]['family_id'],'familia_divergente')
        require(r['scores']==score(r['observed'],gold[r['case_id']],protocol,leaves),'escore_divergente')
        require(r['model']==freeze['configuration']['requested_model'],'modelo_informado_divergente')
        if r['condition']=='B':require(r['facts_sha256']==digest(read_facts(b)[r['case_id']]),'contexto_B_divergente')
        if r['condition']=='C':
            context=r['source_context']
            require(context['run_id']==rid and context['run_manifest_sha256']==sha(manifest_path),'fonte_C_divergente')
            require(context['class_catalog_sha256']==classes.sha256,'catalogo_C_divergente')
            dialogue=read(root/'artifacts/dialogues'/r['C_session_id']/(r['C_turn_id']+'.json'))
            require(dialogue['prompt_hashes']==freeze['production_prompt_hashes'],'prompt_C_divergente')
            require(dialogue['interpreter_sha256']==freeze['interpreter_sha256'],'interpretador_C_divergente')
            require(dialogue['question']==r['question'],'pergunta_C_divergente')
            if dialogue.get('context'):
                require(digest(dialogue['context'])==dialogue['context_sha256'],'hash_contexto_C_divergente')
            if r.get('result'):
                ex=r['result'].get('execution')
                if ex:
                    require(ex['run_id']==rid and ex['run_manifest_sha256']==sha(manifest_path),'revisao_do_resultado_divergente')
                    require(ex['mesh_sha256']==mesh['mesh_sha256'] and ex['catalog_sha256']==classes.sha256,'malha_legenda_resultado_divergentes')
                    require(ex['source_revision']==identity['config']['source_revision'],'revisao_oficial_resultado_divergente')
                for e in r['result']['evidence']:
                    require(e['territory']['geometry_hash']==geometry[e['territory']['code']],'geometria_evidencia_divergente')
        else:require(r['source_context']['data_run_id']==rid,'fonte_AB_divergente')
    # Reconstituir as mensagens A/B iniciais; sem enviar mensagens ao gateway.
    from consultas_ambientais.evaluation.models import BaselineAnswer
    import consultas_ambientais.evaluation.baselines as baselines
    prompt_dir=Path(baselines.__file__).parent/'prompts';facts=read_facts(b)
    for r in records:
        if r['condition'] not in 'AB' or not r['attempts']:continue
        bundle=facts[r['case_id']]
        ctx={'documentation':(prompt_dir/'documentation.txt').read_text(),'catalog_and_scope':bundle['context']}
        if r['condition']=='B':ctx.update(tables=bundle['tables'],table_columns=bundle['table_columns'])
        user=canonical({'condition':r['condition'],'question':r['question'],'context':ctx,'output_contract':BaselineAnswer.model_json_schema()})
        messages=[{'role':'system','content':(prompt_dir/'baseline.txt').read_text()},{'role':'user','content':user}]
        require(digest(messages)==r['attempts'][0]['messages_sha256'],'mensagens_AB_divergentes')
    # Conferir todos os Parquets e sua linhagem; nao confiar no indice DuckDB acumulado.
    paths_by_kind=defaultdict(list);part_hashes={}
    for part in manifest['partitions']:
        code=part['territory_code'];base=root/'data/processed'/rid/code
        require(read(base/'manifest.json')['files']==part['files'],'manifest_particao_divergente')
        for entry in part['files']:
            path=base/entry['name'];require(sha(path)==entry['sha256'],'parquet_divergente')
            part_hashes[str(path.relative_to(root))]=entry['sha256'];paths_by_kind[entry['name']].append(str(path))
    with duckdb.connect(':memory:') as db:
        db.execute('SET threads=1')
        rows=db.execute('SELECT DISTINCT run_id,collection,source_revision,territorial_edition,mesh_sha256,catalog_sha256,method,source_fingerprint FROM read_parquet(?)',[paths_by_kind['areas.parquet']]).fetchall()
        require(rows==[(rid,11,identity['config']['source_revision'],identity['config']['territorial_edition'],mesh['mesh_sha256'],classes.sha256,identity['method'],identity['staging_id'])],'mistura_de_revisoes_nos_Parquets')
        area_count=db.execute('SELECT count(*) FROM read_parquet(?)',[paths_by_kind['areas.parquet']]).fetchone()[0]
        quality_count=db.execute('SELECT count(*) FROM read_parquet(?)',[paths_by_kind['quality.parquet']]).fetchone()[0]
    staging_path=root/'artifacts/staging'/identity['staging_id']/'manifest.json';staging=read(staging_path)
    require(sha(staging_path)==manifest['staging_manifest_sha256'],'staging_manifest_divergente')
    require(staging['overviews_used'] is False and staging['resampling'] is None,'reamostragem_nao_identificada')
    crop_hashes=[]
    for f in staging['files']:
        path=staging_path.parent/f['name'];require(sha(path)==f['sha256'],'recorte_raster_divergente');crop_hashes.append(f['sha256'])
    require(crop_hashes==manifest['input_crop_hashes'],'identificacao_de_recortes_divergente')
    # Conferir os fatos elementares realmente fornecidos a B contra os Parquets atuais.
    reader=ReferenceReader(root,rid,classes)
    for cid,bundle in facts.items():
        codes=[t['territory_code'] for t in bundle['tables']]
        require(reader.facts(codes)==bundle['tables'],'tabela_B_nao_corresponde_aos_derivados')
        require(not bundle['truncated'] and bundle['complete'],'contexto_B_truncado')
    common_by_code=defaultdict(list)
    for q in manifest['quality_summary']:
        if q['support']=='comum' and len(q['territory_code'])==7:common_by_code[q['territory_code']].append(q)
    eligible={code for code,qs in common_by_code.items() if len(qs)==2 and all(q['eligible_complete'] for q in qs)}
    unknown=[{'territory_code':q['territory_code'],'year':q['year'],'support':q['support'],'unknown_codes_m2':q['unknown_codes_m2']} for q in manifest['quality_summary'] if q['unknown_codes_m2']]
    catalog_sources=[]
    cat_root=Path(__import__('consultas_ambientais.semantics.catalog',fromlist=['x']).__file__).parent/'data/mapbiomas_col11_v1/sources'
    for src in classes.data.sources:
        matches=[f for f in cat_root.iterdir() if f.is_file() and sha(f)==src.sha256]
        require(len(matches)==1,'documento_legenda_ausente_ou_alterado')
        catalog_sources.append({'source_id':src.source_id,'url':src.url,'sha256':src.sha256,'retrieved_at':src.retrieved_at.isoformat()})
    from consultas_ambientais.processing.runner import software
    require(software()['implementation_sha256']==identity['software']['implementation_sha256'],'implementacao_geoespacial_divergente')
    summary={'state':'verificado','scope':'auditoria local; sem nova consulta ao banco, raster remoto ou LLM',
             'freeze_sha256':frozen,'run_id':run['run_id'],'data_run_id':rid,'data_manifest_sha256':sha(manifest_path),
             'mesh_sha256':mesh['mesh_sha256'],'snapshot_file_sha256':sha(root/'data/mesh_RN_v1.json'),
             'catalog_sha256':classes.sha256,'catalog_sources':catalog_sources,
             'collection':identity['config']['collection'],'years':identity['years'],'crs':mesh['crs'],
             'official_source_revision':identity['config']['source_revision'],'territorial_edition':mesh['territorial_edition'],
             'municipalities':sum(f['kind']=='municipio' for f in mesh['features']),
             'municipalities_eligible_common':len(eligible),'territories':len(mesh['features']),
             'area_records':area_count,'quality_records':quality_count,'partitions_checked':len(part_hashes),
             'repaired_geometries':sum(f['repair']['repaired'] for f in mesh['features']),
             'unknown_code_diagnostics':unknown,'ranking_eligible':manifest['ranking_eligible'],
             'area_method':identity['method'],'software':identity['software'],'raster_sources':manifest['sources'],
             'crop_hashes':crop_hashes,'native_grids':[f['native_grid'] for f in staging['files']],
             'returned_models':sorted({a['returned_model'] for r in records for a in r['attempts'] if a.get('returned_model')}),
             'configuration':freeze['configuration'],'production_prompt_hashes':freeze['production_prompt_hashes'],
             'baseline_prompt_hashes':{p.name:sha(p) for p in prompt_dir.glob('*.txt')},
             'executor_sha256':freeze['executor_sha256'],'interpreter_sha256':freeze['interpreter_sha256'],
             'primary_records':len(primary),'repeat_records':len(records)-len(primary),
             'all_scores_recomputed':True,'all_B_tables_reconciled':True,'all_C_lineage_reconciled':True,
             'status_of_evidence':{'real':'teste principal, desenvolvimento e diagnostico de contexto do gateway',
                 'synthetic':'testes unitarios/mocks; excluidos das metricas cientificas',
                 'pending':['verdade de campo e acuracia tematica','revisao oficial do espelho','edicao e licenca da malha territorial','revisao humana do benchmark','revisao dos pesos do modelo','ranking positivo completo RN','autoria/afiliacoes e licencas do codigo/benchmark']}}
    return summary,records,cases,protocol


_FACT_CACHE={}
def read_facts(benchmark):
    path=str(Path(benchmark).resolve())
    if path not in _FACT_CACHE:_FACT_CACHE[path]=read(Path(benchmark)/'facts.json')
    return _FACT_CACHE[path]
