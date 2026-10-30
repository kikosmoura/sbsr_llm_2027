"""Referencia independente: Geod/PROJ por pixel, com arestas densificadas."""
import numpy as np
import shapely
from shapely.geometry import shape,box
from shapely.geometry.polygon import orient
from pyproj import Geod
from rasterio.windows import Window,transform as window_transform
from .area import EllipsoidArea
from .common import now
from .models import ProcessingError,METHOD


def geodesic_reference_area(geom,step):
    dense=shapely.segmentize(geom,max_segment_length=step)
    geod=Geod(ellps="WGS84")
    def polygon(g):
        return abs(geod.geometry_area_perimeter(orient(g,sign=1.0))[0])
    return sum(polygon(g) for g in shapely.get_parts(dense) if g.geom_type=="Polygon")


def validate_real(features,datasets,years,leaves,config):
    """Janela 24x24 sobre uma borda real, sem consulta a estatisticas oficiais."""
    ds=datasets[0];feature=next(f for f in features if f["kind"]=="municipio")
    original=shape(feature["geometry"])
    parts=list(shapely.get_parts(original));polygon=max(parts,key=lambda x:x.area)
    coord=list(polygon.exterior.coords)[len(polygon.exterior.coords)//2]
    row,col=ds.index(*coord);row=max(0,min(ds.height-24,row-12));col=max(0,min(ds.width-24,col-12))
    win=Window(col,row,min(24,ds.width-col),min(24,ds.height-row));t=window_transform(win,ds.transform)
    geom=original.intersection(box(t.c,t.f+win.height*t.e,t.c+win.width*t.a,t.f))
    if geom.is_empty:raise ProcessingError("recorte_validacao_sem_geometria")
    method=EllipsoidArea(ds.crs);weights=method.weights(geom,t,(int(win.height),int(win.width)))
    reference=np.zeros_like(weights)
    for r,c in np.ndindex(weights.shape):
        x=t.c+c*t.a;y=t.f+r*t.e
        piece=geom.intersection(box(x,y+t.e,x+t.a,y))
        if not piece.is_empty:
            reference[r,c]=geodesic_reference_area(piece,min(t.a,-t.e)/8)
    checks=[]
    def check(name,a,b):
        tolerance=config.independent_absolute_m2+config.independent_relative_tolerance*abs(b)
        checks.append({"name":name,"production_m2":float(a),"reference_m2":float(b),
            "absolute_difference_m2":float(abs(a-b)),"tolerance_m2":float(tolerance),"passed":bool(abs(a-b)<=tolerance)})
    check("area_total_borda",weights.sum(),reference.sum())
    values=[d.read(1,window=win) for d in datasets];masks=[d.read_masks(1,window=win)>0 for d in datasets]
    valid=[mask & np.isin(v,leaves) for mask,v in zip(masks,values)];common=valid[0]&valid[1]
    for year,v,mask in zip(years,values,valid):
        for support,selected in [("anual",mask),("comum",common)]:
            for code in leaves:
                sel=selected & (v==code)
                check(f"{year}_{support}_{code}",weights[sel].sum(),reference[sel].sum())
    if not all(c["passed"] for c in checks):raise ProcessingError("validacao_independente_real_falhou")
    return {"state":"verificado","checked_at":now(),"kind":"recorte_real_com_referencia_independente",
        "method":METHOD,"reference":"pyproj.Geod WGS84; intersecao por pixel; arestas lonlat densificadas a 1/8 de pixel",
        "territory_code":feature["code"],"window":list(win.flatten()),"checks":checks,
        "unknown_codes":sorted(set(int(v) for a,m in zip(values,masks) for v in np.unique(a[m]))-set(leaves)),
        "official_statistics_compared":False}
