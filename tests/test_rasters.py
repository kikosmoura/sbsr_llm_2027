import io

import numpy as np
import pytest
import requests
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from consultas_ambientais.settings import ProjectConfig
from consultas_ambientais.sources.rasters import RangeSource,RangeReader,RasterProbeError,diagnose_raster,compare_pilot_grids


def response(status,data=b"",headers=None):
    r=requests.Response();r.status_code=status;r.headers.update(headers or {})
    r._content=data;r._content_consumed=True
    return r


class RangeSession:
    def __init__(self,data,status=206):self.data=data;self.status=status;self.calls=[]
    def head(self,url,**kwargs):return response(200,headers={"Content-Length":str(len(self.data)),"ETag":"test-etag"})
    def get(self,url,headers,**kwargs):
        self.calls.append(headers["Range"])
        start,end=map(int,headers["Range"].removeprefix("bytes=").split("-"))
        end=min(end,len(self.data)-1)
        return response(self.status,self.data[start:end+1],{"Content-Range":f"bytes {start}-{end}/{len(self.data)}","ETag":"test-etag"})
    def close(self):pass


def geotiff():
    with MemoryFile() as mem:
        with mem.open(driver="GTiff",width=32,height=32,count=1,dtype="uint8",crs="EPSG:4326",
                      transform=from_origin(-36,-5,0.001,0.001),nodata=0) as dst:
            dst.write(np.full((1,32,32),15,dtype="uint8"))
        return mem.read()


def test_range_reader_seek_and_budget():
    data=bytes(range(256))*256;session=RangeSession(data)
    source=RangeSource("https://example.test/data.tif",ProjectConfig(max_bytes_per_raster=49152),session)
    source.probe();reader=RangeReader(source)
    reader.seek(100);assert reader.read(100)==data[100:200]
    reader.seek(-10,io.SEEK_END);assert reader.read(10)==data[-10:]
    with pytest.raises(RasterProbeError):reader.read()
    with pytest.raises(RasterProbeError):source.fetch(32768,16384)
    assert source.bytes_read<=49152


def test_200_does_not_trigger_full_download():
    session=RangeSession(b"x"*100,status=200)
    source=RangeSource("https://example.test/data.tif",ProjectConfig(),session)
    with pytest.raises(RasterProbeError) as exc:source.probe()
    assert exc.value.code=="range_nao_suportado" and source.bytes_read==0


def test_geotiff_metadata_and_window_via_bounded_opener():
    session=RangeSession(geotiff())
    report=diagnose_raster(ProjectConfig(),2015,session)
    assert report.state.value=="verificado",report
    assert report.details["metadata"]["crs"]=="EPSG:4326"
    assert report.details["window"]["value"]==15
    assert report.details["metadata"]["etag"]=="test-etag"
    assert 0<report.details["bytes_read"]<=ProjectConfig().max_bytes_per_raster


def test_non_tiff_and_grid_unknown():
    report=diagnose_raster(ProjectConfig(),2015,RangeSession(b"not-a-tiff"))
    assert report.state.value=="indisponivel"
    assert compare_pilot_grids([report],[2015,2025]).state.value=="pendente"


def test_grid_comparison_is_not_product_revision_verification():
    reports=[diagnose_raster(ProjectConfig(),y,RangeSession(geotiff())) for y in [2015,2025]]
    result=compare_pilot_grids(reports,[2015,2025])
    assert result.details["same_grid"] is True
    assert result.details["same_official_revision"]=="nao_verificada"
