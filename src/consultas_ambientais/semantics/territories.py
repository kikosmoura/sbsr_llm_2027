"""Resolucao deterministica sobre snapshot de atributos territoriais, sem geometria."""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from .catalog import CatalogError, digest
from .models import Resolution, TerritoryCatalogData, TerritoryReference
from .normalization import normalize


def territory_digest(data):
    return digest(data.model_dump(mode="json", exclude={"content_sha256"}))


class TerritoryCatalog:
    def __init__(self, data: TerritoryCatalogData):
        self.data = data
        if data.content_sha256 != territory_digest(data):
            raise CatalogError("hash_catalogo_territorial_divergente")
        self.sha256 = data.content_sha256
        self.by_code = {r.code:r for r in data.entries}
        if len(self.by_code) != len(data.entries):
            raise CatalogError("codigo_territorial_duplicado")
        ufs = {r.uf_code:r.uf for r in data.entries if r.kind == "uf"}
        for entry in data.entries:
            if ufs.get(entry.uf_code) != entry.uf:
                raise CatalogError("vinculo_uf_incoerente")
        self.index = {}
        for entry in data.entries:
            aliases = [entry.name_original,*entry.search_aliases]
            if entry.kind == "uf": aliases.append(entry.uf)
            for alias in aliases:
                self.index.setdefault(normalize(alias),set()).add(entry.code)

    @classmethod
    def load(cls,path:Path):
        return cls(TerritoryCatalogData.model_validate_json(path.read_text()))

    def candidates(self,codes):
        return [{"code":r.code,"name_original":r.name_original,"kind":r.kind,
                 "uf":r.uf,"alias_notes":r.alias_notes} for r in (self.by_code[c] for c in sorted(codes))]

    def resolve(self,reference:TerritoryReference):
        name = reference.name
        uf = reference.uf
        if name:
            suffix = re.fullmatch(r"(.+?)(?:\s*/\s*|\s+-\s+)([A-Za-z]{2})",name.strip())
            if suffix:
                if uf and uf != suffix[2].upper():
                    return Resolution(status="precisa_esclarecimento",reason="ufs_informadas_divergentes")
                name,uf = suffix[1],suffix[2].upper()
        if uf and uf not in {r.uf for r in self.data.entries if r.kind=="uf"}:
            return Resolution(status="nao_encontrado",reason="uf_desconhecida")
        if reference.code:
            entry=self.by_code.get(reference.code)
            if entry is None:return Resolution(status="nao_encontrado",reason="codigo_territorial_desconhecido")
            incompatible = ((uf and entry.uf!=uf) or (reference.kind and entry.kind!=reference.kind))
            if name and reference.code not in self.index.get(normalize(name),set()): incompatible=True
            if incompatible:
                return Resolution(status="precisa_esclarecimento",reason="codigo_nome_ou_uf_incoerentes",
                                  candidates=self.candidates({entry.code}))
            codes={entry.code};match="codigo_ibge"
        elif reference.kind=="uf" and uf and not name:
            codes={r.code for r in self.data.entries if r.kind=="uf" and r.uf==uf};match="sigla_uf"
        else:
            raw_codes=self.index.get(normalize(name or ""),set())
            codes={c for c in raw_codes if (not uf or self.by_code[c].uf==uf)
                   and (not reference.kind or self.by_code[c].kind==reference.kind)}
            match="nome_normalizado"
            if not codes and raw_codes:
                return Resolution(status="precisa_esclarecimento",reason="nome_uf_ou_tipo_incoerentes",
                                  candidates=self.candidates(raw_codes))
            if not codes:
                scores=[];term=normalize(name or "")
                for alias, matches in self.index.items():
                    allowed={c for c in matches if (not uf or self.by_code[c].uf==uf)
                             and (not reference.kind or self.by_code[c].kind==reference.kind)}
                    if not allowed:continue
                    ratio=SequenceMatcher(None,term,alias).ratio()
                    if ratio>=0.82:scores.append((ratio,allowed))
                if scores:
                    threshold=max(0.82,max(s[0] for s in scores)-0.04)
                    near={c for score,matches in scores if score>=threshold for c in matches}
                    return Resolution(status="precisa_esclarecimento",reason="busca_aproximada_exige_confirmacao",
                                      candidates=self.candidates(near)[:10],match_kind="aproximado",
                                      notes=["Nenhum candidato aproximado foi selecionado automaticamente."])
                return Resolution(status="nao_encontrado",reason="territorio_nao_encontrado")
        if len(codes)!=1:
            return Resolution(status="precisa_esclarecimento",reason="territorio_homonimo",
                              candidates=self.candidates(codes),match_kind=match)
        entry=self.by_code[next(iter(codes))]
        notes=[]
        if name and normalize(name)!=normalize(entry.name_original):
            notes=["Busca usou alias; nome_original preservado.",*entry.alias_notes]
        return Resolution(status="resolvido",reason="territorio_identificado",selected_codes=sorted(codes),
                          candidates=self.candidates(codes),match_kind=match,notes=notes)

    def municipality_universe(self,uf):
        return {r.code for r in self.data.entries if r.kind=="municipio" and r.uf==uf}
