"""Comandos cientificos opt-in, separados da consulta de producao."""
from pathlib import Path
import json
from .common import read


def add_parsers(sub):
    p=sub.add_parser('evaluate',help='Benchmark, congelamento, execucoes A/B/C e bootstrap pareado.')
    p.add_argument('--benchmark',type=Path,default=Path('benchmarks/pt_rn_v1'))
    s=p.add_subparsers(dest='evaluation_command',required=True)
    b=s.add_parser('build',help='Construir benchmark local de derivados; sem rede.')
    b.add_argument('--run-id',required=True)
    for action in ['freeze','run']:
        q=s.add_parser(action)
        q.add_argument('--local-config',type=Path,default=Path('configs/evaluation.json'))
        q.add_argument('--env-file',type=Path,help='Leitura opt-in, sem imprimir valores.')
        if action=='run':
            q.add_argument('--split',choices=['dev','test'],required=True)
            q.add_argument('--smoke',action='store_true')
            q.add_argument('--repeat',action='store_true')
            q.add_argument('--output',type=Path,required=True)
    s.add_parser('verify')
    a=s.add_parser('report');a.add_argument('--output',type=Path,required=True)
    s.add_parser('context-audit',help='Tamanho/completude dos contextos; sem chamadas LLM.')


def run(args,project):
    from .benchmark import build
    from .protocol import initialize,freeze,verify
    from .runner import execute, public_configuration
    from .statistics import aggregate
    from .common import save,canonical
    from ..delivery.settings import LocalSettings,load_environment
    root=Path.cwd();b=args.benchmark
    # Exportacoes nunca sobrescrevem dados ou arquivos privados de origem.
    resolved=b.resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved.relative_to(root.resolve()).parts[0]!='benchmarks':
        raise ValueError('benchmark_exige_diretorio_benchmarks')
    action=args.evaluation_command
    if action=='build':
        result=build(root,b,args.run_id);initialize(b)
    elif action in {'freeze','run'}:
        local=LocalSettings.load(args.local_config);env=load_environment(local,args.env_file)
        if not env.settings.configured:raise ValueError('configuracao_llm_ausente')
        cfg=public_configuration(local,env)
        if action=='freeze':result={'freeze_sha256':freeze(b,cfg)}
        else:
            target=args.output.resolve()
            if not target.is_relative_to((root/'artifacts/evaluation').resolve()):
                raise ValueError('execucao_exige_artifacts_evaluation')
            result=execute(root,b,args.output,args.split,project,local,env,args.smoke,args.repeat)
            result={k:result[k] for k in ['run_id','state','split','freeze_sha256']}
    elif action=='verify':result={'verified':bool(verify(b,root))}
    elif action=='report':
        result=aggregate(args.output,b)
        result={'report':str(args.output/'metrics.json'),'paired_C_minus_B':result['paired_C_minus_B']}
    else:
        facts=read(b/'facts.json');protocol=read(b/'protocol.json')
        sizes={k:len(canonical(v).encode()) for k,v in facts.items()}
        result={'cases':len(sizes),'maximum_bundle_bytes':max(sizes.values()),
                'over_limit':[k for k,v in sizes.items() if v>protocol['max_context_bytes_B']],
                'truncated':any(v.get('truncated') for v in facts.values()),
                'scalability_experiment':'pendente; esse diagnostico mede somente o contexto do benchmark, nao escala nacional'}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
