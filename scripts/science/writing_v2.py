"""Revisao dos textos a partir de diagnosticos, proveniencia e um registro real."""
from copy import deepcopy
import json,re
from .writing import paper,long_report,pt,pct,pp,table


def interval(estimate):
    if estimate.get('state')!='verificado':return 'IC pendente'
    return f"{pp(estimate['difference_C_minus_B'])} [{pp(estimate['ci95'][0])}; {pp(estimate['ci95'][1])}]"


def renumber_references(draft,web_url):
    """Executar antes de inserir JSON/exemplo: [3] de classe nao e uma citacao."""
    refs={re.match(r'\[(\d+)\] ',b['text']).group(1):re.sub(r'^\[\d+\] ','',b['text'])
          for b in draft['blocks'] if b['kind']=='reference'}
    refs['WEB']=f'Projeto MapBiomas. Cobertura 30m: acesso aos dados da Coleção 11. Disponível em {web_url}; acesso em 20 out. 2026.'
    mapping={}
    def replace(match):
        key=match.group(1)
        if key not in mapping:mapping[key]=len(mapping)+1
        return '['+str(mapping[key])+']'
    blocks=[]
    for b in draft['blocks']:
        if b['kind']=='reference':continue
        if b['kind']=='paragraph':b['text']=re.sub(r'\[(\d+|WEB)\]',replace,b['text'])
        blocks.append(b)
    for key,n in mapping.items():blocks.append({'kind':'reference','text':f'[{n}] '+refs[key]})
    draft['blocks']=blocks


def revised_paper(a,m,rules,refs,metadata,s,provenance,example):
    draft=paper(a,m,rules,refs,metadata);draft['draft_notice']='RASCUNHO V2 PARA REVISÃO AUTORAL — NÃO SUBMETIDO'
    main=m['paired_C_minus_B'];common=s['paired_analyses'][0];numeric=s['paired_analyses'][1]
    rates={r['condition']:r for r in s['condition_specific_rates']}
    diag={(r['condition'],r['diagnosis']):r['count'] for r in s['diagnostic_counts']}
    public=provenance['public_verification'];total_chunks=sum(len(f['source_chunks']) for f in provenance['raster_files'])
    matched=sum((f['official_verification'] or {}).get('matched_chunks',0) for f in provenance['raster_files'])
    mesh=provenance['territorial_snapshot']
    draft['abstract_pt']=(f'Avalia-se uma arquitetura de consultas ambientais em português que interpreta planos JSON e calcula respostas verificáveis sobre o MapBiomas Coleção {a["collection"]}. O recorte inclui municípios do Rio Grande do Norte e os anos 2015 e 2025, com malha fixa e área elipsoidal fracionária. O benchmark separa {metadata["dev_cases"]} casos de desenvolvimento e {m["primary_cases"]} de teste. Comparam-se documentação, documentação com tabelas e plano com executor. O contraste principal executor−tabelas foi {pp(main["difference_C_minus_B"])} pontos percentuais, IC95% [{pp(main["ci95"][0])}; {pp(main["ci95"][1])}]. Em análise exploratória dos {common["cases"]} casos sem falha técnica em ambas, a diferença foi {pp(common["paired"]["difference_C_minus_B"])} pontos, IC95% [{pp(common["paired"]["ci95"][0])}; {pp(common["paired"]["ci95"][1])}]. O contraste principal mede o sistema completo sob contratos distintos, sem isolar raciocínio ou cálculo. A proveniência foi reforçada comparando intervalos usados com fontes oficiais; edição e licença da malha permanecem desconhecidas. O benchmark valida respostas sobre referências derivadas, sem verdade de campo ou revisão humana.')
    draft['abstract_en']=(f'We evaluate a Portuguese environmental query architecture that interprets JSON plans and computes verifiable answers from MapBiomas Collection {a["collection"]}. The scope comprises municipalities in Rio Grande do Norte, Brazil, and years 2015 and 2025, using fixed boundaries and fractional ellipsoidal areas. The benchmark separates {metadata["dev_cases"]} development and {m["primary_cases"]} test questions. Conditions use documentation, documentation with tables, and plans with an executor. The primary executor-minus-tables difference was {100*main["difference_C_minus_B"]:.2f} percentage points, 95% CI [{100*main["ci95"][0]:.2f}; {100*main["ci95"][1]:.2f}]. Exploratory analysis of {common["cases"]} cases without technical failure in either condition yielded {100*common["paired"]["difference_C_minus_B"]:.2f} points, 95% CI [{100*common["paired"]["ci95"][0]:.2f}; {100*common["paired"]["ci95"][1]:.2f}]. The primary contrast measures complete systems under different contracts, without isolating reasoning or arithmetic. Used byte ranges were checked against official sources; boundary edition and license remain unknown. Evaluation concerns derived references, without field validation or human benchmark review.')
    new=[]
    for block in draft['blocks']:
        b=deepcopy(block);text=b.get('text','')
        if text.startswith('Foram usados rasters'):
            b['text']=(f'Utilizaram-se brazil_coverage-col11_2015.tif e brazil_coverage-col11_2025.tif de um espelho, com legenda oficial PDF/CSV [3]. A aquisição regional por HTTP Range ocorreu em {provenance["staging"]["acquired_at"][:10]}; recortes nativos, intervalos, URLs, gerações e hashes constam do dossiê suplementar. O snapshot fixo das tabelas internas sbsr.municipios e sbsr.uf foi extraído em {mesh["acquired_at"][:10]}, com {a["territories"]} entidades, {a["crs"]} e hash lógico {mesh["mesh_sha256"][:16]}… (completo no dossiê). Data de extração não identifica edição territorial: provedor, arquivo original, data de publicação e licença da malha não foram comprovados.')
            new.append(b)
            if public.get('state')=='verificado_intervalos_utilizados':
                new.append({'kind':'paragraph','text':f'Em 20/10/2026, a página oficial [WEB] confirmou os endereços GCS; {matched}/{total_chunks} intervalos usados coincidiram byte a byte com os objetos oficiais, fixados por geração. Isso autentica a correspondência dos intervalos conferidos, sem verificar igualdade integral nacional ou revisão temática. O asset GEE divulgado termina em coverage_v3; não se transferiu esse rótulo aos GeoTIFFs sem vínculo explícito. ETag/MD5 reportados não foram tratados como SHA-256 nacional.'})
            else:new.append({'kind':'paragraph','text':'A correspondência com GeoTIFFs oficiais segue pendente; URLs e resultados da tentativa limitada estão no dossiê. Não se atribuiu revisão temática oficial ao espelho.'})
            continue
        if b['kind']=='figure' and b['file']=='fig09_arquitetura_artigo.png':
            b.update(file='fig10_fluxo_componentes_v2.png',caption='Figura 1. Fluxo de C: interpretação, validação local, cálculo permitido e resposta com evidências. O pré-processamento ocorre fora da pergunta.')
        elif b['kind']=='figure' and b['file']=='fig08_ic_artigo.png':
            b.update(file='fig11_sensibilidade_v2.png',caption='Figura 2. IC95% por famílias. Principal predefinido; subconjuntos comuns exploratórios (*) selecionam pelo sucesso observado e não equalizam contratos.')
        elif text.startswith('O benchmark contém'):
            b['text']=(f'O benchmark tem {metadata["dev_cases"]} casos de desenvolvimento e {m["primary_cases"]} de teste, destes {m["numeric_cases"]} quantitativos, em {main["groups"]} famílias. Famílias/paráfrases e municípios canônicos foram separados entre partições, com dependência residual em RN. Perguntas, referências, tolerâncias, prompts e código foram congelados antes do teste. A revisão adiciona análises exploratórias dos registros existentes, sem alterar o sistema ou executar nova condição experimental.')
        elif text.startswith('A diferença pareada principal foi'):
            b['text']=(f'O contraste principal foi {pp(main["difference_C_minus_B"])} pp (IC95% {pp(main["ci95"][0])} a {pp(main["ci95"][1])}), com todos os {main["cases"]} casos e falhas no denominador. Ele compara sistemas sob contratos diferentes. O IC mede acerto de consultas, não incerteza de hectares ou acurácia temática. Resultados quantitativos e sensibilidade territorial predefinidos permanecem no suplemento.')
        elif text.startswith('B acumulou'):
            b['text']=(f'Diagnóstico terminal: B teve {diag["B","retorno_textual_ausente"]} retornos textuais ausentes, {diag["B","rejeicao_contrato_indeterminada"]} rejeições com value_error genérico e {diag["B","erro_semantico_decisao"]} erros de decisão. Não é possível separar retrospectivamente a causa das rejeições genéricas. C teve {diag["C","rejeicao_semantica"]} rejeições semânticas explícitas e {diag["C","erro_semantico_decisao"]} erros de decisão/esclarecimento. As rejeições semânticas mantêm o estado erro_tecnico no escore original; os diagnósticos não se somam novamente a ele.')
            new.append(b)
            new.append({'kind':'table','headers':['Conjunto (n; famílias)','Acertos B / C','Δ pp [IC95%]'],
                'rows':[[f'Comum ({common["cases"]}; {common["paired"]["groups"]})',f'{common["B_correct"]} / {common["C_correct"]}',interval(common['paired'])],
                        [f'Quant. comum ({numeric["cases"]}; {numeric["paired"]["groups"]})',f'{numeric["B_correct"]} / {numeric["C_correct"]}',interval(numeric['paired'])]],
                'caption':'Tabela 2. Sensibilidade pós-hoc: mesmos casos sem erro técnico em ambas, com escores e tolerâncias originais.'})
            new.append({'kind':'paragraph','text':f'O subconjunto comum inclui {common["cases"]} casos ({common["paired"]["groups"]} famílias): {pct(common["B_accuracy"])} em B e {pct(common["C_accuracy"])} em C. Seu IC inclui zero e não sustenta uma conclusão isolada de superioridade aritmética. Selecionar pelo sucesso observado pode enviesar esse contraste. Não se executou condição de contrato equivalente. Após semântica válida, havia {rates["B"]["numeric_semantics_assessable"]}/{rates["C"]["numeric_semantics_assessable"]} respostas quantitativas avaliáveis em B/C, sem erro numérico isolável; isso não esclarece os casos rejeitados nem prova cálculo perfeito.'})
            continue
        elif text.startswith('No benchmark e orçamento avaliados'):
            b['text']=('O resultado principal favorece C como sistema completo neste benchmark e orçamento, com contratos de saída distintos. A sensibilidade exploratória sem falhas técnicas é compatível com diferença nula e não controla causalmente o contrato. Não se demonstrou superioridade isolada de raciocínio ou cálculo. Contratos equivalentes, referências humanas e novos modelos/territórios devem ser avaliados em protocolo e teste novos. Os resultados verificam respostas sobre dados derivados, sem validar verdade de campo.')
        new.append(b)
    draft['blocks']=new
    renumber_references(draft,public.get('official_page',{}).get('url','https://brasil.mapbiomas.org/'))
    # A inclusao posterior impede interpretar arrays JSON/codigos de classe como citacoes.
    insert=next(i for i,b in enumerate(draft['blocks']) if b.get('text','').startswith('A condição A recebe'))+1
    compact=json.dumps(example['validated_plan'],ensure_ascii=False,separators=(', ',': '))
    e=example['evidence'];value=example['value']['value']
    display=f"{e['territory']['name']}/{e['territory']['uf']}: {pt(value)} {example['value']['unit']} de Formação Florestal, em {e['years'][0]}."
    blocks=[{'kind':'paragraph','text':f'Exemplo real auditado ({example["case_id"]}, C): “{example["question"]}” O plano JSON executado foi:'},
            {'kind':'paragraph','text':compact},
            {'kind':'paragraph','text':f'Operação: somar áreas anuais da classe folha {e["class_codes"][0]}, no território e ano do plano, convertendo m²/10.000 para ha. O servidor respondeu: “{display}” Valor sem arredondamento: {value!r} ha. Evidência {e["evidence_id"][:12]}…, execução {e["run_id"][:12]}…, Coleção {e["collection"]}, suporte anual, método {e["area_method"]}. O JSON suplementar contém plano completo, resposta original e hashes; revisão do espelho e edição da malha seguem desconhecidas no registro histórico. É uma ilustração de acerto, não uma observação adicional de desempenho.'}]
    draft['blocks'][insert:insert]=blocks
    draft['word_counts']={'resumo':len(draft['abstract_pt'].split()),'abstract':len(draft['abstract_en'].split())}
    return draft


def supplements(a,m,rules,refs,draft,scale,metadata,s,p,e):
    base=long_report(a,m,rules,refs,draft,scale,metadata)
    rates=s['condition_specific_rates'];common=s['paired_analyses'][0]
    counts=table(['Condição','Diagnóstico observável','Casos'],[[r['condition'],r['diagnosis'],r['count']] for r in s['diagnostic_counts']])
    sensitivities=table(['Subconjunto','n','Famílias','Acertos B','Acertos C','Δ pp [IC95%]'],
        [[r['analysis'],r['cases'],r['paired'].get('groups'),r['B_correct'],r['C_correct'],interval(r['paired'])] for r in s['paired_analyses']])
    strata=table(['B técnico','C técnico','Casos','Acertos B','Acertos C','Contribuição pp no total'],
        [[r['B_technical'],r['C_technical'],r['cases'],r['B_correct'],r['C_correct'],pp(r['contribution_to_full_difference'])] for r in s['technical_strata']])
    extra=['# Revisão científica V2 — análises exploratórias e proveniência','',
        'A versão anterior foi preservada. Não houve nova chamada de modelo nem mudança no benchmark, escores, prompts, executor ou resultados individuais. As análises a seguir são pós-hoc, solicitadas após observar o teste; não foram pré-registradas. O contraste principal continua sendo o protocolo congelado.','',
        '## Separação de falhas e sensibilidade B/C','',counts,'',
        'A taxonomia é mutuamente exclusiva por caso/condição e distingue o estado original de erro técnico de sua causa observável. Em C, divergência de anos/operação/território permite identificar rejeição semântica. Em B, value_error genérico não preserva a razão; não é correto classificá-lo retroativamente como erro JSON, semântico ou numérico. Os registros brutos descartados não foram reconstruídos por inferência.','',sensitivities,'',
        f'Os mesmos case_ids são mantidos em B e C em cada subconjunto. Bootstrap pareado por famílias, {common["paired"]["replicas"]} réplicas, seed {common["paired"]["seed"]}; o IC principal usa a seed e definição originalmente congeladas. A seleção por status observado pode introduzir viés de seleção e não torna os contratos equivalentes. Não selecionar o subconjunto como novo resultado principal. O intervalo do subconjunto comum inclui zero; não se conclui equivalência nem ausência de efeito. Poucas famílias nos subconjuntos limitam a estabilidade do bootstrap.','',
        table(['Condição','Sem falha própria','Acertos','Taxa condicional','Quantitativos com semântica válida','Erros numéricos isoláveis'],[[r['condition'],r['nontechnical_cases'],r['correct'],pct(r['accuracy_conditional_on_own_success']),r['numeric_semantics_assessable'],r['isolated_numeric_errors']] for r in rates]),'',
        'As taxas condicionais por condição têm denominadores diferentes e não devem ser subtraídas como se fossem pareadas. Um erro numérico só é isolável se status, plano, entidades, anos, unidades e estrutura do resultado estiverem coerentes. Zero erro isolável nos casos avaliáveis não permite inferir desempenho aritmético nos casos rejeitados.','',
        '### Decomposição descritiva do contraste completo','',strata,'',
        'As contribuições usam o denominador completo e somam a diferença principal; não são estimativas causais de quanto o contrato explica. Casos com erro técnico apenas em B podem diferir em dificuldade daqueles em que ambas concluem.','',
        '![Sensibilidade](figuras/fig11_sensibilidade_v2.png)','',
        '![Diagnóstico terminal sem dupla contagem](figuras/fig12_diagnosticos_v2.png)','',
        '## Proveniência revisada','',provenance_markdown(p),'',
        '## Arquitetura e exemplo real','',
        '![Fluxo dos componentes](figuras/fig10_fluxo_componentes_v2.png)','',
        'Fontes, snapshot e cálculo fracionário são materializados antes da pergunta. A proposta textual é validada em contrato e semântica. O executor consulta somente derivados da execução escolhida e o servidor renderiza números/evidências. Ambiguidade retorna esclarecimento; falta de cobertura, fora de escopo e erro técnico têm saídas próprias. SQL/código do modelo não são executados.','',
        e['question'],'','```json',json.dumps(e['validated_plan'],ensure_ascii=False,indent=2),'```','',
        'Operação determinística: '+e['operation_executed']['template']+'. '+e['operation_executed']['input_unit']+'.','',
        e['final_answer'],'',
        f"Registro original: `{e['source_record']}`, SHA-256 `{e['source_record_sha256']}`. Answer ID `{e['answer_id']}`; evidência `{e['evidence']['evidence_id']}`. O exemplo é um acerto existente selecionado por regra declarada, não um novo teste de inferência. Plano, valor integral, método, qualidade e fontes completas estão em `exemplo_real.json`.",'',
        '## Condição equivalente futura — não executada','',
        'Para isolar o papel do cálculo, uma nova avaliação deverá congelar um corpus independente e um contrato final comum de fatos (status, entidades resolvidas, unidade, valor e IDs de fonte), com os mesmos fatos disponíveis, orçamento e política de esclarecimento. A execução com cálculo e a sem cálculo devem entregar o mesmo envelope; registrar separadamente a interpretação. Isso exige novo protocolo e execução reais, não recodificar este teste como uma condição equivalente. A revisão atual implementa apenas a alternativa mínima de sensibilidade solicitada.','',
        '## Texto e resultados anteriores para contexto','',base]
    return '\n\n'.join(extra)+'\n'


def provenance_markdown(p):
    mesh=p['territorial_snapshot'];public=p['public_verification']
    rows=[]
    for f in p['raster_files']:
        check=f['official_verification'] or {};obj=check.get('official_object',{})
        rows.append([f['year'],f['original_basename'],obj.get('generation','pendente'),check.get('matched_chunks',0),len(f['source_chunks']),f['native_crop']['sha256']])
    text=[table(['Ano','Arquivo original','Geração GCS conferida','Intervalos iguais','Intervalos registrados','SHA-256 do recorte'],rows),'',
        f"Aquisição histórica por janela: `{p['staging']['acquired_at']}`; estratégia `{p['staging']['strategy']}`; sem reamostragem ou overviews. Manifest `{p['staging']['path']}` SHA-256 `{p['staging']['sha256']}`. URLs do espelho, tamanhos, ETags, Last-Modified, offsets, comprimentos e hashes dos intervalos estão em `proveniencia.json`. ETag não é SHA-256. Os recortes nativos não são os arquivos nacionais originais.",'',
        f"Verificação pública: `{public.get('state')}` em `{public.get('checked_at')}`. A página oficial, seu hash e o asset GEE divulgado foram registrados. As gerações GCS fixam os objetos remotos usados na conferência; não são rótulos de revisão temática. O MD5/CRC32C reportado pelo GCS é metadado do objeto oficial e não foi calculado sobre o raster nacional do espelho. A igualdade dos intervalos utilizados não implica igualdade integral nacional, acurácia temática ou vínculo automático ao asset GEE coverage_v3.",'',
        f"Snapshot `{mesh['path']}` obtido em `{mesh['acquired_at']}`, `{mesh['crs']}`, {mesh['features']} entidades. Fonte comprovada: tabelas internas `{', '.join(mesh['source_tables'])}`, acesso somente leitura. Hash lógico `{mesh['mesh_sha256']}`; hash do arquivo `{mesh['file_sha256']}`. Provedor e arquivo originais, edição, data de publicação e licença não identificados. A data de extração não é data da malha. Não atribuir origem IBGE apenas pelos códigos.",'',
        f"Nova busca de comentários de catálogo: `{mesh['current_catalog_comments_check']['state']}`; motivo `{mesh['current_catalog_comments_check'].get('reason','nao_solicitado')}`. Se a configuração estiver ausente, nenhuma conexão foi realizada. O diagnóstico anterior e o snapshot local foram preservados.",'',
        'Não houve substituição de raster, malha ou estatística para aproveitar uma proveniência mais clara. Uma nova malha/revisão exige execução própria e reavaliação. Snapshot/estatísticas continuam sem liberação de redistribuição pela licença da malha não comprovada.']
    return '\n\n'.join(text)
