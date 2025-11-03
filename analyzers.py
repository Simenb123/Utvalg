"""
analyzers.py (façade)
---------------------
Kort modul som eksponerer analyser for ett datasett ved å videresende til
mindre, spesialiserte moduler. Holder API stabilt for controller/GUI.
"""

from __future__ import annotations

from analyzers_line_checks import (
    duplicates_doc_account,
    round_amounts,
    out_of_period,
)

from analyzers_outliers import (
    outliers_by_group,
)

from analyzers_round_share import (
    round_share_by_group,
)

__all__ = [
    "duplicates_doc_account",
    "round_amounts",
    "out_of_period",
    "outliers_by_group",
    "round_share_by_group",
]
