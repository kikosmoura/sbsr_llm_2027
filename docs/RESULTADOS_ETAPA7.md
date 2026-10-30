# Resultados da etapa 7

Execução real do gateway, teste congelado. Dados ambientais derivados reais; perguntas construídas em português. Revisão humana não realizada. Os testes sintéticos/mocks não integram os resultados abaixo.

Modelo retornado: `RETURNED_MODEL_ID_1`. Parâmetros iguais: temperatura zero, saída de 2048 tokens, timeout de 60 s e até duas tentativas HTTP. Teste: 120 casos, 15 famílias, três condições; mais quatro casos repetidos uma vez por condição.

| Condição | Acerto / 120 | Acerto | Cobertura respondida | Precisão emitida | Erros técnicos |
|---|---:|---:|---:|---:|---:|
| A | 21 | 17.50% | 0.00% | null | 0 |
| B | 49 | 40.83% | 25.00% | 86.67% | 62 |
| C | 104 | 86.67% | 60.83% | 100.00% | 7 |

**Diferença pareada principal C−B:** +45.83 pp (IC95% +25.00 a +64.82 pp).
Bootstrap por família: 15 grupos, 120 casos, 10.000 réplicas, seed 20271019. IC percentil. Esses pontos percentuais medem acerto de consulta e não incerteza da área ambiental.

Análise quantitativa secundária, predefinida: +53.41 pp (IC95% +30.00 a +76.39 pp); 8 famílias e 88 casos.
Sensibilidade por território: +48.91 pp (IC95% +32.95 a +64.77 pp); 22 grupos, 92 casos; 28 casos excluídos por não serem de município único.

Repetibilidade: 11/12 respostas estruturadas iguais (ignorando apenas reason); 11/12 com o mesmo acerto. Não se selecionou a melhor repetição. Temperatura zero não garante determinismo.

| Condição | Latência média (s) | p95 (s) | Tokens totais observados | Custo |
|---|---:|---:|---:|---|
| A | 5.394 | 11.533 | 474281 | null |
| B | 12.388 | 24.003 | 874526 | null |
| C | 10.206 | 21.432 | 701151 | null |

Os tokens são os contadores observados do gateway; tentativas sem usage permanecem identificadas no JSON. Não há preço informado e nenhum custo foi estimado. Latência inclui a execução concorrente local de três workers.

Em B, 33 casos terminaram inválidos após o reparo e 29 não retornaram texto final pelo contrato do gateway. A causa remota desses 29 casos não foi determinada. Em C, sete casos falharam na validação semântica após o limite de reparo. O efeito principal mede confiabilidade ponta a ponta sob os limites fixados, incluindo essas falhas, e não demonstra isoladamente melhora da aritmética.

Os registros individuais incluem status, plano, valores, tentativas e escores; o JSON de validação acrescenta contagens descritivas de falhas dos critérios congelados, sem reavaliar respostas. JSON/contrato e falhas semânticas devem ser analisados junto ao acerto, pois os contratos de B e C têm complexidades diferentes.

O primeiro smoke de desenvolvimento teve bloqueio aos symlinks do ambiente de preparação. Foi preservado como diagnóstico; a nova execução usou cópias idênticas e verificadas dos Parquets. Não houve alteração de prompts, sistema ou benchmark para corrigir respostas de teste.

Limitações: uma UF, famílias e territórios com dependência residual, perguntas construídas, revisão humana pendente, gabaritos independentes apenas no cálculo sobre os mesmos derivados. Rankings reais positivos continuam indisponíveis por cobertura incompleta. Estudo nacional de contexto/escalabilidade não foi executado. O identificador do modelo não comprova revisão imutável de seus pesos.

Congelamento: `3a84b29bb29b63ae7a6848c5e5be116f62734f21b8315cd0ccdfcda73d9ae24e`. Manifesto de execução: `fa7686659da9449d811d154641021724`.

Arquivos: `artifacts/evaluation/test_v1/individual/*.json`, `individual.csv`, `metrics.json`, `run.json`; resumo publicável em `docs/VALIDACAO_ETAPA7.json`. O protocolo e comandos estão em `docs/AVALIACAO_CIENTIFICA.md`.


## Contexto: experimento exploratorio separado

Pergunta fixa de desenvolvimento, uma execucao por tamanho, mesmos parametros de B. Nao entra no teste/IC principal.

| Municipios nas tabelas | Bytes de contexto util | Gateway real | Estado | Acerto |
|---|---:|---|---|---|
| 1 | 12698 | True | respondida | True |
| 5 | 30174 | True | precisa_esclarecimento | False |
| 10 | 51889 | True | precisa_esclarecimento | False |
| 20 | 96067 | True | erro_tecnico | False |
| 40 | 183255 | False | bloqueado por limite local | nao avaliado |
| 80 | 356977 | False | bloqueado por limite local | nao avaliado |
| 167 | 733158 | False | bloqueado por limite local | nao avaliado |

Nenhuma tabela foi truncada. Os pacotes de 40, 80 e 167 municipios excederam 128 KiB e nao foram enviados. Isto mede o limite da aplicacao e um diagnostico exploratorio do modelo, sem estimar sua janela maxima nem generalizar a partir de uma pergunta. Registros em artifacts/evaluation/context_scale_v1.
