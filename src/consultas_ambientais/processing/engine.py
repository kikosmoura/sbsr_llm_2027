"""Areas anuais e comparaveis no mesmo suporte; nenhum codigo e reamostrado."""
import hashlib
import time
import numpy as np
import rasterio
from rasterio.windows import Window,transform as window_transform
from shapely.geometry import shape,box
from ..semantics.catalog import digest
from .area import EllipsoidArea
from .models import AreaRecord,ProcessingError,METHOD
from .raster_io import integer_window,grid_signature


def summarize(values,mask,weights,leaves):
    declared=np.asarray(mask,dtype=bool)
    known=declared & np.isin(values,leaves)
    unknown=declared & ~known
    areas=np.bincount(values[known].astype(int),weights=weights[known],minlength=max(leaves)+1)
    active=unknown & (weights>0)
    unknown_codes={str(int(c)):float(weights[active & (values==c)].sum()) for c in np.unique(values[active])}
    return areas,known,{"observed_area_m2":float(weights[known].sum()),
        "nodata_area_m2":float(weights[~declared].sum()),"unknown_area_m2":float(weights[unknown].sum()),
        "unknown_codes_m2":unknown_codes}


def compute_feature(feature,datasets,years,leaves,run_context,config,budget):
    started=time.monotonic();geom=shape(feature["geometry"])
    if not feature["repair"]["accepted"]:raise ProcessingError("reparo_territorial_requer_revisao")
    if grid_signature(datasets[0])!={**grid_signature(datasets[1]),"nodata":datasets[0].nodata}:
        raise ProcessingError("grades_locais_incompativeis")
    method=EllipsoidArea(datasets[0].crs);ds=datasets[0]
    total=method.area(geom);inside_geom=geom.intersection(box(*ds.bounds))
    inside=method.area(inside_geom);outside=max(0,total-inside)
    accum={(support,year):np.zeros(max(leaves)+1) for support in ["anual","comum"] for year in years}
    quality={(support,year):{"observed_area_m2":0.,"nodata_area_m2":0.,"unknown_area_m2":0.,"unknown_codes_m2":{}} for support in ["anual","comum"] for year in years}
    support_hash=hashlib.sha256();weighted_inside=0.;read_pixels=0;windows=0
    if not inside_geom.is_empty:
        extent=integer_window(inside_geom.bounds,ds)
        for row in range(int(extent.row_off),int(extent.row_off+extent.height),config.window_size):
            for col in range(int(extent.col_off),int(extent.col_off+extent.width),config.window_size):
                budget.check()
                h=min(config.window_size,int(extent.row_off+extent.height)-row);w=min(config.window_size,int(extent.col_off+extent.width)-col)
                win=Window(col,row,w,h);t=window_transform(win,ds.transform)
                if not geom.intersects(box(t.c,t.f+h*t.e,t.c+w*t.a,t.f)):continue
                weights=method.weights(geom,t,(h,w));weighted_inside+=float(weights.sum())
                if not np.any(weights):continue
                values=[d.read(1,window=win) for d in datasets]
                masks=[d.read_masks(1,window=win)>0 for d in datasets]
                read_pixels+=h*w*2;windows+=1
                known=[]
                for value,mask,year in zip(values,masks,years):
                    areas,valid,q=summarize(value,mask,weights,leaves);known.append(valid)
                    accum["anual",year]+=areas
                    _add_quality(quality["anual",year],q)
                common=known[0]&known[1]
                support_hash.update(np.asarray([row,col,h,w],dtype="<i8").tobytes())
                support_hash.update(np.packbits(common & (weights>0)).tobytes())
                both_masks=masks[0]&masks[1]
                unknown=both_masks & ~common
                code_pair={}
                codes={int(c) for value in values for c in np.unique(value[unknown & (weights>0)]) if int(c) not in leaves}
                for code in codes:
                    code_pair[str(code)]=float(weights[unknown & ((values[0]==code)|(values[1]==code))].sum())
                q={"observed_area_m2":float(weights[common].sum()),"nodata_area_m2":float(weights[~both_masks].sum()),
                   "unknown_area_m2":float(weights[unknown].sum()),"unknown_codes_m2":code_pair}
                for value,year in zip(values,years):
                    accum["comum",year]+=np.bincount(value[common].astype(int),weights=weights[common],minlength=max(leaves)+1)
                    _add_quality(quality["comum",year],q)
    tolerance=config.conservation_absolute_m2+config.conservation_relative_tolerance*total
    error=abs(weighted_inside-inside)
    if error>tolerance:raise ProcessingError("falha_conservacao_geometrica")
    common_id=digest({"run_id":run_context["run_id"],"code":feature["code"],"years":years,"mask_sha256":support_hash.hexdigest()})
    records=[];qs=[]
    for (support,year),areas in accum.items():
        q=quality[support,year]
        partition_error=abs(q["observed_area_m2"]+q["nodata_area_m2"]+q["unknown_area_m2"]-inside)
        class_error=abs(float(sum(areas[c] for c in leaves))-q["observed_area_m2"])
        if max(partition_error,class_error)>tolerance:raise ProcessingError("falha_conservacao_classes_e_mascaras")
        complete=q["observed_area_m2"]>0 and q["nodata_area_m2"]+q["unknown_area_m2"]+outside<=tolerance
        qs.append({"run_id":run_context["run_id"],"territory_code":feature["code"],"territory_kind":feature["kind"],
            "year":year,"support":support,"common_support_id":common_id if support=="comum" else None,
            "total_area_m2":total,"inside_raster_area_m2":inside,"outside_raster_area_m2":outside,**q,
            "processing_status":"completo","quality_status":"completo" if complete else "parcial",
            "eligible_complete":bool(complete),"conservation_error_m2":max(error,partition_error,class_error),
            "conservation_tolerance_m2":tolerance})
        for code in leaves:
            value=float(areas[code]) if q["observed_area_m2"]>0 else None
            record=AreaRecord(**run_context,territory_code=feature["code"],territory_kind=feature["kind"],
                provenance="uf_direta" if feature["kind"]=="uf" else "municipio_direto",
                geometry_sha256=feature["geometry_sha256"],support=support,common_support_id=common_id if support=="comum" else None,
                year=year,pair_start=years[0] if support=="comum" else None,pair_end=years[1] if support=="comum" else None,
                class_code=code,area_m2=value,value_status="sem_suporte_valido" if value is None else "zero_real" if value==0 else "observado")
            records.append(record.model_dump(mode="json"))
    return records,qs,{"elapsed_seconds":time.monotonic()-started,"read_pixels":read_pixels,"windows":windows,
        "common_mask_sha256":support_hash.hexdigest(),"method":METHOD}


def _add_quality(target,source):
    for k in ["observed_area_m2","nodata_area_m2","unknown_area_m2"]:target[k]+=source[k]
    for code,area in source["unknown_codes_m2"].items():
        target["unknown_codes_m2"][code]=target["unknown_codes_m2"].get(code,0)+area
