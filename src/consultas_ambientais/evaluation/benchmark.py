"""Benchmark declarativo: familias linguisticas/semanticas inteiras em uma particao."""
from pathlib import Path
from .common import save, write_lines, now, digest
from .reference import ReferenceReader
from ..contracts import QueryPlan
from ..semantics.catalog import ClassCatalog
from ..semantics.territories import TerritoryCatalog


def plan(code, cls=15, years=(2015,), metric='area', unit='ha', operation=None):
    codes = [code] if isinstance(code, str) else code
    operation = operation or ('comparacao_temporal' if len(years) == 2 else 'participacao' if metric == 'participacao' else 'area')
    return QueryPlan(operation=operation, metric=metric, unit=unit, territory_codes=codes,
                     scope_uf='RN', class_codes=[cls] if isinstance(cls, int) else cls, years=list(years),
                     denominator={'participacao': 'area_observada', 'variacao_percentual': 'area_inicial',
                                  'diferenca_pontos_percentuais': 'participacao_por_ano'}.get(metric),
                     limit=5 if operation == 'ranking_delimitado' else None).model_dump(mode='json')


# Quatro redacoes explicitas por familia; nenhuma e enviada ao LLM para gerar gabaritos.
DEV = [
('d01', 'area_pastagem', plan('2410900'), [
'Qual era a área de Pastagem em Riachuelo/RN em 2015, em hectares?',
'Em hectares, informe a área de Pastagem de Riachuelo/RN no ano de 2015.',
'Para Riachuelo/RN, preciso da área em ha de Pastagem em 2015.',
'Consulte a área de Pastagem, em ha, em Riachuelo/RN, ano 2015.']),
('d02', 'delta_urbano', plan('2408102',24,(2015,2025),'diferenca_liquida'), [
'Quanto mudou a área da classe Área Urbanizada de Natal/RN entre 2015 e 2025, em hectares?',
'Qual a diferença líquida da Área Urbanizada em Natal/RN de 2015 para 2025, em ha?',
'Em Natal/RN, mostre o saldo líquido da Área Urbanizada de 2015 para 2025, em hectares.',
'Informe a diferença de área, final menos inicial, de Área Urbanizada em Natal/RN: 2015 e 2025, ha.']),
('d03', 'participacao', plan('2410900',15,(2015,),'participacao','percentual'), [
'Qual a participação de Pastagem na área observada de Riachuelo/RN em 2015?',
'Informe a proporção de Pastagem na área observada em Riachuelo/RN, 2015.',
'Em Riachuelo/RN, 2015, qual a participação percentual de Pastagem na área observada?',
'Para 2015, calcule a participação de Pastagem na área observada de Riachuelo/RN.']),
('d04', 'base_zero', plan('2410900',5,(2015,2025),'variacao_percentual','percentual'), [
'Qual a variação percentual de Mangue em Riachuelo/RN entre 2015 e 2025, em relação à área inicial?',
'Informe a variação percentual da área de Mangue de Riachuelo/RN de 2015 para 2025.',
'Em Riachuelo/RN, como variou percentualmente a área de Mangue entre 2015 e 2025 em relação à área inicial?',
'Calcule a variação percentual de Mangue para Riachuelo/RN, 2015 e 2025, com base na área inicial.']),
('d05', 'serie', plan('2411205',24,(2015,2025),operation='serie_disponivel'), [
'Informe a série de área de Área Urbanizada de Santa Cruz/RN, somente 2015 e 2025, em ha.',
'Quero a série disponível de Área Urbanizada em Santa Cruz/RN nos anos 2015 e 2025, em hectares.',
'Consulte as áreas de Área Urbanizada para Santa Cruz/RN em 2015 e 2025, em ha.',
'Mostre a série de Área Urbanizada de Santa Cruz/RN, em hectares, nos dois anos 2015 e 2025.']),
('d06', 'grupo', plan('2410900',1), [
'Qual a área do grupo Floresta, código 1, em Riachuelo/RN em 2015, em ha?',
'Informe a área em hectares da classe de grupo 1 (Floresta) em Riachuelo/RN em 2015.',
'Para Riachuelo/RN, ano 2015, consulte a área em ha do grupo de código 1.',
'Em hectares, qual a área de Floresta, grupo código 1, em Riachuelo/RN no ano 2015?']),
('d07', 'homonimo', ('precisa_esclarecimento','territorio'), [
'Qual a área de Pastagem em Santa Cruz em 2015, em ha?',
'Informe a área de Pastagem no município de Santa Cruz em 2015, em hectares.',
'Em Santa Cruz, qual a área em ha de Pastagem em 2015?',
'Para o município Santa Cruz, consulte a área de Pastagem em hectares, em 2015.']),
('d08', 'classe_ambigua', ('precisa_esclarecimento','classe'), [
'Qual a área de floresta em Riachuelo/RN em 2015, em hectares?',
'Informe a área de floresta de Riachuelo/RN no ano de 2015, em ha.',
'Em hectares, quanto havia de floresta em Riachuelo/RN em 2015?',
'Consulte floresta em Riachuelo/RN, área em ha no ano 2015.']),
('d09', 'ano_ausente', plan('2410900',15,(2020,)), [
'Qual a área de Pastagem de Riachuelo/RN em 2020, em ha?',
'Informe a área em hectares de Pastagem de Riachuelo/RN em 2020.',
'Para 2020, consulte a área de Pastagem em Riachuelo/RN, em ha.',
'Em Riachuelo/RN, no ano 2020, qual a área de Pastagem em hectares?']),
('d10', 'causa', ('fora_do_escopo',None), [
'Qual a causa da mudança de Área Urbanizada em Natal/RN entre 2015 e 2025?',
'Por que mudou a Área Urbanizada em Natal/RN de 2015 para 2025?',
'O que causou a mudança da Área Urbanizada em Natal/RN entre 2015 e 2025?',
'Explique o motivo da mudança da Área Urbanizada de Natal/RN entre 2015 e 2025.']),
]


def test_families():
    families = []
    def add(tag, p, texts):
        families.append((f't{len(families)+1:02}', tag, p, texts))
    def area(tag, code, cls, name, town, year, unit, noun):
        add(tag, plan(code,cls,(year,),unit=unit), [
            f'Em {year}, quantos {noun} de {name} foram mapeados no município de {town}/RN?',
            f'Dê a extensão de {name} em {town}/RN, ano {year}, como área em {unit}.',
            f'No ano {year}, a área classificada como {name} em {town}/RN corresponde a quantos {noun}?',
            f'Apresente, em {unit}, a área mapeada de {name} no território municipal de {town}/RN para {year}.'])
    area('formacao_florestal','2400109',3,'Formação Florestal','Acari',2015,'ha','hectares')
    area('conversao_km2','2400208',15,'Pastagem','Assú',2025,'km2','quilômetros quadrados')
    area('conversao_m2','2408003',24,'Área Urbanizada','Mossoró',2025,'m2','metros quadrados')
    area('agua_mapeada','2402006',33,'Rio, Lago e Oceano','Caicó',2015,'ha','hectares')
    area('grupo_hierarquico','2403103',1,'grupo Floresta código 1','Currais Novos',2025,'km2','quilômetros quadrados')
    add('uniao_sem_dupla_contagem',plan('2409407',[1,3]),[
        'Qual a área da união das classes Floresta (código 1) e Formação Florestal (código 3), sem dupla contagem, em Pau dos Ferros/RN, 2015, ha?',
        'Em Pau dos Ferros/RN, some por união Floresta código 1 e Formação Florestal código 3, área em ha de 2015, sem contar pixels duas vezes.',
        'Para 2015 em Pau dos Ferros/RN, área em hectares da união do grupo 1 com a classe 3, sem sobreposição duplicada?',
        'A união da classe 1 com a classe 3 cobre qual área em ha em Pau dos Ferros/RN, 2015, contando cada pixel uma vez?'])
    for code, cls, town, name, year in [('2412203',3,'São José de Mipibu','Formação Florestal',2025),('2406106',15,'Jucurutu','Pastagem',2015)]:
        add('fracao_observada_'+str(cls),plan(code,cls,(year,),'participacao','percentual'),[
            f'Na área observada de {town}/RN em {year}, qual a fração percentual classificada como {name}?',
            f'Quanto representa {name} na área observada de {town}/RN em {year}, como participação percentual?',
            f'Para {town}/RN no ano {year}, dê a proporção de {name} usando como denominador a área observada.',
            f'Qual participação, em percentual da área observada, corresponde a {name} em {town}/RN no ano {year}?'])
    add('denominador_ambiguo',('precisa_esclarecimento','metrica'),[
        'Qual o percentual de Pastagem em Parnamirim/RN entre 2015 e 2025?',
        'Em Parnamirim/RN, Pastagem de 2015 para 2025 dá qual percentual?',
        'Calcule o percentual para Pastagem em Parnamirim/RN, 2015 e 2025.',
        'Preciso do percentual de Pastagem de Parnamirim/RN nos anos 2015 e 2025.'])
    add('unidade_ausente',('precisa_esclarecimento','unidade'),[
        'Qual a área de Rio, Lago e Oceano em Touros/RN em 2015?',
        'Em Touros/RN no ano 2015, informe a área de Rio, Lago e Oceano.',
        'Consulte para Touros/RN a área de Rio, Lago e Oceano no ano de 2015.',
        'A classe Rio, Lago e Oceano tem qual área em Touros/RN em 2015?'])
    for code,cls,town,name,unit in [('2406700',3,'Lajes','Formação Florestal','ha'),('2400802',15,'Angicos','Pastagem','km2'),('2401008',33,'Apodi','Rio, Lago e Oceano','m2'),('2402600',24,'Ceará-Mirim','Área Urbanizada','ha')]:
        add('saldo_'+str(cls),plan(code,cls,(2015,2025),'diferenca_liquida',unit),[
            f'Calcule em {unit} a diferença líquida, área final menos inicial, de {name} em {town}/RN entre 2015 e 2025.',
            f'Para {town}/RN, quanto mudou a área de {name} de 2015 a 2025, em {unit}, preservando o sinal?',
            f'Dê o saldo líquido em {unit} de {name} em {town}/RN: cobertura final de 2025 menos inicial de 2015.',
            f'Compare 2015 e 2025 em {town}/RN pela diferença de área de {name}, em {unit}, final menos inicial.'])
    for code,cls,town,name in [('2412500',3,'São Miguel','Formação Florestal'),('2400505',15,'Alexandria','Pastagem'),('2403608',24,'Extremoz','Área Urbanizada'),('2403806',5,'Florânia','Mangue')]:
        add('taxa_'+str(cls),plan(code,cls,(2015,2025),'variacao_percentual','percentual'),[
            f'Em relação à área inicial de 2015, qual a variação percentual de {name} em {town}/RN até 2025?',
            f'Calcule a variação percentual de {name} em {town}/RN entre 2015 e 2025, dividindo pela área inicial.',
            f'Para {town}/RN, obtenha a variação percentual da área de {name} de 2015 para 2025 com base em 2015.',
            f'Quanto foi a variação percentual de {name} entre 2015 e 2025 em {town}/RN, tendo a área inicial como base?'])
    for code,cls,town,name in [('2412005',24,'São Gonçalo do Amarante','Área Urbanizada'),('2407203',33,'Macau','Rio, Lago e Oceano')]:
        add('pontos_'+str(cls),plan(code,cls,(2015,2025),'diferenca_pontos_percentuais','pontos_percentuais'),[
            f'Qual a diferença em pontos percentuais da participação de {name} em {town}/RN entre 2015 e 2025, na área observada de cada ano?',
            f'Compare em pontos percentuais a participação de {name} na área observada em {town}/RN: 2025 menos 2015.',
            f'Dê a mudança de participação de {name} em {town}/RN de 2015 para 2025 em pontos percentuais, com área observada como denominador.',
            f'Em {town}/RN, calcule a diferença de participação de {name}, final menos inicial, em pontos percentuais: 2015 e 2025, sobre a área observada.'])
    for code,cls,town,name in [('2401453',15,'Baraúna','Pastagem'),('2402303',3,'Caraúbas','Formação Florestal')]:
        add('serie_enum_'+str(cls),plan(code,cls,(2015,2025),operation='serie_disponivel'),[
            f'Liste a série de área de {name} em {town}/RN em hectares, limitada aos anos 2015 e 2025.',
            f'Quero uma série com apenas 2015 e 2025: área de {name} em {town}/RN, em ha.',
            f'Apresente separadamente as áreas de {name} de {town}/RN em 2015 e em 2025, ambas em ha.',
            f'Mostre a série disponível nos dois anos 2015 e 2025 para a área de {name} em {town}/RN, em hectares.'])
    for codes,cls,towns,name in [(['2411056','2404200'],3,'Tibau/RN e Goianinha/RN','Formação Florestal'),(['2401206','2402204'],24,'Arez/RN e Canguaretama/RN','Área Urbanizada')]:
        add('comparacao_'+str(cls),plan(codes,cls,(2025,),operation='comparacao_territorial'),[
            f'Compare as áreas de {name} em {towns} no ano 2025, em ha, listando cada município.',
            f'Em 2025, qual a área em hectares de {name} em cada um destes municípios: {towns}?',
            f'Faça uma comparação territorial da área de {name} entre {towns} em 2025, em ha.',
            f'Coloque lado a lado os valores de área de {name} de {towns}, ano 2025, em hectares.'])
    for metric,years,cls,label in [('reducao_liquida',(2015,2025),3,'maior redução líquida de Formação Florestal entre 2015 e 2025'),('area',(2025,),15,'maior área de Pastagem em 2025')]:
        add('ranking_'+metric,plan([],cls,years,metric,operation='ranking_delimitado'),[
            f'Quais os cinco municípios do RN com {label}, em ha?',
            f'Liste os 5 municípios do RN com {label}, em hectares.',
            f'Mostre o ranking top 5 de municípios do RN por {label}, em ha.',
            f'Dentro do RN, quais são os cinco municípios com {label}, em hectares?'])
    add('ano_nao_materializado',plan('2409902',15,(2024,)),[
        'Em Pendências/RN, quantos hectares de Pastagem foram mapeados em 2024?',
        'Dê a área em ha de Pastagem para Pendências/RN no ano 2024.',
        'Apresente a extensão em hectares de Pastagem em Pendências/RN, 2024.',
        'A área classificada como Pastagem em Pendências/RN em 2024 é de quantos ha?'])
    add('homonimo_bom_jesus',('precisa_esclarecimento','territorio'),[
        'Quantos hectares de Pastagem existem no município de Bom Jesus em 2025?',
        'Dê a área de Pastagem, em ha, em Bom Jesus, ano 2025.',
        'Para o município Bom Jesus, mostre a área em hectares de Pastagem de 2025.',
        'Em 2025, a área de Pastagem do município de Bom Jesus mede quantos ha?'])
    add('floresta_bom_jesus',('precisa_esclarecimento','classe'),[
        'Quantos hectares de floresta existem em Bom Jesus/RN em 2025?',
        'Em Bom Jesus/RN, qual a área em ha de floresta no ano 2025?',
        'Dê a extensão de floresta de Bom Jesus/RN, em hectares, para 2025.',
        'A área de floresta em Bom Jesus/RN em 2025 corresponde a quantos ha?'])
    add('inundacao',('fora_do_escopo',None),[
        'Qual a área do evento de inundação em Touros/RN em 2025, em hectares?',
        'Quantos hectares foram afetados pela inundação em Touros/RN em 2025?',
        'A inundação de 2025 em Touros/RN cobriu qual área em ha?',
        'Calcule a área em hectares da enchente de 2025 em Touros/RN.'])
    return families


def cluster_family(case_group):
    # Instancias com a mesma moldura de pergunta ficam no MESMO cluster,
    # mesmo quando territorio/classe/unidade mudam. Evita pseudorreplicacao.
    n = int(case_group[1:])
    for members, name in [({1,2,3,4,5},'area_direta'),({7,8},'participacao'),
                          ({11,12,13,14},'delta'),({15,16,17,18},'variacao'),
                          ({19,20},'pontos'),({21,22},'serie'),({23,24},'territorial'),
                          ({25,26},'ranking')]:
        if n in members:return 'teste_'+name
    return 'teste_'+case_group


def build(root, destination, run_id):
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('benchmark_existente_nao_sobrescrever')
    destination.mkdir(parents=True, exist_ok=True)
    classes = ClassCatalog.load()
    territories = TerritoryCatalog.load(Path(root)/'data/territories_v1.json')
    reader = ReferenceReader(root, run_id, classes)
    cases, gold, facts = [], {}, {}
    from ..llm.context import build_context
    from ..storage.derived import DerivedStore
    from ..settings import ProjectConfig
    from ..llm.dialogue_models import InterpretationConfig
    store = DerivedStore(root, ProjectConfig.load(Path(root)/'configs/project.json'),run_id,classes,territories,Path(root)/'data/capabilities_stage3.json')
    for split, families in [('dev', DEV), ('test', test_families())]:
        for case_group, tag, canonical_plan, questions in families:
            family_id = cluster_family(case_group) if split == 'test' else case_group
            if isinstance(canonical_plan, tuple):
                status, field = canonical_plan
                canonical_plan = None
                values = []
            else:
                status, values = reader.answer(canonical_plan)
                field = None
            for n, question in enumerate(questions):
                case_id = f'{case_group}_{n+1}'
                ctx = build_context(question, {}, classes, territories, store, InterpretationConfig())
                codes = [x['code'] for x in ctx['territory_candidates']]
                # UF nao solicitada como territorio nao precisa de tabela nacional/estadual.
                codes = [c for c in codes if len(c)==7 or (canonical_plan and c in canonical_plan['territory_codes'])]
                facts[case_id] = {'context': ctx, 'tables': reader.facts(codes),
                                  'table_columns': ['support','year','class_code','area_ha'],
                                  'complete': True, 'truncated': False}
                if canonical_plan and canonical_plan['operation'] != 'ranking_delimitado':
                    if not set(canonical_plan['territory_codes']) <= set(codes):
                        raise ValueError('contexto_B_sem_territorio')
                cases.append({'case_id':case_id,'family_id':family_id,'split':split,'tag':tag,
                              'question':question,'territory_codes':canonical_plan['territory_codes'] if canonical_plan else codes,
                              'dependencies': ['universo_RN'] if tag.startswith('ranking_') else codes,
                              'canonical_plan':canonical_plan,'expected_decision':status,
                              'reference_answer':{'values':values,'clarification_field':field}})
                gold[case_id]={'status':status,'plan':canonical_plan,'values':values,'clarification_field':field}
    if len([c for c in cases if c['split']=='dev'])!=40 or len(cases)!=160:
        raise ValueError('contagem_familias_invalida')
    # Um caminho conhecido anterior, sem executar o motor de producao.
    check = reader.answer(plan('2410900'))[1][0]['value']
    if abs(float(check)-8684.038153762798)>1e-10:
        raise ValueError('recorte_conhecido_divergente')
    write_lines(destination/'cases.jsonl',cases)
    save(destination/'gold.json',gold)
    save(destination/'facts.json',facts)
    save(destination/'sources.json',{'created_at':now(),'run_id':run_id,'input_hashes':reader.input_hashes,
                                   'method':'Decimal independente; DuckDB somente desserializa',
                                   'invariants':reader.invariants,'known_cut_riachuelo_ha':check,
                                   'independence_limit':'Compartilha os Parquets e o catalogo oficial com a producao; nao e verdade de campo.'})
    return {'dev':40,'test':120,'dev_families':10,'test_families':len({c['family_id'] for c in cases if c['split']=='test'}),'sha_cases':digest(cases)}
