"""Capacidades nao sao inferidas do intervalo configurado ou de uma amostra de pixels."""
import hashlib
from pathlib import Path

from ..contracts import CheckState, DiagnosticReport
from .catalog import CatalogError
from .models import Capabilities


def from_diagnostic(path:Path,classes,territories):
    raw=path.read_bytes()
    report=DiagnosticReport.model_validate_json(raw)
    years=[];samples=[]
    for check in report.checks:
        if not check.component.startswith("raster_") or check.state!=CheckState.VERIFIED:
            continue
        details=check.details
        meta=details.get("metadata",{})
        year=details.get("year")
        if (type(year) is not int or meta.get("year")!=year or meta.get("collection")!=11 or not details.get("range_verified")
                or details.get("window",{}).get("state")!="verificado"):
            continue
        years.append(year)
        value=details["window"].get("value")
        if type(value) is not int:raise CatalogError("amostra_de_classe_nao_inteira")
        samples.append({"year":year,"sample_size_pixels":1,
                        "diagnostic":classes.audit_codes([value],declared_nodata=meta.get("nodata")),
                        "inventory_complete":False})
    return Capabilities(class_catalog_sha256=classes.sha256,territory_catalog_sha256=territories.sha256,
        diagnostic_sha256=hashlib.sha256(raw).hexdigest(),available_raster_years=sorted(set(years)),
        materializations=[],engine_ready=False,observed_samples=samples)


def load_capabilities(path:Path):
    return Capabilities.model_validate_json(path.read_text())
