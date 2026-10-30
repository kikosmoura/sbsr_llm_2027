**Etapa 5 — pergunta em português e resultado verificável**

Pacote 0.5.0, Python 3.10.12. Sem dependências novas. A CLI `ask` reutiliza o OAuth2/cliente textual da etapa 1 e o executor da etapa 4. Nesta entrega o HTTP do gateway foi testado com mocks; o executor consumiu também os Parquets reais do RN. A interpretação por um modelo real permanece pendente porque as variáveis obrigatórias do gateway não estão exportadas. O `.env` existente não foi aberto.

**Uso no projeto**

Execute na raiz de `sbsr_2027`, com as variáveis `LLM_*` fornecidas localmente pelo seu ambiente/cofre, conforme `.env.example`. Não inclua credenciais na pergunta. A CLI não lê `.env` automaticamente. Uma configuração parcial causa erro redigido; configuração ausente produz `erro_tecnico/configuracao_llm_ausente`, sem chamadas de rede.

```bash
.venv/bin/consultas-ambientais ask --help
.venv/bin/consultas-ambientais schema model_proposal
.venv/bin/consultas-ambientais schema ask_answer
.venv/bin/consultas-ambientais --config configs/project.json ask \
  --run-id a98ccf54c8c82ceeb601ce126cdb379add4de253912a46267601cdc7d9a29802 \
  --question 'Qual era a área de pastagem de Riachuelo/RN em 2015, em hectares?' \
  --json-output reports/pergunta.json --csv-output reports/pergunta.csv
```

Para limitar a primeira verificação real a uma proposta, desative o reparo e reduza as tentativas HTTP:

```bash
LLM_MAX_ATTEMPTS=1 .venv/bin/consultas-ambientais ask \
  --run-id a98ccf54c8c82ceeb601ce126cdb379add4de253912a46267601cdc7d9a29802 \
  --question 'Qual era a área de pastagem de Riachuelo/RN em 2015, em hectares?' \
  --no-repair --max-output-tokens 768 --format json
```

A renovação de 401 do cliente reutilizável continua possível, independentemente de `max_attempts`. Se for imprescindível exatamente uma tentativa HTTP, use antes `diagnose --llm`, cujo cliente de diagnóstico desativa essa renovação. O comando acima limita a uma proposta, não promete uma única chamada HTTP em caso de 401. `LLM_MAX_TOKENS`, se exportado, é respeitado; `--max-output-tokens` tem precedência. Para `ask`, o intervalo é 256..2048, padrão 768. TLS permanece verificado; `LLM_CA_BUNDLE` aceita uma CA existente. Não se presume suporte nativo a tools, seed, JSON Schema ou response_format; o schema é texto no prompt e validação local.

**Esclarecimentos e isolamento**

Uma pergunta sobre Santa Cruz sem UF retorna candidatos nacionais, inclusive fora do piloto. “Floresta” preserva a ambiguidade entre grupo e classe. Área sem unidade e “percentual” sem definição da medida/denominador também pedem esclarecimento. A disponibilidade do RN não autoriza escolher essa UF por conta própria.

A saída fornece `session_id` e `clarification.clarification_id` (`reply_to` no formato textual). Para continuar, copie esses IDs daquela resposta:

```bash
.venv/bin/consultas-ambientais ask \
  --run-id a98ccf54c8c82ceeb601ce126cdb379add4de253912a46267601cdc7d9a29802 \
  --question 'RN' --session-id ID_DA_SESSAO --reply-to ID_DO_ESCLARECIMENTO
```

Sem IDs começa outra sessão. IDs de outra sessão, esclarecimento já consumido, mudança de fontes/prompts/interpretador/configuração ou limite de dez turnos impedem reaproveitamento. A resposta curta altera somente o campo pendente. O histórico de números de outra pergunta não entra no prompt. As sessões são locais, com UUID, lock e arquivos privados; não implementam autenticação multiusuário. Não publique esses diretórios indiscriminadamente.

**Fluxo e contratos**

1. Redigir ou recusar entradas com dados de acesso; verificar políticas de escopo e sessão explícita.
2. Construir contexto com os 41 nós semânticos, disponibilidade materializada e candidatos territoriais necessários. Não enviar áreas, credenciais, conexão, geometrias, respostas anteriores ou gabaritos.
3. Renderizar `llm/prompts/pt_v1/system.txt`, `user.txt` e `proposal.schema.json`. Registrar SHA-256 desses arquivos e de `repair.txt`, do contexto e das mensagens de cada tentativa.
4. Obter JSON inteiro, sem extrair trechos de Markdown. Proibir campos extras, chaves duplicadas, NaN/Infinity e saídas acima de 20 mil caracteres. Exigir `ModelProposal`/`CandidateIntent` tipados.
5. Ancorar entidades, anos, unidades e operação na pergunta original/escolhas confirmadas. Não basta JSON válido. Resolver classes/territórios localmente e validar capacidades efetivamente materializadas.
6. Em saída inválida, permitir uma única nova proposta com erros sanitizados de validação. Não reenviar texto bruto inválido, detalhes internos nem fatos de avaliação. Ambiguidade genuína pede esclarecimento, sem consumir reparo. Falha técnica do gateway não vira resposta numérica.
7. Executar `QueryEngine.answer()` sobre o plano normalizado. Publicar exclusivamente valores/evidências e frase do template do servidor, acrescida de uma ressalva fixa sobre classificação mapeada. Não solicitar uma explicação livre adicional. Se o modelo retornar `explanation`, descartá-la integralmente e registrar fallback.

A interpretação usa guardas linguísticas conservadoras para as operações do MVP. Não é um parser universal de português: paráfrases não reconhecidas podem exigir esclarecimento ou falhar após reparo. Os mocks verificam os contratos, não estimam acurácia linguística. Um benchmark independente e teste real do gateway continuam necessários.

**Rastreabilidade e privacidade**

`artifacts/dialogues/<session_id>/<turn_id>.json` guarda pergunta redigida, data UTC, status, contexto enviado, modelo solicitado/retornado, configuração pública, hashes, propostas tipadas sem explicação livre, falhas originais por hash/tamanho/erros, latências, contadores de requisições e usage quando presente. O plano executado e as evidências estão em `query`: IDs de fatos, valores/unidades/denominadores, método, execução, malha, revisão e hashes/fontes. O registro determinístico da etapa 4 também permanece disponível.

`data/dialogues/<session_id>.json` guarda contexto mínimo de esclarecimento e identidade das fontes. Arquivos são atômicos, modo 0600, em diretórios ignorados no Git. Não gravar OAuth2, Authorization, corpos de erro, saída inválida bruta ou raciocínio interno. Usage arbitrário é filtrado aos três contadores conhecidos. Pergunta com dados de acesso é inteiramente omitida; não é enviada ao modelo. A redação por padrões não garante anonimização de todo texto pessoal possível: perguntas e registros devem tratar apenas o domínio ambiental.

O número de propostas é no máximo dois. Retries HTTP/renovação de token são limites distintos, herdados do cliente, e as chamadas de chat observadas são registradas. Latência e tokens de um teste mock nunca são apresentados como medidas do serviço real.

**Validações e limites reais**

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider
.venv/bin/python scripts/validar_etapa5_contrato.py
```

A suíte cobre 203 testes sintéticos/mocks, 43 novos de interpretação: consulta válida, homônimos, classe/unidade/denominador ambíguos, isolamento de sessão, ano ausente, alteração de entidade/ano pelo modelo, indução de SQL, campo extra, JSON inválido, limite de reparo, falhas de autenticação e explicação com número sem evidência.

O script é explicitamente HTTP mock, com o cliente LLM real e os Parquets reais já derivados, sem rede: nove cenários e onze turnos, incluindo dois esclarecimentos completos. Os planos mock não contêm áreas. Os IDs das consultas equivalentes são comparados aos registros da etapa 4; o gabarito nunca é enviado ao prompt. Saídas completas em `reports/etapa5/contrato_dados_reais.json` e nos registros por turno. A geração usa IDs aleatórios e data atual; os IDs determinísticos dos resultados são estáveis. `docs/VALIDACAO_ETAPA5.json` resume as evidências e distingue o gateway pendente.

Exemplos calculados continuam: pastagem de Riachuelo em 2015 = 8.684,04 ha; diferença líquida de Área Urbanizada de Natal, suporte comum 2015–2025 = +358,03 ha. O gateway desses exemplos foi simulado. Não apresentar como teste ponta a ponta com modelo real.

Permanecem materializados somente 2015 e 2025; 2016 retorna `dados_indisponiveis`. Ranking completo do RN permanece bloqueado pela cobertura parcial/código desconhecido 0 em Areia Branca. Edição territorial e revisão oficial do espelho continuam desconhecidas. Perda bruta exige matriz inexistente; água mapeada não demonstra inundação; diferenças marginais não demonstram desmatamento, causas, ilegalidade ou qualidade temática. Não houve comparação com estatísticas oficiais nem novos acessos ao banco/rasters nesta etapa.

**Atualização: gateway real verificado e versão 0.5.2**

Após a autorização posterior do usuário, o `.env` foi carregado explicitamente pelo novo script `scripts/validar_etapa5_real.py --env-file .env`. Verificação real concluída: 26/26 cenários na rodada final; 211 testes locais. O timeout maior que o teto foi substituído no processo por 120 s; orçamento 2.048 tokens e temperatura 0 foram registrados, preservando o arquivo. Os comandos de reprodução e distinções entre mocks e chamadas reais estão em `VALIDACAO_LLM_REAL.md`. Prompts atuais: pt_v3, com pt_v1/pt_v2 preservados. As indicações anteriores de gateway pendente são registros históricos da primeira entrega. Consulte `VALIDACAO_ETAPA5_REAL.json` para falhas iniciais, correções, hashes e rastreabilidade final.
