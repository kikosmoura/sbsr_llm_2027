**Etapa 6 — CLI e FastAPI locais**

A aplicação usa os Parquets e o motor determinístico já verificados. O caminho de uma pergunta não processa rasters nem acessa o PostgreSQL. CLI e API compartilham capacidades, armazenamento de sessões, resultados e exportações. Não há publicação/deploy nesta entrega.

Execute os comandos na raiz de `sbsr_2027`, em Python 3.10 e no ambiente próprio do projeto. As versões efetivamente testadas estão fixadas em `setup.cfg` e registradas em `requirements-verified.txt`.

```bash
.venv/bin/python -m pip install '.[local,test]'
.venv/bin/consultas-ambientais local --help
.venv/bin/consultas-ambientais local capabilities
.venv/bin/consultas-ambientais local capabilities --territory-code 2410900
.venv/bin/consultas-ambientais schema local_response
.venv/bin/consultas-ambientais schema local_settings
```

Na instalação offline desta entrega, foi usado wheel local com `--no-index --no-deps`, pois todas as dependências fixadas já estavam disponíveis. Não foi reutilizado o ambiente SAR. A aplicação e suas dependências precisam estar instaladas no mesmo ambiente que inicia os processos filhos.

**Configuração e início local**

`configs/project.json` preserva a configuração das fontes. `configs/local.json` seleciona execução, catálogos locais, rede e limites públicos, sem credenciais. A UF das capacidades vem da execução selecionada; alterar a UF na configuração não reinterpreta dados já processados.

```bash
.venv/bin/consultas-ambientais local --env-file .env serve
# Outra porta de loopback, se necessário:
.venv/bin/consultas-ambientais local --env-file .env serve --port 8766
```

Padrão: `http://127.0.0.1:8765`. O servidor aceita somente loopback (`127.0.0.1` ou `::1`), um worker, sem reload, sem proxy headers e sem access log de URLs. Não aceita bind em `0.0.0.0`, não cria túnel, domínio, serviço permanente ou exposição externa. Encerre com Ctrl+C. A documentação interativa com recursos externos não foi habilitada; o contrato está em `/openapi.json`.

`--env-file` é opt-in: lê o arquivo como dados, sem executar shell ou interpolação `${...}`. Não altera o arquivo e não imprime seus valores. As credenciais do banco são usadas apenas para redação preventiva, nunca para conectar nesse caminho. O serviço usa os limites explícitos de `configs/local.json` para timeout HTTP, tentativas, temperatura e tokens; assim o timeout maior presente no `.env` anterior não ultrapassa o contrato validado. TLS do LLM permanece verificado, com CA corporativa opcional pelo contrato existente.

**Sessões e consulta pela CLI**

```bash
.venv/bin/consultas-ambientais local session --key-file data/local_keys/minha_sessao.json
.venv/bin/consultas-ambientais local --env-file .env ask \
  --key-file data/local_keys/minha_sessao.json \
  --question 'Qual era a área de pastagem de Riachuelo/RN em 2015, em hectares?'

.venv/bin/consultas-ambientais local result --key-file data/local_keys/minha_sessao.json --id RESULT_ID
.venv/bin/consultas-ambientais local evidence --key-file data/local_keys/minha_sessao.json --id RESULT_ID
.venv/bin/consultas-ambientais local answer --key-file data/local_keys/minha_sessao.json --id ANSWER_ID
.venv/bin/consultas-ambientais local export --key-file data/local_keys/minha_sessao.json \
  --id RESULT_ID --format csv --output reports/local/resposta.csv
```

O comando `session` grava a chave somente em arquivo privado 0600, sob `data/local_keys/`, e imprime ID e validade. Não sobrescreve uma chave existente. O arquivo é ignorado pelo Git. `result_id` identifica aquele turno; `answer_id` identifica o resultado determinístico. Ambos exigem a sessão correspondente. JSON, CSV e HTML podem ser exportados em `reports/local/`.

Para responder a um esclarecimento pendente, use os IDs retornados:

```bash
.venv/bin/consultas-ambientais local --env-file .env clarify \
  --key-file data/local_keys/minha_sessao.json --id RESULT_ID \
  --reply-to CLARIFICATION_ID --question 'RN'
```

Cada nova pergunta cria um contexto de diálogo separado. Esclarecimentos são vinculados ao resultado e sessão de origem; não aceitam IDs de outra sessão ou troca de contexto silenciosa. Os comandos anteriores `ask`, `query` e `process` permanecem disponíveis. Seus registros históricos não são importados automaticamente para uma nova sessão da API. Executar novamente um plano equivalente sobre a mesma execução conserva o `answer_id` do motor.

Saída CLI: código 0 para operação respondida/administrativa; código 2 para esclarecimento, fora do escopo, dados indisponíveis ou falha. O JSON distingue esses estados; não conclua que toda saída 2 é falha de rede.

**Endpoints**

| Método | Caminho | Conteúdo |
|---|---|---|
| GET | `/healthz` | Liveness, sem chamar o modelo ou afirmar disponibilidade de dados |
| GET | `/v1/capabilities` | Territórios, anos, classes, pares, operações e cobertura verificados |
| POST | `/v1/sessions` | Cria sessão; devolve chave uma vez |
| POST | `/v1/sessions/{session}/questions` | Corpo `{"question":"..."}` |
| POST | `/v1/sessions/{session}/results/{result}/clarifications` | Corpo com `clarification_id` e `reply` |
| GET | `/v1/sessions/{session}/results/{result}` | Estado, texto, números, evidências, fontes e execução |
| GET | `/v1/sessions/{session}/answers/{answer}` | Resultado determinístico por ID estável |
| GET | `/v1/sessions/{session}/results/{result}/evidence` | Evidências e execução daquele resultado |
| GET | `/v1/sessions/{session}/results/{result}/evidence/{evidence}` | Evidência individual |
| GET | `/v1/sessions/{session}/results/{result}/export/{format}` | `json`, `csv` ou `html` |

Todos os endpoints de sessão/resultados, exceto a criação, exigem `X-Session-Token`. IDs sem essa chave não autorizam acesso. Falta de chave, chave inválida, sessão expirada e recurso pertencente a outra sessão retornam 404 sem revelar sua existência. Não há listagem de sessões. Chaves da API são distintas dos tokens OAuth2 do LLM; somente hashes das chaves são guardados no registro do serviço.

Exemplo Python sem imprimir a chave:

```python
import requests
client = requests.Session()
client.trust_env = False  # loopback sem encaminhar a chave a proxies
base = 'http://127.0.0.1:8765'
session = client.post(base + '/v1/sessions').json()
headers = {'X-Session-Token': session['session_token']}
response = client.post(
    base + '/v1/sessions/' + session['session_id'] + '/questions',
    headers=headers,
    json={'question': 'Qual era a área de pastagem de Riachuelo/RN em 2015, em hectares?'},
    timeout=110,
)
value = response.json()
print(value['status'], value.get('result_id'))
```

`LocalResponse.result` contém o `QueryAnswer` da etapa 4, com plano executado, valores integrais, unidade/denominador, fontes, método, malha, revisão e execução. `trace` registra diálogo, modelo informado/retornado, hashes dos prompts/interpretador e tentativas. `source_context` e `limitations` acompanham também recusas e falhas. O contrato não retorna credenciais, conexão, geometria, raciocínio interno ou corpo bruto de erro.

Estados semânticos (`respondida`, `precisa_esclarecimento`, `fora_do_escopo`, `dados_indisponiveis`) usam HTTP 200 após uma pergunta processada. Falha técnica usa 503; timeout do processo, 504; serviço ocupado/cota, 429; corpo inválido, 422; corpo grande, 413; prazo de leitura de corpo excedido, 408. Erros não publicam números. Resultados técnicos que receberam `result_id` também podem ser recuperados posteriormente.

**Capacidades e exportações**

`/v1/capabilities?territory_code=2410900` filtra um território. Anos provêm das materializações da execução, com checagem de hashes das partições e da qualidade registrada. `materialized_years` e `usable_years` são distintos: um recorte processado pode ter cobertura parcial e continuar indisponível para cálculo. As classes distinguem grupos e folhas; não afirmam que toda folha conhecida foi observada como pixel. Pares e elegibilidade de ranking são explícitos, com universo completo e códigos faltantes/parciais.

No piloto real há 168 entidades processadas (167 municípios e uma UF), anos 2015/2025 e 166 municípios com cobertura completa. Areia Branca e UF têm cobertura parcial/código desconhecido 0; não se anuncia ranking completo do RN. Os anos 2016..2024 não se tornam consultáveis por constarem das URLs/configuração.

JSON é o mesmo envelope retornado pela consulta/GET. CSV reutiliza o exportador do motor e preserva valores, denominações e evidências. Base zero continua `null` no JSON e célula vazia com motivo no CSV. HTML é tabela estática com valores integrais reversíveis para float64, sem JavaScript, CDN ou novas fórmulas. Não foi acrescentado gráfico com cálculos próprios nem interface web adicional. A frase quantitativa arredondada continua sendo a do servidor.

**Limites, execução e registros**

Padrões públicos: uma mutação/consulta por vez, sem fila; 4.000 caracteres e 32 KiB de corpo; leitura de corpo em até 10 s; consulta em processo isolado por até 90 s; HTTP do gateway até 30 s por tentativa; até um reparo de plano; duas tentativas HTTP configuradas. O processo é encerrado no timeout total, inclusive se estiver bloqueado em I/O. A computação remota já enviada ao gateway pode continuar do lado do provedor.

As rotas de I/O são síncronas e o FastAPI as executa no pool de threads. O LLM/motor rodam em processo local descartável, com IPC limitado, sem fila ou distribuição. O cache OAuth2 existe dentro desse processo, inclusive durante reparo, sem compartilhar um `requests.Session` entre threads. Liveness continua responsivo. Uma trava de arquivo não bloqueante coordena API e CLI; outra consulta concorrente recebe 429. Use um único worker do servidor.

Sessões: validade 24 h, até 32 sessões e 25 resultados por sessão. Registros públicos internos têm limite de 4 MiB; registro do serviço limitado a 128 MiB. As cotas são verificadas antes da chamada ao modelo. Após expirar, o acesso pela API é negado; os arquivos privados de auditoria continuam no disco para revisão pelo operador. Não há exclusão automática de evidências ou alteração dos dados de origem.

Sessões/resultados: `artifacts/local_service/`; chaves CLI: `data/local_keys/`; auditoria do interpretador: `artifacts/dialogues/`; contexto de esclarecimento: `data/dialogues/`. Todos ficam fora do Git, em arquivos 0600. Os logs HTTP contêm só ID aleatório, status e duração, sem URL, corpo, chave, Authorization ou credenciais. Host/Origin são limitados a loopback; não há CORS aberto. Respostas usam no-store, nosniff e CSP sem recursos externos.

Se houver timeout ao responder esclarecimento, uma gravação final no processo pode ter ocorrido antes da interrupção. A falha não expõe números e orienta começar outra pergunta; não há retomada automática que herde um estado incerto.

**Diagnóstico, materialização e demonstração**

O diagnóstico inicial e a reconstrução dos derivados permanecem nas etapas anteriores:

1. Conferir configuração e fontes com os comandos `diagnose` documentados no README e em `ESTADO_IMPLEMENTACAO.md`; a seleção de LLM é opt-in.
2. Gerar snapshot em leitura, validar poucos recortes e depois processar a UF configurada conforme [PROCESSAMENTO_GEOESPACIAL.md](PROCESSAMENTO_GEOESPACIAL.md). Os comandos são `process snapshot`, `process pilot` e `process full`, com as opções/referências descritas naquele documento. Esses comandos são operações administrativas fora da API.
3. Selecionar o `run_id` concluído em `configs/local.json` e consultar `local capabilities` antes de perguntar. A aplicação não inicia materialização durante uma pergunta.
4. Para comparar planos sem LLM, usar `query --plan ... --run-id ...`, conforme [CONSULTAS_VERIFICAVEIS.md](CONSULTAS_VERIFICAVEIS.md).

Validações e demonstração:

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider
.venv/bin/python -B scripts/demonstrar_etapa6.py --env-file .env
```

O script inicia temporariamente o servidor em porta livre de loopback e o encerra ao terminar. Verifica município, comparação 2015–2025, ranking da UF explicitamente bloqueado, homônimo com esclarecimento, classe ambígua e ano não materializado. Usa gateway e Parquets reais, compara referências da etapa 4 e exerce GET por IDs, evidência, JSON/CSV/HTML, isolamento de sessão e CLI real. Chaves ficam em memória/arquivo privado; o relatório não as publica.

Os testes automatizados de falhas usam dados sintéticos/mocks claramente marcados; não afirmam acesso real ao gateway. A demonstração real é separada, com relatório local em `reports/etapa6/demonstracao_real.json`. O resumo revisado e limitações efetivamente observadas constam de `VALIDACAO_ETAPA6.json`. É demonstração de desenvolvimento, não benchmark independente ou comprovação de qualidade temática dos mapas.
