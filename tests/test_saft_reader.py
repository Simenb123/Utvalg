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


_SAFT_WITH_HEADER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AuditFile>
  <Header>
    <AuditFileVersion>1.30</AuditFileVersion>
    <AuditFileCountry>NO</AuditFileCountry>
    <SoftwareCompanyName>Tripletex</SoftwareCompanyName>
    <SoftwareID>Tripletex.no</SoftwareID>
    <SoftwareVersion>1.0</SoftwareVersion>
    <Company>
      <Name>Test AS</Name>
    </Company>
  </Header>
  <MasterFiles/>
  <GeneralLedgerEntries/>
</AuditFile>
"""


def test_read_saft_header_tripletex(tmp_path: Path) -> None:
    xml_path = tmp_path / "saft_header.xml"
    xml_path.write_text(_SAFT_WITH_HEADER_XML, encoding="utf-8")

    header = saft_reader.read_saft_header(xml_path)

    assert header.software_company == "Tripletex"
    assert header.software_id == "Tripletex.no"
    assert header.software_version == "1.0"


def test_read_saft_header_missing_file(tmp_path: Path) -> None:
    header = saft_reader.read_saft_header(tmp_path / "does_not_exist.xml")
    assert header.software_company == ""
    assert header.software_id == ""


def test_read_saft_header_no_header(tmp_path: Path) -> None:
    """XML uten Header-element gir tom SaftHeader."""
    xml_path = tmp_path / "no_header.xml"
    xml_path.write_text(_MINIMAL_SAFT_XML, encoding="utf-8")

    header = saft_reader.read_saft_header(xml_path)
    assert header.software_company == ""


def test_detect_accounting_system_tripletex() -> None:
    header = saft_reader.SaftHeader(
        software_company="Tripletex",
        software_id="Tripletex.no",
        software_version="1.0",
    )
    assert saft_reader.detect_accounting_system(header) == "Tripletex"


def test_detect_accounting_system_poweroffice() -> None:
    header = saft_reader.SaftHeader(
        software_company="PowerOffice AS",
        software_id="PowerOffice GO",
        software_version="2.0",
    )
    assert saft_reader.detect_accounting_system(header) == "PowerOffice GO"


def test_detect_accounting_system_visma() -> None:
    header = saft_reader.SaftHeader(
        software_company="Visma Software International AS",
        software_id="Visma Global",
        software_version="10.0",
    )
    assert saft_reader.detect_accounting_system(header) == "Visma Business"


def test_detect_accounting_system_unknown() -> None:
    header = saft_reader.SaftHeader(
        software_company="Ukjent System AS",
        software_id="mystery",
        software_version="1.0",
    )
    assert saft_reader.detect_accounting_system(header) == ""


def test_detect_accounting_system_empty() -> None:
    header = saft_reader.SaftHeader()
    assert saft_reader.detect_accounting_system(header) == ""


def test_detect_accounting_system_fiken() -> None:
    header = saft_reader.SaftHeader(
        software_company="Fiken AS",
        software_id="Fiken",
        software_version="3.0",
    )
    assert saft_reader.detect_accounting_system(header) == "Fiken"


def test_detect_accounting_system_xledger() -> None:
    header = saft_reader.SaftHeader(
        software_company="Xledger",
        software_id="Xledger ERP",
        software_version="5.0",
    )
    assert saft_reader.detect_accounting_system(header) == "Xledger"


def test_detect_accounting_system_24seven() -> None:
    header = saft_reader.SaftHeader(
        software_company="24SevenOffice Norge AS",
        software_id="24SevenOffice",
        software_version="1.0",
    )
    assert saft_reader.detect_accounting_system(header) == "24SevenOffice"


def test_detect_accounting_system_uni_micro_alias() -> None:
    header = saft_reader.SaftHeader(
        software_company="Uni Micro AS",
        software_id="Uni Micro",
        software_version="4.0",
    )
    assert saft_reader.detect_accounting_system(header) == "Uni Economy"


def test_build_dataset_auto_detects_system_and_mva(tmp_path: Path, monkeypatch) -> None:
    """Integrasjonstest: build_dataset auto-setter system + MVA-mapping."""
    import src.pages.dataset.backend.pane_build as dataset_pane_build
    import regnskap_client_overrides

    # Pek overrides-dir til tmp slik at vi ikke forurenser ekte data
    monkeypatch.setattr(regnskap_client_overrides, "overrides_dir", lambda: tmp_path / "overrides")
    (tmp_path / "overrides").mkdir()

    # Skriv SAF-T med Tripletex-header
    xml_path = tmp_path / "saft.xml"
    xml_path.write_text(_SAFT_WITH_HEADER_XML, encoding="utf-8")

    client = "TestKlient AS"

    # Verifiser at ingenting er satt fra før
    assert regnskap_client_overrides.load_accounting_system(client) == ""
    assert regnskap_client_overrides.load_mva_code_mapping(client) == {}

    req = dataset_pane_build.BuildRequest(
        path=xml_path,
        mapping={},
        sheet_name=None,
        header_row=0,
        store_client=client,
        store_year="2025",
    )
    result = dataset_pane_build.build_dataset(req)
    assert result.df is not None

    # Regnskapssystem skal nå være satt
    assert regnskap_client_overrides.load_accounting_system(client) == "Tripletex"

    # MVA-mapping skal også være satt
    mva = regnskap_client_overrides.load_mva_code_mapping(client)
    assert len(mva) > 0
    # Tripletex bruker 1:1-mapping, så kode "1" -> "1"
    assert mva.get("1") == "1"


def test_build_dataset_does_not_overwrite_existing_system(tmp_path: Path, monkeypatch) -> None:
    """Skal ikke overskrive manuelt valgt regnskapssystem."""
    import src.pages.dataset.backend.pane_build as dataset_pane_build
    import regnskap_client_overrides

    monkeypatch.setattr(regnskap_client_overrides, "overrides_dir", lambda: tmp_path / "overrides")
    (tmp_path / "overrides").mkdir()

    xml_path = tmp_path / "saft.xml"
    xml_path.write_text(_SAFT_WITH_HEADER_XML, encoding="utf-8")

    client = "Manuell Klient AS"

    # Sett system manuelt først
    regnskap_client_overrides.save_accounting_system(client, "Visma Business")

    req = dataset_pane_build.BuildRequest(
        path=xml_path,
        mapping={},
        sheet_name=None,
        header_row=0,
        store_client=client,
        store_year="2025",
    )
    dataset_pane_build.build_dataset(req)

    # Skal fortsatt være Visma Business, ikke Tripletex
    assert regnskap_client_overrides.load_accounting_system(client) == "Visma Business"


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
