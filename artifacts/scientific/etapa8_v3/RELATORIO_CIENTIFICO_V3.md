# Revisão científica V3 — rascunho para revisão autoral



V1/V2 e todos os resultados originais foram preservados. Esta revisão registra a declaração humana recebida, acrescenta literatura primária e um experimento real complementar. Não houve submissão, publicação ou deploy.



## Revisão humana: o que foi efetivamente declarado



O usuário/autor declarou revisar manualmente as 120 perguntas de teste sem correções, em declaração recebida em 2026-10-21. O arquivo REVISAO_HUMANA_DECLARADA.json liga a declaração a hashes dos casos originais. O momento exato da revisão não foi informado. A declaração não confirma revisão dos gabaritos, anotador independente, cegamento ou concordância. Não foram fabricadas fichas de avaliação humana. As perguntas e os escores antigos não mudaram.



## Literatura primária e posicionamento



| Estudo primário | Relação com o projeto | Distinção de escopo |
| --- | --- | --- |
| GeoGPT | Interface em linguagem natural para coleta/análise SIG por ferramentas | Nossa avaliação restringe operações e rastreia números em derivados fixos. |
| FloodSQL-Bench | Text-to-SQL geoespacial, junções e protocolo de similaridade sem execução | Aqui se pontuam respostas numéricas executadas, sem SQL livre; não se comparam as taxas entre benchmarks. |
| Toolformer | Aprendizagem auto-supervisionada de chamadas de APIs | Não treinamos modelo; fornecemos resultado de função determinística em controle de inferência. |
| ReAct | Intercala raciocínio e ações com observações externas | O controle fixa o plano e não avalia seleção autônoma de ferramentas nem armazena raciocínio interno. |



Metadados, versões, autores, DOI arXiv e hashes de páginas primárias estão em bibliografia_v3.json. Foram conferidos resumo e trechos de método, sem alegar revisão sistemática. Referências a ferramentas e SIG contextualizam antecedentes; não são resultados de uma comparação empírica com o nosso sistema.



## Experimento com contrato equivalente



Protocolo congelado antes das novas chamadas; desenvolvimento em 16 registros reais e avaliação em 176 registros principais (88 pares), mais 8 repetições predefinidas. Dataset reutilizado, não teste externo novo. Planos de referência, tabelas, documentação, prompt de sistema, esquema, LLM e parâmetros são iguais. A única chave de contexto que difere é execution_observations: vazia em B_eq e com a resposta real do executor em C_eq. Ambas geram e validam JSON pelo LLM; C_eq não publica diretamente o template do servidor neste controle.



O tratamento é a disponibilidade do cálculo verificado para um finalizador, condicionado ao plano fornecido. O experimento controla a assimetria do contrato original e exclui interpretação da pergunta como variável. As observações adicionais de C_eq são a intervenção pretendida; comprimentos/tokens de entrada não são idênticos. O resultado inclui copiar valores, conformidade da saída e eventuais falhas de gateway, não habilidade aritmética cognitiva isolada. A ordem é aleatória por caso, sessões independentes, três workers, um reparo máximo e nenhuma referência numérica enviada a B_eq ou ao reparo.



| Condição | Corretos/total | Taxa | Falhas técnicas | Precisão emitida | Média online s | Tokens observados | Tentativas sem usage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B_eq | 61/88 | 69,32% | 27 | 100,00% | 13,08 | 415447 | 26 |
| C_eq | 88/88 | 100,00% | 0 | 100,00% | 5,65 | 549263 | 0 |



C_eq−B_eq = 30,68 pp, IC95% [7,14; 63,24], 8 famílias, 10000 réplicas, seed 20271021. O fornecimento do resultado do executor aumentou o acerto sob o plano fixado e este orçamento. O número pequeno de famílias e o compartilhamento de territórios/dados limitam a precisão e a generalização. Erros técnicos permanecem no denominador principal.



A precisão entre respostas emitidas foi integral em ambas neste experimento. A diferença observada é composta por falhas de emissão/contrato em B_eq, não por erros numéricos nas respostas aceitas. Não se identificou a causa remota de texto final ausente, nem se inferiu exaustão de tokens a partir de ausência de texto. Contrato igual controla a assimetria anterior, mas não transforma confiabilidade operacional em prova de capacidade aritmética intrínseca.



| Condição | Diagnóstico | Casos |
| --- | --- | --- |
| B_eq | acerto | 61 |
| B_eq | contrato_invalido | 1 |
| B_eq | texto_final_ausente | 26 |
| C_eq | acerto | 88 |



| Condição | Família | Acertos | Casos |
| --- | --- | --- | --- |
| B_eq | teste_area_direta | 20 | 20 |
| B_eq | teste_delta | 16 | 16 |
| B_eq | teste_participacao | 0 | 8 |
| B_eq | teste_pontos | 0 | 8 |
| B_eq | teste_serie | 8 | 8 |
| B_eq | teste_t06 | 4 | 4 |
| B_eq | teste_territorial | 8 | 8 |
| B_eq | teste_variacao | 5 | 16 |
| C_eq | teste_area_direta | 20 | 20 |
| C_eq | teste_delta | 16 | 16 |
| C_eq | teste_participacao | 8 | 8 |
| C_eq | teste_pontos | 8 | 8 |
| C_eq | teste_serie | 8 | 8 |
| C_eq | teste_t06 | 4 | 4 |
| C_eq | teste_territorial | 8 | 8 |
| C_eq | teste_variacao | 16 | 16 |



Repetibilidade: 8/8 respostas estruturadas iguais; 8/8 escores iguais. Não se escolheu a melhor resposta nem se incluíram repetições no acerto principal. Preço ausente permanece null, contadores sem usage não são estimados.



## Comparação original preservada



| Condição | Acertos | Casos | Taxa | Técnicos |
| --- | --- | --- | --- | --- |
| A | 21 | 120 | 17,50% | 0 |
| B | 49 | 120 | 40,83% | 62 |
| C | 104 | 120 | 86,67% | 7 |



Diferença original C−B 45,83 pp com contratos distintos. O controle novo tem outra tarefa (plano fixo) e outro momento de execução; não se subtraem taxas entre experimentos para atribuir uma parcela causal do ganho antigo. A sensibilidade V2 e seus limites permanecem em sensibilidade.json.



## Fontes, área e exemplo real



| Ano | Arquivo original | Geração GCS conferida | Intervalos iguais | Intervalos registrados | SHA-256 do recorte |
| --- | --- | --- | --- | --- | --- |
| 2015 | brazil_coverage-col11_2015.tif | 1787144389260083 | 185 | 185 | 99c7a24c07d0b6cf29969ea2385592b9f3e0845b667b1877c7e163e3fd17739a |
| 2025 | brazil_coverage-col11_2025.tif | 1787089134874800 | 204 | 204 | 8b848eb7e2592f26160835b9b256987e985fd39d1dbb2681aa722b9aa8e355b7 |



Aquisição histórica por janela: `2026-10-19T16:27:57.264890+00:00`; estratégia `staging_regional_range_uma_abertura_por_ano`; sem reamostragem ou overviews. Manifest `artifacts/staging/33d91b08a0bec1900a406d91e81d6cc9e0eccca058471253198e3249d70a7c1d/manifest.json` SHA-256 `c38bda88c67d6a07021536e7a4ffe4549bab897c08de18f001047c40bd213815`. URLs do espelho, tamanhos, ETags, Last-Modified, offsets, comprimentos e hashes dos intervalos estão em `proveniencia.json`. ETag não é SHA-256. Os recortes nativos não são os arquivos nacionais originais.



Verificação pública: `verificado_intervalos_utilizados` em `2026-10-20T13:55:05.087918+00:00`. A página oficial, seu hash e o asset GEE divulgado foram registrados. As gerações GCS fixam os objetos remotos usados na conferência; não são rótulos de revisão temática. O MD5/CRC32C reportado pelo GCS é metadado do objeto oficial e não foi calculado sobre o raster nacional do espelho. A igualdade dos intervalos utilizados não implica igualdade integral nacional, acurácia temática ou vínculo automático ao asset GEE coverage_v3.



Snapshot `data/mesh_RN_v1.json` obtido em `2026-10-19T16:20:39.783206+00:00`, `EPSG:4326`, 168 entidades. Fonte comprovada: tabelas internas `sbsr.municipios, sbsr.uf`, acesso somente leitura. Hash lógico `3207282d98e5fc1d01d48008dbe5264150728a4c62d3ba41e0ead57a48444bd0`; hash do arquivo `42850b2d17fbfe9279f09e25417ec94a679b3d4080705a18374feaeceaf98b11`. Provedor e arquivo originais, edição, data de publicação e licença não identificados. A data de extração não é data da malha. Não atribuir origem IBGE apenas pelos códigos.



Nova busca de comentários de catálogo: `indisponivel`; motivo `configuracao_ausente`. Se a configuração estiver ausente, nenhuma conexão foi realizada. O diagnóstico anterior e o snapshot local foram preservados.



Não houve substituição de raster, malha ou estatística para aproveitar uma proveniência mais clara. Uma nova malha/revisão exige execução própria e reavaliação. Snapshot/estatísticas continuam sem liberação de redistribuição pela licença da malha não comprovada.



Método ellipsoid-linear-lonlat-fractional-v1; mesma malha para 2015/2025, máscaras comparáveis e conservação numérica. Incógnitas de malha/licença/revisão temática não foram preenchidas por inferência. Estatísticas/Parquets auditados permanecem os mesmos.



Em 2015, quantos hectares de Formação Florestal foram mapeados no município de Acari/RN?



```json

{
  "operation": "area",
  "metric": "area",
  "unit": "ha",
  "territory_codes": [
    "2400109"
  ],
  "scope_uf": null,
  "class_codes": [
    3
  ],
  "years": [
    2015
  ],
  "denominator": null,
  "direction": "desc",
  "limit": null
}

```



Acari/RN (IBGE 2400109): área mapeada de Formação Florestal [3], em 2015: 14,69 ha.
Coleção 11; revisão desconhecida; malha edição desconhecida; método ellipsoid-linear-lonlat-fractional-v1; execução a98ccf54c8c82ceeb601ce126cdb379add4de253912a46267601cdc7d9a29802.
Mudança observada na classificação não comprova mudança real específica no terreno, causas ou ilegalidade.



## Limitações, direitos e uso de IA



Planos corretos fornecidos: nao avalia interpretacao nem ambiguidades.

Resultado estima efeito do fornecimento de calculo ao finalizador, incluindo conformidade de saida; nao habilidade cognitiva isolada.

Questões reutilizadas e protocolo complementar definido depois do teste original; nao avaliacao externa independente.

Familias compartilham territorios, classes e dados; bootstrap com poucos grupos.

Pesos/modelo/infraestrutura remota nao versionados de forma observavel; ordem aleatoria reduz mas nao elimina efeitos temporais.

Revisao humana declarada cobre perguntas; gabaritos nao tiveram validacao humana confirmada.



A revisão humana das perguntas melhora a documentação sem equivaler a validar números de referência, mapas ou campo. Novidade é a avaliação delimitada de uma arquitetura e seu controle, não a primeira combinação de LLM e GIS. Dados nacionais, novas perguntas e validação humana dos gabaritos continuam necessários. Licenças da malha/código/benchmark e política institucional de publicação das saídas permanecem pendentes. IA não foi adicionada à autoria.



## Referências usadas no manuscrito



[1] C. M. Souza Jr. et al. Reconstructing Three Decades of Land Use and Land Cover Changes in Brazilian Biomes with Landsat Archive and Earth Engine. Remote Sensing 12(17), 2735, 2020. DOI: 10.3390/rs12172735.

[2] W. Chen, X. Ma, X. Wang e W. W. Cohen. Program of Thoughts Prompting: Disentangling Computation from Reasoning for Numerical Reasoning Tasks. arXiv:2211.12588v4, 2023. DOI: 10.48550/arXiv.2211.12588.

[3] Y. Zhang et al. GeoGPT: Understanding and Processing Geospatial Tasks through An Autonomous GPT. arXiv:2307.07930v1, 2023. DOI: 10.48550/arXiv.2307.07930.

[4] H. Liu et al. FloodSQL-Bench: A Retrieval-Augmented Benchmark for Geospatially-Grounded Text-to-SQL. arXiv:2512.12084v2, 2026. DOI: 10.48550/arXiv.2512.12084.

[5] T. Schick et al. Toolformer: Language Models Can Teach Themselves to Use Tools. arXiv:2302.04761v1, 2023. DOI: 10.48550/arXiv.2302.04761.

[6] S. Yao et al. ReAct: Synergizing Reasoning and Acting in Language Models. arXiv:2210.03629v3, 2023. DOI: 10.48550/arXiv.2210.03629.

[7] Projeto MapBiomas. Coleção 11 da Série Anual de Mapas de Cobertura e Uso da Terra do Brasil: códigos de legenda. Documento de legenda oficial, 2026. Disponível em brasil.mapbiomas.org; acesso em 19 out. 2026.

[8] Projeto MapBiomas. Cobertura 30m: acesso aos dados da Coleção 11. Disponível em https://brasil.mapbiomas.org/iniciativas-e-produtos/cobertura-e-uso-da-terra/cobertura-30m/cobertura/; acesso em 20 out. 2026.

[9] C. F. F. Karney. Algorithms for geodesics. Journal of Geodesy 87(1), 43–55, 2013. DOI: 10.1007/s00190-012-0578-z.

[10] C. A. Field e A. H. Welsh. Bootstrapping clustered data. Journal of the Royal Statistical Society: Series B 69(3), 369–390, 2007. DOI: 10.1111/j.1467-9868.2007.00593.x.
