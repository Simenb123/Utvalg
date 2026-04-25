from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

import pandas as pd

from formatting import format_number_no

_NUMERIC_COLUMNS_ZERO_DECIMALS = {"AntallKontoer"}
_NUMERIC_COLUMNS_THREE_DECIMALS = {"Score"}
_NUMERIC_COLUMNS_TWO_DECIMALS = {
    "A07_Belop",
    "A07",
    "AgaGrunnlag",
    "Belop",
    "Diff",
    "Endring",
    "FradragPaalopt",
    "GL_Belop",
    "GL_Sum",
    "IB",
    "KostnadsfortYtelse",
    "SamledeYtelser",
    "TilleggTidligereAar",
    "UB",
}


@dataclass(frozen=True)
class _PickerOption:
    key: str
    label: str
    search_text: str


def _format_picker_amount(value: object, *, decimals: int = 2) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if isinstance(value, Decimal):
        return format_number_no(value, decimals)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format_number_no(value, decimals)
    if isinstance(value, str):
        formatted = format_number_no(value, decimals)
        return formatted if formatted != value else value
    return str(value)


def _numeric_decimals_for_column(column_id: str) -> int | None:
    if column_id in _NUMERIC_COLUMNS_ZERO_DECIMALS:
        return 0
    if column_id in _NUMERIC_COLUMNS_THREE_DECIMALS:
        return 3
    if column_id in _NUMERIC_COLUMNS_TWO_DECIMALS:
        return 2
    return None


def build_gl_picker_options(
    gl_df: pd.DataFrame,
    *,
    basis_col: str = "Endring",
) -> list[_PickerOption]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return []
    amount_col = basis_col if basis_col in gl_df.columns else "Belop"
    work = gl_df.copy()
    work["Konto"] = work["Konto"].astype(str).str.strip()
    work = work[work["Konto"] != ""].copy()
    work = work.drop_duplicates(subset=["Konto"], keep="first")
    work = work.sort_values(by=["Konto"], kind="stable")
    options: list[_PickerOption] = []
    for _, row in work.iterrows():
        konto = str(row.get("Konto") or "").strip()
        if not konto:
            continue
        navn = str(row.get("Navn") or "").strip()
        belop = _format_picker_amount(row.get(amount_col))
        label_parts = [konto]
        if navn:
            label_parts.append(navn)
        if belop:
            label_parts.append(belop)
        options.append(
            _PickerOption(
                key=konto,
                label=" | ".join(label_parts),
                search_text=" ".join(part.lower() for part in label_parts if part),
            )
        )
    return options


def build_a07_picker_options(a07_df: pd.DataFrame) -> list[_PickerOption]:
    if a07_df is None or a07_df.empty or "Kode" not in a07_df.columns:
        return []
    work = a07_df.copy()
    work["Kode"] = work["Kode"].astype(str).str.strip()
    work = work[work["Kode"] != ""].copy()
    work = work.drop_duplicates(subset=["Kode"], keep="first")
    work = work.sort_values(by=["Kode"], kind="stable")
    options: list[_PickerOption] = []
    for _, row in work.iterrows():
        kode = str(row.get("Kode") or "").strip()
        if not kode:
            continue
        navn = str(row.get("Navn") or "").strip()
        belop = _format_picker_amount(row.get("Belop"))
        label_parts = [kode]
        if navn:
            label_parts.append(navn)
        if belop:
            label_parts.append(belop)
        options.append(
            _PickerOption(
                key=kode,
                label=" | ".join(label_parts),
                search_text=" ".join(part.lower() for part in label_parts if part),
            )
        )
    return options


def _filter_picker_options(options: Sequence[_PickerOption], query: str) -> list[_PickerOption]:
    query_s = str(query or "").strip().lower()
    if not query_s:
        return list(options)
    return [option for option in options if query_s in option.search_text]


def _count_nonempty_mapping(mapping: dict[str, str]) -> int:
    return sum(1 for value in (mapping or {}).values() if str(value).strip())


def _parse_konto_tokens(raw: object) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
