# Etapa 4 — consultas verificáveis, sem LLM

O comando `query` aceita um plano JSON, valida-o novamente e consulta exclusivamente os Parquets locais materializados na etapa 3. Não lê `.env`, não acessa a origem PostgreSQL, não abre rasters e não chama o LLM. O diretório aberto inicialmente era o experimento SAR; a implementação e os artefatos pertencem ao projeto separado `sbsr_2027`.

## Comandos reproduzíveis

Python 3.10.12; pacote 0.4.0. Nenhuma dependência nova de infraestrutura: extra `queries` fixa DuckDB 1.4.1, já verificado na etapa 3. Os demais pins permanecem em `setup.cfg`. Não utilizar o venv SAR. A instalação atual é por wheel, porque o caminho do projeto contém espaços.

```bash
.venv/bin/python -m pip wheel --no-cache-dir --no-build-isolation --no-deps --wheel-dir dist .
.venv/bin/python -m pip install --no-deps --force-reinstall dist/consultas_ambientais-0.4.0-py3-none-any.whl
# Em ambiente novo, instalar também o extra [queries] com suas dependências fixadas.
.venv/bin/consultas-ambientais query --help
.venv/bin/consultas-ambientais schema query_answer
.venv/bin/python -m pytest -q
```

Execução geoespacial real escolhida explicitamente, sem agregar execuções anteriores:

```bash
.venv/bin/consultas-ambientais --config configs/project.json query \
  --plan configs/examples/plano_mudanca_urbana_natal.json \
  --run-id a98ccf54c8c82ceeb601ce126cdb379add4de253912a46267601cdc7d9a29802 \
  --json-output reports/etapa4/natal.json \
  --csv-output reports/etapa4/natal.csv

.venv/bin/consultas-ambientais query \
  --plan configs/examples/plano_area_pastagem.json \
  --run-id a98ccf54c8c82ceeb601ce126cdb379add4de253912a46267601cdc7d9a29802 \
  --format json \
  --capabilities-output data/capabilities_stage4.json
```

Os caminhos padrão são `data/territories_v1.json` e `data/capabilities_stage3.json`; há flags para selecioná-los explicitamente. `--capabilities-output` grava uma cópia com `engine_ready=true`, restrita à execução escolhida, mantendo os indicadores de cobertura parcial. O arquivo anterior não é modificado. O código de saída é 0 para `respondida` e 2 para os demais estados. JSON/CSV também são exportados em recusas; nesses casos não há valores/evidências numéricas.

Exemplo de plano:

```json
{
  "operation": "comparacao_temporal",
  "metric": "diferenca_liquida",
  "unit": "ha",
  "territory_codes": ["2408102"],
  "class_codes": [24],
  "years": [2015, 2025]
}
```

Há doze exemplos em `configs/examples/plano_*.json`: área, participação, mudança e variação urbana, pontos percentuais, grupo hierárquico, série, comparação municipal, ranking RN bloqueado, ano ainda não materializado, UF com cobertura parcial e base zero real. Não interpolar anos ausentes. Uma série retorna exatamente os anos solicitados se todos estiverem materializados; qualquer ano faltante gera `dados_indisponiveis`.

## Validação e armazenamento

Fluxo: plano → contrato estrito → catálogo de classes/territórios → disponibilidade e qualidade por execução → plano validado interno → hashes/linhagem dos Parquets → SQL fixo parametrizado → cálculo em hectares → evidências → template/exportação.

`QueryEngine.answer(payload)` é a entrada programática. `execute` exige um objeto interno validado pelo mesmo executor; um JSON que declare estar validado não satisfaz esse contrato. Classes de grupos são expandidas para a união de folhas, sem somar pai/filhos. Códigos, anos e limite não aceitam booleanos ou strings numéricas. O executor limita a entrada a 64 KiB, consultas explícitas a 100 territórios, universo de ranking a 2.000 candidatos de uma UF e resultado de ranking a 100 posições. Esses limites são verificados antes do SQL. Comparação territorial apresenta as métricas por território; não substitui UF direta pela soma municipal.

A leitura usa `storage/derived.py`, verificando manifest da execução, índices de capacidades, arquivos e hashes das partições, coleção/revisão/malha/método, classes completas e conservação de áreas. As qualidades dos Parquets precisam corresponder ao manifest. O índice global `areas.duckdb` não é usado como autoridade, evitando mistura de execuções ou alterações sem hash. DuckDB trabalha em memória, com uma thread, limite de 256 MiB no motor e acesso externo desabilitado, exceto ao diretório dos Parquets permitidos. Os arquivos derivados e o índice da etapa 3 permanecem inalterados.

O SQL seleciona arquivos, territórios, suporte e anos por parâmetros. Identificadores de tabelas, expressões e ordenação são internos e fixos. Não há `eval`, execução de código do plano, SQL livre, shell ou requisições de rede. Um erro de hash, schema, leitura, consistência ou SQL encerra toda a resposta; não se publicam resultados parciais como resposta válida.

## Métricas e denominadores

| Métrica | Fórmula na unidade interna hectare | Saída |
|---|---|---|
| Área | soma das áreas das folhas selecionadas | ha, km² ou m² |
| Participação | 100 × área da classe / área observada anual | % |
| Diferença líquida | área final − área inicial, no suporte comum | área com sinal |
| Redução líquida | max(0, área inicial − área final), no suporte comum | área não negativa |
| Variação percentual | 100 × (final − inicial) / inicial, no suporte comum | %; base zero → null |
| Diferença de participação | participação final − inicial, no suporte comum | pontos percentuais |

A diferença absoluta em unidade de área conserva o sinal de `final − inicial`; não é o módulo da diferença. Séries e comparações territoriais aplicam a métrica permitida a cada seleção. Operações temporais exigem as linhas `support=comum`, o par exato, identificador de máscara comum e denominador físico idêntico nos dois anos. Não há fallback para linhas anuais. Os resultados equivalem ao objeto lógico `areas_comparaveis` descrito no planejamento.

O armazenamento da etapa 3 está em m². Cada área é convertida para ha ao entrar no cálculo; classes são somadas com `math.fsum`, e todas as fórmulas operam em ha. Saída: `km² = ha / 100` e `m² = ha × 10.000`, preservando o sinal. Não arredondar cálculos nem ordenação. Apenas o texto usa duas casas decimais e separadores brasileiros. JSON/CSV conservam os floats completos; a qualidade admite somente a tolerância numérica registrada pelo método. Diferenças minúsculas de soma float64 próximas ao denominador não são tratadas como erro temático nem corrigidas com arredondamento.

Base inicial zero gera `value=null`, `undefined_reason=base_inicial_zero` e denominador zero. É uma resposta definida quanto ao estado dos dados, não ausência de observação. No CSV, null é célula vazia acompanhada do motivo. Pontos percentuais não usam área inicial como denominador; as duas áreas observadas constam das evidências. Perda/ganho brutos exigem matriz de transição e não são calculados; perda bruta retorna `dados_indisponiveis` por matriz ausente. Desmatamento, causas e eventos de inundação não são inferidos destes números.

## Rankings

O universo é o conjunto completo de municípios da UF no catálogo territorial. Antes de ordenar, todos os candidatos precisam estar materializados e ter cobertura elegível para os anos/suporte/classes da seleção. A política conservadora da etapa 3 é mantida: lacunas/códigos desconhecidos além da tolerância numérica bloqueiam a consulta, em vez de virar zero ou serem excluídos silenciosamente.

O resultado registra códigos de todos os candidatos, cobertura, número verificado, métrica, convenção de sinal, direção, limite e desempate por código IBGE crescente. Ordenação usa valores completos. `reducao_liquida` inclui somente redução estritamente positiva; aumentos e estabilidade são excluídos e contabilizados. Ranking de diferença assinada e variação percentual conserva os sinais; valores indefinidos por base zero são identificados e excluídos da ordenação depois de verificar cobertura completa. Nenhum resultado de UF é rotulado Brasil.

Um universo completamente observado sem reduções retorna `respondida`, lista vazia e contexto/evidência de execução, sem inventar um vencedor. O envelope permite esse caso explicitamente e também distingue um ranking vazio por todos os valores percentuais serem indefinidos.

## Evidências e exportação

Contrato novo `resposta-consulta-v1` (`answers/models.py`, schema `query_answer-v1.json`), com os campos centrais do envelope anterior e evidências estendidas tipadas. O `Answer` histórico permanece disponível; consumidores desta etapa devem usar `QueryAnswer`. Cada resposta numérica registra plano solicitado e plano efetivamente executado (códigos folha, anos/territórios canônicos), IDs estáveis, hash do executor, execução geoespacial e hash do manifest, unidades, denominadores e valores sem arredondamento.

Cada valor referencia evidência com território/grafia original, classe expandida, anos, observações em ha, qualidade, proveniência municipal/UF direta, coleção/revisão, malha/método, partições e fontes. Referências incluem hashes de catálogo, malha, manifest, Parquets e recortes, além do identificador/URL pública do espelho. ETag não é descrito como SHA-256. Revisão e edição desconhecidas continuam nulas.

Os IDs derivam dos planos, versão efetiva do executor e fontes identificadas; repetir a consulta com os mesmos insumos mantém seus IDs. O registro integral vai a `artifacts/queries/<answer_id>.json`, fora do Git. `reports/etapa4/` contém os exemplos JSON/CSV. O CSV inclui contexto de execução, plano, unidades, motivo de null, denominadores, fontes e IDs; textos que poderiam virar fórmulas de planilha são escapados. Exportação não sobrescreve planos/catálogos de entrada, partições, manifests geoespaciais ou arquivos de credenciais.

Estados: `respondida`; `precisa_esclarecimento` para seleções inválidas/ambíguas; `fora_do_escopo` para ranking nacional; `dados_indisponiveis` para falta de materialização/cobertura/par/matriz; `erro_tecnico` para falha ou inconsistência de artefatos/execução/exportação. Falhas não devolvem valores numéricos nem corpo de erro da dependência.

## Validação e limites reais

A suíte usa tabelas sintéticas de álgebra/seleção e referências `Decimal`, sem chamar helpers de produção para calcular o esperado. Não pretende reproduzir a física dos pixels da etapa 3. Cobre conversões, classes agregadas/sem dupla contagem, diferenças no suporte correto, participação, variação versus pontos percentuais, base zero, ausência de classe, empate e filtro de ranking, precisão antes da ordenação, universo/par/anos faltantes, limites, SQL/entrada proibidos, corrupção, falha técnica, IDs, CSV/JSON e ausência de rede/origem.

A validação real usa os Parquets existentes. Outro caminho desserializa os arquivos completos, filtra em Python e calcula fórmulas com `Decimal`, sem `DerivedStore`, templates ou helpers numéricos do executor. Compara dados sem arredondamento, com tolerância numérica 10⁻¹² relativa e 10⁻¹⁰ absoluta nas unidades da saída; as diferenças observadas estão no relatório. Nenhuma estatística é apresentada como validação temática oficial.

Exemplos reais: pastagem em Riachuelo/RN em 2015, aproximadamente 8.684,04 ha; diferença líquida de Área Urbanizada em Natal/RN entre 2015 e 2025, aproximadamente +358,03 ha no suporte comum. Código de Mangue em Riachuelo tem base inicial zero e retorna variação percentual null. Os resultados exatos e a proveniência estão em `reports/etapa4/` e no resumo público `VALIDACAO_ETAPA4.json`.

O ranking RN continua bloqueado: código 0 desconhecido em aproximadamente 2,66 ha de Areia Branca, também refletido na UF. Apenas 2015 e 2025 possuem áreas materializadas; disponibilidade de um raster de 2016 não torna sua estatística local disponível. Malha e revisão oficial permanecem desconhecidas. Não foi feita chamada real de banco, LLM ou rede nesta etapa. Próxima etapa: integração textual/avaliação da interpretação por LLM, reutilizando estes planos e evidências.
