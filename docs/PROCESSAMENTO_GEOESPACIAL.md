# Etapa 3 — processamento geoespacial reproduzível

O processamento usa somente SELECTs parametrizados na origem; os demais passos são locais. Não consulta o LLM. A malha do snapshot é a mesma nos dois anos. Edição territorial e revisão oficial do espelho permanecem desconhecidas enquanto não houver evidência documental. Os resultados desta etapa não foram comparados às estatísticas oficiais.

## Execução

Python 3.10.12. Instalar o wheel com os extras `processing,test` no `.venv` próprio. Dependências diretamente verificadas: NumPy 2.2.6, Rasterio 1.4.3, Shapely 2.1.2, pyproj 3.3.0, DuckDB 1.4.1, psutil 7.0.0 e psycopg2-binary 2.9.11. O ambiente atual herda pacotes de sistema; não é isolamento integral. Não se utiliza o venv SAR. PyArrow/Pandas do ambiente apresentaram incompatibilidade com NumPy 2; a escrita Parquet usa o próprio DuckDB e dispensa ambos.

```bash
.venv/bin/consultas-ambientais --config configs/project.json process --help
# Exportar SOURCE_PG_* localmente; nenhum .env é lido automaticamente.
.venv/bin/consultas-ambientais --config configs/project.json process snapshot --output data/mesh_RN_v1.json
.venv/bin/consultas-ambientais --config configs/project.json process pilot --snapshot data/mesh_RN_v1.json --codes 2408102 2410900
.venv/bin/consultas-ambientais --config configs/project.json process full --snapshot data/mesh_RN_v1.json
.venv/bin/python -m pytest -q
```

`pilot` aceita de um a cinco códigos municipais explícitos da UF configurada. `full` exige gate aprovado desse piloto, mesma configuração, código, versões, malha, fontes e catálogo. A extrapolação conservadora por área do retângulo regional precisa caber nos limites de tempo e bytes antes de iniciar a UF. Nenhum comando expande nacionalmente. A UF pode ser alterada em configuração pública, exigindo novo snapshot/gate. O nome padrão do arquivo do snapshot é apenas um exemplo: informar `--output` para outra UF.

Para auditar valores locais sem inferir capacidade de responder perguntas:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import duckdb
p=Path('data/processed/areas.duckdb')
c=duckdb.connect(str(p),read_only=True)
print(c.execute('SELECT run_id, count(*) AS linhas FROM areas GROUP BY run_id').fetchall())
c.close()
PY
```

Selecionar sempre uma execução completa pelo manifest antes de consultar tabelas; o DuckDB conserva execuções anteriores. Não agregar linhas de execuções distintas. O motor de perguntas da etapa 4 ainda não existe e `engine_ready` continua falso.

## Método de área

Identificador: `ellipsoid-linear-lonlat-fractional-v1`. O método implementado e validado aceita EPSG:4326, grade sem rotação, eixo X crescente e Y decrescente, resolução até 0,01 grau. Outros CRS/grades são recusados explicitamente; não há reprojeção automática. As arestas da geometria original são segmentos lineares em longitude/latitude. Não há simplificação, redução de resolução ou uso de overviews para estatística.

O Shapely/GEOS calcula as interseções fracionárias entre a geometria e cada pixel de borda. O interior é identificado por rasterização do centro e as células tocadas pela borda são substituídas por suas interseções. Buracos e componentes múltiplos são preservados. A integração física usa o elipsoide WGS84 extraído do CRS, sem assumir área constante de 900 m². Não é um cálculo esférico nem a área cartesiana em graus.

Para latitude φ em radianos, longitude λ, semieixo maior a e excentricidade e:

```
dS = a² (1−e²) cos(φ) / (1−e² sen²(φ))² dφ dλ
Q(φ) = a²(1−e²)/2 × [sen(φ)/(1−e² sen²(φ)) + atanh(e sen(φ))/e]
S(pixel completo) = Δλ × [Q(φ_norte)−Q(φ_sul)]
S(polígono CCW) = −∮ Q(φ) dλ
```

A integral por segmento usa quadratura Gauss-Legendre de quatro pontos, com constante de referência por anel para reduzir cancelamento numérico; buracos têm orientação oposta. Para pixels de borda, a fração física é `S(interseção)/S(pixel)`, integrada diretamente, sem aproximá-la pela fração em graus quadrados. Cada classe recebe a soma de suas interseções físicas. A integral segue a geometria linear no CRS nativo; não troca arestas longas por geodésicas sem documentar essa diferença.

Tolerâncias fixadas no contrato antes da validação real: conservação `0,01 m² + 10⁻⁹ × área territorial`; referência independente `0,05 m² + 10⁻⁶ × área de referência`. A primeira controla aritmética float64 e interseções GEOS em somas de janelas. A segunda admite o erro da aproximação independente de paralelos/segmentos lonlat por geodésicas muito curtas. Não expressam acurácia temática ou posicional do MapBiomas/malha. Não são parâmetros livres da CLI.

A referência independente usa `pyproj.Geod`/PROJ por interseção de pixel, com segmentos densificados até 1/8 de pixel e orientação explícita de anéis; compara totais e todas as classes anuais e comuns numa janela real de borda de 24 × 24 pixels. Testes sintéticos cobrem bordas oblíquas, buracos, duas latitudes e equador, partição em janelas, NoData, classe ausente, códigos desconhecidos e falta de suporte. Referência técnica: [Geod/pyproj](https://pyproj4.github.io/pyproj/stable/api/geod.html), [Shapely/GEOS](https://shapely.readthedocs.io/en/2.1.2/manual.html).

## Máscaras e denominadores

Cada pixel é separado em: máscara inválida/NoData declarado; código conhecido de classe folha; código desconhecido ou grupo hierárquico indevidamente observado. Código zero não vira NoData por convenção. A qualidade registra os códigos desconhecidos e suas áreas; grupos não são somados a filhos. As 33 folhas da legenda são materializadas, preservando a resolução e os códigos nativos.

Para cada território, ano e classe: área anual no suporte reconhecido desse ano. Para o par, ambas as distribuições são calculadas onde **as duas máscaras são válidas e ambos os códigos são folhas reconhecidas**. O identificador comum inclui execução, território, anos e hash da máscara espacial. Diferenças temporais devem consumir exclusivamente as linhas `support=comum` da mesma execução/identificador. Participação usa a área observada do suporte correspondente, não a área nominal `area_km2` da tabela.

A qualidade anual particiona a área dentro do raster em observada, NoData e desconhecida. A qualidade comum usa NoData em qualquer ano com precedência, desconhecido em qualquer ano restante e o suporte comum reconhecido. O diagnóstico de códigos por par informa a união espacial por código; diferentes códigos desconhecidos entre os anos podem compartilhar o mesmo pixel e não devem ter seus diagnósticos somados. A parte fora da extensão do raster é registrada separadamente. Classe ausente em suporte observado recebe zero real; suporte vazio recebe `null` e `sem_suporte_valido`. Unidade que não terminou não tem partição concluída.

`processing_status=completo` significa que o cálculo terminou; `quality_status=parcial` indica lacunas/códigos desconhecidos. A elegibilidade conservadora exige suporte não vazio e ausência de lacunas acima da tolerância numérica. Ranking só se torna elegível com todos os municípios do universo do snapshot materializados e qualidade elegível nos suportes exigidos. Esta etapa registra o gate; não gera ranking. Estatística direta da UF usa `uf_direta`; áreas municipais usam `municipio_direto`. A soma municipal não é apresentada como área direta estadual, pois sobreposições, lacunas e diferenças de contorno podem existir na malha.

## Snapshot, I/O e retomada

O snapshot registra códigos textuais, nomes originais, SRID, edição, hashes EWKB de origem e WKB derivado, e diagnóstico de geometria. A transação é `REPEATABLE READ`, somente leitura, com timeout de conexão/statement/lock; rollback é obrigatório. Não executa comandos de criação ou correção na origem. A geometria precisa ser poligonal e SRID conhecido. Se inválida, `make_valid` opera somente na cópia; a área original territorial é indefinida, o reparo fica pendente e bloqueia o processamento até revisão. Não se aceita reparo automaticamente comparando uma área algébrica inválida a uma área territorial válida. O snapshot guarda o diagnóstico e área derivada, sem alegar equivalência.

O staging abre cada raster nacional remoto uma vez por execução, verifica grade e identidade HTTP e recorta a extensão regional inteira em blocos/janelas nativos. Novas tentativas reabrem para confirmar identidade e reaproveitam o cache. As consultas municipais compartilham os dois rasters regionais locais abertos. As requisições exigem 206, Content-Range coerente, tamanho/ETag estáveis e TLS verificado. Respostas integrais 200 são recusadas sem consumir o corpo. Cabeçalhos não comprovam revisão oficial e ETag não é SHA-256.

O cache persistente contém blocos de bytes com hashes, associado a URL pública e identidade HTTP; memória mantém somente oito blocos. Dados locais GeoTIFF têm máscara interna, sem reprojeção. SHA-256 do recorte e dos chunks utilizados identifica os bytes efetivamente lidos; não se afirma hash integral do raster nacional. Os limites públicos incluem download agregado, requisições, cache em disco, tamanho do recorte, janelas, cache GDAL, RSS e tempo. Tempo/RSS são verificados entre janelas e requisições, não constituem isolamento de processo pelo kernel; o máximo observado é amostrado. Os timeouts também limitam bloqueios de rede.

Cada unidade grava `areas.parquet`, `quality.parquet` e manifest com hashes. A atualização do índice DuckDB é transacional; manifests e arquivos são substituídos atomicamente. A chave depende de malha, código, fontes, recortes, catálogo, método, configurações e versões efetivamente usadas. Retomada verifica hashes e reconstrói o índice a partir de Parquet, sem duplicar linhas. Interrupções no staging podem repetir a escrita do recorte usando os ranges já cacheados; TIFF temporário nunca é aceito como completo. Um lock impede dois processadores no mesmo projeto.

## Artefatos e publicação

`data/mesh_RN_v1.json`, `data/processed/areas.duckdb`, `data/processed/<run>/<código>/*.parquet`, `data/capabilities_stage3.json`, `cache/ranges/`, `artifacts/staging/` e `artifacts/processing/` ficam fora do Git. Os manifests contêm linhagem, recursos, hashes, data, status e qualidade. Preservam ausência de revisão/edição em vez de inventar valores. Um relatório público resumido e sem conexão/segredos é mantido em `docs/VALIDACAO_ETAPA3.json`; publicar dados ou manifests detalhados requer seleção/revisão explícita.

O LLM não participa do cálculo. Não se calculam perda bruta, desmatamento, causas ou eventos de inundação a partir destas diferenças líquidas. Próxima etapa: consultas determinísticas parametrizadas sobre os Parquets/DuckDB, respeitando execução, suporte e qualidade.

No ambiente desta máquina, pyproj 3.3.0 herdado do sistema inicialmente não localizou o diretório de dados dentro do venv. A instalação foi corrigida com referência local `.venv/share/proj` para `/usr/share/proj` já instalado. Em outro ambiente, instalar o extra fixado e conferir `pyproj.datadir.get_data_dir()`/`proj.db`; fornecer `PROJ_LIB` para o diretório real quando necessário. Não apontar para uma base de versão incompatível. O relatório registra o hash da base efetivamente localizada.
