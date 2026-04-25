from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


TAG_OPPLYSNINGSPLIKTIG = "opplysningspliktig"
TAG_AGA_PLIKTIG = "aga_pliktig"
TAG_FERIEPENGEGRUNNLAG = "feriepengergrunnlag"

RF1022_OVERVIEW_COLUMNS = (
    "GroupId",
    "Post",
    "Omraade",
    "Kontrollgruppe",
    "GL_Belop",
    "SamledeYtelser",
    "A07",
    "Diff",
    "AgaGrunnlag",
    "A07Aga",
    "AgaDiff",
    "Status",
    "AntallKontoer",
)

RF1022_ACCOUNT_COLUMNS = (
    "Post",
    "Konto",
    "Navn",
    "KostnadsfortYtelse",
    "TilleggTidligereAar",
    "FradragPaalopt",
    "SamledeYtelser",
    "AgaPliktig",
    "AgaGrunnlag",
    "Feriepengegrunnlag",
)

RF1022_ACCOUNT_COLUMN_LABELS = {
    "Post": "Post",
    "Konto": "Kontonr",
    "Navn": "Kontobetegnelse",
    "KostnadsfortYtelse": "Kostnadsført ytelse",
    "TilleggTidligereAar": "Tillegg tidl. år",
    "FradragPaalopt": "Fradrag påløpt",
    "SamledeYtelser": "Samlede ytelser",
    "AgaPliktig": "AGA-pliktig",
    "AgaGrunnlag": "AGA-grunnlag",
    "Feriepengegrunnlag": "Feriep.grl.",
}


@dataclass(frozen=True)
class Rf1022Flags:
    opplysningspliktig: bool
    aga_pliktig: bool
    feriepengegrunnlag: bool
    source: str = "tags"


def _clean_tag(value: object) -> str:
    return str(value or "").strip()


def normalize_rf1022_tags(tags: Iterable[object] | None) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags or ():
        tag = _clean_tag(raw)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag)
    return tuple(cleaned)


def rf1022_flags_from_tags(tags: Iterable[object] | None, *, source: str = "tags") -> Rf1022Flags:
    tag_set = set(normalize_rf1022_tags(tags))
    aga_pliktig = TAG_AGA_PLIKTIG in tag_set
    feriepengegrunnlag = TAG_FERIEPENGEGRUNNLAG in tag_set
    # AGA-pliktig and feriepengegrunnlag are RF-1022 sub-spors of
    # opplysningspliktige ytelser. Treat them as opplysningspliktig even if
    # older profile data forgot the explicit parent tag.
    opplysningspliktig = (
        TAG_OPPLYSNINGSPLIKTIG in tag_set
        or aga_pliktig
        or feriepengegrunnlag
    )
    return Rf1022Flags(
        opplysningspliktig=opplysningspliktig,
        aga_pliktig=aga_pliktig,
        feriepengegrunnlag=feriepengegrunnlag,
        source=str(source or "tags"),
    )


def rf1022_taxable_amount(value: object, *, flags: Rf1022Flags, fallback_when_unknown: bool = False) -> object:
    if flags.opplysningspliktig or fallback_when_unknown:
        return value
    return None


def rf1022_aga_flag(*, flags: Rf1022Flags, treatment_kind: str) -> bool | None:
    if str(treatment_kind or "").strip() in {"refund", "pension", "withholding", "accrual_aga"}:
        return None
    return bool(flags.aga_pliktig)


__all__ = [
    "RF1022_ACCOUNT_COLUMN_LABELS",
    "RF1022_ACCOUNT_COLUMNS",
    "RF1022_OVERVIEW_COLUMNS",
    "Rf1022Flags",
    "TAG_AGA_PLIKTIG",
    "TAG_FERIEPENGEGRUNNLAG",
    "TAG_OPPLYSNINGSPLIKTIG",
    "normalize_rf1022_tags",
    "rf1022_aga_flag",
    "rf1022_flags_from_tags",
    "rf1022_taxable_amount",
]
