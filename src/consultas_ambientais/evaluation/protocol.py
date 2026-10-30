"""Congelamento verificavel; o runner nao aceita prompts, gold ou fontes alterados."""
from pathlib import Path
from .common import read, sha, save, now, digest
from .models import BaselineAnswer
from ..semantics.catalog import ClassCatalog
from ..queries.engine import executor_digest
from ..llm.prompting import interpreter_digest, PromptBundle


def default_protocol():
    return {'version':'pt-rn-v1','development_cases':40,'test_cases':120,
            'primary_comparison':'C-B; acerto ponta a ponta em todos os casos',
            'numeric_subset':'analise secundaria predefinida dos pedidos com resposta numerica de referencia',
            'bootstrap_replicas':10000,'seed':20271019,'minimum_territory_groups':10,
            'absolute_tolerance':{'ha':'0.0001','km2':'0.000001','m2':'1','percentual':'0.001','pontos_percentuais':'0.001'},
            'relative_tolerance':'0.000001',
            'tolerance_rationale':'Representacao numerica e aritmetica textual com dez algarismos; nao e tolerancia de erro do mapa.',
            'tie_rule':'valores nao arredondados; empate exato por codigo IBGE crescente; ordem completa exigida',
            'primary_denominator':'todos os casos previstos, inclusive erro tecnico; pares faltantes impedem IC',
            'decision_scoring':'status exato; esclarecimento exige campo correto e nenhum valor; recusas sem numero. Plano informado nas duas pontas tambem deve coincidir.',
            'numeric_scoring':'status, operacao, territorios, uniao de folhas, anos, metrica, unidade, denominador, valores e ordem de ranking',
            'dev_smoke_case_ids':['d01_1','d02_1','d04_1','d06_1','d07_1','d08_1','d09_1','d10_1'],
            'repeat_case_ids':['t01_1','t15_1','t25_1','t28_1'],
            'run_order':'casos intercalados; ordem A/B/C rotativa por indice, com concorrencia registrada',
            'max_context_bytes_B':131072,'context_overflow':'erro_tecnico, sem truncamento; fora do experimento principal se desenho nao comportar fatos',
            'scalability_experiment':'separado; apenas mede tamanho dos contextos, nao mistura com acerto',
            'human_review':'nao_realizada','test_prompt_tuning':'proibido',
            'repeatability':'amostra predefinida, sem garantia de determinismo por temperature zero'}


def initialize(benchmark):
    b=Path(benchmark)
    save(b/'protocol.json',default_protocol())
    save(b/'baseline.schema.json',BaselineAnswer.model_json_schema())
    save(b/'classes.json',{str(c.code):c.leaf_codes for c in ClassCatalog.load().data.classes})


def code_hashes():
    base=Path(__file__).parent
    return {str(p.relative_to(base)):sha(p) for p in sorted(base.rglob('*')) if p.is_file() and p.suffix in {'.py','.txt'}}


def freeze(benchmark, configuration):
    b=Path(benchmark)
    if (b/'freeze.json').exists():raise ValueError('congelamento_existente_imutavel')
    value={'created_at':now(),'files':{p.name:sha(p) for p in sorted(b.iterdir()) if p.is_file()},
           'evaluation_code':code_hashes(),'executor_sha256':executor_digest(),
           'interpreter_sha256':interpreter_digest(),'production_prompt_hashes':PromptBundle().hashes,
           'configuration':configuration,'protocol':'avaliacao-congelada-v1'}
    save(b/'freeze.json',value)
    return sha(b/'freeze.json')


def verify(benchmark, root=None, configuration=None):
    b=Path(benchmark);f=read(b/'freeze.json')
    if {name:sha(b/name) for name in f['files']}!=f['files']:
        raise ValueError('benchmark_congelado_divergente')
    if code_hashes()!=f['evaluation_code'] or executor_digest()!=f['executor_sha256'] or interpreter_digest()!=f['interpreter_sha256'] or PromptBundle().hashes!=f['production_prompt_hashes']:
        raise ValueError('codigo_ou_prompt_congelado_divergente')
    if configuration is not None and configuration!=f['configuration']:
        raise ValueError('configuracao_diverge_do_congelamento')
    if root is not None:
        for name,expected in read(b/'sources.json')['input_hashes'].items():
            if sha(Path(root)/name)!=expected:raise ValueError('fonte_congelada_divergente')
    return sha(b/'freeze.json')
