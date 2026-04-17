"""Tests for ar_registry_pdf_parser — RF-1086 PDF parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from ar_registry_pdf_parser import (
    CompanyHeader,
    ShareholderRecord,
    Transaction,
    detect_year,
    parse_company_header,
    parse_rf1086_pdf,
    parse_shareholder_block,
    split_shareholder_blocks,
)

# ---------------------------------------------------------------------------
# detect_year
# ---------------------------------------------------------------------------


class TestDetectYear:
    def test_standard_title(self):
        assert detect_year("RF-1086 Aksjonærregisteroppgaven 2025") == "2025"

    def test_encoded_title(self):
        assert detect_year("RF-1086 Aksjon\xe6rregisteroppgaven 2024") == "2024"

    def test_no_year(self):
        assert detect_year("Noe annet dokument") == ""


# ---------------------------------------------------------------------------
# parse_shareholder_block
# ---------------------------------------------------------------------------

_SAMPLE_BLOCK = """\
          Selskapsidentifikasjon
          Org. nr.                       Aksjeklasse                        ISIN
          976588614                      Ordinære aksjer
          Aksjonæropplysninger - (navn, adresse, antall aksjer og utbytte)
          Post 19 Aksjonærens navn, adresse
          Aksjonæridentifikasjon (fødsels-/D-nummer, organisasjonsnummer, utenlandsk aksjonær-ID)
          10086345647
          Navn                                              Land
          AASHILD MARIUSSEN                                 NORGE
          Adresse                           Postnummer      Poststed
          OLAV AUKRUSTS VEI 22              0785            OSLO
          Antall 31.12.2024                 Antall 31.12.2025
          Post 20 Antall aksjer per
          aksjonær                         340           490
"""


class TestParseShareholderBlock:
    def test_person_shareholder(self):
        rec = parse_shareholder_block(_SAMPLE_BLOCK, page_number=2)
        assert rec is not None
        assert rec.shareholder_id == "10086345647"
        assert rec.shareholder_kind == "person"
        assert rec.shareholder_name == "AASHILD MARIUSSEN"
        assert rec.land == "NORGE"
        assert rec.address == "OLAV AUKRUSTS VEI 22"
        assert rec.postal_code == "0785"
        assert rec.postal_place == "OSLO"
        assert rec.shares_start == 340
        assert rec.shares_end == 490
        assert rec.page_number == 2

    def test_company_shareholder(self):
        block = _SAMPLE_BLOCK.replace("10086345647", "976588614").replace(
            "AASHILD MARIUSSEN", "SPOR ARKITEKTER AS"
        )
        rec = parse_shareholder_block(block, page_number=12)
        assert rec is not None
        assert rec.shareholder_id == "976588614"
        assert rec.shareholder_kind == "company"
        assert rec.shareholder_name == "SPOR ARKITEKTER AS"

    def test_no_id_returns_none(self):
        rec = parse_shareholder_block("No data here", page_number=1)
        assert rec is None


# ---------------------------------------------------------------------------
# Transaction parsing
# ---------------------------------------------------------------------------

_SAMPLE_WITH_TRANSACTIONS = """\
          Selskapsidentifikasjon
          Org. nr.                       Aksjeklasse                        ISIN
          976588614                      Ordinære aksjer
          Aksjonæropplysninger - (navn, adresse, antall aksjer og utbytte)
          Post 19 Aksjonærens navn, adresse
          Aksjonæridentifikasjon (fødsels-/D-nummer, organisasjonsnummer, utenlandsk aksjonær-ID)
          10086345647
          Navn                                              Land
          AASHILD MARIUSSEN                                 NORGE
          Adresse                           Postnummer      Poststed
          OLAV AUKRUSTS VEI 22              0785            OSLO
          Antall 31.12.2024                 Antall 31.12.2025
          Post 20 Antall aksjer per
          aksjonær                         340           490
         Transaksjoner (aksjer i tilgang/avgang) for denne aksjonæren
         Post 23 Aksjer i tilgang(anskaffelse)
          Se post 9 for opplysninger på selskapsnivå
           Transaksjonstype Antall aksjer   Tidspunkt
           Kjøp                          30 01.11.2025      01:00:00

           Total anskaffelsesverdi Givers/arvelaters f.nr. Givers org.nr.
                     7 530,30
           Transaksjonstype Antall aksjer   Tidspunkt
           Kjøp                          120 01.11.2025     09:00:00

           Total anskaffelsesverdi Givers/arvelaters f.nr. Givers org.nr.
                    30 121,20
"""


class TestTransactionParsing:
    def test_tilgang_transactions(self):
        rec = parse_shareholder_block(_SAMPLE_WITH_TRANSACTIONS, page_number=2)
        assert rec is not None
        assert len(rec.transactions) == 2

        t1 = rec.transactions[0]
        assert t1.direction == "tilgang"
        assert t1.trans_type == "Kjøp"
        assert t1.shares == 30
        assert t1.date == "01.11.2025"
        assert abs(t1.amount - 7530.30) < 0.01

        t2 = rec.transactions[1]
        assert t2.shares == 120
        assert abs(t2.amount - 30121.20) < 0.01

    def test_control_calculation(self):
        rec = parse_shareholder_block(_SAMPLE_WITH_TRANSACTIONS, page_number=2)
        assert rec is not None
        tilgang = sum(t.shares for t in rec.transactions if t.direction == "tilgang")
        avgang = sum(t.shares for t in rec.transactions if t.direction == "avgang")
        assert rec.shares_start + tilgang - avgang == rec.shares_end

    def test_avgang_transactions(self):
        block_with_avgang = _SAMPLE_WITH_TRANSACTIONS + """\
         Post 25 Aksjer i avgang
          Se post 11 for opplysninger på selskapsnivå

           Transaksjonstype Antall aksjer i avgang Tidspunkt
           Salg                         150 01.09.2025      00:00:00
           Totalt vederlag/Utbetalt av Mottakers f.nr. Mottakers org.nr.
           innbetalt kap.

                    37 651,50
"""
        rec = parse_shareholder_block(block_with_avgang, page_number=12)
        assert rec is not None
        avgang = [t for t in rec.transactions if t.direction == "avgang"]
        assert len(avgang) == 1
        assert avgang[0].trans_type == "Salg"
        assert avgang[0].shares == 150
        assert abs(avgang[0].amount - 37651.50) < 0.01


# ---------------------------------------------------------------------------
# split_shareholder_blocks
# ---------------------------------------------------------------------------


class TestSplitShareholderBlocks:
    def test_two_shareholders(self):
        page1 = "RF-1086 header page"
        page2 = "Aksjonæridentifikasjon (fødsels-/D-nummer)\n11111111111\nNavn Land\nALICE NORGE"
        page3 = "Aksjonæridentifikasjon (fødsels-/D-nummer)\n22222222222\nNavn Land\nBOB NORGE"
        blocks = split_shareholder_blocks([page1, page2, page3])
        assert len(blocks) == 2
        assert blocks[0][1] == 2  # page number
        assert blocks[1][1] == 3

    def test_multi_page_shareholder(self):
        page1 = "Header"
        page2 = "Aksjonæridentifikasjon (fødsels-/D-nummer)\n11111111111\nData"
        page3 = "Continuation of transactions..."  # no new ID
        page4 = "Aksjonæridentifikasjon (fødsels-/D-nummer)\n22222222222\nData"
        blocks = split_shareholder_blocks([page1, page2, page3, page4])
        assert len(blocks) == 2
        assert "Continuation" in blocks[0][0]
        assert blocks[0][1] == 2
        assert blocks[1][1] == 4


# ---------------------------------------------------------------------------
# Integration test with real PDF
# ---------------------------------------------------------------------------

_PDF_PATH = Path(__file__).resolve().parent.parent / "doc" / "files" / "7162 Aksjonærregisteroppgaven 2025.pdf"


@pytest.mark.skipif(not _PDF_PATH.exists(), reason="Test PDF not available")
class TestIntegrationRealPdf:
    def test_parse_full_pdf(self):
        pytest.importorskip("pdfplumber", reason="pdfplumber not installed")
        result = parse_rf1086_pdf(_PDF_PATH)

        assert result.header.year == "2025"
        assert result.header.company_orgnr == "976588614"
        assert result.header.company_name == "SPOR ARKITEKTER AS"
        assert result.header.antall_aksjer_start == 2250
        assert result.header.antall_aksjer_end == 2250

        assert len(result.shareholders) == 11
        assert result.warnings == []

        # Verify sum of shares_end equals total
        total = sum(sh.shares_end for sh in result.shareholders)
        assert total == result.header.antall_aksjer_end

        # Check first shareholder
        first = result.shareholders[0]
        assert first.shareholder_id == "10086345647"
        assert first.shareholder_name == "AASHILD MARIUSSEN"
        assert first.shares_start == 340
        assert first.shares_end == 490
        assert first.shareholder_kind == "person"
        assert first.address == "OLAV AUKRUSTS VEI 22"
        assert len(first.transactions) == 2

        # Verify control calculation for all shareholders
        for sh in result.shareholders:
            tilgang = sum(t.shares for t in sh.transactions if t.direction == "tilgang")
            avgang = sum(t.shares for t in sh.transactions if t.direction == "avgang")
            assert sh.shares_start + tilgang - avgang == sh.shares_end, (
                f"{sh.shareholder_name}: {sh.shares_start}+{tilgang}-{avgang} != {sh.shares_end}"
            )

        # Check company as shareholder (egne aksjer)
        company_sh = [s for s in result.shareholders if s.shareholder_kind == "company"]
        assert len(company_sh) == 1
        assert company_sh[0].shareholder_id == "976588614"
        assert company_sh[0].shares_start == 885
        assert company_sh[0].shares_end == 245
        assert len(company_sh[0].transactions) > 0
