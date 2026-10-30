"""Staging regional em resolucao nativa; cache persistente de ranges verificados."""
import io
import math
import os
import time
from collections import OrderedDict
from contextlib import ExitStack
from pathlib import Path
import hashlib
import json
import requests
import numpy as np
import rasterio
from rasterio.windows import Window,from_bounds,transform as window_transform
from shapely.geometry import shape
from shapely.ops import unary_union
from ..sources.rasters import RangeSource,RangeReader,RasterProbeError
from ..semantics.catalog import digest
from .common import atomic_json,sha_file,now
from .models import ProcessingError
from .area import EllipsoidArea

class Budget:
    def __init__(self,config):
        self.config=config;self.started=time.monotonic();self.bytes=0;self.requests=0;self.peak_rss=0
    def check(self):
        import psutil
        rss=psutil.Process().memory_info().rss
        self.peak_rss=max(self.peak_rss,rss)
        if rss>self.config.max_memory_mb*1048576:raise ProcessingError("limite_memoria")
        if time.monotonic()-self.started>self.config.max_seconds:raise ProcessingError("limite_tempo")
        if self.bytes>self.config.max_download_bytes:raise ProcessingError("limite_download")
        if self.requests>self.config.max_range_requests:raise ProcessingError("limite_requisicoes")
    def report(self):
        return {"download_bytes":self.bytes,"range_requests":self.requests,
            "elapsed_seconds":time.monotonic()-self.started,"peak_rss_bytes":self.peak_rss}

class CachedSource(RangeSource):
    def __init__(self,url,config,session,cache_root,budget):
        # A sondagem e o processamento possuem orcamentos independentes.
        from types import SimpleNamespace
        limits=SimpleNamespace(http_timeout_seconds=config.http_timeout_seconds,
            max_bytes_per_raster=config.max_download_bytes,max_range_requests=config.max_range_requests)
        super().__init__(url,limits,session)
        self.processing=config;self.budget=budget;self.root=Path(cache_root)
        self.root.mkdir(parents=True,exist_ok=True)
        if not hasattr(budget,"cache_disk_bytes"):
            budget.cache_disk_bytes=sum(f.stat().st_size for f in self.root.rglob("*.bin"))
        self.memory=OrderedDict();self.used={};self.identity=None;self.directory=None

    def fetch(self,start,length):
        self.budget.check()
        if self.budget.bytes+length>self.processing.max_download_bytes or self.budget.requests>=self.processing.max_range_requests:
            raise ProcessingError("limite_io_antes_da_requisicao")
        before=self.bytes_read;requests_before=self.request_count
        try:return super().fetch(start,length)
        finally:
            self.budget.bytes+=self.bytes_read-before
            self.budget.requests+=self.request_count-requests_before
            self.budget.check()

    def probe(self):
        super().probe()
        # Sem identidade HTTP reproduzivel, nao reutilizar cache persistente entre execucoes.
        if not self.headers.get("ETag") and not self.headers.get("Last-Modified"):
            raise ProcessingError("identidade_http_insuficiente_para_cache")
        self.identity={"url":self.url,"size":self.size,"etag":self.headers.get("ETag"),
            "last_modified":self.headers.get("Last-Modified"),"official_revision_verified":False}
        self.directory=self.root/digest(self.identity)
        self.directory.mkdir(parents=True,exist_ok=True)
        inventory=self.directory/"chunks.json"
        self.inventory=json.loads(inventory.read_text()) if inventory.exists() else {}

    def read_at(self,start,length):
        length=min(length,max(0,self.size-start));values=[];block_size=self.processing.range_block_bytes
        while length:
            block=start//block_size;key=str(block)
            if key in self.memory:
                raw=self.memory.pop(key);self.memory[key]=raw
            else:
                path=self.directory/(key+".bin")
                if path.exists():
                    raw=path.read_bytes()
                    if self.inventory.get(key)!=hashlib.sha256(raw).hexdigest():
                        raise ProcessingError("cache_corrompido")
                else:
                    raw=self.fetch(block*block_size,block_size)
                    if self.budget.cache_disk_bytes+len(raw)>self.processing.max_cache_bytes:
                        raise ProcessingError("limite_cache_disco")
                    temp=path.with_suffix(".tmp");temp.write_bytes(raw);os.replace(temp,path)
                    self.budget.cache_disk_bytes+=len(raw)
                    self.inventory[key]=hashlib.sha256(raw).hexdigest()
                    atomic_json(self.directory/"chunks.json",self.inventory)
                self.memory[key]=raw
                while len(self.memory)>8:self.memory.popitem(last=False)
            self.used[key]={"offset":block*block_size,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
            value=raw[start%block_size:start%block_size+length]
            if not value:break
            values.append(value);start+=len(value);length-=len(value)
        return b"".join(values)


def integer_window(bounds,dataset):
    w=from_bounds(*bounds,transform=dataset.transform)
    c0=max(0,math.floor(w.col_off));r0=max(0,math.floor(w.row_off))
    c1=min(dataset.width,math.ceil(w.col_off+w.width));r1=min(dataset.height,math.ceil(w.row_off+w.height))
    if c1<=c0 or r1<=r0:raise ProcessingError("recorte_fora_do_raster")
    return Window(c0,r0,c1-c0,r1-r0)


def grid_signature(ds):
    return {"crs":ds.crs.to_string() if ds.crs else None,"width":ds.width,"height":ds.height,
        "transform":list(ds.transform)[:6],"count":ds.count,"dtype":ds.dtypes[0],"nodata":ds.nodata}


def stage_pair(project,config,snapshot,features,root,budget=None):
    """Abre cada raster remoto uma vez e grava apenas a janela regional solicitada."""
    budget=budget or Budget(config);root=Path(root)
    cache=root/project.cache_dir;artifacts=root/project.artifacts_dir
    bounds=unary_union([shape(f["geometry"]) for f in features]).bounds
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_PAM_ENABLED="NO",CPL_LOG="/dev/null",
            GDAL_CACHEMAX=config.gdal_cache_mb*1048576,GDAL_TIFF_INTERNAL_MASK=True))
        session=stack.enter_context(requests.Session());sources=[];datasets=[]
        for year in project.pilot_years:
            source=CachedSource(project.raster_url(year),config,session,cache/"ranges",budget)
            source.probe();sources.append(source)
            def opener(path,mode="rb",source=source):
                if str(path)!="mapbiomas.tif":raise FileNotFoundError("auxiliar_nao_usado")
                return RangeReader(source)
            ds=stack.enter_context(rasterio.open("mapbiomas.tif",opener=opener));datasets.append(ds)
        signatures=[grid_signature(d) for d in datasets]
        # NoData pode diferir entre os anos; grade e produto precisam coincidir.
        compare=lambda s:{k:v for k,v in s.items() if k!="nodata"}
        if compare(signatures[0])!=compare(signatures[1]):
            raise ProcessingError("grades_incompativeis_sem_reprojecao_validada")
        ds=datasets[0];EllipsoidArea(ds.crs).validate_grid(ds.transform)
        if ds.count!=1 or ds.dtypes[0] not in {"uint8","uint16","int16","int32"}:
            raise ProcessingError("produto_categorico_incompativel")
        window=integer_window(bounds,ds)
        if window.width*window.height>config.max_crop_pixels:raise ProcessingError("limite_pixels_recorte")
        identity={"mesh_sha256":snapshot["mesh_sha256"],"geometry_hashes":sorted(f["geometry_sha256"] for f in features),
            "sources":[s.identity for s in sources],"window":list(window.flatten()),
            "grid":signatures,"collection":project.collection,"source_revision":project.source_revision}
        key=digest(identity);directory=artifacts/"staging"/key;directory.mkdir(parents=True,exist_ok=True)
        manifest_path=directory/"manifest.json"
        if manifest_path.exists():
            manifest=json.loads(manifest_path.read_text())
            if manifest["identity"]!=identity:raise ProcessingError("identidade_staging_divergente")
            for f in manifest["files"]:
                if sha_file(directory/f["name"])!=f["sha256"]:raise ProcessingError("staging_corrompido")
            return manifest,[directory/f["name"] for f in manifest["files"]],budget
        profile=ds.profile.copy()
        profile.update(driver="GTiff",width=int(window.width),height=int(window.height),
            transform=window_transform(window,ds.transform),compress="deflate",tiled=True,
            blockxsize=256,blockysize=256)
        files=[]
        for year,src,source in zip(project.pilot_years,datasets,sources):
            name=f"native_{year}.tif";path=directory/name;temp=directory/(name+".tmp")
            file_profile={**profile,"nodata":src.nodata}
            # Interrupcoes reaproveitam ranges verificados, nunca um TIFF parcialmente escrito.
            with rasterio.open(temp,"w",**file_profile) as target:
                for row in range(0,int(window.height),config.window_size):
                    for col in range(0,int(window.width),config.window_size):
                        budget.check();h=min(config.window_size,int(window.height)-row);w=min(config.window_size,int(window.width)-col)
                        local=Window(col,row,w,h);native=Window(window.col_off+col,window.row_off+row,w,h)
                        target.write(src.read(1,window=native),1,window=local)
                        target.write_mask(src.read_masks(1,window=native),window=local)
            os.replace(temp,path)
            files.append({"year":year,"name":name,"sha256":sha_file(path),"bytes":path.stat().st_size,
                "source":source.identity,"source_chunks":list(source.used.values()),"native_grid":signatures[len(files)]})
        manifest={"schema_version":"staging-nativo-v1","created_at":now(),"staging_id":key,"identity":identity,
            "strategy":"staging_regional_range_uma_abertura_por_ano","files":files,"resources":budget.report(),
            "overviews_used":False,"resampling":None,"national_file_sha256":None}
        atomic_json(manifest_path,manifest)
        return manifest,[directory/f["name"] for f in files],budget
