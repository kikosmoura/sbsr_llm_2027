# Avaliação científica da arquitetura — etapa 7

Este protocolo compara as respostas em português às estatísticas locais já materializadas. A unidade experimental principal é a família de consulta, e a comparação principal é **C − B** em acerto ponta a ponta. A condição A diagnostica ausência de evidências. O estudo não mede acurácia temática, desmatamento, causas ou verdade de campo.

O benchmark `benchmarks/pt_rn_v1/` contém 40 casos de desenvolvimento (10 famílias) e 120 de teste (15 famílias). Cada instância tem quatro redações. Instâncias que reutilizam a mesma moldura, mesmo em municípios/classes diferentes, pertencem à mesma família estatística: não são contadas como grupos independentes. Os tamanhos podem ser alterados **antes de um novo congelamento**; nunca remover casos com base no desempenho observado. `cases.jsonl` contém `case_id`, `family_id`, pergunta, plano canônico, decisão e resposta de referência. `gold.json` é a representação consumida pelo avaliador; `facts.json` separa explicitamente os fatos que podem chegar a B dos gabaritos que nunca entram nos prompts.

Há 88 pedidos quantitativos no teste, 16 esclarecimentos, 12 recusas por dados indisponíveis e quatro pedidos fora do escopo. Os municípios dos planos canônicos de desenvolvimento e teste são distintos. Operações e conceitos são compartilhados por desenho; não se afirma generalização para operações inéditas. Homônimos e rankings podem envolver outros territórios e o universo RN, criando dependência entre partições e entre famílias. Não existe isolamento geográfico independente entre estados: há uma única UF.

## Gabaritos e revisão

`evaluation/reference.py` lê diretamente os Parquets, usando DuckDB somente para desserialização. Filtros, união de folhas, conversões e fórmulas usam Python/Decimal com precisão 40, sem importar `QueryEngine`, `DerivedStore`, métricas ou renderizador de produção. A referência usa o catálogo oficial para definir folhas, mas faz sua própria união de conjuntos. Confere duplicatas, conservação de áreas, identificador do suporte comum e o recorte conhecido de Riachuelo. A independência é de cálculo sobre os derivados; não representa uma nova validação da classificação ou uma referência geoespacial independente dos dados de entrada.

`sources.json` fixa hashes dos insumos utilizados e os resultados dos invariantes. `review.json` registra revisão semântica por **assistente de IA**, amostra de 18 casos e verificação das famílias ambíguas. Não houve avaliação humana, concordância entre anotadores ou uso do modelo do gateway como juiz. A validação numérica é determinística e independente do modelo que produz as respostas. Uma revisão humana externa permanece recomendada para uma versão publicável do benchmark, sem reabrir este teste para ajustar o sistema.

A suficiência de B foi verificada para todos os 112 casos quantitativos entre desenvolvimento e teste: somente as tabelas enviadas a B permitem recompor cada gabarito. B recebe todas as folhas, ambos os anos e suportes anual/comum dos candidatos necessários, denominadores de área observada e informação de completude. Não recebe deltas, participações, respostas de referência nem resultados do executor. Pedidos de ranking não recebem uma resposta ordenada: recebem a capacidade real que impede ranking por cobertura incompleta. Não há ranking positivo real neste benchmark; ordenação, sinais e empates são verificados em testes sintéticos separados, sem incorporá-los às métricas reais.

## Condições controladas

- **A:** documentação, catálogo, candidatos e disponibilidade, sem valores de área. Deve esclarecer ambiguidades e abster-se de números sem evidência. Seu acerto quantitativo não é a comparação principal.
- **B:** a mesma documentação e as tabelas elementares suficientes, sem ferramentas de cálculo. O próprio modelo produz o plano e os números finais em JSON tipado.
- **C:** interpretação existente, validação semântica, executor determinístico e frase verificada do servidor. Seus prompts de produção são preservados. Nenhum raster é processado durante perguntas.

O mesmo modelo configurado, temperatura, limite de saída, timeout, política HTTP e TLS se aplicam às três condições. Não se envia `seed`, ferramentas nativas ou `response_format`. As políticas locais existentes para código/SQL, causas e conceitos fora do escopo se aplicam a todas as condições. A/B têm no máximo um reparo de sintaxe/contrato; C preserva seu único reparo e sua validação semântica, partes da arquitetura avaliada. Os prompts são diferentes por função e todos têm hashes. Nenhum contém exemplos ou gabaritos de teste.

O runner utiliza três workers locais; cada caso/condição tem cliente próprio, sessão nova e cache OAuth2 privado. A ordem A/B/C é rotativa entre casos. Registra-se latência de parede por condição; ela inclui a carga concorrente local e não é uma estimativa isolada da capacidade do servidor. São até duas tentativas HTTP por chamada, uma renovação após 401 e no máximo um reparo de saída; não se repetem falhas até obter sucesso. Uma execução interrompida retoma somente arquivos ainda ausentes, com a mesma identidade. Não há seed do modelo nem garantia de determinismo por temperatura zero.

## Congelamento e ausência de ajuste ao teste

`freeze.json` fixa perguntas, gabaritos, fatos, tolerâncias, critérios, revisão, schemas, código de avaliação, prompts A/B, hashes dos prompts/interpretação/executor de produção e parâmetros públicos do modelo. O runner verifica esses compromissos antes e depois da execução, além dos hashes dos derivados. Registros individuais recebem hashes no manifesto da execução. O relatório recusa entradas alteradas. Arquivos do benchmark e congelamento são imutáveis; uma nova versão exige outro diretório e justificativa explícita.

Primeiro executa-se a amostra de oito casos de desenvolvimento definida no protocolo, sem usar o teste para escolher prompts. Falhas legítimas do sistema não autorizam ajustes após abrir o teste. O progresso do runner mostra apenas conclusão, sem mostrar escores/gabaritos durante o teste. O relatório é calculado após a execução. Retomada não deve rerrodar casos já concluídos para selecionar uma resposta melhor.

## Métricas e tolerâncias

O acerto quantitativo exige status, operação, código territorial, união das classes folha, anos, métrica, unidade, denominador, valores e ordem de ranking. A ordem dos territórios e das classes no plano não é relevante, mas a ordem do ranking é. UF implícita em códigos municipais equivale à UF informada, fora de rankings. Esclarecimento exige o campo correto e nenhum valor. Recusas exigem status correto e ausência de valores; quando ambos os lados informam plano, ele também deve coincidir. A ausência de plano numa recusa antecipada não é penalizada, pois não houve execução. Esse critério está fixado no protocolo.

Erros técnicos, JSON inválido e falhas semânticas permanecem no denominador principal. Publicam-se cobertura de respostas numéricas, precisão das respostas emitidas, esclarecimento/abstenção, distribuição de estados, falhas de JSON/contrato, latência e tokens observados. Uma resposta emitida errada não se torna correta por ter um texto plausível. A frase de C vem do servidor; A/B publicam somente o envelope estruturado, evitando texto livre que escape à pontuação. Dados de preço/custo não fornecidos ficam `null`; tokens observados não são estimativas de preço.

As tolerâncias absolutas são 0,0001 ha, 0,000001 km², 1 m² e 0,001 nas unidades percentual/pontos percentuais; soma-se tolerância relativa de 0,000001 do valor de referência. São tolerâncias de representação/cálculo textual, fixadas antes das chamadas, e não erro ambiental do mapa. Bases zero exigem `null` com motivo; zero numérico não substitui indefinido. Denominadores são comparados em hectares. Empate de ranking é exato antes de arredondamento, com desempate por código IBGE crescente. A análise secundária quantitativa usa os mesmos critérios, sem substituir o estimando principal misto.

A diferença de acerto C−B é pareada por caso. Em cada uma de 10.000 réplicas, sorteiam-se famílias com reposição, preservando todos os seus casos e condições. A estimativa de cada réplica é a diferença de acerto por caso, ponderada pelos tamanhos das famílias sorteadas; não é a média não ponderada de famílias. O IC95% é percentil, quantis lineares, gerador NumPy PCG64, seed 20271019. Registra-se o número de casos e grupos. Famílias com muitos casos influenciam mais o estimando, conforme definido antes do teste.

A sensibilidade reamostra municípios como grupos quando existem ao menos dez municípios com casos de território único. Exclui comparações multiterritoriais e rankings e informa essa exclusão; portanto avalia um subconjunto, não prova independência espacial. Os intervalos descrevem acerto em consultas neste benchmark, não incerteza das áreas ambientais. São quinze grupos primários: a dependência residual entre territórios, malha e revisão limita a precisão e a generalização.

A repetibilidade usa quatro casos de teste predefinidos, uma repetição por condição. Compara status/plano/valores/campo de esclarecimento, ignorando apenas o código textual `reason`. As repetições não entram no acerto principal e não escolhem uma resposta melhor. Sem executar essa opção, o relatório declara execução única.

## Comandos reproduzíveis

Execute a partir da raiz `sbsr_2027`, usando seu próprio ambiente Python:

```bash
.venv/bin/python -m pip install '.[evaluation]'
.venv/bin/python -m consultas_ambientais evaluate --help
.venv/bin/python -m consultas_ambientais evaluate context-audit
.venv/bin/python -m consultas_ambientais evaluate verify
```

O benchmark entregue já está construído e congelado. Para uma nova versão, use outro caminho e execute `build --run-id ID_DA_MATERIALIZACAO`, revise os arquivos e só então `freeze --env-file .env`. O arquivo local é lido com `python-dotenv`, sem shell ou exibição dos valores. `configs/evaluation.json` define os limites públicos e aplica timeout de 60 s, saída de 2048 tokens, temperatura zero e duas tentativas HTTP antes de validar as variáveis locais.

```bash
.venv/bin/python -m consultas_ambientais evaluate run --split dev --smoke --env-file .env --output artifacts/evaluation/dev_smoke_v2
.venv/bin/python -m consultas_ambientais evaluate report --output artifacts/evaluation/dev_smoke_v2
.venv/bin/python -m consultas_ambientais evaluate run --split test --repeat --env-file .env --output artifacts/evaluation/test_v1
.venv/bin/python -m consultas_ambientais evaluate report --output artifacts/evaluation/test_v1
```

Os comandos `run` fazem chamadas reais e podem consumir orçamento. O número de casos deve ser decidido antes de congelar uma versão. O comando de desenvolvimento pode executar os 40 casos omitindo `--smoke`. IDs/saídas iguais permitem retomar, não criar replicações independentes. Para uma nova replicação, use novo diretório de execução e registre-a como tal.

Cada execução contém `run.json`, `individual/<case_id>_<condition>_<repeat>.json`, `individual.csv` e `metrics.json`. Cada registro individual preserva run/case/family, território, pergunta, modelo/configuração, hashes, resposta final, plano/resultado, tentativas, latência, usage e escores. C referencia também sessão/turno e evidências com hashes dos Parquets e execução geoespacial. Tokens OAuth2, cabeçalhos, corpo bruto de erro e raciocínio interno não são persistidos. Resultados reais ficam em `artifacts/`, ignorado pelo Git; relatórios publicáveis devem ser copiados deliberadamente após revisão de privacidade.

## Contexto e limites

O limite de B é 128 KiB de contexto útil; excesso é erro explícito, nunca truncamento. `context-audit` é uma medição de tamanho do benchmark, sem chamadas de modelo; não é um experimento de escalabilidade nacional. O experimento exploratório separado em `scripts/avaliar_contexto_etapa7.py` usa uma pergunta fixa de desenvolvimento, pacotes de 1, 5, 10, 20, 40, 80 e 167 municípios e quatro tamanhos candidatos a chamadas reais. Seu protocolo próprio e hash são gravados antes dessas chamadas. O limite de 128 KiB bloqueia pacotes maiores explicitamente. Não entra no acerto/IC principal e não estima a janela máxima do gateway. A escala nacional continua fora do experimento. Falta de acesso ao gateway deve resultar em runner disponível e relatório de pendência, não em métricas simuladas. Testes sintéticos e mocks de autenticação/erro não contam como observações científicas reais.

A versão inicial contém tamanhos fixos. Outro orçamento exige selecionar/revisar famílias, atualizar a validação de contagem e o protocolo, e construir outro benchmark antes de congelá-lo; o runner de teste não remove casos por conveniência ou falha. Os contratos de saída de B e C têm complexidades diferentes por desenho: falhas de JSON/contrato são relatadas separadamente, para não atribuir todo efeito observado exclusivamente à aritmética. O identificador do modelo não comprova imutabilidade dos pesos ou do backend do gateway.

Para regenerar o resumo específico das execuções entregues, após os três comandos de relatório: `.venv/bin/python scripts/relatorio_avaliacao_etapa7.py`. Esse script apenas transforma os escores já congelados em tabelas/contagens descritivas e não altera resultados individuais, critérios ou métricas primárias.

Comando do diagnóstico separado, após concluir o teste principal: `.venv/bin/python scripts/avaliar_contexto_etapa7.py --env-file .env`. Resultados em `artifacts/evaluation/context_scale_v1/report.json`. O primeiro congelamento primário previa a medição estrutural de tamanhos; as quatro chamadas de desenvolvimento são um complemento exploratório com protocolo próprio, sem alteração do teste principal.
