from __future__ import annotations

from typing import Callable

import pandas as pd

import classification_workspace


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
        return f"Ingen kontoer er klassifisert under {group_label} enna."

    count = int(len(accounts_df))
    value_column = str(basis_col or "Endring").strip()
    if value_column not in accounts_df.columns:
        value_column = "Endring"
    total_raw = accounts_df.get(value_column, pd.Series(dtype=object)).sum()
    total_amount = "-"
    try:
        if amount_formatter is not None:
            total_amount = amount_formatter(float(total_raw)) or "-"
        else:
            total_amount = str(total_raw or "-")
    except Exception:
        try:
            if amount_formatter is not None:
                total_amount = amount_formatter(total_raw) or "-"
        except Exception:
            total_amount = "-"
    suffix = "konto" if count == 1 else "kontoer"
    return f"{group_label} | {count} {suffix} | {value_column} {total_amount}"


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
    total_groups = int(len(control_statement_df))
    try:
        total_accounts = int(pd.to_numeric(control_statement_df.get("AntallKontoer"), errors="coerce").fillna(0).sum())
    except Exception:
        total_accounts = 0
    try:
        total_value = pd.to_numeric(control_statement_df.get(value_column), errors="coerce").fillna(0).sum()
        if amount_formatter is not None:
            total_amount = amount_formatter(float(total_value)) or "-"
        else:
            total_amount = str(total_value or "-")
    except Exception:
        total_amount = "-"
    parts = [f"{total_groups} grupper", f"{total_accounts} kontoer", f"{value_column} {total_amount}"]
    try:
        unclassified = control_statement_df.loc[
            control_statement_df["Gruppe"].astype(str).str.strip() == "__unclassified__"
        ]
        unclassified_accounts = int(pd.to_numeric(unclassified.get("AntallKontoer"), errors="coerce").fillna(0).sum())
    except Exception:
        unclassified_accounts = 0
    if unclassified_accounts:
        parts.append(f"Uklassifiserte {unclassified_accounts}")
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
    if has_history:
        return "Historikk"
    if best_suggestion is not None:
        if bool(best_suggestion.get("WithinTolerance", False)):
            return "Forslag"
        return "Sjekk"
    return "Manuell"


def control_next_action_label(
    status: str | None,
    *,
    has_history: bool,
    best_suggestion: pd.Series | None,
) -> str:
    status_s = str(status or "").strip()
    if status_s in {"OK", "Ekskludert"}:
        return "Ingen handling nødvendig."
    if has_history:
        return "Bruk historikk."
    if best_suggestion is not None and bool(best_suggestion.get("WithinTolerance", False)):
        return "Bruk beste forslag."
    return "Map manuelt."


def is_saldobalanse_follow_up_action(next_action: object) -> bool:
    action_s = str(next_action or "").strip()
    if not action_s:
        return False
    return "Saldobalanse" in action_s or action_s == "Rydd RF-1022-post for mappede kontoer."


def control_follow_up_guidance(next_action: object) -> str:
    action_s = str(next_action or "").strip()
    if action_s == "Tildel RF-1022-post i Saldobalanse.":
        return "Kontoene er mappet, men mangler RF-1022-post. Fullfor klassifiseringen i Saldobalanse."
    if action_s == "Fullfor lønnsflagg i Saldobalanse.":
        return "Kontoene er mappet, men mangler lonnsflagg. Fullfor klassifiseringen i Saldobalanse."
    if action_s == "Rydd RF-1022-post for mappede kontoer.":
        return "Kontoprofilene peker mot en annen RF-1022-post enn A07-koden tilsier. Rydd dette i Saldobalanse."
    return "A07 viser kontrollbehovet, men klassifiseringen skal ryddes i Saldobalanse."


def saldobalanse_queue_for_control_action(next_action: object) -> str:
    action_s = str(next_action or "").strip()
    if action_s == "Rydd RF-1022-post for mappede kontoer.":
        return classification_workspace.QUEUE_SUSPICIOUS
    if action_s in {
        "Tildel RF-1022-post i Saldobalanse.",
        "Fullfor lønnsflagg i Saldobalanse.",
    }:
        return classification_workspace.QUEUE_REVIEW
    if is_saldobalanse_follow_up_action(action_s):
        return classification_workspace.QUEUE_REVIEW
    return classification_workspace.QUEUE_ALL


def compact_control_next_action(next_action: object) -> str:
    action_s = str(next_action or "").strip()
    if action_s == "Bruk historikk.":
        return "Historikk"
    if action_s == "Bruk beste forslag.":
        return "Forslag"
    if action_s == "Map manuelt.":
        return "Manuell"
    if action_s == "Kontroller historikkmapping.":
        return "Historikk"
    if action_s == "Kontroller manuell mapping.":
        return "Manuell"
    if action_s == "Ingen handling nødvendig.":
        return "Ingen"
    return action_s or "-"


def control_intro_text(
    work_label: object,
    *,
    has_history: bool,
    best_suggestion: pd.Series | None,
) -> str:
    work_s = str(work_label or "").strip()
    if work_s == "Ferdig":
        return "Ser ferdig ut. Kontroller kort og ga videre hvis du er enig."
    if work_s == "Historikk":
        return "Historikkmapping er brukt. Kontroller kort og lås hvis den ser riktig ut."
    if work_s == "Forslag":
        return "Det finnes et trygt forslag. Start gjerne der."
    if work_s == "Uløst":
        return "Ingen mapping er satt ennå. Start med forslag, historikk eller manuell mapping."
    if has_history:
        return "Historikk finnes. Start gjerne med a vurdere historikk."
    if best_suggestion is not None and bool(best_suggestion.get("WithinTolerance", False)):
        return "Det finnes et trygt forslag. Start gjerne der."
    return "Ingen trygg automatikk funnet ennå. Bruk manuell mapping eller dra konto inn."


def filter_control_queue_df(control_df: pd.DataFrame, view_key: str | None) -> pd.DataFrame:
    if control_df is None:
        return pd.DataFrame()
    if control_df.empty:
        return control_df.reset_index(drop=True)
    if "Arbeidsstatus" not in control_df.columns:
        return control_df.reset_index(drop=True)

    view_s = str(view_key or "neste").strip().lower()
    statuses = control_df["Arbeidsstatus"].astype(str).str.strip()
    if view_s in {"", "neste"}:
        mask = statuses != "Ferdig"
    elif view_s == "ulost":
        mask = statuses == "Uløst"
    elif view_s == "forslag":
        mask = statuses == "Forslag"
    elif view_s == "historikk":
        mask = statuses == "Historikk"
    elif view_s == "manuell":
        mask = statuses == "Manuell"
    elif view_s == "ferdig":
        mask = statuses == "Ferdig"
    else:
        return control_df.reset_index(drop=True)
    return control_df.loc[mask].reset_index(drop=True)


def build_control_bucket_summary(control_df: pd.DataFrame) -> str:
    if control_df is None or control_df.empty or "Arbeidsstatus" not in control_df.columns:
        return "Uløste 0 | Forslag 0 | Historikk 0 | Manuell 0 | Ferdig 0"

    statuses = control_df["Arbeidsstatus"].astype(str).str.strip()
    unresolved = int((statuses == "Uløst").sum())
    suggested = int((statuses == "Forslag").sum())
    historical = int((statuses == "Historikk").sum())
    manual = int((statuses == "Manuell").sum())
    done = int((statuses == "Ferdig").sum())
    return f"Uløste {unresolved} | Forslag {suggested} | Historikk {historical} | Manuell {manual} | Ferdig {done}"


def count_pending_control_items(control_df: pd.DataFrame) -> int:
    if control_df is None or control_df.empty or "Arbeidsstatus" not in control_df.columns:
        return 0
    statuses = control_df["Arbeidsstatus"].astype(str).str.strip()
    return int((statuses != "Ferdig").sum())


def control_tree_tag(work_status: object) -> str:
    status_s = str(work_status or "").strip()
    if status_s == "Ferdig":
        return "control_done"
    if status_s in {"Forslag", "Historikk"}:
        return "control_review"
    if status_s in {"Uløst", "Manuell"}:
        return "control_manual"
    return "control_default"


def control_action_style(work_label: object) -> str:
    label_s = str(work_label or "").strip()
    if label_s == "Ferdig":
        return "Ready.TLabel"
    if label_s in {"Forslag", "Historikk", "Uløst", "Manuell"}:
        return "Warning.TLabel"
    return "Muted.TLabel"
