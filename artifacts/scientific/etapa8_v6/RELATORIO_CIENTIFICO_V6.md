# Complemento editorial V6: interação e interpretação do acerto

A V6 amplia a V5 sem novas chamadas, dados, escores, prompts ou hipóteses de teste. O RELATORIO_CIENTIFICO_V5.md continua como relatório-base, preservado nesta entrega.

## Latências descritivas

| Experimento | Condição | Casos | Média (s) | Mediana (s) | P95 (s) |
|---|---|---:|---:|---:|---:|
| Original | A | 120 | 5,39 | 4,47 | 11,53 |
| Original | B | 120 | 12,39 | 11,31 | 24,00 |
| Original | C | 120 | 10,21 | 8,51 | 21,43 |
| Controle 4096 | B_eq | 88 | 14,09 | 6,41 | 38,72 |
| Controle 4096 | C_eq | 88 | 5,28 | 4,10 | 10,18 |

A Figura 3 reutiliza exatamente os bytes de fig05_latencia.png da V5; o gráfico foi originalmente gerado por scripts/science/plots.py a partir dos casos individuais. O manifesto V6 registra o hash da figura e dos insumos.

## Tokens no transporte — controle 4096

| Condição | Entrada | Saída | Total | Respostas sem usage | Custo |
|---|---:|---:|---:|---:|---|
| B_eq | 503951 | 129242 | 633193 | 0 | null |
| C_eq | 510399 | 42564 | 552963 | 0 | null |

## Interpretação e limitações

C tem 31 decisões corretas sem emissão de resposta quantitativa no experimento original; esses casos participam do acerto, mas não da cobertura de respostas.

- Latencias descritivas sob concorrencia local, nao benchmark de capacidade do gateway.
- A/B/C originais tem contratos distintos; A nao emite respostas quantitativas.
- Tokens do transporte 4096 incluem retornos vazios; uso historico no cliente e parcial.
- Contagens nao estimam custo financeiro; preco e reasoning_tokens nao informados.
- Sem nova comparacao inferencial, pareamento de latencia ou estimativa de throughput.

A revisão humana continua sendo a declaração registrada do autor; nenhuma nova revisão humana ou autenticação de malha foi realizada nesta revisão editorial.
