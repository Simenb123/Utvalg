from __future__ import annotations


def run() -> None:
    """
    Robust oppstart som finner App-klassen i ui_main uavhengig av navn.
    Støttede varianter:
      - Klasse: _App / App / MainApp / Application
      - Fabrikk-funksjon: create_app() / build_app() / make_app()

    I tillegg installeres globale hotkeys (Ctrl+A/Ctrl+C) for Treeview/Listbox
    slik at "copy to clipboard" fungerer på tvers av alle visningsbilder.
    """
    import importlib

    # Importer UI-modulen
    ui = importlib.import_module("ui_main")

    inst = None

    # 1) Forsøk kjente klassenavn
    for name in ("_App", "App", "MainApp", "Application"):
        obj = getattr(ui, name, None)
        if isinstance(obj, type):
            inst = obj()
            break

    # 2) Forsøk fabrikk-funksjoner som returnerer et objekt med mainloop()
    if inst is None:
        for name in ("create_app", "build_app", "make_app"):
            fn = getattr(ui, name, None)
            if callable(fn):
                candidate = fn()
                if hasattr(candidate, "mainloop"):
                    inst = candidate
                    break

    # Kommer vi hit, fant vi verken klasse eller fabrikkfunksjon
    if inst is None or not hasattr(inst, "mainloop"):
        raise ImportError(
            "Fant ingen App-klasse i ui_main (forventet _App/App/MainApp/Application), "
            "og ingen create_app()/build_app()/make_app() som returnerer en Tk-app."
        )

    # Installer globale hotkeys (best-effort)
    try:
        import ui_hotkeys

        ui_hotkeys.install_global_hotkeys(inst)
    except Exception:
        # Skal aldri stoppe app-start om hotkeys feiler
        pass

    inst.mainloop()


if __name__ == "__main__":
    run()
