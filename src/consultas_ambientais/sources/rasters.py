"""Diagnostico HTTP e GeoTIFF com limite estrito de bytes recebidos por arquivo."""
import io
import math
import re

import requests

from ..contracts import Check, CheckState, RasterMetadata
from ..errors import network_issue
from ..settings import ProjectConfig


class RasterProbeError(OSError):
    def __init__(self,code,status=None):
        self.code=code
        self.status=status
        super().__init__(code)


class RangeSource:
    def __init__(self,url,config,session):
        self.url=url
        self.config=config
        self.session=session
        self.size=None
        self.headers={}
        self.head_status=None
        self.bytes_read=0
        self.request_count=0
        self.cache={}

    def probe(self):
        try:
            r=self.session.head(self.url,timeout=self.config.http_timeout_seconds,
                                allow_redirects=False,stream=True)
            self.head_status=r.status_code
            if r.status_code==200:
                self.headers={k:r.headers.get(k) for k in ["ETag","Last-Modified","Accept-Ranges"]}
            r.close()
        except requests.RequestException:
            self.head_status=None
        self.fetch(0,4096)

    def fetch(self,start,length):
        if self.size is not None:length=min(length,max(0,self.size-start))
        if not length:return b""
        if (self.request_count>=self.config.max_range_requests or
                self.bytes_read+length>self.config.max_bytes_per_raster):
            raise RasterProbeError("limite_leitura_atingido")
        self.request_count+=1
        try:
            r=self.session.get(self.url,headers={"Range":f"bytes={start}-{start+length-1}",
                                                "Accept-Encoding":"identity"},
                               stream=True,timeout=self.config.http_timeout_seconds,allow_redirects=False)
            try:
                if r.status_code!=206:
                    code={404:"ausente",401:"sem_acesso",403:"sem_acesso",200:"range_nao_suportado"}.get(r.status_code,"falha_http")
                    raise RasterProbeError(code,r.status_code)
                m=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",r.headers.get("Content-Range",""))
                if not m:raise RasterProbeError("content_range_invalido")
                first,last,size=map(int,m.groups())
                if first!=start or last<first or last>=size or last!=min(start+length-1,size-1):
                    raise RasterProbeError("content_range_invalido")
                if self.size is not None and self.size!=size:
                    raise RasterProbeError("objeto_alterado_durante_leitura")
                current_etag=r.headers.get("ETag")
                if self.headers.get("ETag") and current_etag and self.headers["ETag"]!=current_etag:
                    raise RasterProbeError("objeto_alterado_durante_leitura")
                self.size=size
                for k in ["ETag","Last-Modified"]:
                    if r.headers.get(k):self.headers[k]=r.headers[k]
                if r.headers.get("Content-Encoding", "identity")!="identity":
                    raise RasterProbeError("content_encoding_invalido")
                chunks=[]
                received=0
                expected=last-first+1
                for chunk in r.iter_content(chunk_size=min(4096,expected+1)):
                    received+=len(chunk)
                    self.bytes_read+=len(chunk)
                    if received>expected or self.bytes_read>self.config.max_bytes_per_raster:
                        raise RasterProbeError("limite_leitura_atingido")
                    chunks.append(chunk)
                if received!=expected:raise RasterProbeError("resposta_range_truncada")
                return b"".join(chunks)
            finally:
                r.close()
        except requests.Timeout:
            raise RasterProbeError("timeout") from None
        except requests.exceptions.SSLError:
            raise RasterProbeError("falha_tls") from None
        except requests.RequestException as e:
            raise RasterProbeError(network_issue(e)) from None

    def read_at(self,start,length):
        length=min(length,max(0,self.size-start))
        block_size=16384
        data=[]
        while length:
            block=start//block_size
            if block not in self.cache:
                self.cache[block]=self.fetch(block*block_size,block_size)
            offset=start%block_size
            value=self.cache[block][offset:offset+length]
            if not value:break
            data.append(value)
            start+=len(value)
            length-=len(value)
        return b"".join(data)


class RangeReader(io.RawIOBase):
    def __init__(self,source):
        super().__init__()
        self.source=source
        self.pos=0

    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos

    def seek(self,offset,whence=io.SEEK_SET):
        target=offset if whence==io.SEEK_SET else self.pos+offset if whence==io.SEEK_CUR else self.source.size+offset
        if target<0:raise RasterProbeError("seek_invalido")
        self.pos=target
        return self.pos

    def read(self,size=-1):
        if size is None or size<0 or size>self.source.config.max_bytes_per_raster:
            raise RasterProbeError("leitura_integral_bloqueada")
        data=self.source.read_at(self.pos,size)
        self.pos+=len(data)
        return data

    def readinto(self,buffer):
        data=self.read(len(buffer));buffer[:len(data)]=data
        return len(data)


def metadata_and_window(source,year,config):
    import numpy as np
    import rasterio
    from rasterio.windows import Window

    def opener(path,mode="rb"):
        if str(path)!="mapbiomas.tif":raise FileNotFoundError("arquivo auxiliar indisponivel")
        return RangeReader(source)

    # Leitor VSI Python e controlado pelo RangeSource; nao ha /vsicurl sem orcamento.
    with rasterio.Env(GDAL_PAM_ENABLED="NO",CPL_LOG="/dev/null"):
        with rasterio.open("mapbiomas.tif",opener=opener) as dataset:
            nodata=dataset.nodata
            if nodata is not None and not math.isfinite(nodata):nodata="non_finite"
            meta=RasterMetadata(year=year,collection=config.collection,
                source_revision=config.source_revision,catalog_schema=config.catalog_schema,
                width=dataset.width,height=dataset.height,band_count=dataset.count,
                crs=dataset.crs.to_string() if dataset.crs else None,
                transform=list(dataset.transform)[:6],resolution=list(dataset.res),
                dtypes=list(dataset.dtypes),nodata=nodata,
                block_shapes=[list(s) for s in dataset.block_shapes],
                compression=dataset.compression.value if dataset.compression else None,
                cog_layout=dataset.tags(ns="IMAGE_STRUCTURE").get("LAYOUT"),
                size_bytes=source.size,etag=source.headers.get("ETag"),
                last_modified=source.headers.get("Last-Modified"))
            window={"state":"pendente","shape":[1,1],"classification":"janela_diagnostica_nao_estatistica"}
            try:
                pixel=dataset.read(1,window=Window(dataset.width//2,dataset.height//2,1,1))
                value=pixel.item()
                window.update(state="verificado",value=value if np.isfinite(value) else None)
            except Exception:
                window.update(state="indisponivel",outcome="janela_nao_lida_dentro_do_orcamento")
            return meta,window


def diagnose_raster(config:ProjectConfig,year,session=None):
    owned=session is None
    session=session or requests.Session()
    source=RangeSource(config.raster_url(year),config,session)
    details={"year":year,"collection":config.collection,"source_kind":"espelho_informado",
             "official_revision_verified":False,"etag_is_sha256":False}
    def result(state,outcome,extra=None):
        return Check(component=f"raster_{year}",state=state,outcome=outcome,
                     details={**details,**(extra or {}),"bytes_read":source.bytes_read,
                              "range_requests":source.request_count})
    try:
        source.probe()
        details.update(range_verified=True,head_status=source.head_status)
        try:
            meta,window=metadata_and_window(source,year,config)
        except ImportError:
            return result(CheckState.PENDING,"dependencia_rasterio_ausente")
        details.update(metadata=meta.model_dump(mode="json"),window=window)
        valid=meta.crs is not None and meta.band_count==1 and all(t.startswith(("uint","int")) for t in meta.dtypes)
        details["metadata_valid_for_categorical_product"]=valid
        state=CheckState.VERIFIED if valid and window["state"]=="verificado" else CheckState.PENDING
        return result(state,"metadados_e_janela_verificados" if state==CheckState.VERIFIED else "validacao_incompleta")
    except RasterProbeError as e:
        return result(CheckState.UNAVAILABLE,e.code,{"http_status":e.status})
    except Exception:
        return result(CheckState.UNAVAILABLE,"metadados_invalidos_ou_limite_de_leitura")
    finally:
        if owned:session.close()


def compare_pilot_grids(checks,years):
    metas={c.details.get("year"):c.details.get("metadata") for c in checks if c.details.get("metadata")}
    if not all(y in metas for y in years):
        return Check(component="grade_piloto",state=CheckState.PENDING,
                     outcome="metadados_de_um_ou_mais_anos_indisponiveis",details={"years":years})
    a,b=(metas[y] for y in years)
    same=(a["crs"]==b["crs"] and a["crs"] is not None and a["width"]==b["width"] and a["height"]==b["height"]
          and all(math.isclose(x,y,rel_tol=0,abs_tol=1e-12) for x,y in zip(a["transform"],b["transform"])))
    return Check(component="grade_piloto",state=CheckState.VERIFIED,outcome="comparacao_executada",
                 details={"years":years,"same_grid":same,"same_collection":a["collection"]==b["collection"],
                          "same_official_revision":"nao_verificada","valid_mask_overlap":"nao_processada"})
