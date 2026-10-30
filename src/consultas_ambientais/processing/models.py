"""Contratos do processamento: status de execucao e qualidade sao independentes."""
from typing import Literal
from pydantic import Field
from ..contracts import Contract

METHOD = "ellipsoid-linear-lonlat-fractional-v1"
SCHEMA = "areas-geoespaciais-v1"

class ProcessingConfig(Contract):
    window_size: int = Field(default=512, ge=32, le=1024)
    max_memory_mb: int = Field(default=1024, ge=128, le=4096)
    gdal_cache_mb: int = Field(default=64, ge=8, le=128)
    max_download_bytes: int = Field(default=268435456, ge=1048576, le=1073741824)
    max_range_requests: int = Field(default=20000, ge=10, le=50000)
    max_cache_bytes: int = Field(default=536870912, ge=1048576, le=2147483648)
    max_crop_pixels: int = Field(default=180000000, ge=1024, le=250000000)
    max_seconds: int = Field(default=3600, ge=30, le=14400)
    http_timeout_seconds: float = Field(default=30, gt=0, le=120)
    range_block_bytes: int = Field(default=65536, ge=16384, le=1048576)
    # Predefinidas para float64/GEOS e verificacao independente, nao ajustaveis por CLI.
    conservation_relative_tolerance: Literal[1e-9] = 1e-9
    conservation_absolute_m2: Literal[0.01] = 0.01
    independent_relative_tolerance: Literal[1e-6] = 1e-6
    independent_absolute_m2: Literal[0.05] = 0.05

class ProcessingError(ValueError):
    """Apenas codigos estaticos e publicaveis; nao guardar excecoes da origem."""

class AreaRecord(Contract):
    schema_version: Literal["areas-geoespaciais-v1"] = SCHEMA
    run_id: str
    territory_code: str = Field(pattern=r"^(?:[0-9]{2}|[0-9]{7})$")
    territory_kind: Literal["municipio", "uf"]
    provenance: Literal["municipio_direto", "uf_direta"]
    mesh_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    geometry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    territorial_edition: str | None
    collection: Literal[11] = 11
    source_revision: str | None
    source_fingerprint: str
    catalog_sha256: str
    method: Literal["ellipsoid-linear-lonlat-fractional-v1"] = METHOD
    support: Literal["anual", "comum"]
    common_support_id: str | None
    year: int
    pair_start: int | None
    pair_end: int | None
    class_code: int
    area_m2: float | None = Field(ge=0)
    value_status: Literal["observado", "zero_real", "sem_suporte_valido"]
    unit: Literal["m2"] = "m2"
