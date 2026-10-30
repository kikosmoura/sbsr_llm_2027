"""Experimento exploratorio SEPARADO: tamanho de contexto e B em pergunta de DEV.

Nao modifica o benchmark/runner congelado. Sem coleta de novos dados ambientais.
Os tamanhos e a pergunta sao fixados neste script antes de qualquer saida observada.
"""
from pathlib import Path
from uuid import uuid4
import copy
import time
import argparse
from consultas_ambientais.evaluation.common import read,save,sha,digest,canonical,now
from consultas_ambientais.evaluation.reference import ReferenceReader
from consultas_ambientais.evaluation.baselines import run_baseline
from consultas_ambientais.evaluation.scoring import score
from consultas_ambientais.evaluation.protocol import verify
from consultas_ambientais.evaluation.runner import public_configuration
from consultas_ambientais.delivery.settings import LocalSettings,load_environment
from consultas_ambientais.llm.client import GatewayClient
from consultas_ambientais.llm.privacy import Redactor
from consultas_ambientais.semantics.catalog import ClassCatalog


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--env-file',type=Path);args=parser.parse_args()
    root=Path.cwd();benchmark=root/'benchmarks/pt_rn_v1';output=root/'artifacts/evaluation/context_scale_v1'
    if read(root/'artifacts/evaluation/test_v1/run.json')['state']!='concluida':
        raise ValueError('primeiro_concluir_teste_principal')
    local=LocalSettings.load(root/'configs/evaluation.json');environment=load_environment(local,args.env_file)
    config=public_configuration(local,environment);frozen=verify(benchmark,root,config)
    facts=read(benchmark/'facts.json')['d01_1'];protocol=read(benchmark/'protocol.json')
    question='Qual era a área de Pastagem em Riachuelo/RN em 2015, em hectares?'
    sizes=[1,5,10,20,40,80,167]
    identity={'kind':'exploratorio_separado','case_id':'d01_1','question':question,'sizes':sizes,
              'gateway_sizes':[1,5,10,20],'replications':1,'freeze_primary':frozen,'configuration':config,
              'scope':'RN; somente tamanho e uma pergunta de desenvolvimento; nao teste nacional',
              'max_context_bytes':protocol['max_context_bytes_B'],'no_silent_truncation':True,
              'script_sha256':sha(Path(__file__))}
    output.mkdir(parents=True,exist_ok=True)
    if (output/'protocol.json').exists():
        if read(output/'protocol.json')!=identity:raise ValueError('protocolo_contexto_divergente')
    else:save(output/'protocol.json',identity)
    reader=ReferenceReader(root,local.run_id,ClassCatalog.load())
    candidates=sorted(c for c in reader.parts if len(c)==7 and c!='2410900')
    order=['2410900',*candidates]
    baseline_dir=Path(__import__('consultas_ambientais.evaluation.baselines',fromlist=['x']).__file__).parent/'prompts'
    documentation=(baseline_dir/'documentation.txt').read_text()
    records=[]
    for n in sizes:
        path=output/f'{n:03}.json'
        if path.exists():records.append(read(path));continue
        start=time.monotonic();bundle=copy.deepcopy(facts);bundle['tables']=reader.facts(order[:n])
        payload={'documentation':documentation,'catalog_and_scope':bundle['context'],
                 'tables':bundle['tables'],'table_columns':bundle['table_columns']}
        context_bytes=len(canonical(payload).encode());complete=len(bundle['tables'])==n
        record={'created_at':now(),'territories':n,'context_bytes':context_bytes,'context_sha256':digest(payload),
                'complete_tables':complete,'truncated':False,'fits_application_limit':context_bytes<=protocol['max_context_bytes_B'],
                'data_preparation_seconds':time.monotonic()-start,'gateway_executed':False,
                'observed':None,'attempts':[],'scores':None,'latency_seconds':None,'cost':None}
        if n<=20 and record['fits_application_limit']:
            client=GatewayClient(environment.settings)
            redactor=Redactor.from_environment(environment.settings)
            redactor=Redactor([*redactor.secrets,*environment.redaction_secrets])
            try:
                observed,attempts,latency,messages_sha=run_baseline('B',question,bundle,client,redactor,protocol['max_context_bytes_B'])
                record.update(gateway_executed=True,observed=observed,attempts=attempts,
                              latency_seconds=latency,messages_sha256=messages_sha,
                              scores=score(observed,read(benchmark/'gold.json')['d01_1'],protocol,read(benchmark/'classes.json')))
            finally:client.close()
        else:
            record['reason']='contexto_excede_limite_da_aplicacao; nenhuma chamada, nenhum truncamento'
        save(path,record);records.append(record)
        print(f'contexto: {n} territorios; {context_bytes} bytes; gateway={record["gateway_executed"]}',flush=True)
    save(output/'report.json',{'created_at':now(),'protocol_sha256':sha(output/'protocol.json'),'primary_run_unchanged':True,
                             'configuration':config,'kind':'exploratorio_separado','records':records,
                             'input_hashes':reader.input_hashes,
                             'limitations':['Uma pergunta de desenvolvimento e execucao unica por tamanho.',
                                            'Nao estima capacidade maxima do modelo: o limite local e aplicado antes do gateway.',
                                            'Nao entra no acerto ou bootstrap do teste principal.','Dados de custo ausentes ficam null.']})
    verify(benchmark,root,config)


if __name__=='__main__':main()
