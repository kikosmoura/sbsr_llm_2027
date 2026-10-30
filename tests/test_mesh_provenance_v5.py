"""Nao confundir arquivo indisponivel com geometria autenticada (sintetico)."""
import sys
from pathlib import Path
from shapely.geometry import Polygon,mapping
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from science.mesh_provenance_v5 import all_equal,compare

def test_missing_or_inaccessible_files_never_count_as_authenticated():
    assert not all_equal([])
    assert not all_equal([{'state':'indisponivel'},{'state':'indisponivel'}])

def test_exact_comparison_ignores_orientation_but_not_coordinates():
    g=Polygon([(0,0),(1,0),(1,1),(0,1)])
    snap={'crs':'EPSG:4326','features':[{'code':'2400109','kind':'municipio','name_original':'Sintetico',
        'geometry':mapping(g),'geometry_sha256':'fake','source_ewkb_sha256':'fake'}]}
    a=compare(snap,{'2400109':g.reverse()},'CRS sintetico','municipio')
    assert a['normalized_exact_matches']==1 and a['codes_equal']
    b=compare(snap,{'2400109':Polygon([(0,0),(1.001,0),(1,1),(0,1)])},'CRS sintetico','municipio')
    assert b['normalized_exact_matches']==0 and b['topological_exact_matches']==0
