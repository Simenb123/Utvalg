from __future__ import annotations

from typing import Callable

import pandas as pd

import classification_workspace


def _normalize_work_label(value: object) -> str:
    label = str(value or "").strip()
    replacements = {
        "Ulost": "Ulost",
        "Uløst": "Ulost",
        "UlÃ¸st": "Ulost",
        "UlÃƒÂ¸st": "Ulost",
        "Forslag": "Forslag",
        "Historikk": "Historikk",
        "Manuell": "Manuell",
        "Ferdig": "Ferdig",
    }
    return replacements.get(label, label)


def _normalize_guided_status(value: object, *, row: pd.Series | None = None) -> str:
    status = str(value or "").strip()
    mapping = {
        "Ulost": "Maa avklares",
        "Forslag": "Har forslag",
        "Historikk": "Har historikk",
        "Manuell": "Kontroller kobling",
        "Ferdig": "Ferdig",
    }
    if status:
        normalized = mapping.get(_normalize_work_label(status), status)
        return str(normalized or "").strip()
    raw = _normalize_work_label(row.get("Arbeidsstatus") if row is not None else "")
    return mapping.get(raw, str(row.get("Status") if row is not None else "") or "").strip()


def build_control_statement_summary(
    row: pd.Series | None,
    accounts_df: pd.DataFrame,
    *,
    basis_col: str = "Endring",
    amount_formatter: Callable[[object], str | None] | None = None,
) -> str:
    if row is None:
        return "Velg gruppe i kontrolloppstillingen for aa se kontoene bak raden."

    group_label = str(row.get("Navn") or row.get("Gruppe") or "").strip() or "valgt gruppe"
    if accounts_df is None or accounts_df.empty:
        return f"Ingen kontoer er klassifisert under {group_label} ennå."

    value_column = str(basis_col or "Endring").strip()
    if value_column not in accounts_df.columns:
        value_column = "Endring"
    total_raw = accounts_df.get(value_column, pd.Series(dtype=object)).sum()
    try:
        total_amount = amount_formatter(total_raw) if amount_formatter is not None else str(total_raw)
    except Exception:
        total_amount = "-"
    count = int(len(accounts_df.index))
    suffix = "konto" if count == 1 else "kontoer"
    return f"{group_label} | {count} {suffix} | {value_column} {total_amount or '-'}"


def build_control_statement_overview(
    control_statement_df: pd.DataFrame | None,
    *,
    basis_col: str = "Endring",
    selected_row: pd.Series | None = None,
    amount_formatter: Callable[[object], str | None] | None = None,
) -> str:
    if control_statement_df is None or control_statement_df.empty:
        return "Ingen kontrollgrupper er klassifisert ennå."
    value_column = str(basis_col or "Endring").strip()
    if value_column not in control_statement_df.columns:
        value_column = "Endring"
    total_groups = int(len(control_statement_df.index))
    try:
        total_accounts = int(pd.to_numeric(control_statement_df.get("AntallKontoer"), errors="coerce").fillna(0).sum())
    except Exception:
        total_accounts = 0
    try:
        total_value = pd.to_numeric(control_statement_df.get(value_column), errors="coerce").fillna(0).sum()
        total_amount = amount_formatter(total_value) if amount_formatter is not None else str(total_value)
    except Exception:
        total_amount = "-"
    parts = [f"{total_groups} grupper", f"{total_accounts} kontoer", f"{value_column} {total_amount or '-'}"]
    if selected_row is not None:
        label = str(selected_row.get("Navn") or selected_row.get("Gruppe") or "").strip()
        if label:
            parts.append(f"Valgt {label}")
    return " | ".join(parts)


def control_recommendation_label(
    *,
    has_history: bool,
    best_suggestion: pd.Series | None,
) -> str:
    if best_suggestion is not None:
        return "Se forslag"
    if has_history:
        return "Se historikk"
    return "Kontroller kobling"


def control_next_action_label(
    status: str | None,
    *,
    has_history: bool,
    best_suggestion: pd.Series | None,
) -> str:
    status_s = str(status or "").strip()
    if status_s in {"OK", "Ekskludert"}:
        return "Ingen handling nodvendig."
    if best_suggestion is not None:
        return "Se forslag for valgt kode."
    if has_history:
        return "Aapne historikk for valgt kode."
    return "Kontroller dagens kobling."


def is_saldobalanse_follow_up_action(next_action: object) -> bool:
    action_s = str(next_action or "").strip()
    if not action_s:
        return False
    return "Saldobalanse" in action_s or action_s == "Rydd RF-1022-post for mappede kontoer."


def control_follow_up_guidance(next_action: object) -> str:
    action_s = str(next_action or "").strip()
    if action_s == "Tildel RF-1022-post i Saldobalanse.":
        return "Kontoene er mappet, men mangler RF-1022-post. Fullfor klassifiseringen i Saldobalanse."
    if action_s == "Fullfor lonnsflagg i Saldobalanse.":
        return "Kontoene er mappet, men mangler lonnsflagg. Fullfor klassifiseringen i Saldobalanse."
    if action_s == "Rydd RF-1022-post for mappede kontoer.":
        return "Kontoprofilene peker mot en annen RF-1022-post enn A07-koden tilsier."
    return "A07 viser kontrollbehovet, men klassifiseringen gjores i Saldobalanse."


def saldobalanse_queue_for_control_action(next_action: object) -> str:
    action_s = str(next_action or "").strip()
    if action_s == "Rydd RF-1022-post for mappede kontoer.":
        return classification_workspace.QUEUE_SUSPICIOUS
    if action_s in {
        "Tildel RF-1022-post i Saldobalanse.",
        "Fullfor lonnsflagg i Saldobalanse.",
    }:
        return classification_workspace.QUEUE_REVIEW
    if is_saldobalanse_follow_up_action(action_s):
        return classification_workspace.QUEUE_REVIEW
    return classification_workspace.QUEUE_ALL


def compact_control_next_action(next_action: object) -> str:
    action_s = str(next_action or "").strip()
    mapping = {
        "Se historikk": "Historikk",
        "Aapne historikk for valgt kode.": "Historikk",
        "Se forslag": "Forslag",
        "Se forslag for valgt kode.": "Forslag",
        "Kontroller kobling": "Kobling",
        "Kontroller dagens kobling.": "Kobling",
        "Apne lonnsklassifisering": "Kontroll",
        "Ingen handling": "Ingen",
        "Ingen handling nodvendig.": "Ingen",
    }
    return mapping.get(action_s, action_s or "-")


def control_intro_text(
    work_label: object,
    *,
    has_history: bool,
    best_suggestion: pd.Series | None,
) -> str:
    work_s = _normalize_guided_status(work_label)
    if work_s == "Ferdig":
        return "Ser ferdig ut. Kontroller kort og gaa videre hvis du er enig."
    if work_s == "Har historikk":
        return "Historikk finnes for posten. Sammenlign kort for du godkjenner."
    if work_s == "Har forslag":
        return "Det finnes et forslag som bor vurderes."
    if work_s == "Mistenkelig kobling":
        return "Dagens kobling ser mistenkelig ut og bor kontrolleres."
    if work_s == "Lonnskontroll":
        return "Denne posten krever oppfolging i lonnsklassifiseringen."
    if work_s == "Kontroller kobling":
        return "Posten er koblet, men bor kontrolleres."
    if has_history:
        return "Historikk finnes for posten. Sammenlign kort for du godkjenner."
    if best_suggestion is not None:
        return "Det finnes et forslag som bor vurderes."
    return "Velg koblinger eller jobb videre i forslagene nederst."


def filter_control_queue_df(control_df: pd.DataFrame, view_key: str | None) -> pd.DataFrame:
    if control_df is None:
        return pd.DataFrame()
    if control_df.empty:
        return control_df.reset_index(drop=True)

    view_s = str(view_key or "neste").strip().lower()
    statuses = control_df.apply(
        lambda row: _normalize_guided_status(row.get("GuidetStatus"), row=row),
        axis=1,
    )
    if view_s in {"", "neste"}:
        mask = statuses != "Ferdig"
    elif view_s == "ferdig":
        mask = statuses == "Ferdig"
    elif view_s == "alle":
        mask = pd.Series(True, index=control_df.index)
    elif view_s == "ulost":
        mask = statuses.isin({"Maa avklares", "Mistenkelig kobling"})
    elif view_s == "forslag":
        mask = statuses == "Har forslag"
    elif view_s == "historikk":
        mask = statuses == "Har historikk"
    elif view_s == "manuell":
        mask = statuses.isin({"Kontroller kobling", "Lonnskontroll"})
    else:
        mask = pd.Series(True, index=control_df.index)
    return control_df.loc[mask].reset_index(drop=True)


def build_control_bucket_summary(control_df: pd.DataFrame) -> str:
    if control_df is None or control_df.empty:
        return "0 åpne"
    statuses = control_df.apply(
        lambda row: _normalize_guided_status(row.get("GuidetStatus"), row=row),
        axis=1,
    )
    pending = int((statuses != "Ferdig").sum())
    return f"{pending} åpne"


def count_pending_control_items(control_df: pd.DataFrame) -> int:
    if control_df is None or control_df.empty:
        return 0
    statuses = control_df.apply(
        lambda row: _normalize_guided_status(row.get("GuidetStatus"), row=row),
        axis=1,
    )
    return int((statuses != "Ferdig").sum())


def control_tree_tag(work_label: object) -> str:
    label_s = _normalize_guided_status(work_label)
    if label_s == "Ferdig":
        return "control_done"
    if label_s in {"Har forslag", "Har historikk"}:
        return "control_review"
    if label_s in {"Mistenkelig kobling", "Maa avklares", "Lonnskontroll", "Kontroller kobling"}:
        return "control_manual"
    return "control_default"


def control_action_style(work_label: object) -> str:
    label_s = _normalize_guided_status(work_label)
    if label_s == "Ferdig":
        return "Ready.TLabel"
    if label_s in {
        "Har forslag",
        "Har historikk",
        "Mistenkelig kobling",
        "Maa avklares",
        "Lonnskontroll",
        "Kontroller kobling",
    }:
        return "Warning.TLabel"
    return "Muted.TLabel"
