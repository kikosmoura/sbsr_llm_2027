**Estado atual: etapas 0–8 implementadas.** A introdução e atualizações anteriores abaixo são históricas. Consulte [consolidação científica e reprodução](docs/CONSOLIDACAO_CIENTIFICA.md), o [rascunho do artigo](artifacts/scientific/etapa8/manuscrito/rascunho_sbsr2027.pdf) e o [inventário de direitos/privacidade](artifacts/scientific/etapa8/publicacao/INVENTARIO.md). Material para revisão autoral; não submetido nem publicado.

**Consultas ambientais — SBSR 2027**

Configuração para publicar e reutilizar o código: [PUBLICACAO_GIT.md](docs/PUBLICACAO_GIT.md).
Preencha os placeholders de [.env.example](.env.example) em um `.env` local e a URL
de armazenamento em `configs/project.json`. A integração usa a classe
`GatewayClient` e variáveis de ambiente `LLM_*`.

Implementação das etapas 0 a 2: contratos, configuração, CLI, diagnóstico de PostgreSQL/PostGIS e GeoTIFFs, cliente textual LLM e catálogo semântico versionado. Ainda não calcula áreas ambientais, interpreta perguntas livres nem executa o benchmark científico.

Python verificado: 3.10.12. Dependências diretas verificadas e fixadas em `setup.cfg`; o backend de build está em `pyproject.toml`. Metadados em `setup.cfg` mantêm compatibilidade com setuptools 59.6.0 já disponível, sem atualização de ferramentas pela rede.

Instalação normal em ambiente próprio do projeto:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[diagnostics,test]'
.venv/bin/consultas-ambientais --help
.venv/bin/python -m pytest -q
```

Alternativa offline no ambiente em que as versões fixadas já existem no Python de sistema:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-build-isolation --no-deps .
```

Essa alternativa compartilha pacotes do Python de sistema; não constitui isolamento completo das dependências. Não utiliza o `venv` do experimento SAR nem modifica o ambiente `venv` existente neste projeto. `requirements-verified.txt` registra as versões verificadas, não um lock multiplataforma com hashes.

Usar instalação por wheel, sem `-e`: o modo legado `setup.py develop` do setuptools disponível gera um launcher incompatível com caminhos contendo espaços. A instalação normal usa o launcher do pip, validado no caminho real do projeto. Após editar o código, reinstale o pacote ou execute com `PYTHONPATH=src .venv/bin/python -m consultas_ambientais`.

Comandos sem acesso à rede:

```bash
.venv/bin/consultas-ambientais --config configs/project.json config
.venv/bin/consultas-ambientais schema plan
.venv/bin/consultas-ambientais schema answer
.venv/bin/consultas-ambientais diagnose --output reports/nao_solicitado.json
```

O programa não carrega `.env` automaticamente. `.env.example` lista o contrato; forneça valores reais somente por variáveis exportadas no ambiente do processo ou integração com cofre. O arquivo `.env` preexistente é preservado. Diagnósticos não exibem valores de conexão, segredos ou caminhos locais nas mensagens de erro.

Após configurar as variáveis no seu terminal, execute explicitamente:

```bash
.venv/bin/consultas-ambientais --config configs/project.json diagnose --database --output reports/postgis.json
.venv/bin/consultas-ambientais --config configs/project.json diagnose --rasters --years 2015 2025 --output reports/rasters_piloto.json
.venv/bin/consultas-ambientais --config configs/project.json diagnose --rasters --output reports/rasters_todos.json
.venv/bin/consultas-ambientais diagnose --llm --output reports/llm.json
```

`--llm` autoriza uma única requisição de chat pequena, sem retry ou renovação de 401 nesse diagnóstico; a autenticação pode exigir chamadas próprias. O cliente reutilizável, fora desse diagnóstico, possui retry limitado e uma renovação de token após 401. O diagnóstico não presume suporte a ferramentas nativas, seed, JSON Schema ou `response_format`. O modelo deve ser fornecido explicitamente.

Saídas: código 0 para verificações selecionadas executadas; código 2 se uma selecionada ficou pendente/indisponível. Componentes não selecionados ficam `pendente/nao_solicitado`. `verificado` significa que a verificação descrita foi executada; não afirma que um mapa está correto no terreno. Falhas de conexão não provam que um ano inexiste.

Os relatórios JSON recebem permissão 0600, gravação atômica, data UTC e estados por componente. `reports/`, dados, cache e artefatos são ignorados no Git. Para publicar manifests/amostras, copie apenas uma seleção revisada para um diretório público próprio; não altere a regra para liberar todos os relatórios.

O acesso PostGIS usa transação `REPEATABLE READ, READ ONLY`, `default_transaction_read_only=on`, timeout de conexão, consulta e lock, e encerra com rollback. Faz leituras agregadas das tabelas além das amostras pequenas: validação geométrica/contagens podem percorrer todas as linhas e estão limitadas por timeout. Não altera objetos ou valores.

O diagnóstico raster faz HEAD e Range, rejeita status 200 no GET parcial sem consumir o corpo, limita bytes/requisições por arquivo e usa um leitor de janelas com o mesmo orçamento. Lê uma amostra de 1 pixel, sem estimar estatísticas de cobertura. Limites de um bloco comprimido podem impedir a leitura e ficam registrados. Não usa um download integral como fallback.

Veja `docs/CONTRATOS.md`, `docs/DECISOES.md` e `docs/ESTADO_IMPLEMENTACAO.md` para semântica, decisões e evidências de execução. As etapas posteriores permanecem no planejamento original.

O catálogo da Coleção 11 vem empacotado com as fontes e hashes. Consulte `docs/CATALOGO_SEMANTICO.md` para reconstrução, resolução territorial, política de ambiguidades e validação de capacidades. Exemplos offline:

```bash
.venv/bin/consultas-ambientais catalog inspect
.venv/bin/consultas-ambientais catalog expand 1 3
.venv/bin/consultas-ambientais catalog resolve --term floresta
.venv/bin/consultas-ambientais schema intent
```

O snapshot de atributos reais fica em `data/territories_v1.json`, com capacidades em `data/capabilities_stage2.json`. Não confundir fontes raster acessíveis com estatísticas de área já materializadas: o manifesto atual ainda bloqueia consultas quantitativas por falta dessas estatísticas.

Etapa 3: veja [PROCESSAMENTO_GEOESPACIAL.md](docs/PROCESSAMENTO_GEOESPACIAL.md) para snapshot, área fracionária elipsoidal, piloto, retomada e limites. Os comandos são `process snapshot`, `process pilot` e `process full`. O motor de perguntas continua previsto para a etapa 4.

Etapa 4: o comando `query --plan ... --run-id ...` executa consultas verificáveis sobre os Parquets locais, com saída JSON/CSV e evidências. Veja [CONSULTAS_VERIFICAVEIS.md](docs/CONSULTAS_VERIFICAVEIS.md) e `configs/examples/plano_*.json`. Não requer banco de origem ou LLM.

Etapa 5 (pacote 0.5.0): `ask --question '...' --run-id ...` interpreta texto com o cliente LLM, valida entidades/semântica e encaminha ao motor determinístico. Prompts versionados, um reparo no máximo, sessões explícitas de esclarecimento e registros com evidências. Veja [INTERPRETACAO_TEXTO.md](docs/INTERPRETACAO_TEXTO.md). O estado atual das entregas é o descrito nas atualizações por etapa abaixo da introdução histórica: já existem cálculos e consultas implementados. Gateway real pendente por configuração exportada ausente; os exemplos da etapa 5 usam HTTP mock sobre Parquets reais, identificados nos relatórios. `scripts/validar_etapa5_contrato.py` reproduz essa validação sem rede.

Atualização após autorização de leitura do `.env`: o gateway LLM real foi acessado e as consultas foram verificadas contra os Parquets reais. A versão 0.5.1 corrige a interpretação da palavra “união” em composição de classes e valida o escopo de rankings com reparo; os prompts anteriores foram preservados e a versão atual é `pt_v2`. Consulte [VALIDACAO_LLM_REAL.md](docs/VALIDACAO_LLM_REAL.md) e `docs/VALIDACAO_ETAPA5_REAL.json` para resultados e reprodução com `--env-file .env`, mantendo separados os testes reais e os mocks históricos.

A versão 0.5.2 usa prompts `pt_v3`, preservando `pt_v1`/`pt_v2`, e acrescenta validação de esclarecimento inconsistente com um plano completo e da UF derivada de código IBGE. O validador real registra temperatura 0, timeout e orçamento de tokens como parâmetros explícitos; essas opções não alteram o `.env` nem garantem repetibilidade absoluta.

Etapa 6 (0.6.0): CLI `local` e FastAPI exclusivamente em loopback, com sessões protegidas, consulta/esclarecimento, capacidades verificadas, recuperação por IDs e JSON/CSV/tabela HTML. Inicie com `.venv/bin/consultas-ambientais local --env-file .env serve`. Veja [DISPONIBILIZACAO_LOCAL.md](docs/DISPONIBILIZACAO_LOCAL.md) para instalação, endpoints, comandos e demonstração temporária. A API usa os derivados existentes e não materializa rasters durante perguntas.

Avaliação científica (etapa 7): o [protocolo](docs/AVALIACAO_CIENTIFICA.md) descreve o benchmark português, congelamento, condições A/B/C, gabaritos independentes e bootstrap pareado por família. Use `consultas-ambientais evaluate --help`. O benchmark em `benchmarks/pt_rn_v1` é congelado; execuções individuais e exportações ficam em `artifacts/evaluation`, ignorado pelo Git. A execução de modelos é opt-in com `--env-file .env`; os comandos de relatório não chamam o gateway.


Revisão científica V2 (20/10/2026): [novos rascunhos e reprodução](docs/REVISAO_RASCUNHOS_V2.md), com sensibilidade B/C pós-hoc, proveniência dos intervalos oficiais e arquitetura/exemplo real. V1 preservada; nenhuma nova inferência ou condição equivalente foi executada.


Revisão científica V3 (21/10/2026): [rascunhos, controle equivalente e reprodução](docs/REVISAO_RASCUNHOS_V3.md). A revisão manual declarada cobre as 120 perguntas, sem correções; não confirma revisão dos gabaritos. Foi executado um controle real com plano fixo e mesmo JSON final nas duas condições, com resultados e falhas individuais preservados. A V3 acrescenta quatro referências primárias e mantém o recorte e as limitações de proveniência. V1/V2 e a produção permanecem intactas; o novo controle é exploratório e não substitui o teste original.


Revisão científica V4 (21/10/2026): [rascunhos, diagnóstico e revisão dos gabaritos](docs/REVISAO_RASCUNHOS_V4.md). O autor confirmou revisão dos 88 gabaritos, sem correções; um recálculo independente conferiu 104 valores. Novas chamadas instrumentadas investigam os 26 retornos vazios, preservando os escores V3. O artigo separa experimento ponta a ponta e controle com plano fornecido, com destaque ao gráfico e ao efeito do orçamento de saída.


Revisão científica V5 (21/10/2026): [sensibilidade completa a 4.096 tokens e origem IBGE 2025](docs/REVISAO_RASCUNHOS_V5.md). Novos 88 pares B_eq/C_eq, mantendo contexto, contratos e critérios; resultados anteriores preservados. A contribuição é formulada como taxa de respostas válidas/corretas, distinguindo precisão entre emitidas. A origem/edição da malha foi informada pelo autor; aquisição oficial bloqueada por timeout, com GeoJSON e hashes das geometrias utilizadas disponíveis para reprodução.


## Artigo ampliado — V6 (23/10/2026)

A [V6 em PDF](artifacts/scientific/etapa8_v6/manuscrito/rascunho_sbsr2027_v6.pdf) e o [ODT editável](artifacts/scientific/etapa8_v6/manuscrito/rascunho_sbsr2027_v6.odt) acrescentam a figura existente de latência, análise descritiva de tempo/tokens e distinção entre acerto e emissão quantitativa. Quatro páginas, sem alterar resultados ou versões anteriores. Reprodução offline e limites em [REVISAO_RASCUNHOS_V6.md](docs/REVISAO_RASCUNHOS_V6.md).
