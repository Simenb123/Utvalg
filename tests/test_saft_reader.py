from __future__ import annotations

from pathlib import Path
import zipfile

import pandas as pd

import saft_reader


_MINIMAL_SAFT_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<AuditFile>
  <MasterFiles>
    <GeneralLedgerAccounts>
      <Account>
        <AccountID>3000</AccountID>
        <AccountDescription>Sales</AccountDescription>
      </Account>
    </GeneralLedgerAccounts>
    <Customers>
      <Customer>
        <CustomerID>100</CustomerID>
        <CompanyName>Acme AS</CompanyName>
      </Customer>
    </Customers>
  </MasterFiles>
  <GeneralLedgerEntries>
    <Journal>
      <JournalID>1</JournalID>
      <Transactions>
        <Transaction>
          <TransactionID>V1</TransactionID>
          <TransactionDate>2025-01-15</TransactionDate>
          <Description>Sale invoice</Description>
          <Lines>
            <DebitLine>
              <AccountID>1500</AccountID>
              <Description>AR</Description>
              <DebitAmount>
                <Amount>125.00</Amount>
              </DebitAmount>
              <CustomerID>100</CustomerID>
            </DebitLine>
            <CreditLine>
              <AccountID>3000</AccountID>
              <Description>Revenue</Description>
              <CreditAmount>
                <Amount>100.00</Amount>
                <CurrencyCode>NOK</CurrencyCode>
                <CurrencyAmount>100.00</CurrencyAmount>
              </CreditAmount>
            </CreditLine>
            <CreditLine>
              <AccountID>2700</AccountID>
              <Description>VAT</Description>
              <CreditAmount>
                <Amount>25.00</Amount>
              </CreditAmount>
              <TaxInformation>
                <TaxCode>3</TaxCode>
                <TaxPercentage>25</TaxPercentage>
                <TaxAmount>
                  <Amount>25.00</Amount>
                </TaxAmount>
              </TaxInformation>
            </CreditLine>
          </Lines>
        </Transaction>
      </Transactions>
    </Journal>
  </GeneralLedgerEntries>
</AuditFile>
"""


def test_is_saft_path() -> None:
    assert saft_reader.is_saft_path("a.zip")
    assert saft_reader.is_saft_path("a.XML")
    assert not saft_reader.is_saft_path("a.xlsx")


def test_read_saft_ledger_from_xml(tmp_path: Path) -> None:
    xml_path = tmp_path / "saft.xml"
    xml_path.write_text(_MINIMAL_SAFT_XML, encoding="utf-8")

    df = saft_reader.read_saft_ledger(xml_path)

    # 3 linjer (debet + 2 kredit)
    assert len(df) == 3

    # Kanoniske kolonner finnes
    for col in (
        "Konto",
        "Kontonavn",
        "Bilag",
        "Beløp",
        "Dato",
        "Tekst",
    ):
        assert col in df.columns

    # Sign-konvensjon: debit +, credit -
    assert df["Beløp"].sum() == 0

    # Kontonavn fylles fra MasterFiles for konto 3000
    row_3000 = df[df["Konto"] == "3000"].iloc[0]
    assert row_3000["Kontonavn"] == "Sales"

    # Kundenavn fra CustomerID
    row_1500 = df[df["Konto"] == "1500"].iloc[0]
    assert row_1500["Kundenr"] == "100"
    assert row_1500["Kundenavn"] == "Acme AS"

    # Valuta info
    assert (df["Valuta"] == "NOK").any()

    # Dato er datetime
    assert pd.api.types.is_datetime64_any_dtype(df["Dato"])


def test_read_saft_ledger_from_zip(tmp_path: Path) -> None:
    xml_path = tmp_path / "AuditFile.xml"
    xml_path.write_text(_MINIMAL_SAFT_XML, encoding="utf-8")

    zip_path = tmp_path / "saft.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(xml_path, arcname="AuditFile.xml")

    df = saft_reader.read_saft_ledger(zip_path)
    assert len(df) == 3
