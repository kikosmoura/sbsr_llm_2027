"""Síntese descritiva adicional, sem chamadas remotas nem novos testes de hipótese."""
from copy import deepcopy
from math import isclose
from statistics import mean, median

from .audit import require


def interaction_summary(original, high, telemetry):
    """Confere latências individuais e separa uso no transporte de uso no cliente."""
    rows = []
    for summary in original['conditions']:
        times = [r['latency_seconds'] for r in original['latencies']
                 if r['condition'] == summary['condition']]
        require(len(times) == summary['cases'], 'latencias_originais_incompletas')
        require(all(t >= 0 for t in times), 'latencia_negativa')
        require(isclose(mean(times), summary['latency_mean_seconds'], abs_tol=1e-12),
                'media_de_latencia_divergente')
        require(isclose(median(times), summary['latency_median_seconds'], abs_tol=1e-12),
                'mediana_de_latencia_divergente')
        ordered = sorted(times)
        position = (len(ordered) - 1) * .95
        lower = int(position)
        p95 = ordered[lower] + (position - lower) * (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower])
        require(isclose(p95, summary['latency_p95_seconds'], abs_tol=1e-12), 'p95_divergente')
        rows.append({k: summary[k] for k in ['condition', 'cases', 'answered', 'correct',
                     'latency_mean_seconds', 'latency_median_seconds', 'latency_p95_seconds']})
    groups = {r['condition']: r for r in telemetry['groups']}
    control = []
    for summary in high['conditions']:
        group = groups[summary['condition']]
        require(group['cases'] == summary['cases'] and group['usage_missing_responses'] == 0,
                'uso_do_transporte_incompleto')
        usage = group['usage_sum_observed_in_transport']
        require(usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens'],
                'soma_de_tokens_divergente')
        control.append({**{k: summary[k] for k in ['condition', 'cases', 'answered', 'correct',
                       'latency_mean_seconds', 'latency_median_seconds', 'latency_p95_seconds',
                       'executor_seconds_mean']}, 'transport_usage': deepcopy(usage),
                       'usage_missing_responses': group['usage_missing_responses'], 'cost': None})
    c = next(r for r in original['conditions'] if r['condition'] == 'C')
    require(c['precision_emitted'] == 1, 'respostas_C_nao_sao_todas_corretas')
    return {
        'schema_version': 'interacao-descritiva-v6',
        'basis': 'execucoes reais existentes; nenhuma chamada ou escore novo',
        'original': rows, 'control_4096': control,
        'C_correct_nonanswers': c['correct'] - c['answered'],
        'latency_population': 'todos os casos primarios, inclusive erros e recusas; exclui repeticoes',
        'p95_method': 'quantil empirico com interpolacao linear (n-1)*0.95',
        'local_concurrency': 3,
        'limitations': [
            'Latencias descritivas sob concorrencia local, nao benchmark de capacidade do gateway.',
            'A/B/C originais tem contratos distintos; A nao emite respostas quantitativas.',
            'Tokens do transporte 4096 incluem retornos vazios; uso historico no cliente e parcial.',
            'Contagens nao estimam custo financeiro; preco e reasoning_tokens nao informados.',
            'Sem nova comparacao inferencial, pareamento de latencia ou estimativa de throughput.',
        ],
    }


def number(value, decimals=2):
    return f'{value:,.{decimals}f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def manuscript(base, analysis):
    draft = deepcopy(base)
    draft['draft_notice'] = 'RASCUNHO V6 PARA REVISÃO AUTORAL — NÃO SUBMETIDO'
    originals = {r['condition']: r for r in analysis['original']}
    high = {r['condition']: r for r in analysis['control_4096']}
    a, b, c = (originals[k] for k in 'ABC')
    be, ce = (high[k] for k in ['B_eq', 'C_eq'])
    insert = [
        {'kind': 'heading', 'text': '3.5 Latência e consumo de tokens'},
        {'kind': 'figure', 'file': 'fig05_latencia.png', 'caption':
         'Figura 3. Latência no experimento original, 120 casos por condição, incluindo falhas e recusas; três execuções concorrentes. Linha: mediana; triângulo: média; pontos: valores além dos bigodes de 1,5 intervalo interquartil. Contratos distintos.'},
        {'kind': 'paragraph', 'text':
         f'As medianas de A/B/C foram {number(a["latency_median_seconds"])}, '
         f'{number(b["latency_median_seconds"])} e {number(c["latency_median_seconds"])} s (Figura 3). '
         f'Os percentis 95 de B/C foram {number(b["latency_p95_seconds"])} e '
         f'{number(c["latency_p95_seconds"])} s. A menor latência de A acompanha ausência de '
         'respostas quantitativas; não representa melhor desempenho na tarefa. As distribuições '
         'incluem recusas e erros e descrevem o fluxo local com concorrência fixa, sem medir '
         'capacidade do gateway ou tempo de pré-processamento raster.'},
        {'kind': 'paragraph', 'text':
         f'No controle a 4.096 tokens, as médias B_eq/C_eq foram '
         f'{number(be["latency_mean_seconds"])} e {number(ce["latency_mean_seconds"])} s; '
         f'o executor consumiu em média {number(ce["executor_seconds_mean"])} s em C_eq. '
         f'O transporte registrou {number(be["transport_usage"]["completion_tokens"], 0)} e '
         f'{number(ce["transport_usage"]["completion_tokens"], 0)} tokens de saída, e '
         f'{number(be["transport_usage"]["total_tokens"], 0)} e '
         f'{number(ce["transport_usage"]["total_tokens"], 0)} tokens totais, respectivamente. '
         'Essas contagens incluem os retornos vazios e têm cobertura completa, ao contrário '
         'do uso parcial registrado pelo cliente antigo. São observações descritivas; preço '
         'e decomposição de tokens de raciocínio não foram informados, impedindo estimar custo financeiro.'},
        {'kind': 'heading', 'text': '3.6 Acerto e emissão de respostas'},
        {'kind': 'paragraph', 'text':
         f'No teste original, os {c["correct"]} acertos de C incluem {c["answered"]} respostas '
         f'quantitativas e {analysis["C_correct_nonanswers"]} decisões corretas de esclarecimento '
         'ou abstenção. Portanto, acerto ponta a ponta e taxa de emissão medem aspectos distintos: '
         'recusar um ranking com universo incompleto pode ser correto. O controle com plano '
         'fornecido contém apenas casos quantitativos, não avalia essas decisões e não substitui '
         'a avaliação original. Essa separação evita interpretar 100% de C_eq como cobertura '
         'irrestrita do sistema.'},
    ]
    index = next(i for i, b in enumerate(draft['blocks']) if b.get('text') == '4. LIMITAÇÕES E CONCLUSÕES')
    draft['blocks'][index:index] = insert
    # A sensibilidade adicional já está na V5; explicitar seu orçamento na conclusão.
    for block in draft['blocks']:
        if block['kind'] == 'paragraph' and block['text'].startswith('A contribuição é avaliar'):
            block['text'] = block['text'].replace(
                'O IC95% permanece acima de zero neste orçamento.',
                'A sensibilidade completa a 4.096 tokens mantém diferença positiva, com IC95% acima de zero.')
    return draft


def report(analysis):
    lines = ['# Complemento editorial V6: interação e interpretação do acerto', '',
             'A V6 amplia a V5 sem novas chamadas, dados, escores, prompts ou hipóteses de teste. '
             'O RELATORIO_CIENTIFICO_V5.md continua como relatório-base, preservado nesta entrega.', '',
             '## Latências descritivas', '',
             '| Experimento | Condição | Casos | Média (s) | Mediana (s) | P95 (s) |',
             '|---|---|---:|---:|---:|---:|']
    for experiment, rows in [('Original', analysis['original']), ('Controle 4096', analysis['control_4096'])]:
        for r in rows:
            lines.append(f'| {experiment} | {r["condition"]} | {r["cases"]} | '
                         f'{number(r["latency_mean_seconds"])} | {number(r["latency_median_seconds"])} | '
                         f'{number(r["latency_p95_seconds"])} |')
    lines += ['', 'A Figura 3 reutiliza exatamente os bytes de fig05_latencia.png da V5; '
              'o gráfico foi originalmente gerado por scripts/science/plots.py a partir dos casos individuais. '
              'O manifesto V6 registra o hash da figura e dos insumos.', '',
              '## Tokens no transporte — controle 4096', '',
              '| Condição | Entrada | Saída | Total | Respostas sem usage | Custo |',
              '|---|---:|---:|---:|---:|---|']
    for r in analysis['control_4096']:
        u = r['transport_usage']
        lines.append(f'| {r["condition"]} | {u["prompt_tokens"]} | {u["completion_tokens"]} | '
                     f'{u["total_tokens"]} | {r["usage_missing_responses"]} | null |')
    lines += ['', '## Interpretação e limitações', '',
              f'C tem {analysis["C_correct_nonanswers"]} decisões corretas sem emissão de resposta quantitativa '
              'no experimento original; esses casos participam do acerto, mas não da cobertura de respostas.', '']
    lines += ['- ' + s for s in analysis['limitations']]
    lines += ['', 'A revisão humana continua sendo a declaração registrada do autor; nenhuma nova '
              'revisão humana ou autenticação de malha foi realizada nesta revisão editorial.', '']
    return '\n'.join(lines)
