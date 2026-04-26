from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd


@dataclass(frozen=True)
class MappingEvidence:
    signal: str
    score: float
    detail: str
    kind: str = "positive"


@dataclass(frozen=True)
class FlowAlert:
    severity: str
    message: str


@dataclass(frozen=True)
class FlowObservation:
    behavior_key: str
    behavior_label: str
    direction_label: str
    dominant_counterparties: tuple[str, ...]
    dominant_counterparty_groups: tuple[str, ...]


@dataclass(frozen=True)
class AccountBehaviorProfile:
    konto: str
    kontonavn: str
    current_regnr: int | None
    current_regnskapslinje: str
    observed_sign: int
    ib: float
    endring: float
    ub: float
    antall: int
    amount_total: float
    has_mva: bool
    text_tokens: tuple[str, ...]
    observation: FlowObservation
    alerts: tuple[FlowAlert, ...]


@dataclass(frozen=True)
class MappingSuggestion:
    konto: str
    suggested_regnr: int | None
    suggested_regnskapslinje: str
    behavior_key: str
    behavior_label: str
    confidence_score: float
    confidence_label: str
    status: str
    explanation: str
    evidences: tuple[MappingEvidence, ...]
    alerts: tuple[FlowAlert, ...]


@dataclass(frozen=True)
class _Rule:
    key: str
    label: str
    expected_sign: int | None
    allowed_ranges: tuple[tuple[int, int], ...]
    rl_keywords: tuple[str, ...]
    account_keywords: tuple[str, ...]
    text_keywords: tuple[str, ...]
    expected_counterparties: tuple[str, ...]
    vat_bonus: bool = False


_RULES: tuple[_Rule, ...] = (
    _Rule(
        key="salgsinntekt",
        label="Salgsinntekt",
        expected_sign=-1,
        allowed_ranges=((3000, 3999),),
        rl_keywords=("salg", "inntekt", "driftsinntekt", "revenue"),
        account_keywords=("salg", "inntekt", "honorar", "omsetning", "revenue"),
        text_keywords=("faktura", "sale", "kunde"),
        expected_counterparties=("kundefordringer", "bank", "mva"),
        vat_bonus=True,
    ),
    _Rule(
        key="kundefordringer",
        label="Kundefordringer",
        expected_sign=1,
        allowed_ranges=((1500, 1699),),
        rl_keywords=("kunde", "fordring", "debitor", "receivable"),
        account_keywords=("kunde", "fordring", "debitor", "receivable"),
        text_keywords=("faktura", "kunde"),
        expected_counterparties=("salgsinntekt", "mva", "bank"),
    ),
    _Rule(
        key="leverandorgjeld",
        label="Leverandorgjeld",
        expected_sign=-1,
        allowed_ranges=((2400, 2999),),
        rl_keywords=("leverandor", "gjeld", "payable"),
        account_keywords=("leverandor", "gjeld", "kreditor", "payable"),
        text_keywords=("leverandor", "invoice"),
        expected_counterparties=("varekost", "driftskostnad", "bank", "mva"),
    ),
    _Rule(
        key="bank",
        label="Bank",
        expected_sign=1,
        allowed_ranges=((1900, 1999),),
        rl_keywords=("bank", "kontant", "innskudd"),
        account_keywords=("bank", "konto", "kontant", "innskudd"),
        text_keywords=("bank", "betaling"),
        expected_counterparties=("salgsinntekt", "leverandorgjeld", "lonn", "lan"),
    ),
    _Rule(
        key="varekost",
        label="Varekost",
        expected_sign=1,
        allowed_ranges=((4000, 4999),),
        rl_keywords=("varekost", "innkjop", "cost", "driftskost"),
        account_keywords=("vare", "innkjop", "cost", "kjop"),
        text_keywords=("kjop", "supplier"),
        expected_counterparties=("leverandorgjeld", "bank", "mva", "lager"),
        vat_bonus=True,
    ),
    _Rule(
        key="driftskostnad",
        label="Driftskostnad",
        expected_sign=1,
        allowed_ranges=((5000, 7999),),
        rl_keywords=("kostnad", "drift", "expense"),
        account_keywords=("kost", "drift", "leie", "forsik", "expense"),
        text_keywords=("periodisering", "kostnad", "expense"),
        expected_counterparties=("leverandorgjeld", "bank", "forskudd_periode", "mva"),
        vat_bonus=True,
    ),
    _Rule(
        key="lager",
        label="Lager",
        expected_sign=1,
        allowed_ranges=((1400, 1499),),
        rl_keywords=("lager", "beholdning", "inventory"),
        account_keywords=("lager", "beholdning", "inventory", "konsignasjon"),
        text_keywords=("lager", "beholdning"),
        expected_counterparties=("varekost", "leverandorgjeld", "bank"),
    ),
    _Rule(
        key="forskudd_periode",
        label="Forskudd/periode",
        expected_sign=1,
        allowed_ranges=((1700, 1799), (2900, 2999)),
        rl_keywords=("forskudd", "periode", "periodisering", "prepaid"),
        account_keywords=("forskudd", "periode", "periodisering", "prepaid"),
        text_keywords=("periodisering", "forskudd"),
        expected_counterparties=("driftskostnad", "salgsinntekt", "bank"),
    ),
    _Rule(
        key="anleggsmidler",
        label="Anleggsmidler",
        expected_sign=1,
        allowed_ranges=((1000, 1399),),
        rl_keywords=("anlegg", "varige", "utstyr", "fixed"),
        account_keywords=("maskin", "utstyr", "inventar", "anlegg", "leasing"),
        text_keywords=("aktiva", "asset"),
        expected_counterparties=("bank", "leverandorgjeld", "driftskostnad"),
    ),
    _Rule(
        key="lan",
        label="Lan/gjeld",
        expected_sign=-1,
        allowed_ranges=((2200, 2399),),
        rl_keywords=("lan", "gjeld", "leasing", "obligasjon"),
        account_keywords=("lan", "leasing", "gjeld", "kassekreditt"),
        text_keywords=("avdrag", "rente", "lan"),
        expected_counterparties=("bank", "rentekostnad"),
    ),
    _Rule(
        key="mva",
        label="MVA",
        expected_sign=0,
        allowed_ranges=((2700, 2799),),
        rl_keywords=("mva", "avgift", "vat"),
        account_keywords=("mva", "avgift", "vat"),
        text_keywords=("mva", "vat"),
        expected_counterparties=("salgsinntekt", "varekost", "leverandorgjeld", "kundefordringer"),
    ),
    _Rule(
        key="lonn",
        label="Lonn",
        expected_sign=1,
        allowed_ranges=((5000, 5999),),
        rl_keywords=("lonn", "personal", "salary"),
        account_keywords=("lonn", "ferie", "person", "salary"),
        text_keywords=("lonn", "ferie", "ansatt"),
        expected_counterparties=("bank", "leverandorgjeld"),
    ),
)


def _account_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def _normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    for src, target in (("ø", "o"), ("æ", "ae"), ("å", "a")):
        text = text.replace(src, target)
    return text


def _text_contains_any(text: str, keywords: Sequence[str]) -> list[str]:
    matches: list[str] = []
    for keyword in keywords:
        needle = _normalize_text(keyword)
        if needle and needle in text:
            matches.append(keyword)
    return matches


def _sign_from_amounts(*, endring: float, ub: float, ib: float, amount_total: float) -> int:
    for value in (endring, ub, amount_total, ib):
        try:
            num = float(value or 0.0)
        except Exception:
            continue
        if abs(num) < 1e-9:
            continue
        return 1 if num > 0 else -1
    return 0


def _counterparty_group(account: str) -> str:
    account_int = _account_int(account)
    if account_int is None:
        return "ukjent"
    if 1500 <= account_int <= 1699:
        return "kundefordringer"
    if 2700 <= account_int <= 2799:
        return "mva"
    if 2400 <= account_int <= 2999:
        return "leverandorgjeld"
    if 3000 <= account_int <= 3999:
        return "salgsinntekt"
    if 4000 <= account_int <= 4999:
        return "varekost"
    if 5000 <= account_int <= 7999:
        return "driftskostnad"
    if 1900 <= account_int <= 1999:
        return "bank"
    if 1400 <= account_int <= 1499:
        return "lager"
    if 2200 <= account_int <= 2399:
        return "lan"
    return "ukjent"


def _coerce_number_series(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame.columns:
        return pd.Series([0.0] * len(frame.index), index=frame.index, dtype=float)
    return pd.to_numeric(frame[name], errors="coerce").fillna(0.0)


def _extract_text_tokens(frame: pd.DataFrame) -> tuple[str, ...]:
    text_col = None
    for candidate in ("Tekst", "Kontonavn"):
        if candidate in frame.columns:
            text_col = candidate
            break
    if text_col is None or frame.empty:
        return ()

    tokens: list[str] = []
    for value in frame[text_col].astype(str).tolist():
        text = _normalize_text(value)
        for token in text.replace("/", " ").replace(",", " ").split():
            if len(token) < 4:
                continue
            if token not in tokens:
                tokens.append(token)
            if len(tokens) >= 12:
                return tuple(tokens)
    return tuple(tokens)


def _dominant_counterparties(df_all: pd.DataFrame, konto: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if df_all is None or df_all.empty or "Bilag" not in df_all.columns or "Konto" not in df_all.columns:
        return (), ()

    work = df_all.copy()
    work["_konto"] = work["Konto"].astype(str).str.strip()
    work["_bilag"] = work["Bilag"].astype(str).str.strip()
    work = work.loc[(work["_konto"] != "") & (work["_bilag"] != "")]
    if work.empty:
        return (), ()

    selected = work.loc[work["_konto"] == str(konto).strip(), "_bilag"].drop_duplicates()
    if selected.empty:
        return (), ()

    counterparts = work.loc[work["_bilag"].isin(selected.tolist()) & (work["_konto"] != str(konto).strip()), "_konto"]
    if counterparts.empty:
        return (), ()

    counter_counts = counterparts.value_counts(dropna=False).head(5)
    accounts = tuple(str(idx).strip() for idx in counter_counts.index if str(idx).strip())
    groups: list[str] = []
    for account in accounts:
        group = _counterparty_group(account)
        if group not in groups and group != "ukjent":
            groups.append(group)
    return accounts, tuple(groups)


def _find_rule_by_key(key: str) -> _Rule | None:
    for rule in _RULES:
        if rule.key == key:
            return rule
    return None


def _confidence_label(score: float) -> str:
    if score >= 80.0:
        return "Hoy"
    if score >= 60.0:
        return "Middels"
    return "Lav"


def _pick_regnskapslinje(rule: _Rule, regnskapslinjer: pd.DataFrame | None) -> tuple[int | None, str]:
    if regnskapslinjer is None or regnskapslinjer.empty:
        return None, ""

    try:
        from .mapping import normalize_regnskapslinjer

        regn = normalize_regnskapslinjer(regnskapslinjer)
    except Exception:
        return None, ""

    best_score = -1
    best_regnr: int | None = None
    best_label = ""
    for row in regn.loc[~regn["sumpost"], ["regnr", "regnskapslinje"]].itertuples(index=False):
        label = str(row.regnskapslinje or "").strip()
        label_norm = _normalize_text(label)
        score = 0
        for keyword in rule.rl_keywords:
            if _normalize_text(keyword) in label_norm:
                score += 1
        if score > best_score:
            best_score = score
            best_regnr = int(row.regnr)
            best_label = label

    if best_score <= 0:
        return None, ""
    return best_regnr, best_label


def build_account_behavior_profile(
    konto_row: pd.Series | dict[str, object],
    *,
    df_all: pd.DataFrame | None,
) -> AccountBehaviorProfile:
    row = konto_row if isinstance(konto_row, pd.Series) else pd.Series(konto_row)
    konto = str(row.get("Konto", "") or "").strip()
    kontonavn = str(row.get("Kontonavn", "") or "").strip()
    current_regnr = row.get("Nr")
    try:
        current_regnr_int = int(current_regnr) if current_regnr == current_regnr else None
    except Exception:
        current_regnr_int = None
    current_regnskapslinje = str(row.get("Regnskapslinje", "") or "").strip()
    ib = float(pd.to_numeric(pd.Series([row.get("IB", 0.0)]), errors="coerce").fillna(0.0).iloc[0])
    endring = float(pd.to_numeric(pd.Series([row.get("Endring", 0.0)]), errors="coerce").fillna(0.0).iloc[0])
    ub = float(pd.to_numeric(pd.Series([row.get("UB", 0.0)]), errors="coerce").fillna(0.0).iloc[0])
    antall = int(pd.to_numeric(pd.Series([row.get("Antall", 0)]), errors="coerce").fillna(0).iloc[0])

    if isinstance(df_all, pd.DataFrame) and not df_all.empty and "Konto" in df_all.columns:
        account_scope = df_all.loc[df_all["Konto"].astype(str).str.strip() == konto].copy()
    else:
        account_scope = pd.DataFrame()

    amount_total = float(_coerce_number_series(account_scope, "Beløp").sum()) if not account_scope.empty else endring
    has_mva = bool(
        not account_scope.empty
        and (
            ("MVA-kode" in account_scope.columns and account_scope["MVA-kode"].astype(str).str.strip().ne("").any())
            or ("MVA-beløp" in account_scope.columns and _coerce_number_series(account_scope, "MVA-beløp").abs().gt(0).any())
        )
    )
    text_tokens = _extract_text_tokens(account_scope if not account_scope.empty else pd.DataFrame({"Kontonavn": [kontonavn]}))
    counterpart_accounts, counterpart_groups = _dominant_counterparties(df_all if isinstance(df_all, pd.DataFrame) else pd.DataFrame(), konto)
    observed_sign = _sign_from_amounts(endring=endring, ub=ub, ib=ib, amount_total=amount_total)

    observation = FlowObservation(
        behavior_key=_counterparty_group(konto),
        behavior_label="Uklassifisert",
        direction_label="Debet" if observed_sign > 0 else "Kredit" if observed_sign < 0 else "Blandet",
        dominant_counterparties=counterpart_accounts,
        dominant_counterparty_groups=counterpart_groups,
    )

    alerts: list[FlowAlert] = []
    label_norm = _normalize_text(current_regnskapslinje)
    if label_norm and "lager" in label_norm and observed_sign < 0:
        alerts.append(FlowAlert(severity="medium", message="Lagerlinje beveger seg hovedsakelig kredit."))
    if label_norm and any(token in label_norm for token in ("gjeld", "lan")) and observed_sign > 0:
        alerts.append(FlowAlert(severity="medium", message="Gjeldslinje beveger seg hovedsakelig debet."))
    if counterpart_groups and "salgsinntekt" in counterpart_groups and "fordring" not in label_norm and "inntekt" not in label_norm and _counterparty_group(konto) != "salgsinntekt":
        alerts.append(FlowAlert(severity="high", message="Konto har salgslignende motposter uten a være mappet som inntekt/kundefordring."))

    return AccountBehaviorProfile(
        konto=konto,
        kontonavn=kontonavn,
        current_regnr=current_regnr_int,
        current_regnskapslinje=current_regnskapslinje,
        observed_sign=observed_sign,
        ib=ib,
        endring=endring,
        ub=ub,
        antall=antall,
        amount_total=amount_total,
        has_mva=has_mva,
        text_tokens=text_tokens,
        observation=observation,
        alerts=tuple(alerts),
    )


def suggest_mapping(
    profile: AccountBehaviorProfile,
    *,
    regnskapslinjer: pd.DataFrame | None = None,
) -> MappingSuggestion:
    account_norm = _normalize_text(profile.kontonavn)
    current_norm = _normalize_text(profile.current_regnskapslinje)
    text_blob = " ".join(profile.text_tokens)
    account_int = _account_int(profile.konto)
    counterparties = set(profile.observation.dominant_counterparty_groups)

    scored: list[tuple[float, _Rule, list[MappingEvidence]]] = []
    for rule in _RULES:
        score = 0.0
        evidences: list[MappingEvidence] = []

        if account_int is not None and any(start <= account_int <= end for start, end in rule.allowed_ranges):
            score += 22.0
            evidences.append(MappingEvidence(signal="intervall", score=22.0, detail=f"Konto {profile.konto} ligger i forventet intervall for {rule.label}."))

        account_hits = _text_contains_any(account_norm, rule.account_keywords)
        if account_hits:
            score += min(22.0, 10.0 + (len(account_hits) * 4.0))
            evidences.append(MappingEvidence(signal="kontonavn", score=min(22.0, 10.0 + (len(account_hits) * 4.0)), detail=f"Kontonavn matcher {', '.join(account_hits[:3])}."))

        text_hits = _text_contains_any(text_blob, rule.text_keywords)
        if text_hits:
            score += min(14.0, 6.0 + (len(text_hits) * 2.5))
            evidences.append(MappingEvidence(signal="transaksjonstekst", score=min(14.0, 6.0 + (len(text_hits) * 2.5)), detail=f"Transaksjonstekst matcher {', '.join(text_hits[:3])}."))

        current_hits = _text_contains_any(current_norm, rule.rl_keywords)
        if current_hits:
            score += 8.0
            evidences.append(MappingEvidence(signal="naavaerende-linje", score=8.0, detail=f"Navaerende linje ligner {rule.label}."))

        if rule.expected_sign in (-1, 1):
            if profile.observed_sign == rule.expected_sign:
                score += 14.0
                evidences.append(MappingEvidence(signal="fortegn", score=14.0, detail=f"Fortegn stemmer med forventet saldo for {rule.label}."))
            elif profile.observed_sign != 0:
                score -= 10.0
                evidences.append(MappingEvidence(signal="fortegn", score=-10.0, detail=f"Fortegn trekker mot {rule.label}.", kind="negative"))

        matched_counterparties = counterparties.intersection(rule.expected_counterparties)
        if matched_counterparties:
            counterpart_score = min(22.0, 8.0 + 7.0 * len(matched_counterparties))
            score += counterpart_score
            evidences.append(MappingEvidence(signal="motpost", score=counterpart_score, detail=f"Motposter ligner {', '.join(sorted(matched_counterparties))}."))

        if rule.vat_bonus and profile.has_mva:
            score += 6.0
            evidences.append(MappingEvidence(signal="mva", score=6.0, detail="MVA-signaler styrker dette forslaget."))

        if score > 0:
            scored.append((score, rule, evidences))

    if not scored:
        base_alerts = tuple(profile.alerts)
        explanation = "Fant ikke et tydelig forslag ut fra intervall, tekst, fortegn og motposter."
        return MappingSuggestion(
            konto=profile.konto,
            suggested_regnr=None,
            suggested_regnskapslinje="",
            behavior_key=profile.observation.behavior_key,
            behavior_label="Uklassifisert",
            confidence_score=0.0,
            confidence_label="Lav",
            status="weak",
            explanation=explanation,
            evidences=(),
            alerts=base_alerts,
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_rule, evidences = scored[0]
    target_regnr, target_label = _pick_regnskapslinje(best_rule, regnskapslinjer)
    confidence = max(0.0, min(100.0, best_score))
    confidence_label = _confidence_label(confidence)
    alerts = list(profile.alerts)

    if profile.current_regnskapslinje:
        current_rl_norm = _normalize_text(profile.current_regnskapslinje)
        if not _text_contains_any(current_rl_norm, best_rule.rl_keywords) and confidence >= 60.0:
            alerts.append(FlowAlert(severity="high", message=f"Konto oppforer seg mer som {best_rule.label} enn dagens mapping."))

    status = "aligned"
    if alerts:
        status = "conflict"
    if confidence < 60.0:
        status = "weak"

    observation_label = best_rule.label
    explanation_bits = [f"Oppforer seg som {observation_label} ({confidence_label.lower()} tillit)."]
    if target_label:
        explanation_bits.append(f"Foreslatt regnskapslinje: {target_regnr} {target_label}.")
    if profile.observation.dominant_counterparty_groups:
        explanation_bits.append(f"Dominerende motposter: {', '.join(profile.observation.dominant_counterparty_groups)}.")
    explanation = " ".join(explanation_bits)

    return MappingSuggestion(
        konto=profile.konto,
        suggested_regnr=target_regnr,
        suggested_regnskapslinje=f"{target_regnr} {target_label}".strip() if target_label else "",
        behavior_key=best_rule.key,
        behavior_label=best_rule.label,
        confidence_score=confidence,
        confidence_label=confidence_label,
        status=status,
        explanation=explanation,
        evidences=tuple(evidences),
        alerts=tuple(alerts),
    )


def analyze_account_rows(
    accounts_df: pd.DataFrame,
    *,
    df_all: pd.DataFrame | None,
    regnskapslinjer: pd.DataFrame | None = None,
    review_state: dict[str, dict[str, object]] | None = None,
) -> tuple[pd.DataFrame, dict[str, MappingSuggestion], dict[str, AccountBehaviorProfile]]:
    if accounts_df is None or accounts_df.empty:
        return pd.DataFrame(), {}, {}

    review_state = review_state or {}
    suggestions: dict[str, MappingSuggestion] = {}
    profiles: dict[str, AccountBehaviorProfile] = {}
    rows: list[dict[str, object]] = []

    for row in accounts_df.reset_index(drop=True).to_dict("records"):
        profile = build_account_behavior_profile(row, df_all=df_all)
        suggestion = suggest_mapping(profile, regnskapslinjer=regnskapslinjer)
        suggestions[profile.konto] = suggestion
        profiles[profile.konto] = profile

        current_label = f"{row.get('Nr', '')} {row.get('Regnskapslinje', '')}".strip()
        alerts = [alert.message for alert in suggestion.alerts]
        review_payload = review_state.get(profile.konto, {})
        review_text = str(review_payload.get("status", "") or "").strip()
        if review_text == "accepted":
            review_text = "Akseptert"
        elif review_text == "rejected":
            review_text = "Avvist"
        else:
            review_text = ""

        rows.append(
            {
                "Nr": row.get("Nr", ""),
                "Regnskapslinje": row.get("Regnskapslinje", ""),
                "Konto": profile.konto,
                "Kontonavn": profile.kontonavn,
                "OppfortSom": current_label,
                "OppforerSegSom": suggestion.behavior_label,
                "ForslattRL": suggestion.suggested_regnskapslinje,
                "Confidence": suggestion.confidence_label,
                "ConfidenceScore": float(suggestion.confidence_score),
                "Avvik": "; ".join(alerts[:3]),
                "Review": review_text,
                "IB": float(row.get("IB", 0.0) or 0.0),
                "Endring": float(row.get("Endring", 0.0) or 0.0),
                "UB": float(row.get("UB", 0.0) or 0.0),
                "Antall": int(row.get("Antall", 0) or 0),
            }
        )

    detail_df = pd.DataFrame(rows)
    if not detail_df.empty:
        detail_df = detail_df.sort_values(
            ["ConfidenceScore", "Avvik", "Konto"],
            ascending=[False, False, True],
            kind="mergesort",
            ignore_index=True,
        )
    return detail_df, suggestions, profiles


def build_suggestion_rows(
    suggestion: MappingSuggestion | None,
    profile: AccountBehaviorProfile | None,
) -> list[tuple[str, str, str]]:
    if suggestion is None:
        return []

    rows: list[tuple[str, str, str]] = [
        ("Forslag", suggestion.confidence_label, suggestion.explanation),
    ]
    if profile is not None:
        current_label = f"{profile.current_regnr or ''} {profile.current_regnskapslinje}".strip()
        rows.append(("Oppfort som", profile.observation.direction_label, current_label))
        rows.append(("Oppforer seg som", suggestion.behavior_label, ", ".join(profile.observation.dominant_counterparty_groups) or "Ingen tydelig motpostfamilie"))
    for evidence in suggestion.evidences:
        status = "+" if evidence.score >= 0 else "-"
        rows.append((evidence.signal, status, evidence.detail))
    for alert in suggestion.alerts:
        rows.append(("Avvik", alert.severity, alert.message))
    return rows


def has_actionable_deviation(row: pd.Series | dict[str, object]) -> bool:
    series = row if isinstance(row, pd.Series) else pd.Series(row)
    avvik = str(series.get("Avvik", "") or "").strip()
    confidence = str(series.get("Confidence", "") or "").strip().lower()
    oppfort = str(series.get("OppfortSom", "") or "").strip()
    forslag = str(series.get("ForslattRL", "") or "").strip()
    return bool(avvik or confidence == "lav" or (forslag and oppfort and forslag != oppfort))


def summarize_alerts(rows: Iterable[str]) -> str:
    clean = [str(value or "").strip() for value in rows if str(value or "").strip()]
    if not clean:
        return ""
    if len(clean) <= 2:
        return " | ".join(clean)
    return " | ".join(clean[:2]) + f" (+{len(clean) - 2})"


__all__ = [
    "AccountBehaviorProfile",
    "FlowAlert",
    "FlowObservation",
    "MappingEvidence",
    "MappingSuggestion",
    "analyze_account_rows",
    "build_account_behavior_profile",
    "build_suggestion_rows",
    "has_actionable_deviation",
    "suggest_mapping",
    "summarize_alerts",
]
