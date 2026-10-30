"""Importacao auditavel da legenda oficial: PDF para hierarquia, CSV para conferencia."""
import csv
import hashlib
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

from .models import CatalogClass, ClassCatalogData, Resolution, SourceDocument
from .normalization import normalize


class CatalogError(ValueError):
    pass


def digest(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class LegendHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.cells = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.cells = []
        if tag in {"td", "th"}: self.cell = []

    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.cells: self.rows.append(self.cells)


def parse_pdf_text(text):
    if "Coleção 11" not in text or "13/08/2026" not in text:
        raise CatalogError("documento_nao_identificado_como_legenda_col11")
    entries = []
    pending = ""
    for line in text.splitlines():
        match = re.search(r"\s+(\d+)\s+(#[0-9A-Fa-f]{6})\s*$", line)
        if not match:
            parts = re.split(r"\s{2,}", line.strip())
            if parts and re.match(r"^\d+(?:\.\d+)*\.\s*", parts[0]): pending = parts[0]
            continue
        columns = re.split(r"\s{2,}", line[:match.start()].strip())
        if len(columns) != 2:
            raise CatalogError("colunas_pdf_inesperadas")
        pt, en = columns
        if pending:
            pt = pending + " " + pt
            pending = ""
        prefix = re.match(r"^(\d+(?:\.\d+)*)(?:\.)?\s+(.+)$", pt)
        if not prefix:
            raise CatalogError("prefixo_hierarquico_pdf_invalido")
        entries.append({"code": int(match[1]), "printed_path": prefix[1],
                        "name": prefix[2], "name_en": re.sub(r"^[\d.]+\s*", "", en),
                        "color": match[2].lower()})
    if len(entries) != 41 or len({x["code"] for x in entries}) != 41:
        raise CatalogError("quantidade_ou_unicidade_pdf_inesperada")
    return entries


def build_catalog(source_dir: Path):
    sources = [SourceDocument.model_validate(s) for s in json.loads((source_dir / "manifest.json").read_text())]
    if {s.source_id for s in sources} != {"legend.pdf", "legend.csv", "official_page.html"}:
        raise CatalogError("fontes_obrigatorias_ausentes")
    for source in sources:
        raw = (source_dir / source.source_id).read_bytes()
        if len(raw) != source.bytes or hashlib.sha256(raw).hexdigest() != source.sha256:
            raise CatalogError("hash_de_fonte_divergente")
    by_source = {s.source_id: s for s in sources}
    converter = shutil.which("pdftotext")
    if not converter:raise CatalogError("pdftotext_indisponivel_para_reconstrucao")
    try:
        extracted = subprocess.run([converter,"-layout",str(source_dir/"legend.pdf"),"-"],
                                   check=True,capture_output=True,timeout=20).stdout
    except (subprocess.SubprocessError,OSError):
        raise CatalogError("falha_extracao_pdf") from None
    if extracted != (source_dir/"legend.txt").read_bytes():
        raise CatalogError("texto_extraido_nao_corresponde_ao_pdf")
    entries = parse_pdf_text(extracted.decode("utf8"))
    rows = list(csv.DictReader((source_dir / "legend.csv").open(encoding="utf-8-sig", newline="")))
    csv_by_code = {int(row["class_id"]): row for row in rows}
    if len(rows) != len(csv_by_code) or set(csv_by_code) != {r["code"] for r in entries if r["code"] not in {1,10,14,18,19,36,22,26}}:
        raise CatalogError("codigos_csv_pdf_divergentes")
    page = LegendHTML()
    page.feed((source_dir / "official_page.html").read_text())
    path_48_verified = any(len(r) >= 3 and r[2] == "48" and r[1].startswith("3.2.2.4") for r in page.rows)
    if not path_48_verified:
        raise CatalogError("correcao_hierarquica_48_sem_conferencia_oficial")
    discrepancies = []
    for entry in entries:
        entry["canonical_path"] = entry["printed_path"]
        if entry["code"] == 48:
            if entry["printed_path"] != "3.2.1.4":
                raise CatalogError("fonte_pdf_mudou_revisar_correcao_48")
            entry["canonical_path"] = "3.2.2.4"
            discrepancies.append({"code":48,"field":"hierarchy_path","pdf":"3.2.1.4",
                                  "canonical":"3.2.2.4","reason":"Numeracao PDF repete ramo temporario; posicao sob Lavoura Perene e pagina oficial confirmam ramo perene.",
                                  "corroborating_source":"official_page.html"})
        row = csv_by_code.get(entry["code"])
        if row:
            for key, csv_key in [("name","class_name_pt_br"),("name_en","class_name_en")]:
                if entry[key] != row[csv_key]:
                    discrepancies.append({"code":entry["code"],"field":key,"pdf":entry[key],"csv":row[csv_key],
                                          "chosen_source":"legend.pdf"})
            if entry["color"] != row["hex_code"].lower():
                raise CatalogError("cores_pdf_csv_divergentes")
    path_map = {r["canonical_path"]:r["code"] for r in entries}
    if len(path_map) != len(entries): raise CatalogError("hierarquia_duplicada")
    children = {r["code"]:[] for r in entries}
    parents = {}
    for row in entries:
        path = row["canonical_path"]
        parent = path_map.get(path.rsplit(".",1)[0]) if "." in path else None
        if "." in path and parent is None: raise CatalogError("pai_ausente")
        parents[row["code"]] = parent
        if parent is not None: children[parent].append(row["code"])
    def descendants(code):
        return sorted({c for child in children[code] for c in [child,*descendants(child)]})
    def leaves(code):
        return sorted({c for child in children[code] for c in leaves(child)}) if children[code] else [code]
    aliases = {1:["grupo Floresta","floresta","área florestal"],3:["floresta","área florestal"],
               15:["pastagens"],24:["área urbana","áreas urbanizadas"],
               26:["grupo Corpo D'água","água","superfície de água"],33:["rio/lago/oceano","água","superfície de água"]}
    result = []
    for row in entries:
        code = row["code"]
        all_aliases = aliases.get(code,[])[:]
        if code in csv_by_code and csv_by_code[code]["class_name_pt_br"] != row["name"]:
            all_aliases.append(csv_by_code[code]["class_name_pt_br"])
        result.append(CatalogClass(**row,parent_code=parents[code],leaf_codes=leaves(code),
            descendant_codes=descendants(code),kind="grupo" if children[code] else "classe_folha",
            aliases=list(dict.fromkeys(all_aliases)),beta="(beta)" in row["name"].casefold(),
            source_hash=by_source["legend.pdf"].sha256,
            sources=["legend.pdf"]+(["legend.csv"] if code in csv_by_code else [])))
    return ClassCatalogData(sources=sources,classes=result,discrepancies=discrepancies,
        extraction={"tool":"pdftotext -layout","text_sha256":hashlib.sha256((source_dir/"legend.txt").read_bytes()).hexdigest(),
                    "csv_leaf_count":len(rows),"pdf_node_count":len(result),"hierarchy_authority":"legend.pdf; excecao 48 corroborada pela pagina oficial"})


class ClassCatalog:
    def __init__(self,data: ClassCatalogData):
        self.data=data
        self.sha256=digest(data)
        self.by_code={c.code:c for c in data.classes}
        if len(self.by_code)!=len(data.classes):raise CatalogError("codigo_duplicado")
        self._validate_tree()
        self.index={}
        for item in data.classes:
            for term in [item.name,*item.aliases]:
                self.index.setdefault(normalize(term),set()).add(item.code)

    def _validate_tree(self):
        def visit(code,stack):
            if code in stack:raise CatalogError("ciclo_na_hierarquia")
            node=self.by_code[code]
            if node.parent_code is not None:
                if node.parent_code not in self.by_code:raise CatalogError("pai_ausente")
                visit(node.parent_code,stack|{code})
        for c in self.by_code:visit(c,set())
        for c,node in self.by_code.items():
            actual=sorted(n for n in self.by_code if n!=c and self._has_ancestor(n,c))
            leaves=sorted(n for n in [c,*actual] if self.by_code[n].kind=="classe_folha")
            if node.descendant_codes!=actual or node.leaf_codes!=leaves:
                raise CatalogError("descendentes_ou_folhas_incoerentes")
            has_children=any(n.parent_code==c for n in self.by_code.values())
            if (node.kind=="grupo") != has_children:raise CatalogError("tipo_de_no_incoerente")

    def _has_ancestor(self,code,ancestor):
        parent=self.by_code[code].parent_code
        while parent is not None:
            if parent==ancestor:return True
            parent=self.by_code[parent].parent_code
        return False

    @classmethod
    def load(cls,path:Path|None=None):
        if path is None:path=Path(__file__).parent/"data/mapbiomas_col11_v1/catalog.json"
        return cls(ClassCatalogData.model_validate_json(path.read_text()))

    def expand(self,codes):
        if any(c not in self.by_code for c in codes):raise CatalogError("codigo_de_classe_desconhecido")
        return sorted({leaf for code in codes for leaf in self.by_code[code].leaf_codes})

    def resolve(self,term=None,code=None):
        candidates=self.index.get(normalize(term),set()) if term else set()
        if code is not None:
            if code not in self.by_code:return Resolution(status="nao_encontrado",reason="codigo_de_classe_desconhecido")
            if term and code not in candidates:
                return Resolution(status="precisa_esclarecimento",reason="codigo_e_termo_divergentes")
            candidates={code}
        if not candidates:return Resolution(status="nao_encontrado",reason="termo_de_classe_desconhecido")
        rows=[{"code":c,"name":self.by_code[c].name,"kind":self.by_code[c].kind} for c in sorted(candidates)]
        if len(candidates)>1:return Resolution(status="precisa_esclarecimento",reason="classe_ambigua",candidates=rows)
        return Resolution(status="resolvido",reason="classe_identificada",selected_codes=sorted(candidates),candidates=rows,match_kind="exato_normalizado")

    def audit_codes(self,codes,declared_nodata=None):
        observed=set(codes)
        nodata={declared_nodata} & observed if declared_nodata is not None else set()
        effective=observed-nodata
        unknown=sorted(effective-self.by_code.keys())
        groups=sorted(c for c in effective if c in self.by_code and self.by_code[c].kind=="grupo")
        return {"observed_codes":sorted(observed),"declared_nodata_observed":sorted(nodata),
                "known_leaf_codes":sorted(c for c in effective if c in self.by_code and self.by_code[c].kind=="classe_folha"),
                "unknown_codes":unknown,"group_codes_observed":groups,
                "status":"inconsistencia_explicita" if unknown or groups else "codigos_conhecidos_na_amostra",
                "inventory_complete":False}
