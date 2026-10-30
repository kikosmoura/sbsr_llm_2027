import os
from pathlib import Path
from uuid import uuid4

from ..contracts import DiagnosticReport


def write_report(report:DiagnosticReport,path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name("."+path.name+"."+uuid4().hex+".tmp")
    try:
        with temporary.open("x",encoding="utf-8") as f:
            os.chmod(temporary,0o600)
            f.write(report.model_dump_json(indent=2)+"\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
