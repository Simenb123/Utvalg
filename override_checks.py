"""
Kompatibilitetsmodul.

Historisk/planlagt importsti i repoet:
    from override_checks import large_vouchers, ...

Selve implementasjonen ligger i pakken `overstyring/` for å holde filene små og logisk gruppert.
"""

from overstyring.core import CheckResult, build_voucher_summary, resolve_core_columns
from overstyring.checks_amounts import large_vouchers, round_amount_vouchers
from overstyring.checks_risk import override_risk_vouchers
from overstyring.checks_duplicates import duplicate_lines_vouchers

__all__ = [
    "CheckResult",
    "resolve_core_columns",
    "build_voucher_summary",
    "large_vouchers",
    "round_amount_vouchers",
    "override_risk_vouchers",
    "duplicate_lines_vouchers",
]
