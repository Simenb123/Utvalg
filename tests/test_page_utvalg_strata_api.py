from __future__ import annotations

import ast
from pathlib import Path


def _load_ast(path: Path) -> ast.AST:
    src = path.read_text(encoding="utf-8")
    return ast.parse(src, filename=str(path))


def _find_class(tree: ast.AST, name: str) -> ast.ClassDef:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"Fant ikke class {name!r} i AST")


def _find_method(cls: ast.ClassDef, name: str) -> ast.FunctionDef:
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Fant ikke metode {name!r} i class {cls.name!r}")


def test_utvalg_strata_page_constructor_uses_on_commit_selection_keyword() -> None:
    """Regresjonstest for runtime-feilen i appen.

    Vi hadde en krasj ved oppstart:
        TypeError: SelectionStudio.__init__() got an unexpected keyword argument 'on_commit'

    Årsak: etter refaktor ble callback-parametret i SelectionStudio hetende
    `on_commit_selection`, men page_utvalg_strata brukte fortsatt `on_commit`.

    Denne testen verifiserer at UtvalgStrataPage nå oppretter SelectionStudio med
    riktig keyword og uten ekstra posisjonelle argumenter.
    """

    root = Path(__file__).resolve().parents[1]
    path = root / "page_utvalg_strata.py"
    assert path.exists(), f"Mangler fil: {path}"

    tree = _load_ast(path)
    cls = _find_class(tree, "UtvalgStrataPage")
    init = _find_method(cls, "__init__")

    calls = [
        n
        for n in ast.walk(init)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "SelectionStudio"
    ]
    assert calls, "Fant ingen kall til SelectionStudio(...) i UtvalgStrataPage.__init__"

    call = calls[0]
    kw_names = {kw.arg for kw in call.keywords if kw.arg is not None}

    assert "on_commit_selection" in kw_names, "SelectionStudio må få callback via on_commit_selection=..."
    assert "on_commit" not in kw_names, "Legacy keyword on_commit=... må ikke brukes her"

    # Etter refaktor er data lastet via load_data() i _refresh(); derfor kun master som pos-arg.
    assert len(call.args) == 1, "SelectionStudio skal kun få master som posisjonelt argument"


def test_utvalg_strata_page_refresh_calls_load_data_without_df_all_keyword() -> None:
    """Regresjonstest: `load_data`-signaturen ble endret.

    SelectionStudio.load_data har per nå signaturen:
        load_data(df_all, df_base=None)

    Tidligere kode prøvde å kalle `load_data(..., df_all=...)` som gir TypeError.
    """

    root = Path(__file__).resolve().parents[1]
    path = root / "page_utvalg_strata.py"
    tree = _load_ast(path)
    cls = _find_class(tree, "UtvalgStrataPage")
    refresh = _find_method(cls, "_refresh")

    load_calls: list[ast.Call] = []
    for n in ast.walk(refresh):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "load_data":
            load_calls.append(n)

    assert load_calls, "Forventer minst ett kall til self.studio.load_data(...) i _refresh()"

    # Ingen av kallene skal bruke keyword-argumentet 'df_all' (det finnes ikke i signaturen nå).
    for c in load_calls:
        for kw in c.keywords:
            assert kw.arg != "df_all", "Skal ikke sende df_all=... som keyword til load_data()"

    # Vi forventer at minst ett av kallene sender hele datasettet først (posisjonelt).
    # (Implementasjonen kan bruke `df_all` direkte eller en fallback-variabel.)
    assert any(
        len(c.args) >= 1
        and isinstance(c.args[0], ast.Name)
        and c.args[0].id in {"df_all", "df_all_for_studio"}
        for c in load_calls
    ), "Forventer et kall som bruker df_all/df_all_for_studio som første argument til load_data()"
