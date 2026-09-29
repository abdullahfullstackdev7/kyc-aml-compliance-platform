"""Name normalization pipeline shared by sanctions list ingestion and customer screening.

The same normalization must be applied to SDN names and to customer names so that
token, trigram and phonetic comparisons are meaningful. See PROJECT_PLAN.md section 3.1.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import jellyfish
from anyascii import anyascii

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)

_HONORIFICS = {
    "MR",
    "MRS",
    "MS",
    "MISS",
    "DR",
    "PROF",
    "SIR",
    "MADAM",
    "SHEIKH",
    "SHEIK",
    "HAJI",
    "HAJJI",
    "GENERAL",
    "GEN",
    "COLONEL",
    "COL",
    "CAPTAIN",
    "CAPT",
    "IMAM",
    "MULLAH",
    "AYATOLLAH",
    "ENGINEER",
    "ENG",
    "HAJJ",
}

_LEGAL_SUFFIX_MAP = {
    "LLC": "SUFFIXCORP",
    "L.L.C": "SUFFIXCORP",
    "LTD": "SUFFIXCORP",
    "LIMITED": "SUFFIXCORP",
    "CO": "SUFFIXCORP",
    "COMPANY": "SUFFIXCORP",
    "CORP": "SUFFIXCORP",
    "CORPORATION": "SUFFIXCORP",
    "INC": "SUFFIXCORP",
    "INCORPORATED": "SUFFIXCORP",
    "JSC": "SUFFIXCORP",
    "OOO": "SUFFIXCORP",
    "ZAO": "SUFFIXCORP",
    "SA": "SUFFIXCORP",
    "S.A": "SUFFIXCORP",
    "GMBH": "SUFFIXCORP",
    "PLC": "SUFFIXCORP",
    "BV": "SUFFIXCORP",
    "AG": "SUFFIXCORP",
    "FZE": "SUFFIXCORP",
    "FZCO": "SUFFIXCORP",
}

# Curated name-variant equivalence table. Each key maps to a canonical spelling so
# that transliteration variants collapse to a single token during comparison.
_NAME_EQUIVALENCE = {
    "MOHAMMED": "MOHAMMAD",
    "MUHAMMAD": "MOHAMMAD",
    "MOHAMAD": "MOHAMMAD",
    "MUHAMMED": "MOHAMMAD",
    "MOHAMED": "MOHAMMAD",
    "MAHOMET": "MOHAMMAD",
    "ABDUL": "ABD",
    "ABD AL": "ABD",
    "ABDUL AL": "ABD",
    "YUSUF": "YOUSEF",
    "YOUSSEF": "YOUSEF",
    "YOUSIF": "YOUSEF",
    "HUSSEIN": "HUSSAIN",
    "HUSAIN": "HUSSAIN",
    "HUSSAYN": "HUSSAIN",
    "IBRAHIM": "IBRAHIM",
    "EBRAHIM": "IBRAHIM",
    "OSAMA": "USAMA",
    "USAMAH": "USAMA",
}


@dataclass
class NormalizedName:
    full_name: str
    normalized: str
    tokens: list[str] = field(default_factory=list)
    sorted_token_key: str = ""
    phonetic: list[str] = field(default_factory=list)


def _strip_accents_and_transliterate(text: str) -> str:
    nfkc = unicodedata.normalize("NFKC", text)
    return anyascii(nfkc)


def _strip_punctuation(text: str) -> str:
    # Periods are dropped rather than turned into a space first, so dotted
    # abbreviations collapse into one token ("S.A." -> "SA", "L.L.C" -> "LLC")
    # and are recognized by the legal-suffix and honorific maps below. Doing
    # this after the general punctuation-to-space pass would instead leave
    # them as separate single-letter tokens that never match anything.
    text = text.replace(".", "")
    text = _PUNCTUATION_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _apply_token_rules(tokens: list[str]) -> list[str]:
    result: list[str] = []
    for token in tokens:
        if token in _HONORIFICS:
            continue
        token = _LEGAL_SUFFIX_MAP.get(token, token)
        token = _NAME_EQUIVALENCE.get(token, token)
        result.append(token)
    return result


def _phonetic_keys(tokens: list[str]) -> list[str]:
    keys: list[str] = []
    for token in tokens:
        if not token or token == "SUFFIXCORP":
            continue
        try:
            keys.append(jellyfish.nysiis(token))
        except (ValueError, IndexError):
            continue
        try:
            dm = jellyfish.metaphone(token)
            if dm:
                keys.append(dm)
        except (ValueError, IndexError):
            continue
    return keys


def normalize_name(raw_name: str) -> NormalizedName:
    """Normalize a name for matching: transliterate, casefold, strip noise, tokenize."""
    if not raw_name:
        return NormalizedName(full_name="", normalized="")

    ascii_text = _strip_accents_and_transliterate(raw_name)
    casefolded = ascii_text.casefold().upper()
    cleaned = _strip_punctuation(casefolded)

    raw_tokens = cleaned.split(" ") if cleaned else []
    tokens = _apply_token_rules(raw_tokens)
    normalized = " ".join(tokens)
    sorted_token_key = " ".join(sorted(tokens))
    phonetic = _phonetic_keys(tokens)

    return NormalizedName(
        full_name=raw_name,
        normalized=normalized,
        tokens=tokens,
        sorted_token_key=sorted_token_key,
        phonetic=phonetic,
    )
