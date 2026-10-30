"""Parquet por unidade e indice DuckDB local; retomada verifica hashes e linhas."""
import json
import os
from pathlib import Path
import duckdb
from ..processing.common import atomic_json,sha_file
from ..processing.models import AreaRecord,ProcessingError

AREA_TYPES={"area_m2":"DOUBLE","year":"INTEGER","pair_start":"INTEGER","pair_end":"INTEGER","class_code":"INTEGER","collection":"INTEGER"}
QUALITY_TYPES={"year":"INTEGER","eligible_complete":"BOOLEAN",**{n:"DOUBLE" for n in ["total_area_m2","inside_raster_area_m2","outside_raster_area_m2","observed_area_m2","nodata_area_m2","unknown_area_m2","conservation_error_m2","conservation_tolerance_m2"]}}

class AreaStore:
    def __init__(self,root,config):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.conn=duckdb.connect(str(self.root/"areas.duckdb"))
        self.conn.execute("SET threads=1")
        self.conn.execute("SET memory_limit=?",[f"{max(64,config.max_memory_mb//4)}MB"])
        self.conn.execute("SET allowed_directories=?",[[str(self.root.resolve())]])
        self.conn.execute("SET enable_external_access=false")
    def close(self):self.conn.close()

    def _table(self,name,rows,types):
        columns=list(rows[0])
        if any(list(row)!=columns for row in rows):raise ProcessingError("linhas_armazenamento_incoerentes")
        spec=", ".join(f'"{c}" {types.get(c,"VARCHAR")}' for c in columns)
        self.conn.execute(f'CREATE TABLE IF NOT EXISTS "{name}" ({spec})')
        return columns

    def complete(self,run_id,code):
        path=self.root/run_id/code/"manifest.json"
        if not path.exists():return None
        m=json.loads(path.read_text())
        if m.get("run_id")!=run_id or m.get("territory_code")!=code:raise ProcessingError("manifest_particao_invalido")
        for f in m["files"]:
            if sha_file(path.parent/f["name"])!=f["sha256"]:raise ProcessingError("particao_corrompida")
        # Recuperar indice local mesmo se o DuckDB foi removido ou a transacao interrompida.
        for table in ["areas","quality"]:
            file=path.parent/(table+".parquet")
            self.conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" AS SELECT * FROM read_parquet(?) LIMIT 0',[str(file)])
            self.conn.execute(f'DELETE FROM "{table}" WHERE run_id=? AND territory_code=?',[run_id,code])
            self.conn.execute(f'INSERT INTO "{table}" SELECT * FROM read_parquet(?)',[str(file)])
        return m

    def commit(self,run_id,code,areas,quality,resources):
        directory=self.root/run_id/code;directory.mkdir(parents=True,exist_ok=True)
        if any(r["run_id"]!=run_id or r["territory_code"]!=code for r in [*areas,*quality]):
            raise ProcessingError("identidade_das_linhas_diverge_da_particao")
        qrows=[{**q,"unknown_codes_m2":json.dumps(q["unknown_codes_m2"],sort_keys=True)} for q in quality]
        self.conn.execute("BEGIN TRANSACTION")
        files=[]
        try:
            for table,rows,types in [("areas",areas,AREA_TYPES),("quality",qrows,QUALITY_TYPES)]:
                columns=self._table(table,rows,types)
                self.conn.execute(f'DELETE FROM "{table}" WHERE run_id=? AND territory_code=?',[run_id,code])
                # Uma insercao tipada por lote: executemany do binding 1.4.1 reteve
                # memoria proporcional a linhas/colunas no perfil desta carga.
                fields=", ".join(f"CAST(json_extract_string(value, '$.{c}') AS {types.get(c,'VARCHAR')})" for c in columns)
                self.conn.execute(f'INSERT INTO "{table}" SELECT {fields} FROM json_each(?)',
                                  [json.dumps(rows,allow_nan=False)])
                temp=directory/(table+".parquet.tmp");path=directory/(table+".parquet")
                # Caminhos e seletores sao argumentos, nunca interpolados em SQL.
                self.conn.execute(f'COPY (SELECT * FROM "{table}" WHERE run_id=? AND territory_code=? ORDER BY year,support'+(',class_code' if table=='areas' else '')+') TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(temp),run_id,code])
                os.replace(temp,path)
                files.append({"name":path.name,"sha256":sha_file(path),"rows":len(rows)})
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK");raise
        m={"schema_version":"particao-areas-v1","run_id":run_id,"territory_code":code,"status":"completo",
           "resources":resources,"files":files,"quality":quality}
        atomic_json(directory/"manifest.json",m)
        return m
