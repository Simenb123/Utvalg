"""Parser for Altinn MVA-melding (skattemelding for MVA).

Leser JSON-eksport fra Altinn og returnerer strukturert data per termin.

Støtter det enklere "samlet per termin"-formatet Altinn eksporterer til
sluttbrukere (ikke XML-innrapporteringsformatet). V1 støtter kun JSON;
XML kan legges til senere ved behov.

JSON-strukturen antas å være en dict som mimicker feltene i skjemaet:

    {
      "aar": 2025,
      "termin": 1,
      "organisasjonsnummer": "999999999",
      "omsetning_utenfor_mvaloven": 0.0,
      "post1_grunnlag_25": 1000000.0,
      "post1_avgift_25": 250000.0,
      "post11_grunnlag_15": 0.0,
      "post11_avgift_15": 0.0,
      "post12_grunnlag_12": 0.0,
      "post12_avgift_12": 0.0,
      "post14_grunnlag_omvendt": 0.0,
      "post14_avgift_omvendt": 0.0,
      "post17_inngaende_25": 180000.0,
      "post18_inngaende_15": 0.0,
      "post19_inngaende_12": 0.0,
      "sum_netto_skyldig": 70000.0
    }

Parseren er tolerant — ukjente eller manglende felter lagres som 0.0.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class MvaMeldingData:
    """Parset MVA-melding for én termin."""
    år: int = 0
    termin: int = 0
    organisasjonsnummer: str = ""
    # Utgående
    post1_grunnlag_25: float = 0.0
    post1_avgift_25: float = 0.0
    post11_grunnlag_15: float = 0.0
    post11_avgift_15: float = 0.0
    post12_grunnlag_12: float = 0.0
    post12_avgift_12: float = 0.0
    post14_grunnlag_omvendt: float = 0.0
    post14_avgift_omvendt: float = 0.0
    # Inngående
    post17_inngaende_25: float = 0.0
    post18_inngaende_15: float = 0.0
    post19_inngaende_12: float = 0.0
    # Utenfor MVA-loven
    omsetning_utenfor_mvaloven: float = 0.0
    # Sum
    sum_netto_skyldig: float = 0.0
    # Rå kilde-data (for feilsøking/revisjonsspor)
    raw: dict = field(default_factory=dict)

    def sum_utgaaende(self) -> float:
        return (
            self.post1_avgift_25
            + self.post11_avgift_15
            + self.post12_avgift_12
            + self.post14_avgift_omvendt
        )

    def sum_inngaaende(self) -> float:
        return (
            self.post17_inngaende_25
            + self.post18_inngaende_15
            + self.post19_inngaende_12
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MvaMeldingData":
        if not isinstance(data, dict):
            return cls()
        clean: dict = {}
        for f_name in cls.__dataclass_fields__:
            if f_name in data:
                clean[f_name] = data[f_name]
        return cls(**clean)


def _to_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            s = str(value).replace(" ", "").replace(",", ".")
            return float(s)
        except (TypeError, ValueError):
            return 0.0


def _to_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default


# Feltnavn-aliaser — mapper fra interne felter til alternative nøkkelformer
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "år": ("år", "aar", "year", "inntektsaar"),
    "termin": ("termin", "periode", "period"),
    "organisasjonsnummer": ("organisasjonsnummer", "orgnr", "org_nr"),
    "post1_grunnlag_25": ("post1_grunnlag_25", "post1_grunnlag", "grunnlag_25"),
    "post1_avgift_25": ("post1_avgift_25", "post1_avgift", "avgift_25"),
    "post11_grunnlag_15": ("post11_grunnlag_15", "grunnlag_15"),
    "post11_avgift_15": ("post11_avgift_15", "avgift_15"),
    "post12_grunnlag_12": ("post12_grunnlag_12", "grunnlag_12"),
    "post12_avgift_12": ("post12_avgift_12", "avgift_12"),
    "post14_grunnlag_omvendt": ("post14_grunnlag_omvendt", "grunnlag_omvendt"),
    "post14_avgift_omvendt": ("post14_avgift_omvendt", "avgift_omvendt"),
    "post17_inngaende_25": ("post17_inngaende_25", "inngaende_25", "inngaaende_25"),
    "post18_inngaende_15": ("post18_inngaende_15", "inngaende_15", "inngaaende_15"),
    "post19_inngaende_12": ("post19_inngaende_12", "inngaende_12", "inngaaende_12"),
    "omsetning_utenfor_mvaloven": ("omsetning_utenfor_mvaloven", "utenfor_mvaloven"),
    "sum_netto_skyldig": ("sum_netto_skyldig", "netto_skyldig", "sum_skyldig"),
}


def _pick(data: dict, field_name: str, as_int: bool = False, as_str: bool = False):
    aliases = _FIELD_ALIASES.get(field_name, (field_name,))
    for key in aliases:
        if key in data and data[key] not in (None, ""):
            val = data[key]
            if as_int:
                return _to_int(val)
            if as_str:
                return str(val).strip()
            return _to_float(val)
    return 0 if as_int else ("" if as_str else 0.0)


def parse_mva_melding_dict(data: dict) -> MvaMeldingData:
    """Parse MVA-melding fra allerede innlest JSON-dict."""
    if not isinstance(data, dict):
        raise ValueError("MVA-melding må være en dict")

    result = MvaMeldingData(raw=dict(data))
    result.år = _pick(data, "år", as_int=True)
    result.termin = _pick(data, "termin", as_int=True)
    result.organisasjonsnummer = _pick(data, "organisasjonsnummer", as_str=True)

    for fname in [
        "post1_grunnlag_25", "post1_avgift_25",
        "post11_grunnlag_15", "post11_avgift_15",
        "post12_grunnlag_12", "post12_avgift_12",
        "post14_grunnlag_omvendt", "post14_avgift_omvendt",
        "post17_inngaende_25", "post18_inngaende_15", "post19_inngaende_12",
        "omsetning_utenfor_mvaloven", "sum_netto_skyldig",
    ]:
        setattr(result, fname, _pick(data, fname))

    if result.termin < 1 or result.termin > 6:
        raise ValueError(
            f"Ugyldig termin i MVA-melding: {result.termin} (forventet 1-6)"
        )

    return result


def parse_mva_melding(path: str | Path) -> MvaMeldingData:
    """Parse Altinn MVA-melding fra JSON-fil.

    Returns:
        MvaMeldingData for én termin.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    suffix = p.suffix.lower()
    if suffix not in (".json", ".txt"):
        raise ValueError(
            f"Ikke-støttet filtype '{suffix}'. V1 støtter kun JSON "
            "(Altinn XML-eksport støttes i v2)."
        )

    try:
        raw = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = p.read_text(encoding="latin-1")

    data = json.loads(raw)

    # Hvis JSON er en liste eller har en "skjema"-wrapper — pakk ut.
    if isinstance(data, list):
        if not data:
            raise ValueError("Tom JSON-liste — ingen MVA-melding funnet.")
        data = data[0]
    if isinstance(data, dict) and "skjema" in data and isinstance(data["skjema"], dict):
        data = data["skjema"]
    if isinstance(data, dict) and "mvaMelding" in data and isinstance(data["mvaMelding"], dict):
        data = data["mvaMelding"]

    return parse_mva_melding_dict(data)
