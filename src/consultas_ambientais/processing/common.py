import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from .models import ProcessingError

def now(): return datetime.now(timezone.utc).isoformat()

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""): h.update(b)
    return h.hexdigest()

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False))
    os.replace(temp,path)

def confined(path,root):
    p=Path(path).resolve();r=Path(root).resolve()
    if not p.is_relative_to(r): raise ProcessingError("caminho_fora_da_area_local")
    return p
