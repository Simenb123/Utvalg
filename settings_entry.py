# settings_entry.py
from __future__ import annotations

from typing import Callable, Optional

import tkinter as tk


def open_settings(
    root: tk.Tk | tk.Toplevel,
    *,
    on_data_dir_changed: Optional[Callable[[], None]] = None,
    on_clients_changed: Optional[Callable[[], None]] = None,
) -> None:
    """Åpner innstillingsvindu.

    Brukes både fra hovedappen (som Toplevel) og som eget entrypoint.
    """

    from views_settings import open_settings as _open

    _open(root, on_data_dir_changed=on_data_dir_changed, on_clients_changed=on_clients_changed)


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    open_settings(root)
    root.mainloop()


if __name__ == "__main__":
    main()
