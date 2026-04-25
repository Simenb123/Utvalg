"""consolidation.suggestions – Forslagsmotor for elimineringer.

Genererer elimineringskandidater basert paa en eksplisitt regelkatalog
over regnskapslinjenavn. Arbeider paa regnskapslinjenivaa — kontoer
brukes kun for sporbarhet.

Bruksflyt:
    1. generate_suggestions() analyserer mapped TBer og returnerer kandidater
    2. GUI viser kandidater i Forslag-fanen
    3. Bruker godkjenner/ignorerer/redigerer
    4. create_journal_from_suggestion() oppretter journal med ferdig linjer
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .models import (
    CompanyTB,
    ConsolidationProject,
    EliminationLine,
    EliminationJournal,
    EliminationSuggestion,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regelkatalog — eksplisitte match-par basert paa regnskapslinjenavn
# ---------------------------------------------------------------------------

@dataclass
class MatchRule:
    """En regel som matcher to regnskapslinjer som elimineringskandidater."""
    kind: str                         # SUGGESTION_KINDS-verdi
    pattern_a: str                    # regex for linje A (debet-side)
    pattern_b: str                    # regex for linje B (kredit-side)
    label: str = ""                   # menneskelesbar beskrivelse
    sign_flip: bool = True            # True = A og B forventes aa ha motsatt fortegn
    template_only: bool = False       # True = generer template, ikke autojournal


# V1 regelkatalog — norske regnskapslinjenavn
_RULES: list[MatchRule] = [
    # --- Konsernmellomvaerende ---
    MatchRule(
        kind="intercompany",
        pattern_a=r"konsernfordring",
        pattern_b=r"konserngjeld",
        label="Konsernmellomværende (fordring/gjeld)",
    ),
    MatchRule(
        kind="intercompany",
        pattern_a=r"mellomværende.*konsern|fordring.*konsern",
        pattern_b=r"gjeld.*konsern|skyldig.*konsern",
        label="Konsernmellomværende (mellomværende)",
    ),
    # --- Renter ---
    MatchRule(
        kind="interest",
        pattern_a=r"renteinntekt.*(?:foretak|konsern|samme\s*konsern)",
        pattern_b=r"rentekostnad.*(?:foretak|konsern|samme\s*konsern)",
        label="Konsernrenter (inntekt/kostnad)",
    ),
    # --- Konsernbidrag ---
    MatchRule(
        kind="group_contribution",
        pattern_a=r"mottatt\s*konsernbidrag",
        pattern_b=r"(?:avgitt|avsatt)\s*konsernbidrag",
        label="Konsernbidrag (mottatt/avgitt)",
    ),
    # --- Utbytte ---
    MatchRule(
        kind="group_contribution",
        pattern_a=r"utbytte.*(?:datter|konsern|foretak)|mottatt.*utbytte",
        pattern_b=r"(?:avsatt|foreslått).*utbytte|utbytte.*(?:avsatt|betalt)",
        label="Utbytte (mottatt/avsatt)",
    ),
    # --- Investering / EK (template) ---
    MatchRule(
        kind="investment_equity",
        pattern_a=r"investering.*(?:datter|konsern)|andel.*(?:datter|konsern)",
        pattern_b=r"(?:aksje|egenkapital|innbetalt|opptjent).*(?:kapital|egenkapital)",
        label="Investering mot EK (template)",
        template_only=True,
    ),
    # --- Utvidede varianter ---
    MatchRule(
        kind="intercompany",
        pattern_a=r"kundefordring.*(?:konsern|foretak|same\s*konsern)",
        pattern_b=r"leverand.rgjeld.*(?:konsern|foretak|same\s*konsern)",
        label="Konsern kundefordring/leverandørgjeld",
    ),
    MatchRule(
        kind="intercompany",
        pattern_a=r"(?:annen|andre)\s*(?:lang|kort).*fordring.*(?:konsern|foretak)",
        pattern_b=r"(?:annen|andre)\s*(?:lang|kort).*gjeld.*(?:konsern|foretak)",
        label="Annen konsernfordring/-gjeld",
    ),
    MatchRule(
        kind="group_contribution",
        pattern_a=r"konsernbidrag.*mottatt|mottatt.*konsernbidrag",
        pattern_b=r"konsernbidrag.*(?:avgitt|ytt)|(?:avgitt|ytt).*konsernbidrag",
        label="Konsernbidrag (mottatt/avgitt, variant)",
    ),
    MatchRule(
        kind="interest",
        pattern_a=r"(?:annen\s*)?finansinntekt.*(?:konsern|foretak)",
        pattern_b=r"(?:annen\s*)?finanskostnad.*(?:konsern|foretak)",
        label="Konsern finansinntekt/-kostnad",
    ),
]


def _normalize_line_name(text: str) -> str:
    """Normaliser regnskapslinjenavn for fuzzy matching."""
    t = text.lower().strip()
    replacements = {
        "æ": "ae", "ø": "oe", "å": "aa",
        "é": "e", "ü": "u",
        "-": " ", "/": " ", "&": " og ",
    }
    for src, dst in replacements.items():
        t = t.replace(src, dst)
    return " ".join(t.split())


def _match_pattern(text: str, pattern: str) -> bool:
    """Case-insensitive regex match with fuzzy normalization."""
    if re.search(pattern, text, re.IGNORECASE):
        return True
    # Try normalized form
    normalized = _normalize_line_name(text)
    normalized_pattern = _normalize_line_name(pattern)
    if re.search(pattern, normalized, re.IGNORECASE):
        return True
    # Keyword containment fallback: all words in pattern present in text
    pattern_words = set(re.findall(r"\w+", normalized_pattern))
    if pattern_words and len(pattern_words) >= 2:
        text_words = set(re.findall(r"\w+", normalized))
        if pattern_words.issubset(text_words):
            return True
    return False


# ---------------------------------------------------------------------------
# Valutakonvertering
# ---------------------------------------------------------------------------

def _convert_amount(
    amount: float,
    regnr: int,
    company: CompanyTB,
    reporting_currency: str,
) -> tuple[float, float]:
    """Konverter beloep fra selskapsvaluta til rapporteringsvaluta.

    Returnerer (konvertert_beloep, brukt_kurs).
    Resultatlinjer (regnr < 500) bruker snittkurs,
    balanselinjer (regnr >= 500) bruker sluttkurs.
    """
    if not company.currency_code or company.currency_code == reporting_currency:
        return amount, 1.0
    if company.closing_rate == 1.0 and company.average_rate == 1.0:
        return amount, 1.0

    rate = company.average_rate if regnr < 500 else company.closing_rate
    return amount * rate, rate


# ---------------------------------------------------------------------------
# Kandidatgenerering
# ---------------------------------------------------------------------------

def _make_suggestion_key(kind: str, cid_a: str, cid_b: str, regnr_a: int, regnr_b: int) -> str:
    """Stabil noekkel for en kandidat — deterministisk for persistert state."""
    parts = sorted([(cid_a, regnr_a), (cid_b, regnr_b)])
    return f"{kind}:{parts[0][0]}:{parts[0][1]}:{parts[1][0]}:{parts[1][1]}"


def _canonical_direction(
    cid_a: str, cid_b: str,
    rn_a: int, rn_b: int,
    parent_id: str,
    companies_by_id: dict[str, CompanyTB],
) -> tuple[str, str, int, int]:
    """Normaliser retning slik at parent alltid er A-siden.

    Hvis ingen parent: stabil sortering paa selskapsnavn/id.
    Returnerer (company_a, company_b, regnr_a, regnr_b).
    """
    if parent_id:
        if cid_b == parent_id:
            return cid_b, cid_a, rn_b, rn_a
        return cid_a, cid_b, rn_a, rn_b
    # Stabil sortering: alfabetisk paa navn, deretter id
    name_a = companies_by_id.get(cid_a, CompanyTB()).name
    name_b = companies_by_id.get(cid_b, CompanyTB()).name
    if (name_a, cid_a) > (name_b, cid_b):
        return cid_b, cid_a, rn_b, rn_a
    return cid_a, cid_b, rn_a, rn_b


def generate_suggestions(
    project: ConsolidationProject,
    mapped_tbs: dict[str, pd.DataFrame],
    regnr_to_name: dict[int, str],
) -> list[EliminationSuggestion]:
    """Generer elimineringskandidater fra mapped TBer.

    Retning normaliseres: parent er alltid company_a.
    Duplikater (speilet retning) filtreres bort via stabil noekel.
    """
    companies_by_id = {c.company_id: c for c in project.companies}
    parent_id = project.parent_company_id or ""
    ignored = set(project.ignored_suggestion_keys)
    applied = set(project.applied_suggestion_keys)

    # Bygg regnr -> aggregert beloep per selskap
    company_regnr_amounts: dict[str, dict[int, float]] = {}
    for cid, tb in mapped_tbs.items():
        if tb is None or tb.empty or "regnr" not in tb.columns:
            continue
        valid = tb.dropna(subset=["regnr"]).copy()
        valid["regnr"] = valid["regnr"].astype(int)
        agg = valid.groupby("regnr")["ub"].sum()
        company_regnr_amounts[cid] = agg.to_dict()

    regnr_names: dict[int, str] = dict(regnr_to_name)

    suggestions: list[EliminationSuggestion] = []
    seen_keys: set[str] = set()

    company_ids = sorted(company_regnr_amounts.keys())

    for rule in _RULES:
        matching_a = [
            rn for rn, name in regnr_names.items()
            if _match_pattern(name, rule.pattern_a)
        ]
        matching_b = [
            rn for rn, name in regnr_names.items()
            if _match_pattern(name, rule.pattern_b)
        ]
        if not matching_a or not matching_b:
            continue

        for i, cid_x in enumerate(company_ids):
            comp_x = companies_by_id.get(cid_x)
            if not comp_x:
                continue

            for cid_y in company_ids[i + 1:]:
                comp_y = companies_by_id.get(cid_y)
                if not comp_y:
                    continue

                for rn_a in matching_a:
                    for rn_b in matching_b:
                        # Proev begge tilordninger av regnr til selskap
                        for cx, cy, ra, rb in [
                            (cid_x, cid_y, rn_a, rn_b),
                            (cid_y, cid_x, rn_a, rn_b),
                        ]:
                            amt_a_raw = company_regnr_amounts.get(cx, {}).get(ra, 0.0)
                            amt_b_raw = company_regnr_amounts.get(cy, {}).get(rb, 0.0)
                            if abs(amt_a_raw) < 0.005 and abs(amt_b_raw) < 0.005:
                                continue

                            key = _make_suggestion_key(rule.kind, cx, cy, ra, rb)
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)

                            # Normaliser retning: parent alltid A
                            ca, cb, ra_n, rb_n = _canonical_direction(
                                cx, cy, ra, rb, parent_id, companies_by_id,
                            )
                            # Hent beloep i normalisert retning
                            amt_a_raw = company_regnr_amounts.get(ca, {}).get(ra_n, 0.0)
                            amt_b_raw = company_regnr_amounts.get(cb, {}).get(rb_n, 0.0)

                            comp_ca = companies_by_id[ca]
                            comp_cb = companies_by_id[cb]
                            amt_a_nok, rate_a = _convert_amount(
                                amt_a_raw, ra_n, comp_ca, project.reporting_currency,
                            )
                            amt_b_nok, rate_b = _convert_amount(
                                amt_b_raw, rb_n, comp_cb, project.reporting_currency,
                            )

                            diff = amt_a_nok + amt_b_nok

                            status = "ny"
                            if key in applied:
                                status = "journalfoert"
                            elif key in ignored:
                                status = "ignorert"

                            draft_lines = _build_draft_lines(
                                ca, cb, ra_n, rb_n,
                                amt_a_nok, amt_b_nok,
                                rule, project,
                            )

                            suggestions.append(EliminationSuggestion(
                                suggestion_key=key,
                                kind=rule.kind,
                                company_a_id=ca,
                                company_b_id=cb,
                                regnr_a=ra_n,
                                regnr_b=rb_n,
                                line_name_a=regnr_names.get(ra_n, ""),
                                line_name_b=regnr_names.get(rb_n, ""),
                                amount_a=amt_a_nok,
                                amount_b=amt_b_nok,
                                diff_nok=diff,
                                currency_a=comp_ca.currency_code,
                                currency_b=comp_cb.currency_code,
                                source_amount_a=amt_a_raw,
                                source_amount_b=amt_b_raw,
                                status=status,
                                journal_draft_lines=draft_lines,
                            ))

    # Sorter: kind, deretter motpart (B) navn
    kind_order = {k: i for i, k in enumerate(
        ("intercompany", "interest", "group_contribution",
         "investment_equity", "fx_difference")
    )}
    suggestions.sort(key=lambda s: (
        kind_order.get(s.kind, 99),
        companies_by_id.get(s.company_b_id, CompanyTB()).name,
        s.regnr_a,
    ))

    logger.info("Generated %d elimination suggestions", len(suggestions))
    return suggestions


# ---------------------------------------------------------------------------
# Journalutkast fra kandidat
# ---------------------------------------------------------------------------

def _build_draft_lines(
    cid_a: str, cid_b: str,
    regnr_a: int, regnr_b: int,
    amount_a_nok: float, amount_b_nok: float,
    rule: MatchRule,
    project: ConsolidationProject,
) -> list[EliminationLine]:
    """Bygg journal-utkastlinjer for en kandidat."""
    lines = []

    if rule.sign_flip:
        # Standard eliminering: reverser begge sider
        lines.append(EliminationLine(
            regnr=regnr_a,
            company_id=cid_a,
            amount=-amount_a_nok,
            description=f"Elim {rule.label}",
        ))
        lines.append(EliminationLine(
            regnr=regnr_b,
            company_id=cid_b,
            amount=-amount_b_nok,
            description=f"Elim {rule.label}",
        ))
    else:
        # Ikke-standard (template): bare vis beloepene
        lines.append(EliminationLine(
            regnr=regnr_a,
            company_id=cid_a,
            amount=-amount_a_nok,
            description=f"Template: {rule.label}",
        ))
        lines.append(EliminationLine(
            regnr=regnr_b,
            company_id=cid_b,
            amount=amount_a_nok,
            description=f"Template: {rule.label} (motpost)",
        ))

    return lines


def create_journal_from_suggestion(
    suggestion: EliminationSuggestion,
    project: ConsolidationProject,
    *,
    name: str = "",
) -> EliminationJournal:
    """Opprett EliminationJournal fra en godkjent kandidat.

    Kopierer draft_lines inn i en ny journal og markerer suggestion som applied.
    """
    if not name:
        name = f"Elim: {suggestion.line_name_a} / {suggestion.line_name_b}"

    journal = EliminationJournal(
        voucher_no=project.next_elimination_voucher_no(),
        name=name,
        kind="template" if suggestion.kind == "investment_equity" else "from_suggestion",
        source_suggestion_key=suggestion.suggestion_key,
        lines=[
            EliminationLine(
                regnr=line.regnr,
                company_id=line.company_id,
                amount=line.amount,
                description=line.description,
                source_suggestion_key=suggestion.suggestion_key,
            )
            for line in suggestion.journal_draft_lines
        ],
    )
    if not journal.name:
        journal.name = journal.display_label

    # Oppdater project state
    if suggestion.suggestion_key not in project.applied_suggestion_keys:
        project.applied_suggestion_keys.append(suggestion.suggestion_key)
    # Fjern fra ignorert hvis den var det
    if suggestion.suggestion_key in project.ignored_suggestion_keys:
        project.ignored_suggestion_keys.remove(suggestion.suggestion_key)

    return journal


def ignore_suggestion(
    suggestion_key: str,
    project: ConsolidationProject,
) -> None:
    """Marker en kandidat som ignorert."""
    if suggestion_key not in project.ignored_suggestion_keys:
        project.ignored_suggestion_keys.append(suggestion_key)
    if suggestion_key in project.applied_suggestion_keys:
        project.applied_suggestion_keys.remove(suggestion_key)


def unignore_suggestion(
    suggestion_key: str,
    project: ConsolidationProject,
) -> None:
    """Fjern ignorert-markering fra en kandidat."""
    if suggestion_key in project.ignored_suggestion_keys:
        project.ignored_suggestion_keys.remove(suggestion_key)
