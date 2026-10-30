"""Normalizacao de busca; nunca substitui o nome de origem."""
import re
import unicodedata


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def encoding_search_alias(value: str) -> str | None:
    """Alias candidato reversivel, com menos marcadores; nao e renomeacao."""
    markers = ("Ã", "Â", "�")
    before = sum(value.count(m) for m in markers)
    if not before:
        return None
    try:
        decoded = value.encode("latin1").decode("utf8")
        reversible = decoded.encode("utf8").decode("latin1") == value
    except UnicodeError:
        return None
    after = sum(decoded.count(m) for m in markers)
    if reversible and after < before and not any(unicodedata.category(c) == "Cc" for c in decoded):
        return decoded
    return None
