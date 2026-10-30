"""Verificacao opt-in de fontes; nao altera dados historicos nem reprocessa areas."""
import hashlib
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from consultas_ambientais.evaluation.common import read, save, sha
from .audit import require
from .publication import scan_text


def bounded_body(response, limit):
    chunks=[];size=0
    for chunk in response.iter_content(16384):
        size+=len(chunk)
        if size>limit:raise ValueError('limite_de_bytes')
        chunks.append(chunk)
    return b''.join(chunks)


def check_chunk(url, head, chunk, session=None):
    start=chunk['offset'];length=chunk['bytes'];end=start+length-1
    result={'offset':start,'bytes':length,'historical_sha256':chunk['sha256'],'state':'indisponivel'}
    own=session is None
    session=session or requests.Session()
    try:
        with session.get(url, params={'generation':head['generation']},
                         headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity','If-Match':head['etag']},
                         stream=True,timeout=(10,20),verify=True) as response:
            result['http_status']=response.status_code
            # Rejeitar 200 antes de consumir o corpo para impedir download nacional.
            if response.status_code!=206:result['reason']='range_nao_atendido';return result
            if response.headers.get('Content-Range')!=f'bytes {start}-{end}/{head["size"]}':
                result['reason']='content_range_incoerente';return result
            if response.headers.get('x-goog-generation')!=head['generation']:
                result['reason']='geracao_divergente';return result
            body=bounded_body(response,length)
            if len(body)!=length:result['reason']='comprimento_divergente';return result
            digest=hashlib.sha256(body).hexdigest();match=digest==chunk['sha256']
            result.update(state='verificado' if match else 'divergente',official_sha256=digest,match=match)
    except (requests.RequestException,ValueError):result['reason']='rede_tls_ou_limite'
    finally:
        if own:session.close()
    return result


def acquire_public(root, output, policy):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    run=read(root/'artifacts/evaluation/test_v1/run.json')
    geo=read(root/'artifacts/processing'/run['data_run_id']/'manifest.json')
    staging_path=root/'artifacts/staging'/geo['identity']['staging_id']/'manifest.json'
    require(sha(staging_path)==geo['staging_manifest_sha256'],'staging_alterado')
    staging=read(staging_path)
    config=policy['public_provenance_check'];started=time.monotonic()
    expected_bytes=sum(c['bytes'] for f in staging['files'] for c in f['source_chunks'])
    expected_requests=sum(len(f['source_chunks']) for f in staging['files'])+3
    require(expected_bytes<=config['max_bytes'] and expected_requests<=config['max_requests'],'orcamento_publico_insuficiente')
    report={'schema_version':'proveniencia-publica-v2','checked_at':datetime.now(timezone.utc).isoformat(),
            'checked_on':datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat(),'source_geo_run_id':run['data_run_id'],'staging_sha256':sha(staging_path),
            'tls_verified':True,'full_national_download':False,'policy':config,'files':[]}
    page_path=output/'mapbiomas_cobertura.html'
    with requests.get(config['page'],timeout=(10,30),stream=True,verify=True) as response:
        response.raise_for_status();page=bounded_body(response,2*1024*1024)
    page_path.write_bytes(page)
    text=html.unescape(page.decode(errors='replace'))
    assets=sorted(set(re.findall(r'projects/PROJECT_ID/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v\d+',text)))
    report['official_page']={'url':config['page'],'sha256':sha(page_path),'bytes':len(page),'observed_gee_assets':assets,
        'geotiff_link_found':config['official_base']+'/brazil_coverage-col11_2025.tif' in text}
    require(report['official_page']['geotiff_link_found'],'url_oficial_nao_confirmada_na_pagina')
    for source in staging['files']:
        year=int(source['name'].split('_')[-1].split('.')[0]);url=config['official_base']+f'/brazil_coverage-col11_{year}.tif'
        row={'year':year,'official_url':url,'mirror':source['source'],'crop_file':source['name'],'crop_sha256':source['sha256'],
             'official_revision_of_historical_mirror':None,'chunks':[]}
        try:
            with requests.head(url,timeout=(10,25),verify=True,allow_redirects=True) as response:
                require(response.status_code==200,'head_nao_disponivel')
                head={'size':int(response.headers['Content-Length']),'etag':response.headers['ETag'],
                      'last_modified':response.headers.get('Last-Modified'),'generation':response.headers['x-goog-generation'],
                      'reported_hashes':response.headers.get('x-goog-hash')}
            row['official_object']=head
            require(head['size']==source['source']['size'],'tamanho_oficial_espelho_divergente')
            with ThreadPoolExecutor(max_workers=config['workers']) as pool:
                futures={pool.submit(check_chunk,url,head,c):c for c in source['source_chunks']}
                for future in as_completed(futures,timeout=max(1,config['wall_timeout_seconds']-(time.monotonic()-started))):
                    row['chunks'].append(future.result())
                    if len(row['chunks'])%40==0:print(json.dumps({'year':year,'intervals_checked':len(row['chunks'])}),flush=True)
            row['chunks'].sort(key=lambda c:c['offset'])
        except (requests.RequestException,ValueError,KeyError,TimeoutError):
            row['acquisition_issue']='verificacao_nao_concluida; nao equivale a arquivo ausente'
        row['expected_chunks']=len(source['source_chunks']);row['matched_chunks']=sum(c.get('match') is True for c in row['chunks'])
        row['requested_bytes']=sum(c['bytes'] for c in row['chunks']);row['state']='verificado_intervalos_utilizados' if row['matched_chunks']==row['expected_chunks'] else 'pendente_ou_divergente'
        report['files'].append(row)
        save(output/'verificacao_publica.json',report)
    report['elapsed_seconds']=time.monotonic()-started
    report['state']='verificado_intervalos_utilizados' if all(f['state']=='verificado_intervalos_utilizados' for f in report['files']) else 'pendente_ou_divergente'
    report['scope_note']='Igualdade dos bytes dos intervalos utilizados, nao hash integral nacional nem identificacao de revisao tematica. Asset GEE e GeoTIFF nao sao vinculados por inferencia.'
    save(output/'verificacao_publica.json',report)
    return report


def database_comments(root, output):
    """Uma transacao READ ONLY limitada aos comentarios do catalogo; nenhuma geometria."""
    from dotenv import dotenv_values
    from consultas_ambientais.settings import DatabaseSettings
    import psycopg2
    values=dotenv_values(Path(root)/'.env',interpolate=False)
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'state':'indisponivel',
            'scope':'comentarios de catalogo de sbsr.municipios e sbsr.uf; nenhuma geometria; rollback',
            'read_only_confirmed':False,'tables':[],'creation_or_edition_date_inferred':False}
    conn=None
    try:
        settings=DatabaseSettings.from_env(values)
        if not settings.configured:report['reason']='configuracao_ausente';return report
        conn=psycopg2.connect(host=settings.host.get_secret_value(),port=settings.port,
             dbname=settings.database.get_secret_value(),user=settings.user.get_secret_value(),password=settings.password.get_secret_value(),
             sslmode=settings.sslmode,connect_timeout=settings.connect_timeout,
             options='-c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=1000')
        conn.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        private=[v for k,v in values.items() if v and (k.startswith('SOURCE_PG_') or k in {'LLM_CLIENT_SECRET','LLM_CLIENT_ID'}) and len(v)>3]
        with conn.cursor() as cursor:
            cursor.execute('SHOW transaction_read_only');require(cursor.fetchone()[0]=='on','conexao_nao_somente_leitura');report['read_only_confirmed']=True
            cursor.execute("""SELECT c.relname,obj_description(c.oid,'pg_class'),a.attname,col_description(c.oid,a.attnum)
                FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
                WHERE n.nspname=%s AND c.relname IN (%s,%s) ORDER BY c.relname,a.attnum""",('sbsr','municipios','uf'))
            rows=cursor.fetchall();require(len(rows)<=80,'metadados_fora_do_limite')
        for table in ['municipios','uf']:
            selected=[r for r in rows if r[0]==table];comments=[{'column':r[2],'comment':r[3]} for r in selected if r[3]]
            table_comment=selected[0][1] if selected else None
            raw=json.dumps({'table_comment':table_comment,'column_comments':comments},ensure_ascii=False)
            safe=not scan_text(raw,private)
            report['tables'].append({'name':'sbsr.'+table,'found':bool(selected),'table_comment':table_comment if safe else None,
                'column_comments':comments if safe else [],'redacted':not safe,'edition_identified':False,'license_identified':False})
        report['state']='verificado';report['reason']='comentarios_inspecionados; ausencia_nao_identifica_origem'
    except Exception:report['reason']='falha_de_configuracao_conexao_ou_consulta; detalhes_redigidos'
    finally:
        if conn:
            try:conn.rollback()
            finally:conn.close()
        save(Path(output)/'metadados_malha.json',report)
    return report
