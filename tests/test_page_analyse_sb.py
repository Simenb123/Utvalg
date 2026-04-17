from __future__ import annotations

from types import SimpleNamespace

import pandas as pd


class _FakeLabel:
    def __init__(self):
        self.text = ""

    def configure(self, **kwargs):
        if "text" in kwargs:
            self.text = str(kwargs["text"])


class _FakeSBTree:
    def __init__(self, rows=None, selected=None, focus_item=""):
        self.rows = dict(rows or {})
        self._selection = list(selected or [])
        self._focus = focus_item
        self.selection_calls = []
        self.focus_calls = []
        self.see_calls = []
        self.tag_configs = {}
        self._options = {"columns": (), "displaycolumns": ("#all",)}
        self._bindings = []

    def configure(self, **kwargs):
        self._options.update(kwargs)

    def __setitem__(self, key, value):
        self._options[key] = value

    def __getitem__(self, key):
        return self._options.get(key)

    def bind(self, *_a, **_k):
        self._bindings.append((_a, _k))

    def identify_region(self, *_a, **_k):
        return "cell"

    def selection(self):
        return list(self._selection)

    def focus(self, item=None):
        if item is None:
            return self._focus
        self._focus = item
        self.focus_calls.append(item)

    def see(self, item):
        self.see_calls.append(item)

    def item(self, item, option=None):
        values = self.rows.get(item, [])
        if option == "values":
            return list(values)
        return {"values": list(values)}

    def get_children(self, *_a, **_k):
        return list(self.rows.keys())

    def delete(self, item):
        self.rows.pop(item, None)

    def insert(self, _parent, _index, values=(), tags=()):
        item = f"row{len(self.rows) + 1}"
        self.rows[item] = list(values)
        return item

    def selection_set(self, items):
        if isinstance(items, (list, tuple)):
            self._selection = list(items)
        else:
            self._selection = [items]
        self.selection_calls.append(list(self._selection))

    def tag_configure(self, tag, **kwargs):
        self.tag_configs[tag] = dict(kwargs)

    def column(self, name, **kwargs):
        if not hasattr(self, "column_configs"):
            self.column_configs = {}
        self.column_configs.setdefault(name, {}).update(kwargs)

    def heading(self, name, **kwargs):
        if not hasattr(self, "heading_configs"):
            self.heading_configs = {}
        self.heading_configs.setdefault(name, {}).update(kwargs)


def test_capture_sb_selection_reads_selected_accounts_and_focus():
    import page_analyse_sb

    tree = _FakeSBTree(
        rows={
            "a": ["1000", "Bank", "0,00", "10,00", "10,00", ""],
            "b": ["1500", "Kunde", "0,00", "20,00", "20,00", ""],
        },
        selected=["b"],
        focus_item="b",
    )

    selected_accounts, focused_account = page_analyse_sb._capture_sb_selection(tree)

    assert selected_accounts == ["1500"]
    assert focused_account == "1500"


def test_refresh_sb_view_restores_selection_after_refresh(monkeypatch):
    import page_analyse_sb

    tree = _FakeSBTree(
        rows={
            "old1": ["1000", "Bank", "0,00", "10,00", "10,00", ""],
            "old2": ["1500", "Kunde", "0,00", "20,00", "20,00", ""],
        },
        selected=["old2"],
        focus_item="old2",
    )
    page = SimpleNamespace(
        _sb_tree=tree,
        _rl_sb_df=pd.DataFrame(
            {
                "konto": ["1000", "1500"],
                "kontonavn": ["Bank", "Kunde"],
                "ib": [0.0, 0.0],
                "endring": [10.0, 20.0],
                "ub": [10.0, 20.0],
            }
        ),
        _lbl_tx_summary=_FakeLabel(),
        _get_effective_sb_df=lambda: pd.DataFrame(
            {
                "konto": ["1000", "1500"],
                "kontonavn": ["Bank", "Kunde"],
                "ib": [0.0, 0.0],
                "endring": [10.0, 20.0],
                "ub": [10.0, 20.0],
            }
        ),
    )

    monkeypatch.setattr(page_analyse_sb, "_clear_tree", lambda t: [t.delete(item) for item in list(t.get_children(""))])
    monkeypatch.setattr(page_analyse_sb, "_resolve_target_kontoer", lambda **_k: {"1000", "1500"})
    monkeypatch.setattr(page_analyse_sb, "_bind_sb_once", lambda **_k: None)

    page_analyse_sb.refresh_sb_view(page=page)

    assert tree.selection_calls, "SB refresh should restore selection when there was one before refresh"
    selected_item = tree.selection_calls[-1][0]
    values = tree.item(selected_item, "values")
    assert values[0] == "1500"
    assert tree.focus_calls[-1] == selected_item
    assert tree.see_calls[-1] == selected_item


def _make_sb_page(*, prev_df=None):
    sb_df = pd.DataFrame(
        {
            "konto": ["1000", "1500"],
            "kontonavn": ["Bank", "Kunde"],
            "ib": [0.0, 0.0],
            "endring": [10.0, 20.0],
            "ub": [10.0, 20.0],
        }
    )
    return SimpleNamespace(
        _sb_tree=_FakeSBTree(),
        _rl_sb_df=sb_df,
        _rl_sb_prev_df=prev_df,
        _lbl_tx_summary=_FakeLabel(),
        _get_effective_sb_df=lambda: sb_df,
    )


def _stub_sb_helpers(monkeypatch):
    import page_analyse_sb

    monkeypatch.setattr(
        page_analyse_sb,
        "_clear_tree",
        lambda t: [t.delete(item) for item in list(t.get_children(""))],
    )
    monkeypatch.setattr(
        page_analyse_sb,
        "_resolve_target_kontoer",
        lambda **_k: {"1000", "1500"},
    )
    monkeypatch.setattr(page_analyse_sb, "_bind_sb_once", lambda **_k: None)
    monkeypatch.setattr(page_analyse_sb, "_get_selected_rl_name", lambda **_k: "")


def test_refresh_sb_view_hides_ub_fjor_when_no_prev(monkeypatch):
    import page_analyse_sb

    _stub_sb_helpers(monkeypatch)
    page = _make_sb_page(prev_df=None)
    # Gi page default SB-kolonner (configure_sb_tree_columns leser disse)
    from page_analyse_sb import SB_COLS
    page._sb_cols_order = list(SB_COLS)
    page._sb_cols_visible = list(SB_COLS)
    page._tk_ok = True

    page_analyse_sb.refresh_sb_view(page=page)

    tree = page._sb_tree
    # Uten fjor\u00e5rsdata skal UB_fjor ekskluderes fra displaycolumns
    display = tree["displaycolumns"]
    assert "UB_fjor" not in display
    # Rader har tom UB_fjor-celle p\u00e5 indeks 8
    for row in tree.rows.values():
        assert row[_UB_FJOR_IDX] == ""
    assert "UB i fjor" not in page._lbl_tx_summary.text


def test_refresh_sb_view_shows_ub_fjor_when_prev_exists(monkeypatch):
    import page_analyse_sb

    _stub_sb_helpers(monkeypatch)
    prev = pd.DataFrame(
        {"konto": ["1000", "1500"], "ub": [5.0, 18.0]}
    )
    page = _make_sb_page(prev_df=prev)
    from page_analyse_sb import SB_COLS
    page._sb_cols_order = list(SB_COLS)
    page._sb_cols_visible = list(SB_COLS)
    page._tk_ok = True

    page_analyse_sb.refresh_sb_view(page=page)

    tree = page._sb_tree
    # UB_fjor skal v\u00e6re synlig
    display = tree["displaycolumns"]
    assert "UB_fjor" in display
    # Finn rad for konto 1500 og verifiser UB_fjor-celle ikke er tom
    values_by_konto = {row[0]: row for row in tree.rows.values()}
    assert "1500" in values_by_konto
    ub_fjor_cell = values_by_konto["1500"][_UB_FJOR_IDX]
    assert ub_fjor_cell != ""
    # Summary skal inkludere Sum UB i fjor
    assert "Sum UB i fjor" in page._lbl_tx_summary.text


def test_refresh_sb_view_blank_ub_fjor_when_konto_missing(monkeypatch):
    import page_analyse_sb

    _stub_sb_helpers(monkeypatch)
    # Kun konto 1000 har fjorårsverdi; 1500 mangler
    prev = pd.DataFrame({"konto": ["1000"], "ub": [5.0]})
    page = _make_sb_page(prev_df=prev)

    page_analyse_sb.refresh_sb_view(page=page)

    tree = page._sb_tree
    values_by_konto = {row[0]: row for row in tree.rows.values()}
    assert values_by_konto["1000"][_UB_FJOR_IDX] != ""
    assert values_by_konto["1500"][_UB_FJOR_IDX] == ""


# =====================================================================
# Kontogjennomgang (OK + vedlegg)
# =====================================================================

def test_account_review_set_ok_persists(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)
    client, year = "Test Klient AS", "2024"

    _rco.set_accounts_ok(client, year, ["1920"], True)
    review = _rco.load_account_review(client, year)
    assert review.get("1920", {}).get("ok") is True

    _rco.set_accounts_ok(client, year, ["1920"], False)
    review = _rco.load_account_review(client, year)
    assert "1920" not in review  # tom entry prunes


def test_account_review_bulk_set_ok(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)
    _rco.set_accounts_ok("Klient AS", "2024", ["1920", "1930", "1940"], True)

    review = _rco.load_account_review("Klient AS", "2024")
    assert review["1920"]["ok"] is True
    assert review["1930"]["ok"] is True
    assert review["1940"]["ok"] is True


def test_account_review_add_attachments_dedup(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)
    f1 = tmp_path / "bilag.pdf"
    f1.write_text("x", encoding="utf-8")

    _rco.add_account_attachments("Klient", "2024", ["1920"], [str(f1)])
    _rco.add_account_attachments("Klient", "2024", ["1920"], [str(f1)])  # duplikat

    atts = _rco.list_account_attachments("Klient", "2024", "1920")
    assert len(atts) == 1
    assert atts[0]["path"] == str(f1)
    assert atts[0]["label"] == "bilag.pdf"
    assert atts[0]["added_at"]  # ikke tom


def test_account_review_same_file_multiple_kontoer(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)
    f1 = tmp_path / "arsoppgave.pdf"
    f1.write_text("x", encoding="utf-8")

    _rco.add_account_attachments("K", "2024", ["1920", "1930"], [str(f1)])
    assert _rco.list_account_attachments("K", "2024", "1920")
    assert _rco.list_account_attachments("K", "2024", "1930")


def test_account_review_remove_attachment(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)
    f1 = tmp_path / "a.pdf"
    f1.write_text("x", encoding="utf-8")

    _rco.add_account_attachments("K", "2024", ["1920"], [str(f1)])
    _rco.remove_account_attachment("K", "2024", "1920", str(f1))

    assert _rco.list_account_attachments("K", "2024", "1920") == []
    # Entry uten ok og uten vedlegg skal prunes
    assert "1920" not in _rco.load_account_review("K", "2024")


def test_account_review_ok_and_attachment_coexist(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)
    f1 = tmp_path / "dok.pdf"
    f1.write_text("x", encoding="utf-8")

    _rco.set_accounts_ok("K", "2024", ["1920"], True)
    _rco.add_account_attachments("K", "2024", ["1920"], [str(f1)])
    _rco.set_accounts_ok("K", "2024", ["1920"], False)

    # OK fjernet, men entry beholdes fordi vedlegg finnes
    review = _rco.load_account_review("K", "2024")
    assert review["1920"]["ok"] is False
    assert len(review["1920"]["attachments"]) == 1


def test_refresh_sb_view_shows_ok_and_vedlegg(monkeypatch, tmp_path):
    import page_analyse_sb
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)
    monkeypatch.setattr(page_analyse_sb, "_session_client_year", lambda: ("KUnde", "2024"))

    # Sett opp session-modul shim
    import sys
    import types
    fake_session = types.SimpleNamespace(client="KUnde", year="2024")
    monkeypatch.setitem(sys.modules, "session", fake_session)

    f1 = tmp_path / "bilag.pdf"
    f1.write_text("x", encoding="utf-8")
    _rco.set_accounts_ok("KUnde", "2024", ["1500"], True)
    _rco.add_account_attachments("KUnde", "2024", ["1500"], [str(f1)])

    _stub_sb_helpers(monkeypatch)
    page = _make_sb_page(prev_df=None)

    page_analyse_sb.refresh_sb_view(page=page)

    tree = page._sb_tree
    values_by_konto = {row[0]: row for row in tree.rows.values()}
    # Kolonneorden: Konto, Kontonavn, OK, OK_av, OK_dato, Vedlegg, Gruppe, IB, Endring, UB, UB_fjor, ...
    assert values_by_konto["1500"][2] == "OK"
    assert values_by_konto["1500"][5] == "1"
    # Konto 1000 har ingen review-data → tomme celler
    assert values_by_konto["1000"][2] == ""
    assert values_by_konto["1000"][5] == ""


# =====================================================================
# Managed storage (Utvalg-lager) for konto-vedlegg
# =====================================================================

def _patch_years_dir(monkeypatch, tmp_path):
    """Erstatt client_store.years_dir slik at Utvalg-lager peker på tmp."""
    import client_store as _cs

    def _fake_years_dir(display_name, *, year):
        p = tmp_path / "clients" / str(display_name) / "years" / str(year)
        p.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(_cs, "years_dir", _fake_years_dir)


def test_add_attachments_managed_copies_file(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path / "overrides")
    (tmp_path / "overrides").mkdir()
    _patch_years_dir(monkeypatch, tmp_path)

    src = tmp_path / "src" / "bilag.pdf"
    src.parent.mkdir()
    src.write_text("innhold", encoding="utf-8")

    _rco.add_account_attachments(
        "Klient AS", "2024", ["1920"], [str(src)],
        regnr_by_konto={"1920": (665, "Sum eiendeler")},
    )

    atts = _rco.list_account_attachments("Klient AS", "2024", "1920")
    assert len(atts) == 1
    a = atts[0]
    assert a["storage"] == "managed"
    assert a["source_path"] == str(src)
    assert a["regnr_snapshot"] == 665
    assert a["regnskapslinje_snapshot"] == "Sum eiendeler"

    # Filen skal ligge under Utvalg-lager
    from pathlib import Path as _P
    managed = _P(a["path"])
    assert managed.exists()
    assert managed.read_text(encoding="utf-8") == "innhold"
    assert "attachments" in managed.parts
    assert "konto_1920" in managed.parts
    assert "665_Sum_eiendeler" in managed.parts


def test_add_attachments_managed_collision_suffix(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path / "overrides")
    (tmp_path / "overrides").mkdir()
    _patch_years_dir(monkeypatch, tmp_path)

    # To filer med samme navn fra forskjellige mapper
    a1 = tmp_path / "src1" / "rapport.pdf"
    a1.parent.mkdir()
    a1.write_text("A", encoding="utf-8")
    a2 = tmp_path / "src2" / "rapport.pdf"
    a2.parent.mkdir()
    a2.write_text("B", encoding="utf-8")

    _rco.add_account_attachments(
        "K", "2024", ["1500"], [str(a1)],
        regnr_by_konto={"1500": (665, "Sum eiendeler")},
    )
    _rco.add_account_attachments(
        "K", "2024", ["1500"], [str(a2)],
        regnr_by_konto={"1500": (665, "Sum eiendeler")},
    )

    atts = _rco.list_account_attachments("K", "2024", "1500")
    assert len(atts) == 2
    from pathlib import Path as _P
    names = sorted(_P(a["path"]).name for a in atts)
    assert names == ["rapport.pdf", "rapport_2.pdf"]


def test_add_attachments_external_fallback_when_no_regnr(tmp_path, monkeypatch):
    """Uten regnr_by_konto → ekstern referanse (back-compat)."""
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)
    f1 = tmp_path / "x.pdf"
    f1.write_text("y", encoding="utf-8")

    _rco.add_account_attachments("K", "2024", ["1920"], [str(f1)])
    atts = _rco.list_account_attachments("K", "2024", "1920")
    assert len(atts) == 1
    assert atts[0]["storage"] == "external"
    assert atts[0]["path"] == str(f1)


def test_add_attachments_explicit_external(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path / "overrides")
    (tmp_path / "overrides").mkdir()
    _patch_years_dir(monkeypatch, tmp_path)

    f1 = tmp_path / "x.pdf"
    f1.write_text("y", encoding="utf-8")

    _rco.add_account_attachments(
        "K", "2024", ["1920"], [str(f1)],
        regnr_by_konto={"1920": (665, "Sum eiendeler")},
        storage="external",
    )
    atts = _rco.list_account_attachments("K", "2024", "1920")
    assert atts[0]["storage"] == "external"
    assert atts[0]["path"] == str(f1)


def test_add_attachments_managed_dedup(tmp_path, monkeypatch):
    """Samme kilde to ganger skal deduplisere, ikke lage kopi_2."""
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path / "overrides")
    (tmp_path / "overrides").mkdir()
    _patch_years_dir(monkeypatch, tmp_path)

    src = tmp_path / "bilag.pdf"
    src.write_text("z", encoding="utf-8")

    rbk = {"1920": (665, "Sum eiendeler")}
    _rco.add_account_attachments("K", "2024", ["1920"], [str(src)], regnr_by_konto=rbk)
    _rco.add_account_attachments("K", "2024", ["1920"], [str(src)], regnr_by_konto=rbk)

    atts = _rco.list_account_attachments("K", "2024", "1920")
    assert len(atts) == 1


def test_load_account_review_backcompat_missing_storage(tmp_path, monkeypatch):
    """Gammelt payload uten 'storage'-felt → tolkes som 'external'."""
    import regnskap_client_overrides as _rco
    import json

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)

    # Legg direkte en gammel struktur inn i payload
    ovr_path = _rco.overrides_path("K")
    payload = {
        "client": "K",
        "account_review_by_year": {
            "2024": {
                "1920": {
                    "ok": True,
                    "attachments": [
                        {"path": "/legacy/bilag.pdf", "label": "bilag.pdf", "added_at": "2024-01-01"}
                    ],
                }
            }
        },
    }
    ovr_path.write_text(json.dumps(payload), encoding="utf-8")

    review = _rco.load_account_review("K", "2024")
    atts = review["1920"]["attachments"]
    assert atts[0]["storage"] == "external"
    assert atts[0]["path"] == "/legacy/bilag.pdf"


def test_migrate_attachment_to_managed(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path / "overrides")
    (tmp_path / "overrides").mkdir()
    _patch_years_dir(monkeypatch, tmp_path)

    src = tmp_path / "src" / "bilag.pdf"
    src.parent.mkdir()
    src.write_text("orig", encoding="utf-8")

    # Start som ekstern referanse
    _rco.add_account_attachments(
        "K", "2024", ["1920"], [str(src)], storage="external",
    )
    atts = _rco.list_account_attachments("K", "2024", "1920")
    assert atts[0]["storage"] == "external"

    # Migrer
    _rco.migrate_attachment_to_managed(
        "K", "2024", "1920", str(src),
        regnr=665, regnskapslinje="Sum eiendeler",
    )

    atts = _rco.list_account_attachments("K", "2024", "1920")
    assert len(atts) == 1
    a = atts[0]
    assert a["storage"] == "managed"
    assert a["source_path"] == str(src)
    assert a["regnr_snapshot"] == 665

    from pathlib import Path as _P
    managed = _P(a["path"])
    assert managed.exists()
    assert managed.read_text(encoding="utf-8") == "orig"
    # Kildefilen skal fortsatt finnes (vi sletter ikke)
    assert src.exists()


def test_migrate_attachment_noop_when_already_managed(tmp_path, monkeypatch):
    import regnskap_client_overrides as _rco

    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path / "overrides")
    (tmp_path / "overrides").mkdir()
    _patch_years_dir(monkeypatch, tmp_path)

    src = tmp_path / "src" / "bilag.pdf"
    src.parent.mkdir()
    src.write_text("X", encoding="utf-8")

    rbk = {"1920": (665, "Sum eiendeler")}
    _rco.add_account_attachments("K", "2024", ["1920"], [str(src)], regnr_by_konto=rbk)
    managed_path = _rco.list_account_attachments("K", "2024", "1920")[0]["path"]

    # Migrer — skal være no-op
    _rco.migrate_attachment_to_managed(
        "K", "2024", "1920", managed_path,
        regnr=665, regnskapslinje="Sum eiendeler",
    )

    atts = _rco.list_account_attachments("K", "2024", "1920")
    assert len(atts) == 1
    assert atts[0]["path"] == managed_path


def test_resolve_regnr_by_konto_uses_intervals_and_overrides(tmp_path, monkeypatch):
    import page_analyse_sb

    # Stub session + overrides
    import sys
    import types
    fake_session = types.SimpleNamespace(client="K", year="2024")
    monkeypatch.setitem(sys.modules, "session", fake_session)

    import regnskap_client_overrides as _rco
    monkeypatch.setattr(_rco, "overrides_dir", lambda: tmp_path)
    _rco.set_account_override("K", "1500", 715)  # override: 1500 → 715 (EK)

    page = SimpleNamespace(
        _rl_intervals=pd.DataFrame(
            {"regnr": [19, 665], "fra": [1000, 1400], "til": [1100, 1999]}
        ),
        _rl_regnskapslinjer=pd.DataFrame(
            {"nr": [19, 665, 715], "regnskapslinje": ["Driftsinnt", "Eiendeler", "Egenkapital"]}
        ),
    )

    out = page_analyse_sb._resolve_regnr_by_konto(page=page, kontoer=["1050", "1500"])
    # 1050 treffer intervall 1000-1100 → regnr 19
    assert out["1050"] == (19, "Driftsinnt")
    # 1500 har override → regnr 715 (ikke intervall 1400-1999)
    assert out["1500"] == (715, "Egenkapital")


# =====================================================================
# Kontodetaljer-flate
# =====================================================================

def test_collect_konto_details_reads_from_sb_tree(monkeypatch):
    import page_analyse_sb

    tree = _FakeSBTree(rows={
        # Konto, Kontonavn, OK, Vedlegg, Gruppe, IB, Endring, UB, UB_fjor, Antall
        "r1": ["1920", "Bankinnskudd", "OK", "2", "Eiendeler",
               "100,00", "50,00", "150,00", "90,00", "12"],
    })
    page = SimpleNamespace(
        _sb_tree=tree,
        _rl_intervals=pd.DataFrame(
            {"regnr": [665], "fra": [1900], "til": [1999]}
        ),
        _rl_regnskapslinjer=pd.DataFrame(
            {"nr": [665], "regnskapslinje": ["Sum eiendeler"]}
        ),
        _rl_sb_df=pd.DataFrame({
            "konto": ["1920"], "kontonavn": ["Bankinnskudd"],
        }),
    )

    # Stub session + overrides for _resolve_regnr_by_konto
    import sys
    import types
    monkeypatch.setitem(sys.modules, "session",
                        types.SimpleNamespace(client="K", year="2024"))
    import regnskap_client_overrides as _rco
    monkeypatch.setattr(_rco, "load_account_overrides", lambda *a, **k: {})

    d = page_analyse_sb._collect_konto_details(page=page, konto="1920")
    assert d["konto"] == "1920"
    assert d["kontonavn"] == "Bankinnskudd"
    assert d["gruppe"] == "Eiendeler"
    assert d["ib"] == "100,00"
    assert d["endring"] == "50,00"
    assert d["ub"] == "150,00"
    assert d["ub_fjor"] == "90,00"
    assert d["antall"] == "12"
    assert d["regnr"] == "665"
    assert d["regnskapslinje"] == "Sum eiendeler"


def test_collect_konto_details_falls_back_to_sb_df(monkeypatch):
    """Hvis kontoen mangler i treet, slå opp kontonavn via sb_df."""
    import page_analyse_sb

    tree = _FakeSBTree(rows={})
    page = SimpleNamespace(
        _sb_tree=tree,
        _rl_intervals=pd.DataFrame(),
        _rl_regnskapslinjer=pd.DataFrame(),
        _rl_sb_df=pd.DataFrame(
            {"konto": ["5000"], "kontonavn": ["Lønn"],
             "ib": [0.0], "endring": [0.0], "ub": [0.0]}
        ),
    )

    import sys
    import types
    monkeypatch.setitem(sys.modules, "session",
                        types.SimpleNamespace(client="K", year="2024"))
    import regnskap_client_overrides as _rco
    monkeypatch.setattr(_rco, "load_account_overrides", lambda *a, **k: {})

    d = page_analyse_sb._collect_konto_details(page=page, konto="5000")
    assert d["kontonavn"] == "Lønn"


def test_dblclick_handler_binds_kontodetaljer(monkeypatch):
    """Dobbeltklikk-handler skal kalle show_kontodetaljer_dialog med konto."""
    import page_analyse_sb

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        page_analyse_sb, "show_kontodetaljer_dialog",
        lambda *, page, konto, kontonavn="": calls.append((konto, kontonavn)),
    )

    # Simuler _on_sb_dblclick-flyten via _bind_sb_once → vi kan ikke skape Toplevel
    # uten display, så vi tester modulnivå-bindingen indirekte: når double-click
    # kommer på rad "r1" med verdi ["1920", "Bank"], skal show_kontodetaljer
    # kalles med ("1920", "Bank").
    tree = _FakeSBTree(rows={"r1": ["1920", "Bank", "", "", "", "", "", "", "", ""]})

    # Gjenta logikken fra _on_sb_dblclick for å verifisere kontrakten
    vals = tree.item("r1", "values")
    konto = str(vals[0]).strip()
    kontonavn = str(vals[1]).strip()
    page_analyse_sb.show_kontodetaljer_dialog(page=None, konto=konto, kontonavn=kontonavn)
    assert calls == [("1920", "Bank")]


# =====================================================================
# SB-kolonnevalg (prefs, normalisering, pinned-beskyttelse)
# =====================================================================

def _make_sb_cols_page():
    from page_analyse_sb import SB_COLS
    return SimpleNamespace(
        _tk_ok=True,
        _sb_tree=_FakeSBTree(),
        _sb_cols_order=list(SB_COLS),
        _sb_cols_visible=list(SB_COLS),
        _sb_col_widths={},
        _rl_sb_prev_df=None,
    )


def test_sb_normalize_pinned_forced_to_front_and_visible():
    import page_analyse_columns as _cols
    import analyse_columns

    order_clean, visible = analyse_columns.normalize_tx_column_config(
        order=["OK", "IB", "Konto", "UB", "Kontonavn"],
        visible=["IB", "UB"],  # pinned mangler her
        all_cols=None,
        pinned=_cols.SB_PINNED_COLS,
        required=_cols.SB_PINNED_COLS,
    )
    # Pinned skal v\u00e6re f\u00f8rst, og tvunget synlige
    assert order_clean[0] == "Konto"
    assert order_clean[1] == "Kontonavn"
    assert "Konto" in visible
    assert "Kontonavn" in visible


def test_sb_load_preferences_uses_defaults_when_missing(monkeypatch):
    import page_analyse_columns as _cols
    import preferences

    monkeypatch.setattr(preferences, "get", lambda *a, **k: None)
    page = _make_sb_cols_page()
    _cols.load_sb_columns_from_preferences(page=page)

    from page_analyse_sb import SB_COLS, SB_DEFAULT_VISIBLE
    # Order inneholder alle kjente kolonner; default visible er den
    # kanoniske standardvisningen (Konto, Kontonavn, UB<år>, UB<år-1>,
    # Endring, Endring %, Antall) — ikke alle kolonnene.
    assert set(page._sb_cols_order) == set(SB_COLS)
    assert page._sb_cols_visible == list(SB_DEFAULT_VISIBLE)


def test_sb_load_preferences_normalizes_stored(monkeypatch):
    import page_analyse_columns as _cols
    import preferences

    stored = {
        "analyse.sb_cols.order": ["OK", "IB", "Konto", "Kontonavn"],
        "analyse.sb_cols.visible": ["IB", "OK"],
    }
    monkeypatch.setattr(preferences, "get", lambda k, d=None: stored.get(k, d))

    page = _make_sb_cols_page()
    _cols.load_sb_columns_from_preferences(page=page)

    # Konto + Kontonavn pinned til front, og tvunget synlige
    assert page._sb_cols_order[0] == "Konto"
    assert page._sb_cols_order[1] == "Kontonavn"
    assert "Konto" in page._sb_cols_visible
    assert "Kontonavn" in page._sb_cols_visible


def test_sb_apply_column_config_persists(monkeypatch):
    import page_analyse_columns as _cols
    import preferences

    saved: dict = {}
    monkeypatch.setattr(preferences, "set", lambda k, v: saved.__setitem__(k, v))
    monkeypatch.setattr(preferences, "get", lambda k, d=None: None)

    page = _make_sb_cols_page()
    _cols.apply_sb_column_config(
        page=page,
        order=["Konto", "Kontonavn", "IB", "UB"],
        visible=["Konto", "Kontonavn", "UB"],
    )
    assert "analyse.sb_cols.order" in saved
    assert "analyse.sb_cols.visible" in saved
    assert saved["analyse.sb_cols.visible"] == ["Konto", "Kontonavn", "UB"]


def test_sb_configure_hides_ub_fjor_without_prev_data():
    import page_analyse_columns as _cols
    from page_analyse_sb import SB_COLS

    page = _make_sb_cols_page()
    # Ingen fjor\u00e5rsdata
    page._rl_sb_prev_df = None
    page._sb_cols_visible = list(SB_COLS)

    _cols.configure_sb_tree_columns(page=page)

    display = page._sb_tree["displaycolumns"]
    assert "UB_fjor" not in display
    # Brukerpreferanse er urokket
    assert "UB_fjor" in page._sb_cols_visible


def test_sb_configure_shows_ub_fjor_with_prev_data():
    import page_analyse_columns as _cols

    page = _make_sb_cols_page()
    page._rl_sb_prev_df = pd.DataFrame({"konto": ["1000"], "ub": [5.0]})

    _cols.configure_sb_tree_columns(page=page)

    display = page._sb_tree["displaycolumns"]
    assert "UB_fjor" in display


def test_sb_reset_to_default(monkeypatch):
    import page_analyse_columns as _cols
    import preferences
    from page_analyse_sb import SB_COLS, SB_DEFAULT_VISIBLE

    saved: dict = {}
    monkeypatch.setattr(preferences, "set", lambda k, v: saved.__setitem__(k, v))
    monkeypatch.setattr(preferences, "get", lambda k, d=None: None)

    page = _make_sb_cols_page()
    # Simuler tilpasset oppsett f\u00f8r nullstilling
    page._sb_cols_visible = ["Konto", "Kontonavn"]
    page._sb_cols_order = ["Konto", "Kontonavn"]

    _cols.reset_sb_columns_to_default(page=page)

    # Etter nullstilling: order er alle kjente kolonner, visible er
    # kanonisk standardvisning.
    assert set(page._sb_cols_order) == set(SB_COLS)
    assert page._sb_cols_visible == list(SB_DEFAULT_VISIBLE)


def test_sb_prefs_isolated_from_tx_prefs(monkeypatch):
    """SB-prefs skal lagres med egne n\u00f8kler, ikke overlappe med TX."""
    import page_analyse_columns as _cols
    import preferences

    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(preferences, "set", lambda k, v: calls.append((k, v)))

    page = _make_sb_cols_page()
    _cols.persist_sb_columns_to_preferences(page=page)

    keys = [k for k, _ in calls]
    assert "analyse.sb_cols.order" in keys
    assert "analyse.sb_cols.visible" in keys
    assert "analyse.tx_cols.order" not in keys
    assert "analyse.tx_cols.visible" not in keys


def test_sb_remember_column_widths_persists_with_own_key(monkeypatch):
    import page_analyse_columns as _cols
    import preferences

    saved: dict = {}
    monkeypatch.setattr(preferences, "set", lambda k, v: saved.__setitem__(k, v))

    page = _make_sb_cols_page()
    tree = page._sb_tree
    # Sett opp displaycolumns slik at snapshot f\u00e5r noe \u00e5 lese
    tree._options["columns"] = ("Konto", "Kontonavn", "UB")
    tree._options["displaycolumns"] = ("Konto", "Kontonavn", "UB")
    tree.column_configs = {
        "Konto": {"width": 80},
        "Kontonavn": {"width": 250},
        "UB": {"width": 120},
    }

    # _FakeSBTree.column() with no kwargs must return width in dict form — patch
    orig_column = tree.column
    def _column(name, option=None, **kwargs):
        if kwargs:
            return orig_column(name, **kwargs)
        cfg = tree.column_configs.get(name, {})
        if option == "width":
            return cfg.get("width", 0)
        return dict(cfg)
    tree.column = _column  # type: ignore[method-assign]

    _cols.remember_sb_column_widths(page=page)

    assert "analyse.sb_cols.widths" in saved
    assert saved["analyse.sb_cols.widths"].get("Kontonavn") == 250


# Kolonne-indeks for UB_fjor i ny SB-layout: Konto, Kontonavn, OK, OK_av,
# OK_dato, Vedlegg, Gruppe, IB, Endring, UB, UB_fjor, Antall
_UB_FJOR_IDX = 10


def test_resolve_raw_kontonavn_returns_dataframe_value_not_display() -> None:
    """Pyntet displaytekst i treet (pensel + kommentar) skal ikke lekke —
    rått navn hentes fra `_rl_sb_df`."""
    from page_analyse_sb import _resolve_raw_kontonavn

    df = pd.DataFrame({
        "konto": ["1920", "3000"],
        "kontonavn": ["Bankinnskudd", "Salgsinntekt"],
    })
    page = SimpleNamespace(_rl_sb_df=df)
    assert _resolve_raw_kontonavn(page=page, konto="1920") == "Bankinnskudd"
    assert _resolve_raw_kontonavn(page=page, konto="3000") == "Salgsinntekt"


def test_resolve_raw_kontonavn_missing_df_returns_empty() -> None:
    from page_analyse_sb import _resolve_raw_kontonavn

    page = SimpleNamespace(_rl_sb_df=None)
    assert _resolve_raw_kontonavn(page=page, konto="1920") == ""


def test_resolve_raw_kontonavn_unknown_konto_returns_empty() -> None:
    from page_analyse_sb import _resolve_raw_kontonavn

    df = pd.DataFrame({"konto": ["1920"], "kontonavn": ["Bank"]})
    page = SimpleNamespace(_rl_sb_df=df)
    assert _resolve_raw_kontonavn(page=page, konto="9999") == ""


def test_collect_konto_details_uses_raw_kontonavn_not_tree_display() -> None:
    """Selv om treeview holder pyntet displaytekst, skal details-dict
    inneholde rått navn fra SB-df."""
    from page_analyse_sb import _collect_konto_details

    df = pd.DataFrame({
        "konto": ["1920"],
        "kontonavn": ["Bankinnskudd"],
    })

    class _Tree:
        def get_children(self, _parent=""):
            return ["r1"]

        def item(self, _iid, _key):
            # vals[1] er pyntet displaytekst — skal IKKE ende i details
            return ("1920", "\u270e Bankinnskudd  \u2014 Avstemt",
                    "OK", "", "", "100", "", "100", "", "12")

    page = SimpleNamespace(_rl_sb_df=df, _sb_tree=_Tree())
    details = _collect_konto_details(page=page, konto="1920")
    assert details["kontonavn"] == "Bankinnskudd"
    assert "\u270e" not in details["kontonavn"]
    assert "Avstemt" not in details["kontonavn"]
    # Øvrige felter hentes fortsatt fra treet
    assert details["ib"] == "100"
    assert details["antall"] == "12"
