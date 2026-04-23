from __future__ import annotations

from collections import Counter, defaultdict
from typing import Mapping, Sequence

import pandas as pd

from .helpers import _get_series, _konto_in_ranges, _konto_int, _norm_token, _tokenize
from .models import AccountUsageFeatures, BASIS_ENDRING
from .rulebook import RulebookRule


_ACCOUNT_ALIASES = ("konto", "account", "accountid", "kontonr")
_VOUCHER_ALIASES = ("bilag", "voucher", "bilagsnummer", "bilagsnr", "journalnr", "entryid")
_DATE_ALIASES = ("dato", "date", "bilagsdato", "postingdate", "documentdate")
_AMOUNT_ALIASES = ("beløp", "beloep", "belop", "amount", "netto", "sum")
_NAME_ALIASES = ("kontonavn", "navn", "accountname", "name")
_TEXT_ALIASES = (
    "tekst",
    "description",
    "beskrivelse",
    "transaksjonstekst",
    "bilagstekst",
    "memo",
)


def _resolve_column(df: pd.DataFrame, aliases: Sequence[str]) -> str | None:
    cols_l = {str(col).strip().lower(): str(col) for col in df.columns}
    for alias in aliases:
        if alias in cols_l:
            return cols_l[alias]
    return None


def _counterparty_prefix(account_no: str) -> str:
    konto = str(account_no or "").strip()
    if not konto:
        return ""
    if len(konto) >= 2 and konto[:2].isdigit():
        return konto[:2]
    if konto[:1].isdigit():
        return konto[:1]
    return ""


def _top_items(counter: Counter[str], *, limit: int = 6) -> tuple[str, ...]:
    out: list[str] = []
    for item, _count in counter.most_common(limit):
        text = str(item or "").strip()
        if text:
            out.append(text)
    return tuple(out)


# Modul-nivå cache. Funksjonen er deterministisk i input-DataFrame, så
# vi kan trygt returnere cached resultat hvis samme objekt sendes inn.
# Cache-nøkkel = id(df) + (n_rows, kolonner) som ekstra verifisering
# slik at vi ikke får falsk hit hvis Python gjenbruker minneadressen.
# Profil-måling viste at funksjonen tar ~4 sek for 200k rader pga
# iterrows(), og kalles på hver Analyse-refresh via mapping_issues.
_USAGE_CACHE: tuple[int, int, tuple, dict] | None = None


def _invalidate_usage_cache() -> None:
    """Tving re-bygging neste gang. For tester eller eksplisitt invalidering."""
    global _USAGE_CACHE
    _USAGE_CACHE = None


def build_account_usage_features(df_transactions: pd.DataFrame | None) -> dict[str, AccountUsageFeatures]:
    if df_transactions is None or not isinstance(df_transactions, pd.DataFrame) or df_transactions.empty:
        return {}

    global _USAGE_CACHE
    cache_key_a = id(df_transactions)
    cache_key_b = len(df_transactions.index)
    cache_key_c = tuple(str(c) for c in df_transactions.columns)
    cached = _USAGE_CACHE
    if (
        cached is not None
        and cached[0] == cache_key_a
        and cached[1] == cache_key_b
        and cached[2] == cache_key_c
    ):
        return cached[3]

    konto_col = _resolve_column(df_transactions, _ACCOUNT_ALIASES)
    if not konto_col:
        return {}

    frame = df_transactions.copy()
    frame["__konto"] = frame[konto_col].astype(str).str.strip()
    frame = frame.loc[frame["__konto"] != ""].copy()
    if frame.empty:
        return {}

    voucher_col = _resolve_column(frame, _VOUCHER_ALIASES)
    date_col = _resolve_column(frame, _DATE_ALIASES)
    amount_col = _resolve_column(frame, _AMOUNT_ALIASES)
    name_col = _resolve_column(frame, _NAME_ALIASES)
    text_col = _resolve_column(frame, _TEXT_ALIASES)

    if amount_col:
        frame["__amount"] = pd.to_numeric(frame[amount_col], errors="coerce").fillna(0.0)
    else:
        frame["__amount"] = _get_series(frame, BASIS_ENDRING)
    if voucher_col:
        frame["__voucher"] = frame[voucher_col].astype(str).str.strip()
    else:
        frame["__voucher"] = frame.index.astype(str)

    if date_col:
        dates = pd.to_datetime(frame[date_col], errors="coerce")
        frame["__month"] = dates.dt.to_period("M").astype(str).replace("NaT", "")
    else:
        frame["__month"] = ""

    if text_col:
        frame["__text"] = frame[text_col].fillna("").astype(str)
    else:
        frame["__text"] = ""
    if name_col:
        frame["__text"] = (frame["__text"].astype(str) + " " + frame[name_col].fillna("").astype(str)).str.strip()
    frame["__text_tokens"] = frame["__text"].map(lambda value: tuple(sorted(_tokenize(str(value)))))

    all_months = {month for month in frame["__month"].astype(str).tolist() if month}
    observed_months = max(len(all_months), 1)

    voucher_accounts: dict[str, set[str]] = defaultdict(set)
    for _, row in frame.iterrows():
        voucher = str(row.get("__voucher") or "").strip()
        konto = str(row.get("__konto") or "").strip()
        if voucher and konto:
            voucher_accounts[voucher].add(konto)

    counterparty_accounts: dict[str, Counter[str]] = defaultdict(Counter)
    counterparty_prefixes: dict[str, Counter[str]] = defaultdict(Counter)
    for voucher, accounts in voucher_accounts.items():
        unique_accounts = {str(account).strip() for account in accounts if str(account).strip()}
        if len(unique_accounts) <= 1:
            continue
        for account in unique_accounts:
            others = unique_accounts - {account}
            if not others:
                continue
            counterparty_accounts[account].update(others)
            counterparty_prefixes[account].update(
                prefix
                for prefix in (_counterparty_prefix(other) for other in others)
                if prefix
            )

    out: dict[str, AccountUsageFeatures] = {}
    for account_no, group in frame.groupby("__konto", sort=False):
        posting_count = int(len(group.index))
        unique_vouchers = int(group["__voucher"].astype(str).replace("", pd.NA).dropna().nunique())
        months = {str(month).strip() for month in group["__month"].astype(str).tolist() if str(month).strip()}
        active_months = len(months)
        positive_ratio = float((group["__amount"] > 0).mean()) if posting_count else 0.0
        negative_ratio = float((group["__amount"] < 0).mean()) if posting_count else 0.0

        abs_amounts = group["__amount"].abs().round(2)
        repeat_amount_ratio = 0.0
        if posting_count:
            counts = abs_amounts.value_counts(dropna=True)
            if not counts.empty:
                repeat_amount_ratio = float(counts.max()) / float(posting_count)

        text_counter: Counter[str] = Counter()
        for tokens in group["__text_tokens"].tolist():
            text_counter.update(str(token).strip() for token in (tokens or ()) if str(token).strip())

        out[str(account_no)] = AccountUsageFeatures(
            posting_count=posting_count,
            unique_vouchers=unique_vouchers or posting_count,
            active_months=active_months,
            monthly_regularity=float(active_months) / float(observed_months) if observed_months else 0.0,
            positive_ratio=max(0.0, min(1.0, positive_ratio)),
            negative_ratio=max(0.0, min(1.0, negative_ratio)),
            repeat_amount_ratio=max(0.0, min(1.0, repeat_amount_ratio)),
            top_text_tokens=_top_items(text_counter),
            top_counterparty_accounts=_top_items(counterparty_accounts.get(str(account_no), Counter())),
            top_counterparty_prefixes=_top_items(counterparty_prefixes.get(str(account_no), Counter())),
        )

    _USAGE_CACHE = (cache_key_a, cache_key_b, cache_key_c, out)
    return out


def score_usage_signal(
    *,
    code_tokens: set[str],
    rule: RulebookRule | None,
    usage: AccountUsageFeatures | None,
    historical_accounts: set[str] | None = None,
) -> tuple[float, tuple[str, ...]]:
    if usage is None:
        return 0.0, ()

    usage_tokens = {str(token).strip() for token in usage.top_text_tokens if str(token).strip()}
    historical = {str(account).strip() for account in (historical_accounts or set()) if str(account).strip()}

    token_hits = sorted(code_tokens & usage_tokens)
    token_score = (len(token_hits) / max(len(code_tokens), 1)) if code_tokens else 0.0

    counterparty_score = 0.0
    counterparty_signals: list[str] = []
    counterparty_accounts = {str(account).strip() for account in usage.top_counterparty_accounts if str(account).strip()}
    counterparty_prefixes = {str(prefix).strip() for prefix in usage.top_counterparty_prefixes if str(prefix).strip()}
    if historical:
        history_hits = sorted(counterparty_accounts & historical)
        if history_hits:
            counterparty_score = max(counterparty_score, 1.0)
            counterparty_signals.append("historikk")

    if rule is not None:
        if rule.allowed_ranges and any(_konto_in_ranges(account, rule.allowed_ranges) for account in counterparty_accounts):
            counterparty_score = max(counterparty_score, 0.8)
            counterparty_signals.append("motkonto")
        boost_set = {int(value) for value in rule.boost_accounts}
        if boost_set and any(_konto_int(account) in boost_set for account in counterparty_accounts):
            counterparty_score = max(counterparty_score, 1.0)
            counterparty_signals.append("boost")
        if rule.allowed_ranges:
            range_prefixes = {str(start)[:2] for start, _end in rule.allowed_ranges if str(start)}
            if counterparty_prefixes & range_prefixes:
                counterparty_score = max(counterparty_score, 0.5)
                counterparty_signals.append("intervall")

    regularity_score = 0.5 * float(usage.monthly_regularity or 0.0) + 0.5 * float(usage.repeat_amount_ratio or 0.0)

    sign_score = 0.0
    if rule is not None and rule.expected_sign in (-1, 1):
        sign_score = float(usage.positive_ratio if int(rule.expected_sign) > 0 else usage.negative_ratio)

    score = (
        0.45 * token_score
        + 0.30 * counterparty_score
        + 0.15 * regularity_score
        + 0.10 * sign_score
    )
    score = max(0.0, min(1.0, score))

    reasons: list[str] = []
    if token_hits:
        reasons.append("tekst:" + ",".join(token_hits[:2]))
    for signal in ("historikk", "motkonto", "boost", "intervall"):
        if signal in counterparty_signals:
            reasons.append(signal)
            break
    if usage.monthly_regularity >= 0.5 or usage.repeat_amount_ratio >= 0.5:
        reasons.append("periodisitet")
    return score, tuple(reasons)
