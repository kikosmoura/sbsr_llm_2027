# Configuração para publicação

O projeto usa nomes genéricos para a integração com o gateway: a classe
`GatewayClient` e as variáveis `LLM_*`. Os valores de conexão devem ser fornecidos
pelo ambiente ou por um arquivo `.env` local lido explicitamente com `--env-file`.
O arquivo `.env.example` contém somente placeholders.

Em `configs/project.json`, substitua `https://storage.example.invalid/BUCKET_NAME`
pelo endereço do armazenamento que você utilizará. URLs com domínio `.invalid`,
`BUCKET_NAME`, `PROJECT_ID`, `MODEL_ID` e valores terminados em `_PLACEHOLDER`
são exemplos a preencher. Os endereços de autenticação, identificador de cliente,
segredo de cliente, modelo e credenciais do banco ficam no `.env` local.

As referências bibliográficas públicas foram mantidas. Identificadores de classes
ambientais, códigos IBGE e hashes de dados continuam presentes, pois fazem parte
dos contratos e da rastreabilidade dos cálculos.

As substituições também alcançam relatórios, configurações e rascunhos em texto.
Essas cópias foram sanitizadas e seus hashes podem diferir dos registros históricos
de congelamento. Os registros históricos não foram recalculados para apresentar
as cópias editadas como originais. Para uma nova execução, gere novos artefatos e
congelamentos com sua configuração. O manifesto da fonte HTML empacotada e o
catálogo semântico identificam a cópia sanitizada distribuída com o código.

O `.gitignore` exclui credenciais, tokens de sessão, caches, bytecode, pacotes
antigos, bancos locais e saídas operacionais. Os documentos PDF e ODT foram
preservados e podem conter as informações originais; revise a seleção desses
documentos antes de incluí-los em um repositório público.
