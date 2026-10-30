"""Controle completo 4096, opt-in de gateway e congelado separadamente."""
import argparse,json
from pathlib import Path
from science.sensitivity_v5 import prepare,run

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('--root',type=Path,default=Path.cwd());p.add_argument('--benchmark',type=Path,default=Path('benchmarks/controle_contrato_4096_v1'))
    p.add_argument('--output',type=Path);p.add_argument('--split',choices=['dev','test'],default='dev');p.add_argument('--env-file',type=Path);p.add_argument('--repeat',action='store_true')
    a=p.parse_args();code=Path(__file__).resolve().parent
    if a.action=='prepare':result=prepare(a.root,a.benchmark,code)
    else:
        if not a.env_file or not a.output:p.error('run exige --env-file e --output')
        result=run(a.root,a.benchmark,a.output,code,a.split,a.env_file,a.repeat)
    print(json.dumps({'state':result.get('state','congelado')}))

if __name__=='__main__':main()
