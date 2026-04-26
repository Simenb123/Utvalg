from __future__ import annotations

from pathlib import Path

import src.shared.saft.reader as saft_reader


_SAFT_WITH_REFERENCE = """<?xml version="1.0" encoding="UTF-8"?>
<AuditFile>
  <MasterFiles>
    <GeneralLedgerAccounts>
      <Account>
        <AccountID>3000</AccountID>
        <AccountDescription>Sales</AccountDescription>
      </Account>
    </GeneralLedgerAccounts>
  </MasterFiles>
  <GeneralLedgerEntries>
    <Journal>
      <Transactions>
        <Transaction>
          <TransactionID>100443</TransactionID>
          <TransactionDate>2025-01-15</TransactionDate>
          <Description>Faktura nummer 443 til kunde</Description>
          <Lines>
            <DebitLine>
              <AccountID>1500</AccountID>
              <ReferenceNumber>443</ReferenceNumber>
              <Description>AR</Description>
              <DebitAmount>
                <Amount>125.00</Amount>
              </DebitAmount>
            </DebitLine>
            <CreditLine>
              <AccountID>3000</AccountID>
              <ReferenceNumber>443</ReferenceNumber>
              <Description>Revenue</Description>
              <CreditAmount>
                <Amount>100.00</Amount>
              </CreditAmount>
            </CreditLine>
          </Lines>
        </Transaction>
      </Transactions>
    </Journal>
  </GeneralLedgerEntries>
</AuditFile>
"""


def test_saft_reader_preserves_reference_number_as_extra_column(tmp_path: Path) -> None:
    xml_path = tmp_path / "saft.xml"
    xml_path.write_text(_SAFT_WITH_REFERENCE, encoding="utf-8")

    df = saft_reader.read_saft_ledger(xml_path)

    assert "Bilag" in df.columns
    assert "Referanse" in df.columns
    assert set(df["Bilag"].astype(str)) == {"100443"}
    assert set(df["Referanse"].astype(str)) == {"443"}
