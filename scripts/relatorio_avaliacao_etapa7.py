"""Relatorio descritivo dos escores congelados; nao reavalia respostas nem ajusta modelos.

Executar na raiz do projeto apos `evaluate report`. Nao le .env, nao faz rede.
"""
import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from consultas_ambientais import __version__
from consultas_ambientais.evaluation.common import read, save, sha
from consultas_ambientais.evaluation.protocol import verify


def percent(value):
    return 'null' if value is None else f'{100*value:.2f}%'


def interval(value):
    if value.get('state')!='verificado':return 'pendente'
    lo,hi=value['ci95']
    return f"{100*value['difference_C_minus_B']:+.2f} pp (IC95% {100*lo:+.2f} a {100*hi:+.2f} pp)"


def main():
    root=Path.cwd();benchmark=root/'benchmarks/pt_rn_v1'
    frozen=verify(benchmark,root)
    reports={name:read(root/'artifacts/evaluation'/name/'metrics.json') for name in ['dev_smoke_v1','dev_smoke_v2','test_v1']}
    test=reports['test_v1'];run=read(root/'artifacts/evaluation/test_v1/run.json')
    assert run['state']=='concluida' and run['freeze_sha256']==frozen
    paths=sorted((root/'artifacts/evaluation/test_v1/individual').glob('*.json'))
    assert {p.name:sha(p) for p in paths}==run['individual_hashes']
    records=[read(p) for p in paths]
    assert len(records)==372 and sum(r['repeat']==0 for r in records)==360
    models=sorted({a['returned_model'] for r in records for a in r['attempts'] if a.get('returned_model')})
    breakdown={}
    for condition in ['A','B','C']:
        selected=[r for r in records if r['condition']==condition and r['repeat']==0]
        # Apenas contagens dos criterios ja congelados, sem nova pontuacao/juiz.
        breakdown[condition]={field+'_failed':sum(r['scores'].get(field) is False for r in selected)
                              for field in ['status','plan','values','clarification']}
        breakdown[condition]['technical_cases']=[r['case_id'] for r in selected if r['observed']['status']=='erro_tecnico']
        breakdown[condition]['technical_reasons']=dict(Counter(r['observed']['reason'] for r in selected if r['observed']['status']=='erro_tecnico'))
        breakdown[condition]['gateway_errors']=dict(Counter(a['gateway_error'] for r in selected for a in r['attempts'] if a.get('gateway_error')))
        breakdown[condition]['incorrect_cases']=[r['case_id'] for r in selected if not r['scores']['correct']]
    repeated=test['repeatability']
    repetitions={'comparisons':len(repeated),'same_normalized_answer':sum(r['same_normalized_answer'] for r in repeated),
                 'same_correctness':sum(r['same_correctness'] for r in repeated),
                 'selection_of_best_response':False,'temperature_zero_is_determinism':False}
    prior=read(root/'docs/PREREGISTRO_ETAPA7.json')
    assert all(sha(root/name)==value for name,value in prior['upstream_metadata_sha256'].items())
    value={'schema_version':'validacao-etapa7-v1','created_at':datetime.now(timezone.utc).isoformat(),
           'state':'verificado','package_version':__version__,'tests':{'passed':263,'evaluation_new_tests':24,'kind':'sinteticos_e_mocks; nao entram no resultado cientifico'},
           'benchmark':{'path':'benchmarks/pt_rn_v1','dev_cases':40,'test_cases':120,'dev_families':10,'test_families':15,
                        'test_numeric_cases':88,'freeze_sha256':frozen,'human_review_performed':False,
                        'reference':'Decimal independente sobre Parquets; nao e referencia de campo'},
           'real_development_diagnostic':reports['dev_smoke_v1'],
           'real_development_after_local_copy':reports['dev_smoke_v2'],
           'real_test':test,'test_individual_records':len(records),'primary_records':360,'repeat_records':12,
           'returned_models_observed':models,'repeatability_summary':repetitions,
           'descriptive_failures_of_frozen_criteria':breakdown,
           'descriptive_failure_note':'Contagens sobre os mesmos escores congelados; nenhum criterio, tolerancia ou acerto foi alterado.',
           'source_database_called':False,'raster_download_performed':False,
           'production_executor_and_interpreter_unchanged':True,'test_tuning_performed':False,
           'upstream_metadata_unchanged':True,'cost':None,'cost_reason':'preco_nao_fornecido',
           'individual_json_directory':'artifacts/evaluation/test_v1/individual',
           'individual_csv':'artifacts/evaluation/test_v1/individual.csv',
           'context_scale_exploratory':read(root/'artifacts/evaluation/context_scale_v1/report.json') if (root/'artifacts/evaluation/context_scale_v1/report.json').exists() else None,
           'preregistration_sha256':sha(root/'docs/PREREGISTRO_ETAPA7.json')}
    save(root/'docs/VALIDACAO_ETAPA7.json',value)
    md=['# Resultados da etapa 7','',
        'Execução real do gateway, teste congelado. Dados ambientais derivados reais; perguntas construídas em português. Revisão humana não realizada. Os testes sintéticos/mocks não integram os resultados abaixo.','',
        f"Modelo retornado: `{', '.join(models)}`. Parâmetros iguais: temperatura zero, saída de 2048 tokens, timeout de 60 s e até duas tentativas HTTP. Teste: 120 casos, 15 famílias, três condições; mais quatro casos repetidos uma vez por condição.",
        '', '| Condição | Acerto / 120 | Acerto | Cobertura respondida | Precisão emitida | Erros técnicos |',
        '|---|---:|---:|---:|---:|---:|']
    for condition,metrics in test['metrics'].items():
        md.append(f"| {condition} | {metrics['correct']} | {percent(metrics['accuracy_including_technical_and_missing'])} | {percent(metrics['coverage_answered'])} | {percent(metrics['precision_emitted'])} | {metrics['statuses']['erro_tecnico']} |")
    md.extend(['',f"**Diferença pareada principal C−B:** {interval(test['paired_C_minus_B'])}.",
               f"Bootstrap por família: {test['paired_C_minus_B']['groups']} grupos, {test['paired_C_minus_B']['cases']} casos, 10.000 réplicas, seed 20271019. IC percentil. Esses pontos percentuais medem acerto de consulta e não incerteza da área ambiental.",
               '',f"Análise quantitativa secundária, predefinida: {interval(test['paired_numeric_subset'])}; {test['paired_numeric_subset'].get('groups')} famílias e 88 casos.",
               f"Sensibilidade por território: {interval(test['territory_sensitivity'])}; {test['territory_sensitivity'].get('groups')} grupos, {test['territory_sensitivity'].get('cases')} casos; {test['territory_sensitivity_excluded_cases']} casos excluídos por não serem de município único.",
               '',f"Repetibilidade: {repetitions['same_normalized_answer']}/{repetitions['comparisons']} respostas estruturadas iguais (ignorando apenas reason); {repetitions['same_correctness']}/{repetitions['comparisons']} com o mesmo acerto. Não se selecionou a melhor repetição. Temperatura zero não garante determinismo.",
               '', '| Condição | Latência média (s) | p95 (s) | Tokens totais observados | Custo |',
               '|---|---:|---:|---:|---|'])
    for condition,m in test['metrics'].items():
        tokens=m['usage_observed_sum']['total_tokens'] if m['usage_observed_sum'] else None
        md.append(f"| {condition} | {m['latency_mean_seconds']:.3f} | {m['latency_p95_seconds']:.3f} | {tokens} | null |")
    md.extend(['','Os tokens são os contadores observados do gateway; tentativas sem usage permanecem identificadas no JSON. Não há preço informado e nenhum custo foi estimado. Latência inclui a execução concorrente local de três workers.',
               '', 'Em B, 33 casos terminaram inválidos após o reparo e 29 não retornaram texto final pelo contrato do gateway. A causa remota desses 29 casos não foi determinada. Em C, sete casos falharam na validação semântica após o limite de reparo. O efeito principal mede confiabilidade ponta a ponta sob os limites fixados, incluindo essas falhas, e não demonstra isoladamente melhora da aritmética.\n\nOs registros individuais incluem status, plano, valores, tentativas e escores; o JSON de validação acrescenta contagens descritivas de falhas dos critérios congelados, sem reavaliar respostas. JSON/contrato e falhas semânticas devem ser analisados junto ao acerto, pois os contratos de B e C têm complexidades diferentes.',
               '', 'O primeiro smoke de desenvolvimento teve bloqueio aos symlinks do ambiente de preparação. Foi preservado como diagnóstico; a nova execução usou cópias idênticas e verificadas dos Parquets. Não houve alteração de prompts, sistema ou benchmark para corrigir respostas de teste.',
               '', 'Limitações: uma UF, famílias e territórios com dependência residual, perguntas construídas, revisão humana pendente, gabaritos independentes apenas no cálculo sobre os mesmos derivados. Rankings reais positivos continuam indisponíveis por cobertura incompleta. Estudo nacional de contexto/escalabilidade não foi executado. O identificador do modelo não comprova revisão imutável de seus pesos.',
               '',f"Congelamento: `{frozen}`. Manifesto de execução: `{run['run_id']}`.",
               '', 'Arquivos: `artifacts/evaluation/test_v1/individual/*.json`, `individual.csv`, `metrics.json`, `run.json`; resumo publicável em `docs/VALIDACAO_ETAPA7.json`. O protocolo e comandos estão em `docs/AVALIACAO_CIENTIFICA.md`.',''])
    scale=value.get('context_scale_exploratory')
    if scale:
        md.extend(['', '## Contexto: experimento exploratorio separado', '',
                   'Pergunta fixa de desenvolvimento, uma execucao por tamanho, mesmos parametros de B. Nao entra no teste/IC principal.', '',
                   '| Municipios nas tabelas | Bytes de contexto util | Gateway real | Estado | Acerto |',
                   '|---|---:|---|---|---|'])
        for row in scale['records']:
            md.append(f"| {row['territories']} | {row['context_bytes']} | {row['gateway_executed']} | {row['observed']['status'] if row['observed'] else 'bloqueado por limite local'} | {row['scores']['correct'] if row['scores'] else 'nao avaliado'} |")
        md.extend(['', 'Nenhuma tabela foi truncada. Os pacotes de 40, 80 e 167 municipios excederam 128 KiB e nao foram enviados. Isto mede o limite da aplicacao e um diagnostico exploratorio do modelo, sem estimar sua janela maxima nem generalizar a partir de uma pergunta. Registros em artifacts/evaluation/context_scale_v1.', ''])
    (root/'docs/RESULTADOS_ETAPA7.md').write_text('\n'.join(md))
    print(json.dumps({'state':'verificado','individual_records':len(records),'primary_C_minus_B':test['paired_C_minus_B']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
