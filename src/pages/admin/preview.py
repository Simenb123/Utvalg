from __future__ import annotations

from typing import Any

import classification_workspace

from page_admin_helpers import _clean_text


def _has_preview_state(item: classification_workspace.ClassificationWorkspaceItem) -> bool:
    return bool(
        item.current.a07_code.display
        or item.current.control_group.display
        or item.current.control_tags.display
        or item.suggested.a07_code is not None
        or item.suggested.control_group is not None
        or item.suggested.control_tags is not None
    )


def _preview_status_text(item: classification_workspace.ClassificationWorkspaceItem) -> str:
    if not item.payroll_relevant and not _has_preview_state(item):
        return "Ikke lønnsrelevant"
    return item.status_label or "Trenger vurdering"


def _preview_next_action_text(item: classification_workspace.ClassificationWorkspaceItem) -> str:
    if _preview_status_text(item) == "Ikke lønnsrelevant":
        return "Ingen handling i lønnsflyten."
    return item.next_action_label or "Åpne klassifisering."


def _preview_detail(item: classification_workspace.ClassificationWorkspaceItem) -> dict[str, str]:
    status_text = _preview_status_text(item)
    if status_text == "Ikke lønnsrelevant":
        return {
            "headline": f"{item.account_no} | {item.account_name or 'Uten navn'} | Status: {status_text}",
            "current": "A07: -\nRF-1022: -\nFlagg: -",
            "suggested": "Ingen lønnsforslag.\nTillit: -",
            "why": "Kontoen ser ikke lønnsrelevant ut med gjeldende regler.\nNeste: Ingen handling i lønnsflyten.",
        }
    detail = classification_workspace.format_why_panel(item)
    detail["headline"] = f"{item.account_no} | {item.account_name or 'Uten navn'} | Status: {status_text}"
    return detail


_RL_PREVIEW_FILTER_OPTIONS = (
    "Alle",
    "Klar til forslag",
    "Umappet",
    "Sumpost",
    "Mappet",
    "Overstyrt",
)


def _rl_preview_status_text(issue: Any) -> str:
    """Diagnostisk statusetikett basert kun på ``mapping_status``.

    Returnerer den faktiske RL-statusen ("Mappet", "Overstyrt", "Sumpost",
    "Umappet"). "Klar til forslag" er et arbeidsfilter, ikke en status,
    og skal aldri returneres herfra.
    """
    status_code = _clean_text(getattr(issue, "mapping_status", ""))
    if status_code == "override":
        return "Overstyrt"
    if status_code == "interval":
        return "Mappet"
    if status_code == "sumline":
        return "Sumpost"
    return "Umappet"


def _rl_preview_is_ready_for_suggestion(issue: Any) -> bool:
    """Arbeidsfilter-predikat: kontoen har forslag og trenger handling.

    True når det finnes et smartforslag og gjeldende status er et problem
    (``unmapped`` eller ``sumline``). Brukes som eget filter uten å
    overskrive ``mapping_status``-etiketten i gridet.
    """
    if getattr(issue, "suggested_regnr", None) is None:
        return False
    status_code = _clean_text(getattr(issue, "mapping_status", ""))
    return status_code in {"unmapped", "sumline"}


def _rl_preview_next_action_text(issue: Any) -> str:
    status_code = _clean_text(getattr(issue, "mapping_status", ""))
    if status_code in {"interval", "override"}:
        return "Ingen handling i mappingflyten."
    if getattr(issue, "suggested_regnr", None) is not None:
        return "Apne mapping med forslag."
    return "Apne mapping."


def _format_rl_mapping_source(issue: Any) -> str:
    src = _clean_text(getattr(issue, "mapping_source", ""))
    if src == "interval":
        return "Intervall"
    if src == "override":
        return "Overstyrt"
    if _clean_text(getattr(issue, "mapping_status", "")) == "unmapped":
        return "Ingen"
    return ""


def _format_rl_current(issue: Any) -> str:
    regnr = getattr(issue, "effective_regnr", None)
    if regnr is None:
        regnr = getattr(issue, "regnr", None)
    if regnr is None:
        return ""
    name = _clean_text(
        getattr(issue, "effective_regnskapslinje", "")
        or getattr(issue, "regnskapslinje", "")
    )
    if name:
        return f"{int(regnr)} {name}"
    return str(int(regnr))


def _format_rl_baseline(row: Any) -> str:
    regnr = getattr(row, "interval_regnr", None)
    if regnr is None:
        return ""
    return str(int(regnr))


def _format_rl_override(row: Any) -> str:
    regnr = getattr(row, "override_regnr", None)
    if regnr is None:
        return ""
    return str(int(regnr))


def _format_rl_suggestion(issue: Any) -> str:
    sug = getattr(issue, "suggested_regnr", None)
    if sug is None:
        return ""
    name = _clean_text(getattr(issue, "suggested_regnskapslinje", ""))
    if name:
        return f"{int(sug)} {name}"
    return str(int(sug))


def _rl_mapping_source_explanation(issue: Any) -> str:
    status = _clean_text(getattr(issue, "mapping_status", ""))
    src = _clean_text(getattr(issue, "mapping_source", ""))
    interval_regnr = getattr(issue, "interval_regnr", None)
    override_regnr = getattr(issue, "override_regnr", None)
    if status == "interval":
        if interval_regnr is not None:
            return f"Baseline-intervall traff {int(interval_regnr)} (kontoplan)."
        return "Mappet via baseline-intervall (kontoplan)."
    if status == "override":
        if override_regnr is not None and interval_regnr is not None and int(override_regnr) != int(interval_regnr):
            return (
                f"Klient-override {int(override_regnr)} overstyrer baseline {int(interval_regnr)}."
            )
        if override_regnr is not None:
            return f"Klient-override {int(override_regnr)} styrer regnr (uten baseline-treff)."
        return "Klient-override styrer regnr (regnskap_client_overrides)."
    if status == "sumline":
        if src == "override":
            return "Klient-override peker på en sumlinje – velg en leaf-linje i stedet."
        return "Baseline-intervallet treffer en sumlinje – krever override til leaf."
    if status == "unmapped":
        return "Ingen baseline-intervall traff og ingen override eksisterer."
    return ""


def _rl_preview_detail(issue: Any) -> dict[str, str]:
    headline = f"{issue.konto} | {issue.kontonavn or 'Uten navn'} | Status: {_rl_preview_status_text(issue)}"
    interval_regnr = getattr(issue, "interval_regnr", None)
    override_regnr = getattr(issue, "override_regnr", None)
    effective_text = _format_rl_current(issue) or "-"
    src_label = _format_rl_mapping_source(issue) or "-"
    current_lines = [
        f"Baseline (intervall): {int(interval_regnr) if interval_regnr is not None else '-'}",
        f"Override (klient): {int(override_regnr) if override_regnr is not None else '-'}",
        f"Effektiv RL: {effective_text}",
        f"Mappingkilde: {src_label}",
        f"Statuskode: {issue.mapping_status}",
    ]
    current = "\n".join(current_lines)
    if getattr(issue, "suggested_regnr", None) is not None:
        suggested_lines = [
            f"Forslag: {_format_rl_suggestion(issue)}",
            f"Kilde: {getattr(issue, 'suggestion_source', '') or '-'}",
            f"Tillit: {getattr(issue, 'confidence_bucket', '') or '-'}",
        ]
        sign_note = getattr(issue, "sign_note", "")
        if sign_note:
            suggested_lines.append(f"Fortegn: {sign_note}")
        suggested = "\n".join(suggested_lines)
    else:
        suggested = "Ingen smartforslag."
    why_lines = [
        _rl_mapping_source_explanation(issue) or "Ingen statusforklaring tilgjengelig.",
        getattr(issue, "suggestion_reason", "") or "Ingen smartforslag-signaler.",
        f"Neste: {_rl_preview_next_action_text(issue)}",
    ]
    return {
        "headline": headline,
        "current": current,
        "suggested": suggested,
        "why": "\n".join(why_lines),
    }
