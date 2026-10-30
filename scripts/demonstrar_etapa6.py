"""Demonstracao REAL opt-in: FastAPI em loopback temporario + CLI + LLM.

Nao publica a aplicacao. Chaves de sessao ficam somente em memoria/arquivo privado;
nao sao incluidas nos relatorios. Execute na raiz do projeto com dados derivados.
"""
import argparse
import csv
import io
import json
import math
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import requests
from consultas_ambientais.storage.dialogues import private_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('reports/etapa6/demonstracao_real.json'))
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to((Path.cwd()/'reports/etapa6').resolve()):
        raise ValueError('relatorio_exige_reports_etapa6')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    process=subprocess.Popen([sys.executable,'-B','-m','consultas_ambientais','local','--env-file',str(args.env_file),
                              'serve','--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=requests.Session();client.trust_env=False
    base=f'http://127.0.0.1:{port}'
    report={'schema_version':'demonstracao-etapa6-real-v1','started_at':datetime.now(timezone.utc).isoformat(),
            'data_kind':'real','gateway_kind':'real','public_deployment':False,'loopback_only':True,'phase':'startup','cases':[]}
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('servidor_local_nao_iniciou')
            try:
                if client.get(base+'/healthz',timeout=1).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.1)
        else:raise RuntimeError('servidor_local_indisponivel')
        def get(path):
            r=client.get(base+path,timeout=15);r.raise_for_status();return r
        report['phase']='capabilities'
        caps=get('/v1/capabilities').json()
        assert caps['data_kind']=='real' and caps['materialized_years']==[2015,2025]
        assert len(caps['territories'])==168
        assert caps['ranking'][0]['status']=='dados_indisponiveis'
        assert caps['ranking'][0]['missing_or_partial_codes']==['2401107']
        report['capabilities']=caps
        raw=client.post(base+'/v1/sessions',timeout=10);raw.raise_for_status()
        sess=raw.json();sid=sess['session_id'];client.headers['X-Session-Token']=sess['session_token']
        reference=json.loads(Path('docs/VALIDACAO_ETAPA4.json').read_text())
        refs={r['case']:r for r in reference['real_cases']}
        def verify_result(a):
            assert a['data_kind']=='real'
            url=f'/v1/sessions/{sid}/results/{a["result_id"]}'
            assert get(url).json()==a
            assert get(url+'/export/json').json()==a
            private_json(args.output.parent/'responses'/(a['result_id']+'.json'),a)
            if a['result'] and a['result']['values']:
                q=a['result'];assert q['execution']['run_id']==caps['run_id']
                ev=get(url+'/evidence').json()['evidence']
                assert ev==q['evidence']
                assert get(f'/v1/sessions/{sid}/answers/{q["answer_id"]}').json()==q
                rows=list(csv.DictReader(io.StringIO(get(url+'/export/csv').text)))
                assert len(rows)==len(q['values'])
                html=get(url+'/export/html').text
                for row,v in zip(rows,q['values']):
                    assert (row['value']=='' if v['value'] is None else float(row['value'])==v['value'])
                    assert row['evidence_id']==v['evidence_id']
                    assert get(url+'/evidence/'+v['evidence_id']).json()['evidence_id']==v['evidence_id']
                    if v['value'] is not None:assert repr(v['value']) in html
                assert q['message'] in a['message']
        examples=[('municipio','Qual era a área de pastagem de Riachuelo/RN em 2015, em hectares?','respondida','plano_area_pastagem'),
                  ('comparacao_2015_2025','Qual a diferença líquida de área urbanizada de Natal/RN entre 2015 e 2025, em hectares?','respondida','plano_mudanca_urbana_natal'),
                  ('ranking_rn','Quais os cinco municípios de RN com maior redução de Formação Florestal de 2015 a 2025, em hectares?','dados_indisponiveis',None),
                  ('homonimo','Qual a área de pastagem de Santa Cruz em 2015, em hectares?','precisa_esclarecimento',None),
                  ('classe_ambigua','Qual a área de floresta de Riachuelo/RN em 2015, em hectares?','precisa_esclarecimento',None),
                  ('ano_ausente','Qual a área de pastagem de Riachuelo/RN em 2016, em hectares?','dados_indisponiveis',None)]
        for name,question,expected,ref in examples:
            report['phase']=name
            r=client.post(base+f'/v1/sessions/{sid}/questions',json={'question':question},timeout=110)
            assert r.status_code==200
            a=r.json();verify_result(a)
            checks=[a['status']==expected]
            if ref and a['result']:
                checks.append(a['result']['answer_id']==refs[ref]['answer_id'])
                checks.append(len(a['result']['values'])==len(refs[ref]['checks']))
                checks.append(all(math.isclose(v['value'],float(w['reference_decimal']),rel_tol=1e-12,abs_tol=1e-10)
                                  for v,w in zip(a['result']['values'],refs[ref]['checks'])))
            record={'case':name,'question':question,'turns':[a],'checks_passed':all(checks)}
            if name=='homonimo' and a['clarification']:
                checks.append({c['uf'] for c in a['clarification']['candidates']}=={'RN','PB','PE'})
                r=client.post(base+f'/v1/sessions/{sid}/results/{a["result_id"]}/clarifications',
                              json={'clarification_id':a['clarification']['clarification_id'],'reply':'RN'},timeout=110)
                assert r.status_code==200
                b=r.json();verify_result(b);record['turns'].append(b)
                checks.append(b['status']=='respondida' and b['result']['plan']['territory_codes']==['2411205'])
            record['checks_passed']=all(checks);report['cases'].append(record)
            private_json(args.output,report)
            print(json.dumps({'case':name,'passed':record['checks_passed'],'statuses':[t['status'] for t in record['turns']]},ensure_ascii=False),flush=True)
        other=client.post(base+'/v1/sessions',timeout=10).json()
        first=report['cases'][0]['turns'][0]
        unauthorized=client.get(base+f'/v1/sessions/{sid}/results/{first["result_id"]}',
                                headers={'X-Session-Token':other['session_token']},timeout=5)
        assert unauthorized.status_code==404
        report['cross_session_denied']=True
        # CLI usa a mesma camada e os mesmos Parquets, com uma chave privada propria.
        report['phase']='cli'
        key=Path('data/local_keys')/('etapa6-'+uuid4().hex+'.json')
        def cli(*tail,env=False):
            command=[sys.executable,'-B','-m','consultas_ambientais','local']
            if env:command+=['--env-file',str(args.env_file)]
            r=subprocess.run([*command,*tail],capture_output=True,text=True,timeout=110)
            data=json.loads(r.stdout)
            assert r.returncode==0
            return data
        created=cli('session','--key-file',str(key))
        a=cli('ask','--key-file',str(key),'--question',examples[0][1],env=True)
        assert a['status']=='respondida' and a['result']['answer_id']==refs['plano_area_pastagem']['answer_id']
        assert cli('result','--key-file',str(key),'--id',a['result_id'])==a
        target='reports/local/demo_etapa6.csv'
        cli('export','--key-file',str(key),'--id',a['result_id'],'--format','csv','--output',target)
        assert float(list(csv.DictReader(Path(target).open()))[0]['value'])==a['result']['values'][0]['value']
        private_json(args.output.parent/'cli_result.json',a)
        report['cli']={'verified':True,'result_id':a['result_id'],'answer_id':a['result']['answer_id'],
                       'private_key_file':str(key),'token_published':False,'json_csv_agree':True}
        report.update(phase='complete',finished_at=datetime.now(timezone.utc).isoformat(),state='verificado',case_count=len(report['cases']),
                      all_checks_passed=all(c['checks_passed'] for c in report['cases']))
        private_json(args.output,report)
        return 0 if report['all_checks_passed'] else 2
    finally:
        client.close();process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        report['temporary_server_stopped']=process.poll() is not None
        private_json(args.output,report)


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print(json.dumps({'status':'erro_tecnico','reason':'demonstracao_nao_concluida_detalhes_omitidos'}))
        raise SystemExit(2)
