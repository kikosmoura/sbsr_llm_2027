"""Aquisição limitada de dois ZIPs oficiais RN/IBGE 2025; leitura local da malha."""
import argparse,json
from pathlib import Path
from science.mesh_provenance_v5 import acquire
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path.cwd());p.add_argument('--output',type=Path,default=Path('artifacts/scientific/fontes_v5'))
    p.add_argument('--offline',action='store_true',help='regerar inventario a partir da aquisicao registrada, sem rede')
    a=p.parse_args();r=acquire(a.root,a.output,a.offline)
    print(json.dumps({'files':len(r['official_files']),'all_numeric_geometries_equal':r['all_numeric_geometries_equal'],
                     'comparisons':[{k:f.get('comparison',{}).get(k) for k in ['features','normalized_exact_matches','topological_exact_matches','official_crs','snapshot_crs']} for f in r['official_files']]}))
if __name__=='__main__':main()
