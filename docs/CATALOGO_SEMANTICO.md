**Catálogo semântico — etapa 2, versão 0.2.0**

O catálogo e a validação são determinísticos e funcionam sem LLM. A etapa transforma seleções estruturadas em um plano resolvido e verifica capacidades. A interpretação de uma pergunta livre pelo LLM permanece na etapa 5; nenhum número ambiental é estimado aqui.

**Fontes e versão da legenda**

A distribuição contém um snapshot em `src/consultas_ambientais/semantics/data/mapbiomas_col11_v1/`, também incluído no wheel. `sources/manifest.json` registra URLs oficiais, obtenção em UTC, tamanho e SHA-256 dos arquivos originais. `catalog.json` registra coleção, hierarquia, aliases, beta, fontes e discrepâncias. O catálogo possui fingerprint semântico próprio calculado a partir de JSON canônico, distinto do hash de cada documento.

- PDF: `19ddb657d66ce1039be8aba31f20689d9ab66af7d39b86d976727dc3265b7865`.
- CSV: `603239c5de7cca95799c788ab553a73ec3fc16477f681f63bb5af191d2f54dbe`.
- Fingerprint do catálogo semântico: `04f699fe08ce817f759c9923d38cb71d817722bee37c3f2322d8419e32963660`.

São 41 nós: 8 grupos e 33 classes-folha. Os quatro códigos iniciais, conferidos nas fontes, são Formação Florestal (3), Pastagem (15), Área Urbanizada (24) e Rio, Lago e Oceano (33). O restante da legenda é mantido para interpretar hierarquia e diagnosticar outros códigos; não representa uma afirmação de que todos apareçam em cada raster.

O PDF fornece hierarquia e nomes canônicos; o CSV fornece uma conferência independente dos códigos de folhas e cores. Há seis discrepâncias registradas, incluindo grafia/capitalização e dois erros em inglês. Na classe 48, o PDF imprime `3.2.1.4`, repetindo o ramo temporário, apesar de a classe estar sob Lavoura Perene. A página oficial confirma `3.2.2.4`; o catálogo registra caminho impresso, caminho canônico e fonte corroborante, atribuindo pai 36. Nenhuma correção fica implícita.

Fontes oficiais: [PDF da Coleção 11](https://brasil.mapbiomas.org/wp-content/uploads/sites/3/2026/08/CodigosDeLegenda_LegendCodes_MapBiomas_Brazil_Collection11_PDF.pdf), [CSV da Coleção 11](https://brasil.mapbiomas.org/wp-content/uploads/sites/3/2026/08/legend_code_mapbiomas_brazil_collection_11.csv) e [página do produto](https://brasil.mapbiomas.org/iniciativas-e-produtos/cobertura-e-uso-da-terra/cobertura-30m/cobertura/). O texto derivado é conferido com nova extração do próprio PDF ao reconstruir o catálogo. `pdftotext` é necessário para reconstrução; consultas usam o snapshot empacotado sem essa ferramenta e sem rede.

**Expansão e códigos observados**

`ClassCatalog.expand([1, 3])` retorna `[3, 4, 5, 6, 7, 49]`. O grupo não é somado novamente à própria área e a folha 3 não é duplicada. A carga rejeita ciclos, pais inexistentes e descendentes/folhas inconsistentes.

Termos genéricos `floresta`, `área florestal`, `água` e `superfície de água` são intencionalmente ambíguos. `grupo Floresta`, `Formação Florestal` ou código explícito desambiguam. Código e termo contraditórios exigem esclarecimento.

`audit_codes` separa classes-folha conhecidas, grupos observados como pixels, valores desconhecidos e NoData explicitamente declarado. O código 0 não é presumido como NoData; 27 ou qualquer outro valor ausente da legenda não recebe um significado inventado. Um código de grupo observado como pixel é uma inconsistência explícita, não autorização para distribuí-lo entre filhos.

O manifesto real derivado dos diagnósticos da etapa 1 observa apenas 1 pixel por ano: nessa amostra apareceram os códigos 4 e 12. Isso não é um inventário completo, não comprova ausência de outras classes nem constitui estatística de área. As folhas da legenda e os códigos observados são registrados separadamente.

**Cadastro territorial**

`territories export` lê apenas código, nome, sigla e código de UF das duas tabelas, com transação somente leitura e timeout. Não lê geometria, não altera valores, não busca serviços externos e não usa LLM. O snapshot real em `data/territories_v1.json` contém 5.600 entidades: 5.573 municípios e 27 UFs; sua edição permanece desconhecida. O arquivo é local e ignorado pelo Git, com fingerprint próprio.

A busca normaliza caixa, espaços, acentos e pontuação, preservando sempre `name_original`. Uma transformação Latin-1/UTF8 somente gera um alias de busca se for reversível e reduzir os marcadores de codificação suspeita. O alias é anotado como candidato, não substitui o nome de origem e não altera o banco. Colisões decorrentes de aliases continuam exigindo esclarecimento.

Resolução por código valida também nome/UF/tipo fornecidos. Nomes homônimos retornam candidatos. Buscas aproximadas, mesmo com um candidato, exigem confirmação. UF pode ser informada separadamente ou como `Nome/RN`; siglas minúsculas são normalizadas. As três ocorrências reais de Santa Cruz nesta base foram retornadas como candidatos de RN, PB e PE. São Paulo/SP foi localizado por alias, mantendo o nome originalmente codificado no snapshot.

O snapshot territorial é de atributos para resolução semântica, não o snapshot de geometrias necessário ao cálculo de área da etapa 3. Seus hashes não são intercambiáveis.

**Contratos e política**

`QueryIntent` aceita operação, referências de território/classe, escopo, anos, métrica/termo, unidade/termo, denominador, direção e limite. Os candidatos territoriais e de classes também possuem tipos no JSON Schema. `QueryPlan` continua como plano canônico das etapas anteriores; a nova camada resolve nomes e expande grupos antes de produzi-lo.

`SemanticDecision` usa os estados:

| Estado | Significado |
|---|---|
| `plano_validado` | Seleções, fontes, cobertura e executor validados; ainda não é uma resposta quantitativa |
| `precisa_esclarecimento` | Homônimo, aproximação, conflito de código/nome/UF, métrica/unidade ambígua ou intenção malformada |
| `fora_do_escopo` | Conceito não suportado: perda bruta sem matriz, evento de inundação, causalidade, ilegalidade, projeção ou vegetação nativa sem definição |
| `dados_indisponiveis` | Ano sem fonte verificada, estatística/par não materializado, universo incompleto ou executor indisponível |
| `erro_tecnico` | Catálogos de versões incompatíveis, hashes inválidos ou falha operacional de carregamento/importação |

`respondida` continua reservado ao contrato `Answer`, quando houver resultado calculado e evidências. Uma validação não fabrica uma resposta ambiental.

“Percentual” isolado exige esclarecimento; participação, variação percentual e pontos percentuais são medidas diferentes. A unidade precisa ser informada. Quando a métrica é inequívoca, seu denominador é derivado da definição documentada; um denominador explícito incompatível é rejeitado. Redução líquida não implica perda bruta, desmatamento ou inundação.

**Capacidades e completude**

`semantic capabilities` lê um relatório real, exige verificações raster concluídas e distingue disponibilidade de fonte de disponibilidade de estatísticas. Registra o hash do relatório e os fingerprints dos catálogos. Não importa todos os anos candidatos por configuração.

O manifesto real atual tem fontes verificadas em 2015..2025, zero materializações e `engine_ready=false`. Portanto uma seleção correta como área de Pastagem em Riachuelo/RN produz plano normalizado, mas retorna `dados_indisponiveis/estatisticas_nao_materializadas`. Esse é o comportamento esperado até as etapas 3–4, não falha de interpretação.

As materializações futuras devem identificar território, anos, classes cobertas, completude e execução. Um par temporal exige suporte comum. Ranking exige registros completos de todos os municípios da UF para as seleções necessárias; uma amostra de municípios não é aceita como universo. Versões incompatíveis entre catálogo e capacidades bloqueiam o plano.

**Comandos reproduzíveis**

Depois de instalar a versão atual por wheel:

```bash
.venv/bin/consultas-ambientais catalog inspect
.venv/bin/consultas-ambientais catalog resolve --term 'Formação Florestal'
.venv/bin/consultas-ambientais catalog resolve --term floresta
.venv/bin/consultas-ambientais catalog expand 1 3
.venv/bin/consultas-ambientais catalog audit-codes 0 3 255
.venv/bin/consultas-ambientais schema intent
.venv/bin/consultas-ambientais schema decision
.venv/bin/consultas-ambientais schema capabilities
```

Para reproduzir a obtenção/reconstrução das fontes, com rede e `pdftotext`:

```bash
.venv/bin/consultas-ambientais catalog fetch --output-dir data/legend-sources
.venv/bin/consultas-ambientais catalog build --sources-dir data/legend-sources --output data/legend-rebuilt.json
```

A obtenção tem limite de 2 MB por arquivo e exige diretório vazio. Se as fontes oficiais mudarem, hashes, divergências e correções precisam ser novamente revisados; não substituir o catálogo publicado automaticamente.

Para reproduzir os atributos e as capacidades, com variáveis PostGIS já exportadas:

```bash
.venv/bin/consultas-ambientais territories export --output data/territories_v1.json
.venv/bin/consultas-ambientais territories resolve --catalog data/territories_v1.json --name 'Santa Cruz'
.venv/bin/consultas-ambientais territories resolve --catalog data/territories_v1.json --name 'Santa Cruz/RN' --kind municipio
.venv/bin/consultas-ambientais semantic capabilities --diagnostic reports/diagnostico_rede.json --territories data/territories_v1.json --output data/capabilities_stage2.json
.venv/bin/consultas-ambientais semantic validate --intent configs/examples/intent_area_pastagem.json --territories data/territories_v1.json --capabilities data/capabilities_stage2.json
.venv/bin/consultas-ambientais semantic validate --intent configs/examples/intent_floresta_ambigua.json --territories data/territories_v1.json --capabilities data/capabilities_stage2.json
```

Resoluções incompletas retornam código de saída 2 e decisão JSON explícita. Catálogo reconstruído e snapshot territorial possuem versões próprias; reconstruir um snapshot exige reconstruir o manifesto de capacidades correspondente.

**Validação e limites**

A suíte combina os testes anteriores com testes de hashes/fontes, erro hierárquico, união de grupos, classes beta, desconhecidos/NoData, ciclos, homônimos, acentos, aliases de codificação, busca aproximada, UF incoerente, anos faltantes, unidades, suporte comum e ranking incompleto. Os cenários de plano pronto usam capacidades e materializações sintéticas, rotuladas como tal: não são resultados ambientais reais.

O cadastro real e as fontes oficiais foram obtidos. A primeira tentativa de cadastro sofreu timeout de conexão; a repetição limitada com timeout de 15 segundos concluiu. Nenhuma chamada a LLM foi feita. Não houve cálculo de áreas, inventário nacional de pixels, atualização do banco ou leitura do `.env`.
