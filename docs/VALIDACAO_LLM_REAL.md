**Validação com LLM real — etapa 5**

A instrução inicial proibia abrir o `.env`; por isso a primeira entrega usou apenas configuração exportada e deixou o gateway pendente. A autorização posterior do usuário permitiu carregar o arquivo local. A presença de variáveis em um arquivo não as exporta automaticamente para o processo Python.

A leitura agora é explícita e feita com `python-dotenv`, sem executar o arquivo como shell. O arquivo foi preservado. URLs de autenticação, identificador do cliente, segredo, credenciais do banco e tokens não são publicados. O programa continua sem carregar `.env` automaticamente em comandos comuns; o validador opt-in implementa essa autorização pelo argumento `--env-file`.

O timeout encontrado no arquivo excedia o teto de 120 s aceito por `LLMSettings`. O validador usa explicitamente 120 s, orçamento de saída de 2.048 tokens e temperatura 0, registrando esses três parâmetros. As primeiras rodadas preservaram a temperatura não informada do arquivo. Não altera o `.env`, não aumenta limites da aplicação e mantém TLS verificado. Os demais parâmetros reconhecidos são carregados do arquivo, incluindo modelo e autenticação. Expansão de variáveis `${...}` não é executada.

Reprodução na raiz de `sbsr_2027`, com ambiente próprio e Parquets já presentes:

```bash
# Necessário apenas se a dependência opcional ainda não estiver instalada:
.venv/bin/python -m pip install -r scripts/requirements-validacao-real.txt

.venv/bin/python -B scripts/validar_etapa5_real.py \
  --env-file .env --output reports/etapa5/real/repeticao/resumo.json

.venv/bin/python -B -m pytest -q -p no:cacheprovider
```

A segunda linha efetua chamadas reais e tem custo/latência do gateway. O primeiro comando não foi necessário nesta sessão: python-dotenv 1.2.2 já estava instalado. `--only` permite selecionar IDs listados na função `cases()`; `--timeout`, `--max-output-tokens` e `--temperature` definem os limites do processo de validação, ainda sujeitos aos contratos da aplicação. Os relatórios só podem ser gravados dentro de `reports/etapa5/real/`.

O validador cobre as operações da etapa 4 e sua rastreabilidade: área, participação, diferença líquida, variação percentual, pontos percentuais, união de classes, série, comparação territorial, base inicial zero e conversões de unidade. Também verifica IBGE, homônimo, classe vaga, unidade/denominador ausentes, esclarecimentos explícitos, ano não materializado, cobertura parcial e bloqueio de ranking. Inclui tentativas de induzir SQL, causa, perda bruta, inundação, texto não JSON, campo extra e explicação sem evidência.

As referências quantitativas da etapa 4 foram calculadas por caminho independente com Decimal. Nesta validação elas ficam somente no avaliador, sem entrar nos prompts. O plano completo é comparado ao plano esperado, além dos valores, unidades, motivos de indefinição e IDs de evidência. A tolerância segue a etapa 4: absoluta 1e-10 e relativa 1e-12 para representação float64, sem arredondar os dados.

Os casos adversariais submetidos ao modelo podem ser corretamente ignorados por ele; isso não garante produzir toda modalidade de saída inválida. Os testes de contrato com respostas controladas, inclusive JSON inválido, campos extras, explicação fabricada, 401/429/5xx e erros sensíveis, permanecem sintéticos/mocks. Não se provoca falha de autenticação deliberada no serviço real. A recusa de SQL e conceitos proibidos pode ocorrer localmente antes do gateway, e isso é registrado com zero chamadas naquele caso.

São casos de desenvolvimento/revisão, com repetições conhecidas, não um benchmark independente congelado. Temperatura 0 não garante repetibilidade absoluta. Não estimar acurácia geral, comparar modelos ou obter significância estatística a partir destes resultados. O script registra cada tentativa, incluindo reparos reais, sem texto bruto inválido, raciocínio interno ou tokens OAuth2. Uso de tokens, latência e contadores de chamadas são observações reais quando indicados como tal.

O relatório detalhado e os resultados por turno ficam em `reports/etapa5/real/`; os registros originais ficam em `artifacts/dialogues/<session_id>/<turn_id>.json`. A pergunta, contexto permitido, hashes dos prompts/interpretador, modelo informado/retornado, plano candidato/executado e evidências vinculam cada resposta aos Parquets e à execução geoespacial. JSON/CSV usam gravação privada. Somente o resumo revisado em `docs/VALIDACAO_ETAPA5_REAL.json` é publicável por seleção explícita.

A validação não consulta o PostgreSQL nem baixa rasters. Permanecem os limites dos dados: somente 2015/2025 materializados; ranking RN bloqueado por cobertura parcial/código 0; edição territorial e revisão oficial desconhecidas; sem matriz de transição ou inferência causal. Os relatórios antigos de ausência de configuração e de mocks são históricos e foram preservados; o resumo atual da etapa 5 os distingue da verificação real posterior.

**Resultados efetivamente observados**

Versão final instalada 0.5.2, prompts pt_v3: 26/26 cenários aprovados, 30 turnos, 28 chamadas reais de chat incluindo o probe e uma chamada OAuth2, com cache de token observado na execução. Quatro pedidos proibidos/sem matriz foram barrados localmente, sem chamada ao modelo nesses casos. Houve um reparo real na rodada final, preservando a falha inicial. Uma verificação adicional da CLI instalada fez mais uma chamada real e validou JSON/CSV e o ID determinístico da resposta. Total da bateria final mais CLI: 29 chamadas de chat.

A suíte local passou com 211 testes, dos quais 51 de interpretação; os casos com respostas/falhas controladas continuam claramente identificados como mocks. As rodadas anteriores foram preservadas: primeira completa 24/26, seguinte 22/26. Essas falhas motivaram as correções de contexto/composição de classes, formato/escopo de ranking, pedido de esclarecimento sem pendência, expressão de métrica literal e UF derivada de código IBGE. Os prompts pt_v1 e pt_v2 e os wheels anteriores foram preservados para reanálise. A mudança de prompts e temperatura é documentada; não comparar essas rodadas como se fossem repetições da mesma condição.

Na execução final, o modelo retornou RETURNED_MODEL_ID_1. Pastagem em Riachuelo/RN em 2015 continuou 8.684,04 ha e a diferença líquida de Área Urbanizada em Natal/RN, suporte comum 2015–2025, +358,03 ha. Os valores completos e fontes estão nos registros por turno, sem arredondamento do cálculo. O número sugerido na indução adversarial não foi publicado na frase quantitativa. O código do executor numérico e os 336 Parquets conservaram seus hashes. Nenhum resultado é apresentado como estatística oficial ou prova de mudança real específica no terreno.
