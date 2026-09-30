"""Document-ID's voor callers en companies (TEAMPLAN §1.3). Eén plek, gedeeld door backend en scripts/seed.py.

Spraakherkenning levert varianten ("Bakkerij Verhulst BV", "bakkerij verhulst"); daarom normaliseren we
accenten, hoofdletters, leestekens en Belgische/Nederlandse rechtsvormen vóór het slug-en.
"""

from __future__ import annotations

import re
import unicodedata

_LEGAL_FORMS = {
    "bv", "bvba", "nv", "cv", "cvba", "vzw", "vof", "comm.v", "commv",
    "srl", "sprl", "sa", "sc", "scrl", "asbl", "snc", "scs",
}


def slug(text: str) -> str:
    """'Café Dé Smet NV' -> 'cafe-de-smet'."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", ascii_text.lower())
    return "-".join(words)


def company_id(company_name: str) -> str:
    words = slug(company_name).split("-")
    while len(words) > 1 and words[-1] in _LEGAL_FORMS:
        words.pop()
    return "-".join(words)


def caller_id(caller_name: str, company: str) -> str:
    """company is het company_id (TEAMPLAN: slug(caller_name + company_id))."""
    return f"{slug(caller_name)}--{company}"
