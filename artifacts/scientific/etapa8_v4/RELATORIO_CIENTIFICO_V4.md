# Revisão científica V4 — material suplementar



V3 e seus escores permanecem intactos. Esta revisão acrescenta investigação separada, recálculo independente e declaração humana, sem ajustar o sistema usando resultados. Não houve submissão/publicação/deploy.

## Investigação de retornos vazios

Os logs historicos dos 26 casos nao preservaram finish_reason, usage ou status HTTP final. Em replays novos selecionados por falha, com as mesmas mensagens, houve 23/26 retornos vazios a 2.048 tokens e 6/26 a 4.096. No primeiro limite, 23 casos combinaram texto ausente e finish_reason=length; 23/26 consumiram exatamente o limite de saida informado. Esses dados diagnosticam as novas chamadas, sem reconstruir a causa das antigas nem substituir os seus escores.

| Seleção | Limite de saída | Casos | Texto final | JSON válido | Vazios | Vazio e length | Uso igual ao limite |
| --- | --- | --- | --- | --- | --- | --- | --- |
| old_empty | 2048 | 26 | 3 | 3 | 23 | 23 | 23 |
| old_empty | 4096 | 26 | 20 | 20 | 6 | 6 | 6 |
| positive_control | 2048 | 2 | 2 | 2 | 0 | 0 | 0 |
| positive_control | 4096 | 2 | 2 | 2 | 0 | 0 | 0 |

HTTP observado nas novas chamadas: `{"oauth": {"200": 56}, "chat": {"200": 56}}`. Erros de transporte: `{}`.

Os contadores de entrada variaram de 5433 a 5684 tokens e foram iguais entre os dois limites para cada caso: True. O campo de raciocínio esteve presente em 56/56 respostas, mas seu texto não foi gravado. O contador reasoning_tokens não foi informado em 56/56; não se estima quantos tokens foram usados internamente.

| Hipótese | Registro histórico | Reexecução observada | Alcance da conclusão |
| --- | --- | --- | --- |
| Limite de saída | finish_reason/usage perdidos na exceção | length + consumo igual ao teto nos vazios; menos vazios com teto maior | Evidência de sensibilidade ao orçamento nas novas chamadas; causa antiga individual não recuperada |
| Timeout | Erro registrado foi texto_final_ausente, não timeout | Nenhum erro de transporte/timeout capturado | Não foi a falha observada nos replays; não reconstrói eventos internos antigos |
| HTTP/gateway | Status exato e retries ausentes; final 2xx inferido do código | Todos os chats HTTP 200, sem retries capturados | Sem erro HTTP observado no diagnóstico; não identifica backend/parser |
| Truncamento da resposta na rede/cliente | Não há corpo preservado | JSON completo; wrapper conta bytes; sem erro de leitura registrado | Sem truncamento de transporte observado; distinto de término por limite de geração |
| Entrada/contexto | Mensagens reconstruíveis por hash; sem usage nos vazios | Mesmo hash e mesmos contadores de entrada entre limites | Não permite provar a ausência de truncamento interno do servidor |
| Formato das mensagens | Contrato textual de dois papéis confirmado no código | Mesmas mensagens, sem mudar formatos ou endpoints | Não se testou formato alternativo; implementação interna permanece desconhecida |

As mensagens iniciais foram reconstruídas e conferidas por hash contra B_eq. O wrapper preserva metadados mesmo quando o cliente original rejeita texto vazio. Registram-se somente estados/contadores, sem texto de raciocínio, corpo HTTP, tokens OAuth2 ou Authorization. Não houve teste de outro formato de mensagens, API, modelo, seed ou esforço de raciocínio.

Não se conclui ausência histórica de erros HTTP a partir de status null. O caminho de código permite inferir somente resposta final 2xx/JSON antes da rejeição; retries intermediários não estão nos logs antigos. Da mesma forma, presença de campo de raciocínio não mede tokens internos: o contador fica null se não informado.

A documentação primária do modelo descreve seu formato Harmony e separação de canais ([repositório oficial gpt-oss](https://github.com/openai/gpt-oss/blob/main/README.md), consultado em 21/10/2026). Isso contextualiza a necessidade de distinguir texto final e outros campos, sem identificar o backend, versão, parser ou configuração interna do LLM. Não se infere um bug do gateway dessa documentação.

Uma replicação com novos casos e orçamento predefinido em ambos os braços seria necessária para estimar o contraste sob outro teto. Não se atualiza o acerto principal usando replays selecionados pelas falhas, nem se ajustam prompts ou produção com base neles.

Replays novos e selecionados pelas falhas antigas; nao substituem o experimento V3.

Logs originais nao capturaram finish_reason/usage quando nao houve texto; a causa historica individual nao e recuperavel.

Somente o limite de saida difere entre replays; mesmo modelo identificado nao garante pesos/infraestrutura remota identicos.

length identifica encerramento por limite reportado pelo servico; nao prova a causa interna do gateway.

Sem texto de raciocinio, corpos HTTP, credenciais ou precos estimados nos registros.

## Revisão humana dos gabaritos

O autor confirmou: “Revisei também os 88 gabaritos, sem correções”. A pergunta de esclarecimento explicitou território, classe, período, operação, denominador e valor. A declaração recebida em 21/10/2026 cobre todos os 88 casos quantitativos, identificados por hashes. Não foram alterados perguntas, gabaritos ou escores. Não foi informada a data efetiva da revisão, nem fornecidas fichas originais ou segunda revisão independente.

O recálculo automático adicional usou DuckDB apenas para ler Parquet verificado por hash e fórmulas Decimal em outro módulo, sem executor nem oráculo anterior. Foram conferidos 88 casos e 104 valores; aprovação integral: True. Tolerâncias são as originais e referem-se à representação, não à incerteza ambiental.

FICHAS_88_GABARITOS.md e fichas_88.json documentam folhas unidas, território, anos, suporte, operandos, fórmula, denominadores, referência e valor recalculado. Essas fichas foram geradas depois da declaração e não são apresentadas como anotações humanas anteriores.

## Dois experimentos, duas interpretações

| Aspecto | Original A/B/C | Complementar B_eq/C_eq |
| --- | --- | --- |
| Entrada | Pergunta e contexto | Pergunta, contexto e plano correto fornecido |
| Tarefa | Interpretação, validação, cálculo e resposta | Finalização com/sem cálculo disponível |
| Contrato | B plano/resultado; C proposta + executor/template | Mesmo JSON final gerado pelo mesmo LLM |
| Casos | 120 testes; famílias separadas do desenvolvimento | 88 quantitativos reutilizados; exploratório |
| 100% de C_eq | Não se aplica | Condicionado ao plano e orçamento; não pergunta inédita |
| Estimando | Diferença entre sistemas completos | Efeito operacional de disponibilizar cálculo ao finalizador |

O diagnóstico novo tem amostra selecionada por falhas e outro orçamento; não fornece uma terceira estimativa de acerto principal, não substitui casos, e não identifica qual parcela do contraste original é causada pelo executor.

## Suplemento preservado e limites

As tabelas originais de latência/tokens, bootstrap por famílias, proveniência do espelho, malha, legenda, código e uso de IA permanecem nos arquivos V3 copiados sem alterar valores. O material V4 destaca o controle no texto e move pormenores operacionais para este suplemento. Custos ausentes continuam null; reprodução remota não é determinismo garantido.

Persistem edição/licença/provedor da malha desconhecidos e revisão temática não autenticada. Não há validação de campo ou alegação de superioridade geral. Autoria/afiliações seguem pendentes e publicação dos artefatos depende de direitos.
