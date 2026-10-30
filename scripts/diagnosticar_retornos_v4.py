"""Diagnostico opt-in separado; nunca substitui os registros da V3."""
import argparse,json
from pathlib import Path
from science.gateway_diagnostics_v4 import prepare,run

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('--root',type=Path,default=Path.cwd());p.add_argument('--protocol',type=Path,default=Path('benchmarks/diagnostico_retornos_v1'))
    p.add_argument('--output',type=Path);p.add_argument('--env-file',type=Path);a=p.parse_args();code=Path(__file__).resolve().parent
    if a.action=='prepare':result=prepare(a.root,a.protocol,code)
    else:
        if not a.env_file or not a.output:p.error('run exige --env-file e --output')
        result=run(a.root,a.protocol,a.output,code,a.env_file)
    print(json.dumps({'state':result.get('state','congelado')}))

if __name__=='__main__':main()
