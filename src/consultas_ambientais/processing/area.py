"""Intersecao GEOS fracionaria + integral de superficie no elipsoide do CRS.

Arestas da malha sao lineares em longitude/latitude; meridianos e paralelos
mantem sua definicao nativa. Nao e area esferica nem area cartesiana em graus.
"""
import numpy as np
import shapely
from pyproj import CRS
from rasterio.features import rasterize
from .models import ProcessingError

class EllipsoidArea:
    def __init__(self, crs):
        self.crs=CRS.from_user_input(crs)
        if not self.crs.is_geographic or self.crs.to_epsg()!=4326:
            raise ProcessingError("crs_nao_validado_para_metodo_4326")
        ell=self.crs.ellipsoid
        self.a=ell.semi_major_metre
        self.e2=1-(ell.semi_minor_metre/self.a)**2
        self.e=np.sqrt(self.e2)
        self.nodes,self.coeff=np.polynomial.legendre.leggauss(4)

    def primitive(self,latitude):
        s=np.sin(np.deg2rad(latitude))
        if self.e==0: return self.a**2*s
        return self.a**2*(1-self.e2)/2*(s/(1-self.e2*s*s)+np.arctanh(self.e*s)/self.e)

    def row_areas(self,transform,height):
        self.validate_grid(transform)
        y=transform.f+np.arange(height+1)*transform.e
        return np.abs(np.diff(self.primitive(y))*np.deg2rad(transform.a))

    def validate_grid(self,t):
        if t.b!=0 or t.d!=0 or t.a<=0 or t.e>=0 or max(t.a,-t.e)>0.01:
            raise ProcessingError("grade_rotacionada_ou_resolucao_nao_validada")

    def areas(self,geometries):
        """Integral de linha com quadratura Gauss-4, vetorizada por geometria."""
        arr=np.atleast_1d(np.asarray(geometries,dtype=object))
        out=np.zeros(len(arr),dtype=float)
        parts,owners=shapely.get_parts(arr,return_index=True)
        is_poly=shapely.get_type_id(parts)==3
        parts=shapely.orient_polygons(parts[is_poly],exterior_cw=False)
        owners=owners[is_poly]
        if not len(parts):return out
        rings,rp=shapely.get_rings(parts,return_index=True)
        coords,ri=shapely.get_coordinates(rings,return_index=True)
        if len(coords)<2:return out
        good=ri[:-1]==ri[1:]
        start=coords[:-1][good];end=coords[1:][good]
        go=owners[rp[ri[:-1][good]]]
        # Subtracao de uma constante por anel reduz cancelamento; integral fechada e invariante.
        centers=np.bincount(ri,weights=coords[:,1])/np.bincount(ri)
        reference=self.primitive(centers[ri[:-1][good]])
        dl=np.deg2rad(end[:,0]-start[:,0]); total=np.zeros(len(start))
        for node,weight in zip(self.nodes,self.coeff):
            lat=(start[:,1]+end[:,1])/2+(end[:,1]-start[:,1])*node/2
            total+=weight*(self.primitive(lat)-reference)
        out=np.bincount(go,weights=-dl*total/2,minlength=len(arr))
        if np.min(out,initial=0)<-0.01:raise ProcessingError("integral_de_area_negativa")
        return np.maximum(out,0)

    def area(self,geom): return float(self.areas([geom])[0])

    def weights(self,geom,transform,shape):
        """Interior por linha; somente bordas exigem intersecoes exatas por pixel."""
        h,w=shape
        self.validate_grid(transform)
        center=rasterize([(geom,1)],out_shape=shape,transform=transform,dtype="uint8")
        border=rasterize([(geom.boundary,1)],out_shape=shape,transform=transform,
                         all_touched=True,dtype="uint8")
        weights=center*self.row_areas(transform,h)[:,None]
        rr,cc=np.nonzero(border)
        if len(rr):
            left=transform.c+cc*transform.a;top=transform.f+rr*transform.e
            cells=shapely.box(left,top+transform.e,left+transform.a,top)
            pieces=shapely.intersection(cells,geom)
            weights[rr,cc]=self.areas(pieces)
        return weights
