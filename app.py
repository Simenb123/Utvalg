from __future__ import annotations


def run() -> None:
    """
    Robust oppstart som finner App-klassen i ui_main uavhengig av navn.
    Støttede varianter:
      - Klasse: _App / App / MainApp / Application
      - Fabrikk-funksjon: create_app() / build_app() / make_app()
    """
    import importlib

    ui = importlib.import_module("ui_main")

    # 1) Forsøk kjente klassenavn
    for name in ("_App", "App", "MainApp", "Application"):
        obj = getattr(ui, name, None)
        if isinstance(obj, type):
            obj().mainloop()
            return

    # 2) Forsøk fabrikk-funksjoner som returnerer et objekt med mainloop()
    for name in ("create_app", "build_app", "make_app"):
        fn = getattr(ui, name, None)
        if callable(fn):
            inst = fn()
            if hasattr(inst, "mainloop"):
                inst.mainloop()
                return

    raise ImportError(
        "Fant ingen App-klasse i ui_main (forventet _App/App/MainApp/Application), "
        "og ingen create_app()/build_app()/make_app() som returnerer en Tk-app."
    )


if __name__ == "__main__":
    run()
