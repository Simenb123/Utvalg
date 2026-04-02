from __future__ import annotations

import pandas as pd

from document_control_app_service import build_voucher_context


def test_build_voucher_context_handles_alternative_column_names() -> None:
    df = pd.DataFrame(
        {
            "Bilagsnr": [1001, 1001],
            "Beskrivelse": ["INV-77 Eksempel Partner AS", "MVA INV-77"],
            "InvoiceDate": ["2025-02-15", "2025-02-15"],
            "SumBelop": [1250.0, 250.0],
        }
    )

    context = build_voucher_context(df)

    assert context is not None
    assert context.bilag == "1001"
    assert context.row_count == 2
    assert "INV-77 Eksempel Partner AS" in context.texts
    assert "15.02.2025" in context.dates
    assert context.amounts == [1250.0, 250.0]
