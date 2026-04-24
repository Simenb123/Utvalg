# Utvalg-1 — prosjektstandarder

## UI-konvensjoner

Nye GUI-komponenter skal følge disse standardene. Se de lenkede
dokumentene for detaljer og eksempelkode.

### Popups / dialoger

Alle nye modale popups skal opprettes via
[ui_dialog.make_dialog()](ui_dialog.py) — ikke rå `tk.Toplevel`.

Se [docs/POPUP_STANDARD.md](docs/POPUP_STANDARD.md) for bruksmønster
og migrering av eksisterende dialoger.

### Treeview-tabeller

Nye (og migrerende) `ttk.Treeview`-tabeller bygges via
[ui_managed_treeview.ManagedTreeview](ui_managed_treeview.py). Den
gir drag-n-drop-omorganisering, kolonne­velger på høyreklikk,
klikk-sortering og preferanse-persistens som én pakke.

Se [docs/TREEVIEW_PLAYBOOK.md](docs/TREEVIEW_PLAYBOOK.md).
