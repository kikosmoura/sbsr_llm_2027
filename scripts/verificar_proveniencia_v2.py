"""Verificacoes reais opt-in, limitadas; sem chamadas LLM nem alteracao de fontes."""
import argparse,json
from pathlib import Path
from consultas_ambientais.evaluation.common import read
from science.provenance_v2 import acquire_public,database_comments


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--output',type=Path,default=Path('artifacts/scientific/fontes_v2'))
    parser.add_argument('--public-rasters',action='store_true')
    parser.add_argument('--database-comments',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    targets=(['verificacao_publica.json'] if args.public_rasters else [])+(['metadados_malha.json'] if args.database_comments else [])
    if any((args.output/name).exists() for name in targets):
        print('Verificacao historica existente: selecione outro --output para preserva-la.')
        return 2
    policy=read(Path(__file__).resolve().parent.parent/'configs/science/revisao_v2.json')
    result={}
    if args.public_rasters:
        try:result['public_rasters']=acquire_public(args.root,args.output,policy)['state']
        except Exception:result['public_rasters']='indisponivel; verificacao interrompida sem presumir ausencia'
    if args.database_comments:result['database_comments']=database_comments(args.root,args.output)['state']
    print(json.dumps(result,ensure_ascii=False))
    return 2 if any(not state.startswith('verificado') for state in result.values()) else 0


if __name__=='__main__':raise SystemExit(main())
