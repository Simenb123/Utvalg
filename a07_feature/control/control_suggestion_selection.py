from __future__ import annotations

from .queue_shared import *  # noqa: F403


def a07_suggestion_is_strict_auto(row: pd.Series | dict[str, object]) -> bool:
    getter = getattr(row, "get", None)
    if not callable(getter):
        return False

    def _text(value: object) -> str:
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        return str(value or "").strip()

    def _flag(value: object) -> bool:
        try:
            if pd.isna(value):
                return False
        except Exception:
            pass
        return bool(value)

    try:
        if not _flag(getter("WithinTolerance", False)):
            return False
        guardrail = _text(getter("SuggestionGuardrail", "")).lower()
        return guardrail == "accepted"
    except Exception:
        return False

def select_batch_suggestion_rows(
    suggestions_df: pd.DataFrame,
    mapping_existing: dict[str, str],
    *,
    min_score: float = 0.85,
    locked_codes: set[str] | None = None,
) -> list[int]:
    if suggestions_df is None or suggestions_df.empty:
        return []
    selected_rows = select_batch_suggestions(
        [ui_suggestion_row_from_series(row) for _, row in suggestions_df.iterrows()],
        mapping_existing,
        min_score=min_score,
        locked_codes=locked_codes,
    )
    strict_indexes = {int(idx) for idx, row in suggestions_df.iterrows() if a07_suggestion_is_strict_auto(row)}
    return [
        int(row.source_index)
        for row in selected_rows
        if row.source_index is not None and int(row.source_index) in strict_indexes
    ]

def select_magic_wand_suggestion_rows(
    suggestions_df: pd.DataFrame,
    mapping_existing: dict[str, str],
    *,
    unresolved_codes: Sequence[object] | None = None,
    locked_codes: set[str] | None = None,
) -> list[int]:
    if suggestions_df is None or suggestions_df.empty:
        return []
    selected_rows = select_magic_wand_suggestions(
        [ui_suggestion_row_from_series(row) for _, row in suggestions_df.iterrows()],
        mapping_existing,
        unresolved_codes=unresolved_codes,
        locked_codes=locked_codes,
    )
    strict_indexes = {int(idx) for idx, row in suggestions_df.iterrows() if a07_suggestion_is_strict_auto(row)}
    return [
        int(row.source_index)
        for row in selected_rows
        if row.source_index is not None and int(row.source_index) in strict_indexes
    ]

