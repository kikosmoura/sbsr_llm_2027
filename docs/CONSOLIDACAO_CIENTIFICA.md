# Etapa 8 — consolidação reproduzível

Entrega local para revisão autoral. Há resultados reais da etapa 7, preservados; não houve novas chamadas ao banco, ao gateway ou aos rasters durante a consolidação. Não houve submissão, publicação de repositório ou deploy. Autoria/afiliações, revisão humana do benchmark e direitos indicados no inventário permanecem pendentes. Não apresentar o rascunho como artigo final aprovado.

## Ler e revisar

- [Relatório científico completo](../artifacts/scientific/etapa8/RELATORIO_CIENTIFICO.md): método, fontes, resultados e limitações.
- [Rascunho PDF](../artifacts/scientific/etapa8/manuscrito/rascunho_sbsr2027.pdf) e [ODT editável](../artifacts/scientific/etapa8/manuscrito/rascunho_sbsr2027.odt): três páginas no ODT oficial vinculado pela chamada, autoria como marcador explícito. O Markdown espelha o texto gerado.
- [Auditoria](../artifacts/scientific/etapa8/auditoria.json): linhagem geoespacial/semântica/modelo/prompts, cobertura, revisões desconhecidas e hashes.
- [Métricas recalculadas](../artifacts/scientific/etapa8/consolidado.json), [tabelas CSV](../artifacts/scientific/etapa8/tabelas/) e [figuras PNG/SVG/PDF](../artifacts/scientific/etapa8/figuras/).
- [Inventário de redistribuição](../artifacts/scientific/etapa8/publicacao/INVENTARIO.md): candidatos e condições, sem liberar automaticamente os artefatos.
- [Manifest](../artifacts/scientific/etapa8/manifest.json) e [validação tipográfica](../artifacts/scientific/etapa8/validacao_documento.json).

Os números do relatório e do manuscrito vêm do mesmo `consolidado.json`, refeito das saídas por caso. Não corrigir números manualmente no ODT ou nas figuras. Uma revisão da apresentação deve alterar `scripts/science/writing.py`/`plots.py` e regenerar. O benchmark, os escores congelados, os prompts e o executor não devem ser ajustados com este teste; uma avaliação nova exige protocolo e conjunto de teste novos.

## Reprodução local, sem modelos

Execute a partir da raiz de `sbsr_2027`, com o ambiente próprio e os dados locais das etapas anteriores. A instalação do pacote continua na versão 0.7.0, preservando os hashes de produção. `requirements-verified.txt`/`setup.cfg` descrevem o ambiente do núcleo. Não reutilizar o ambiente do experimento SAR.

```bash
.venv/bin/python -B scripts/consolidar_etapa8.py --help
.venv/bin/python -B scripts/obter_template_etapa8.py
.venv/bin/python -B scripts/consolidar_etapa8.py --env-file .env
.venv/bin/python -B -m pytest -q
```

O segundo comando verifica o cache do modelo oficial; somente se ausente faz um download público limitado a 1 MiB, com TLS e SHA-256 conferidos. Se os bytes oficiais mudarem, para e exige nova revisão das normas, sem substituir o modelo local. Ele não verifica automaticamente que o prazo e todas as regras continuam vigentes: reconsultar a chamada antes de uma submissão futura.

O consolidador não faz chamadas de inferência nem consulta fontes remotas. O argumento opcional `--env-file .env` lê valores privados apenas em memória para detectar sua presença indevida nos candidatos; não os exporta, mostra ou regrava. Sem esse argumento a busca por padrões continua, mas a busca por valores locais conhecidos fica registrada como não executada. Não compartilhar o `.env`.

Entradas necessárias: `benchmarks/pt_rn_v1`, `artifacts/evaluation/test_v1`, o diagnóstico separado `artifacts/evaluation/context_scale_v1`, dados/manifest da execução geoespacial auditada, snapshot/catalogue e recortes nativos com seus hashes. A falta ou divergência de uma entrada interrompe a geração; não há fallback para métricas simuladas. Ver `docs/AVALIACAO_CIENTIFICA.md` e `docs/PROCESSAMENTO_GEOESPACIAL.md` para reconstruir essas entradas. A revisão desconhecida do espelho impede garantir uma nova aquisição idêntica; os recortes preservados permitem repetir os cálculos sobre os bytes utilizados, observados seus direitos de redistribuição.

Para comparar uma regeneração sem substituir a entrega:

```bash
.venv/bin/python -B scripts/consolidar_etapa8.py \
  --output artifacts/scientific/reproducao_local --env-file .env
```

O script usa as fontes em `artifacts/scientific/fontes_sbsr2027` e grava somente sua saída selecionada. Mantém estáticos os derivados e o congelamento, recalcula os escores e ICs e compara com os resultados anteriores. O inventário seleciona a execução auditada, não todos os históricos de processamento. Não rodar dois consolidadores para o mesmo diretório de saída simultaneamente.

## Ambiente de figuras e renderização

O processo principal usa Python 3.10.12, NumPy 2.2.6, DuckDB 1.4.1, Pydantic 2.12.5 e Requests 2.32.5 verificados no ambiente existente. A plotagem/documento usa outro processo: `/usr/bin/python3 -s`, Python 3.10.12, NumPy 1.21.5, Matplotlib 3.5.1, Pillow 9.0.1 e lxml 4.8.0. Esse isolamento evita a incompatibilidade do Matplotlib disponível com NumPy 2; não altera o ambiente numérico congelado. Nenhum pacote foi instalado nesta etapa.

As versões auxiliares estão em `scripts/requirements-science-verified.txt`. Em outra máquina, um ambiente de figuras separado pode ser criado e passado explicitamente:

```bash
python3.10 -m venv .venv-figuras
.venv-figuras/bin/python -m pip install -r scripts/requirements-science-verified.txt
.venv/bin/python -B scripts/consolidar_etapa8.py \
  --plot-python .venv-figuras/bin/python --env-file .env
```

Essa instalação é uma instrução de reprodução, não uma execução realizada neste ambiente. Requer disponibilidade das versões para a plataforma. O processo de figuras grava sua configuração temporária fora dos artefatos. A tipografia foi conferida com Times New Roman, LibreOffice 25.2.6.2 e Poppler 22.02.0 (`pdfinfo`, `pdftotext`, `pdffonts`). Esses binários/fontes são dependências externas; não se redistribuem fontes proprietárias. O renderizador usa um perfil temporário exclusivo e encerra somente seu próprio grupo de processos após verificar o PDF completo, sem interferir em sessões do usuário.

Se não houver renderizador disponível:

```bash
.venv/bin/python -B scripts/consolidar_etapa8.py \
  --output artifacts/scientific/sem_pdf --no-pdf --env-file .env
```

Nesse modo as figuras e ODT continuam disponíveis e a validação de PDF/páginas fica **pendente**, não aprovada. Os resultados numéricos e os hashes de fontes são reproduzíveis; datas dos manifests e de criação do PDF podem variar. O manifest identifica os bytes de cada geração, sem prometer identidade binária do PDF entre instalações. Alterar fontes, renderizador ou nomes/afiliações pode mudar a paginação; conferir novamente após revisão autoral.

## Normas e revisão autoral

Fontes oficiais e hashes estão em `configs/science/normas_verificadas.json`. A consulta de 19/10/2026 confirmou prazo de 30/10/2026, máximo de quatro páginas incluindo figuras/tabelas/fórmulas/referências, PDF sem numeração, resumos de 100–150 palavras e abstract em inglês para artigo em português. O arquivo tem resumos de 137/132 palavras e três páginas, com texto em Times New Roman. A conferência visual de legibilidade foi feita por IA, sem equivaler à revisão humana.

A chamada aponta para um ODT hospedado no domínio do SBSR 2023. Foi utilizado por ser o link da chamada vigente. Há divergência entre Letter do ODT e A4 do LaTeX também vinculado; preservou-se a geometria do ODT. O eixo recomendado é **Geoinformática / Inteligência artificial**, presente na página oficial de eixos; não se inferiu um número de subárea ausente do formulário consultado. Antes da submissão, o autor deve conferir novamente o template/formulário e resolver essa diferença de formato se necessário.

Nenhuma cláusula específica de IA generativa foi identificada na chamada, ODT e página de eixos consultados. Isso não afirma inexistência de outra política institucional ou de regra posterior. Há regra geral de integridade/autoria; o relatório e o rascunho propõem declaração transparente sobre auxílio de IA sem atribuí-la a uma exigência não encontrada. Inserir somente autores com contribuição real, após revisão e consentimento. Bibliografia em `configs/science/bibliografia_verificada.json`, verificada em fontes primárias quanto a metadados/resumos, não uma revisão sistemática nem validação temática da Coleção 11.

## Publicação e limites científicos

O inventário distingue varredura de privacidade de permissão de redistribuição. MapBiomas declara CC BY 4.0 com atribuição; licença/edição da malha de origem interna, licença do código/benchmark e condições institucionais de divulgação das saídas continuam não comprovadas. Estatísticas/snapshot têm bloqueio de redistribuição registrado pela falta de licença da malha. O ODT original e HTMLs das fontes são cache local para revisão, não parte de um pacote proposto como liberado.

Não foi criado repositório público, licença presumida, arquivo de submissão enviado ou deploy. Há separação entre observações reais, testes sintéticos/mocks e pendências. O IC é do acerto de consultas e mantém dependência por famílias; não é IC de área ambiental. O benchmark verifica respostas sobre dados de referência, não a verdade de campo dos mapas. O relatório discute recorte RN/2015–2025, templates, dependência territorial, cobertura incompleta para ranking, erros técnicos de B, unidade/denominadores, método de bordas, malha fixa, edição desconhecida, revisão do espelho, revisão dos pesos não observada e validade externa limitada.
