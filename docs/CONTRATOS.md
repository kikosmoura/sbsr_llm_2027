**Contratos e limites das etapas 0–2**

`src/consultas_ambientais/contracts.py` centraliza modelos Pydantic com campos extras proibidos, números finitos e erros sem reprodução dos valores de entrada. A validação de disponibilidade dos anos/classes/territórios será acrescentada pelo catálogo da etapa 2: estar no intervalo candidato não prova disponibilidade.

| Contrato | Responsabilidade |
|---|---|
| Territory | Código textual, nome, UF, edição territorial e hash de geometria |
| LandClass | Código, hierarquia, folhas sem duplicatas, beta, aliases e hash de fonte |
| RasterMetadata | Coleção/ano, revisão conhecida ou nula, grade, banda, CRS, NoData, blocos e identificadores HTTP |
| ProcessingQuality | Não processado/parcial/completo, suporte observado, NoData, método e suporte comum |
| QueryPlan | Operação, métrica, unidade, códigos, anos, denominador e universo do ranking |
| Evidence/ResultValue | Fontes, método, execução, valores e referências a evidências |
| Answer | Estado e resposta; um resultado quantitativo exige plano, valores e evidências |
| Check/DiagnosticReport | Estado de uma verificação, resultado, detalhes e data UTC |

Os estados de resposta são `respondida`, `precisa_esclarecimento`, `fora_do_escopo`, `dados_indisponiveis` e `erro_tecnico`. Não são substitutos uns dos outros. Não há geração dessas respostas por LLM na etapa 1.

A etapa 2 acrescenta contratos em `semantics/models.py`: documentos de fonte, catálogo de classes, snapshot de atributos territoriais, referências e candidatos tipados, `QueryIntent`, `Capabilities`, `Materialization` e `SemanticDecision`. Consulte `docs/CATALOGO_SEMANTICO.md`. O estado semântico `plano_validado` indica prontidão para o motor; `respondida` permanece reservado a uma resposta com resultado e evidências.

Operações: `area`, `participacao`, `comparacao_temporal`, `serie_disponivel`, `comparacao_territorial`, `ranking_delimitado`. Ranking exige UF explícita e limite e não aceita uma lista parcial de municípios como se fosse todo o universo. A etapa de execução deverá garantir completude do universo antes de publicar um ranking.

Fórmulas, implementadas como funções puras em `queries/metrics.py` para conferir o contrato:

```text
area_km2 = area_ha / 100
area_m2 = area_ha * 10000
delta_ha = final_ha - inicial_ha
reducao_liquida_ha = max(0, inicial_ha - final_ha)
variacao_percentual = 100 * delta_ha / inicial_ha
participacao_percentual = 100 * classe_ha / suporte_observado_ha
delta_participacao_pp = participacao_final - participacao_inicial
```

Base inicial zero produz variação percentual `null`, com motivo `base_inicial_zero`; suporte observado zero produz participação indefinida. Percentual de mudança e pontos percentuais são medidas distintas. Operações temporais exigem dois anos distintos em ordem e, na execução futura, áreas no suporte comum. Redução líquida não é perda bruta/desmatamento. Não há arredondamento nos cálculos.

O contrato não contém SQL livre, caminhos de execução nem expressões Python. Não existe executor de perguntas nesta etapa. Não há tabela fictícia de áreas, resultado ambiental demonstrativo inventado ou API simulando consulta concluída.

Metadados de ETag e Last-Modified não são hashes criptográficos. Compatibilidade de grade não comprova identidade da revisão oficial nem interseção das máscaras válidas. Estas verificações permanecem separadas.
