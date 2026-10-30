"""Rascunhos V3: revisao humana declarada, literatura primaria e controle real."""
from copy import deepcopy
import json,re
from .writing import pt,pct,pp,table
from .writing_v2 import revised_paper,provenance_markdown


def interpretation(effect):
    lo,hi=effect['ci95']
    if lo>0:return 'O fornecimento do resultado do executor aumentou o acerto sob o plano fixado e este orçamento.'
    if hi<0:return 'O fornecimento do resultado do executor reduziu o acerto sob o plano fixado e este orçamento.'
    return 'O intervalo inclui zero: não há evidência conclusiva da direção do efeito neste recorte; isso não demonstra equivalência.'


def renumber(draft,extra):
    references={re.match(r'\[(\d+)\]',b['text']).group(1):re.sub(r'^\[\d+\]\s*','',b['text'])
        for b in draft['blocks'] if b['kind']=='reference'}
    short={'geogpt2023':'Y. Zhang et al.','floodsql2026':'H. Liu et al.','toolformer2023':'T. Schick et al.','react2023':'S. Yao et al.'}
    for r in extra:
        references[r['id']]=f"{short[r['id']]} {r['title']}. arXiv:{r['version']}, {r['year']}. DOI: {r['doi']}."
    mapping={};blocks=[]
    def sub(match):
        key=match.group(1)
        if key not in references:return match.group()
        mapping.setdefault(key,len(mapping)+1)
        return '['+str(mapping[key])+']'
    for b in draft['blocks']:
        if b['kind']=='reference':continue
        if b['kind']=='paragraph' and not b.get('citation_exempt'):
            b['text']=re.sub(r'\[(\d+|geogpt2023|floodsql2026|toolformer2023|react2023)\]',sub,b['text'])
        blocks.append(b)
    for key,n in mapping.items():blocks.append({'kind':'reference','text':f'[{n}] '+references[key]})
    draft['blocks']=blocks


def manuscript(a,m,rules,refs,metadata,s,p,e,controlled,human,literature):
    require_review(human)
    draft=revised_paper(a,m,rules,refs,metadata,s,p,e);draft['draft_notice']='RASCUNHO V3 PARA REVISÃO AUTORAL — NÃO SUBMETIDO'
    effect=controlled['paired_Ceq_minus_Beq'];n=effect['cases'];cm={r['condition']:r for r in controlled['conditions']}
    primary=m['paired_C_minus_B'];common=s['paired_analyses'][0]
    draft['abstract_pt']=(f'Avaliamos consultas ambientais em português sobre o MapBiomas Coleção 11, no Rio Grande do Norte, em 2015 e 2025. A arquitetura interpreta planos tipados e calcula áreas com evidências. O benchmark separa 40 casos de desenvolvimento e 120 de teste; o autor declarou revisar manualmente as 120 perguntas, sem correções, sem confirmar revisão dos gabaritos. O contraste original entre sistema com executor e modelo com tabelas foi {pp(primary["difference_C_minus_B"])} pontos percentuais, sob contratos diferentes. Um experimento complementar fixou planos de referência e o mesmo contrato JSON em {n} consultas quantitativas reutilizadas. Ambas as condições usam o mesmo LLM finalizador; apenas uma recebe o resultado do executor. A diferença foi {pp(effect["difference_C_minus_B"])} pontos, IC95% [{pp(effect["ci95"][0])}; {pp(effect["ci95"][1])}]. Esse controle avalia disponibilidade de cálculo após o plano, sem validar interpretação, verdade de campo ou generalização para perguntas inéditas.')
    draft['abstract_en']=(f'We evaluate Portuguese environmental queries over MapBiomas Collection 11 in Rio Grande do Norte, Brazil, for 2015 and 2025. The architecture interprets typed plans and computes areas with evidence. The benchmark separates 40 development and 120 test questions. The author reported manually reviewing all test questions without corrections; human review of numerical references was not confirmed. The original executor-system versus tables-model contrast was {100*primary["difference_C_minus_B"]:.2f} percentage points under different contracts. A complementary experiment fixed reference plans and an identical JSON output contract for {n} reused quantitative queries. Both conditions use the same LLM finalizer; only one receives executor results. The paired difference was {100*effect["difference_C_minus_B"]:.2f} points, 95% CI [{100*effect["ci95"][0]:.2f}; {100*effect["ci95"][1]:.2f}]. This control evaluates calculation availability after planning, without validating interpretation, field truth or generalization to unseen questions.')
    new=[]
    for original in draft['blocks']:
        b=deepcopy(original);text=b.get('text','')
        if text.startswith('A separação entre interpretação e cálculo'):
            b['text']='Separar interpretação e cálculo tem antecedentes em Program of Thoughts [2]. GeoGPT [geogpt2023] conecta linguagem natural a coleta, processamento e análise SIG por ferramentas. FloodSQL-Bench [floodsql2026] estuda Text-to-SQL geoespacial com junções de dados de inundação e avaliação por similaridade de consultas, sem execução no protocolo descrito.'
            new.append(b)
            new.append({'kind':'paragraph','text':'Toolformer [toolformer2023] aprende chamadas de APIs com supervisão gerada pelo próprio modelo; ReAct [react2023] intercala ações e raciocínio. Não reivindicamos inaugurar interfaces SIG ou uso de ferramentas por LLMs. A contribuição específica é avaliar consultas em português com operações restritas, suporte comparável entre anos, evidência numérica rastreável e um controle de disponibilidade de cálculo. Não há comparação direta de desempenho com esses sistemas.'})
            continue
        if text.startswith('As referências numéricas usam'):
            b['text']='As referências usam Parquet e Decimal independentes do executor; invariantes e suficiência dos fatos foram conferidos. O autor declarou em 21/10/2026 revisar manualmente as 120 perguntas de teste, sem correções; hashes identificam os casos. A declaração não confirma revisão numérica dos gabaritos, revisão cega, segundo anotador ou concordância entre revisores. Acerto exige estado, entidades, classes, anos, métrica, unidade, denominador e valores; erros técnicos permanecem no denominador.'
        elif text.startswith('O benchmark tem'):
            b['text']='O benchmark original contém 40 casos de desenvolvimento e 120 de teste, 88 quantitativos em oito das quinze famílias. Famílias/paráfrases e municípios canônicos foram separados, com dependência residual em RN. Perguntas, referências, tolerâncias, prompts e sistema original foram congelados antes do teste. Não se alteraram essas entradas; a declaração de revisão humana foi recebida posteriormente, sem informar a data exata da revisão.'
            new.append(b)
            new.append({'kind':'paragraph','text':f'Para controlar o contrato, o novo experimento usa os {n} casos quantitativos, com planos de referência fixados e as mesmas tabelas completas. B_eq calcula com o LLM; C_eq recebe também o resultado real do executor. Ambas chamam o mesmo LLM finalizador e devem gerar exatamente o mesmo esquema JSON de estado/valores, sem produzir plano. A única diferença planejada é execution_observations vazia ou preenchida com o cálculo. Não se executa SQL/código do modelo.'})
            new.append({'kind':'paragraph','text':f'Protocolo, planos, esquema, prompts, critérios e runner foram hashados antes das chamadas novas. Após oito casos de desenvolvimento nas duas condições, executaram-se {n} pares, com ordem aleatória por caso (seed 20261021), três workers e uma repetição em quatro casos por condição. Modelo, temperatura, limites e reparo são iguais entre B_eq/C_eq. O contraste complementar usa bootstrap pareado de famílias, {effect["replicas"]} réplicas e seed {effect["seed"]}. Perguntas reutilizadas tornam a avaliação exploratória, sem testar a interpretação ponta a ponta.'})
            continue
        elif text.startswith('O gateway LLM informou'):
            b['text']='Na comparação original, o gateway'+text[len('O gateway'):]
        elif text.startswith('Exemplo real auditado'):
            b['citation_exempt']=True
        elif text.startswith('{"operation"'):
            b['citation_exempt']=True
        elif text.startswith('Operação: somar áreas anuais'):
            b['text']=f'Operação: soma da classe folha 3 no suporte anual, com conversão m²/10.000 para ha. Resposta real: “Acari/RN: {pt(e["value"]["value"])} ha de Formação Florestal em 2015”. Evidência {e["evidence"]["evidence_id"][:12]}… e execução {e["execution"]["run_id"][:12]}…; plano, valor integral, método e hashes completos no suplemento. É ilustração de um acerto registrado, sem nova observação de desempenho.'
        elif b['kind']=='figure' and b['file']=='fig11_sensibilidade_v2.png':
            b.update(file='fig13_controle_contrato_v3.png',caption='Figura 2. Controle complementar: mesmo plano, tabelas, modelo e JSON final; C_eq acrescenta o resultado do executor antes da finalização pelo LLM.')
        elif b['kind']=='table' and b.get('caption','').startswith('Tabela 2.'):
            b={'kind':'table','headers':['Controle','Acerto','Taxa','Técnicos'],
                'rows':[[r['condition'],f'{r["correct"]}/{r["cases"]}',pct(r['accuracy']),str(r['technical_errors'])] for r in controlled['conditions']],
                'caption':'Tabela 2. Contrato equivalente sob plano fixo; falhas técnicas incluídas no denominador.'}
            new.append(b)
            diagnoses={(r['condition'],r['type']):r['count'] for r in controlled['errors']}
            new.append({'kind':'paragraph','text':f'No controle, B_eq teve {cm["B_eq"]["technical_errors"]} falhas técnicas: {diagnoses.get(("B_eq","texto_final_ausente"),0)} sem texto final e {diagnoses.get(("B_eq","contrato_invalido"),0)} de contrato. C_eq teve {cm["C_eq"]["technical_errors"]}. Entre as respostas emitidas, {cm["B_eq"]["correct"]}/{cm["B_eq"]["answered"]} em B_eq e {cm["C_eq"]["correct"]}/{cm["C_eq"]["answered"]} em C_eq estavam corretas. O ganho observado corresponde à disponibilidade de resposta sob este orçamento, sem erros aritméticos observados nas emitidas. A causa remota dos retornos vazios não foi identificada.'})
            continue
        elif text.startswith('O subconjunto comum inclui'):
            b['text']=(f'A sensibilidade pós-hoc original, nos {common["cases"]} casos sem erro técnico em ambas, permanece {pp(common["paired"]["difference_C_minus_B"])} pp (IC95% {pp(common["paired"]["ci95"][0])} a {pp(common["paired"]["ci95"][1])}), condicionada ao sucesso observado. No controle de contrato, C_eq−B_eq foi {pp(effect["difference_C_minus_B"])} pp (IC95% {pp(effect["ci95"][0])} a {pp(effect["ci95"][1])}), com {effect["groups"]} famílias. '+interpretation(effect)+' O efeito refere-se a fornecer resultados verificados ao finalizador, incluindo conformidade da saída; não mede capacidade cognitiva intrínseca.')
        elif text.startswith('As latências médias por condição A/B/C'):
            b['text']=(f'No controle, as latências médias online B_eq/C_eq foram {pt(cm["B_eq"]["latency_mean_seconds"])} / {pt(cm["C_eq"]["latency_mean_seconds"])} s; tokens observados {cm["B_eq"]["usage_observed_sum"]["total_tokens"]} / {cm["C_eq"]["usage_observed_sum"]["total_tokens"]}. Custos não conhecidos. Repetiram-se {sum(r["same_answer"] for r in controlled["repeatability"])}/{len(controlled["repeatability"])} respostas estruturadas na amostra limitada; temperatura zero não garante determinismo. Resultados históricos e contadores ausentes estão no suplemento.')
        elif text.startswith('O resultado principal favorece C'):
            b['text']=('O contraste original avalia sistemas completos sob contratos distintos. O controle novo remove essa diferença de saída e fixa a interpretação, estimando o efeito de disponibilizar cálculo ao mesmo finalizador. '+interpretation(effect)+' Sua validade fica restrita aos dados, modelo, orçamento e planos fornecidos; não sustenta superioridade geral nem valida o significado ambiental dos mapas. São necessários perguntas inéditas, validação humana dos gabaritos, outros modelos e recortes.')
        elif text.startswith('IA assistiu programação, construção de perguntas'):
            b['text']='IA assistiu programação, construção de perguntas e redação; LLM foi objeto da avaliação. O autor declarou revisar as 120 perguntas, sem correções; não confirmou revisão dos gabaritos. Não se inventaram anotações, avaliação independente ou concordância entre revisores. Autores reais devem confirmar contribuições, revisar o texto e assumir responsabilidade. A política institucional permanece a confirmar. [AUTORIA, AFILIAÇÕES E CONTATOS A PREENCHER].'
        new.append(b)
    draft['blocks']=new;renumber(draft,literature['new_primary_references'])
    draft['word_counts']={'resumo':len(draft['abstract_pt'].split()),'abstract':len(draft['abstract_en'].split())}
    return draft


def require_review(human):
    if human['question_count']!=120 or human['corrections_reported'] is not False or human['reference_answer_review_confirmed']:
        raise ValueError('escopo_da_revisao_humana_divergente_da_declaracao')


def report(a,m,s,p,e,c,dev,human,literature,draft):
    effect=c['paired_Ceq_minus_Beq']
    comparison=table(['Condição','Corretos/total','Taxa','Falhas técnicas','Precisão emitida','Média online s','Tokens observados','Tentativas sem usage'],
        [[r['condition'],f'{r["correct"]}/{r["cases"]}',pct(r['accuracy']),r['technical_errors'],pct(r['precision_emitted']) if r['precision_emitted'] is not None else 'indefinida',pt(r['latency_mean_seconds']),r['usage_observed_sum']['total_tokens'],r['usage_missing_attempts']] for r in c['conditions']])
    literature_table=table(['Estudo primário','Relação com o projeto','Distinção de escopo'],[
        ['GeoGPT','Interface em linguagem natural para coleta/análise SIG por ferramentas','Nossa avaliação restringe operações e rastreia números em derivados fixos.'],
        ['FloodSQL-Bench','Text-to-SQL geoespacial, junções e protocolo de similaridade sem execução','Aqui se pontuam respostas numéricas executadas, sem SQL livre; não se comparam as taxas entre benchmarks.'],
        ['Toolformer','Aprendizagem auto-supervisionada de chamadas de APIs','Não treinamos modelo; fornecemos resultado de função determinística em controle de inferência.'],
        ['ReAct','Intercala raciocínio e ações com observações externas','O controle fixa o plano e não avalia seleção autônoma de ferramentas nem armazena raciocínio interno.']])
    blocks=['# Revisão científica V3 — rascunho para revisão autoral','',
        'V1/V2 e todos os resultados originais foram preservados. Esta revisão registra a declaração humana recebida, acrescenta literatura primária e um experimento real complementar. Não houve submissão, publicação ou deploy.','',
        '## Revisão humana: o que foi efetivamente declarado','',
        f"O usuário/autor declarou revisar manualmente as {human['question_count']} perguntas de teste sem correções, em declaração recebida em {human['declaration_received_on']}. O arquivo REVISAO_HUMANA_DECLARADA.json liga a declaração a hashes dos casos originais. O momento exato da revisão não foi informado. A declaração não confirma revisão dos gabaritos, anotador independente, cegamento ou concordância. Não foram fabricadas fichas de avaliação humana. As perguntas e os escores antigos não mudaram.",'',
        '## Literatura primária e posicionamento','',literature_table,'',
        'Metadados, versões, autores, DOI arXiv e hashes de páginas primárias estão em bibliografia_v3.json. Foram conferidos resumo e trechos de método, sem alegar revisão sistemática. Referências a ferramentas e SIG contextualizam antecedentes; não são resultados de uma comparação empírica com o nosso sistema.','',
        '## Experimento com contrato equivalente','',
        f"Protocolo congelado antes das novas chamadas; desenvolvimento em {sum(r['cases'] for r in dev['conditions'])} registros reais e avaliação em {c['primary_records']} registros principais ({effect['cases']} pares), mais {c['repeat_records']} repetições predefinidas. Dataset reutilizado, não teste externo novo. Planos de referência, tabelas, documentação, prompt de sistema, esquema, LLM e parâmetros são iguais. A única chave de contexto que difere é execution_observations: vazia em B_eq e com a resposta real do executor em C_eq. Ambas geram e validam JSON pelo LLM; C_eq não publica diretamente o template do servidor neste controle.",'',
        'O tratamento é a disponibilidade do cálculo verificado para um finalizador, condicionado ao plano fornecido. O experimento controla a assimetria do contrato original e exclui interpretação da pergunta como variável. As observações adicionais de C_eq são a intervenção pretendida; comprimentos/tokens de entrada não são idênticos. O resultado inclui copiar valores, conformidade da saída e eventuais falhas de gateway, não habilidade aritmética cognitiva isolada. A ordem é aleatória por caso, sessões independentes, três workers, um reparo máximo e nenhuma referência numérica enviada a B_eq ou ao reparo.','',comparison,'',
        f"C_eq−B_eq = {pp(effect['difference_C_minus_B'])} pp, IC95% [{pp(effect['ci95'][0])}; {pp(effect['ci95'][1])}], {effect['groups']} famílias, {effect['replicas']} réplicas, seed {effect['seed']}. {interpretation(effect)} O número pequeno de famílias e o compartilhamento de territórios/dados limitam a precisão e a generalização. Erros técnicos permanecem no denominador principal.",'',
        'A precisão entre respostas emitidas foi integral em ambas neste experimento. A diferença observada é composta por falhas de emissão/contrato em B_eq, não por erros numéricos nas respostas aceitas. Não se identificou a causa remota de texto final ausente, nem se inferiu exaustão de tokens a partir de ausência de texto. Contrato igual controla a assimetria anterior, mas não transforma confiabilidade operacional em prova de capacidade aritmética intrínseca.','',
        table(['Condição','Diagnóstico','Casos'],[[r['condition'],r['type'],r['count']] for r in c['errors']]),'',
        table(['Condição','Família','Acertos','Casos'],[[r['condition'],r['family_id'],r['correct'],r['cases']] for r in c['families']]),'',
        f"Repetibilidade: {sum(r['same_answer'] for r in c['repeatability'])}/{len(c['repeatability'])} respostas estruturadas iguais; {sum(r['same_correctness'] for r in c['repeatability'])}/{len(c['repeatability'])} escores iguais. Não se escolheu a melhor resposta nem se incluíram repetições no acerto principal. Preço ausente permanece null, contadores sem usage não são estimados.",'',
        '## Comparação original preservada','',
        table(['Condição','Acertos','Casos','Taxa','Técnicos'],[[r['condition'],r['correct'],r['cases'],pct(r['accuracy']),r['technical_errors']] for r in m['conditions']]),'',
        f"Diferença original C−B {pp(m['paired_C_minus_B']['difference_C_minus_B'])} pp com contratos distintos. O controle novo tem outra tarefa (plano fixo) e outro momento de execução; não se subtraem taxas entre experimentos para atribuir uma parcela causal do ganho antigo. A sensibilidade V2 e seus limites permanecem em sensibilidade.json.",'',
        '## Fontes, área e exemplo real','',provenance_markdown(p),'',
        f"Método {a['area_method']}; mesma malha para 2015/2025, máscaras comparáveis e conservação numérica. Incógnitas de malha/licença/revisão temática não foram preenchidas por inferência. Estatísticas/Parquets auditados permanecem os mesmos.",'',
        e['question'],'','```json',json.dumps(e['validated_plan'],ensure_ascii=False,indent=2),'```','',e['final_answer'],'',
        '## Limitações, direitos e uso de IA','',
        *c['limitations'],'',
        'A revisão humana das perguntas melhora a documentação sem equivaler a validar números de referência, mapas ou campo. Novidade é a avaliação delimitada de uma arquitetura e seu controle, não a primeira combinação de LLM e GIS. Dados nacionais, novas perguntas e validação humana dos gabaritos continuam necessários. Licenças da malha/código/benchmark e política institucional de publicação das saídas permanecem pendentes. IA não foi adicionada à autoria.','',
        '## Referências usadas no manuscrito','',*[b['text'] for b in draft['blocks'] if b['kind']=='reference']]
    return '\n\n'.join(blocks)+'\n'
