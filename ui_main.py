from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from dataset_pane import DatasetPane
from page_analyse import AnalysePage
from page_utvalg import UtvalgPage
from page_logg import LoggPage
import bus
import theme
import session
import analysis_pkg

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Utvalg – Hovedbok → Analyse og utvalg")
        self.geometry("1240x860")
        self.minsize(1120, 760)
        try:
            theme.apply_theme(self)
        except Exception:
            pass

        # Meny
        self._build_menu()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Datasett
        frm_data = ttk.Frame(self.nb); self.nb.add(frm_data, text="Datasett")
        self.dataset_panel = DatasetPane(frm_data, title="Bygg datasett")
        self.dataset_panel.frm.pack(fill=tk.BOTH, expand=True)

        # Analyse
        self.page_analyse = AnalysePage(self.nb); self.nb.add(self.page_analyse, text="Analyse")

        # Utvalg
        self.page_utvalg = UtvalgPage(self.nb); self.nb.add(self.page_utvalg, text="Utvalg")
        bus.set_utvalg_page(self.page_utvalg)

        # Logg
        self.page_logg = LoggPage(self.nb); self.nb.add(self.page_logg, text="Logg")

        # Auto-flyt
        self.bind("<<DatasetReady>>", self._on_dataset_ready)

    def _build_menu(self):
        menubar = tk.Menu(self)
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Avslutt", command=self.destroy)
        menubar.add_cascade(label="Fil", menu=m_file)

        m_an = tk.Menu(menubar, tearoff=0)
        m_an.add_command(label="Generer analyser (Excel)…", command=self._run_analyses)
        menubar.add_cascade(label="Analyser", menu=m_an)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="README", command=self._show_readme_hint)
        menubar.add_cascade(label="Hjelp", menu=m_help)

        self.config(menu=menubar)

    def _show_readme_hint(self):
        messagebox.showinfo("README", "README.md beskriver struktur, flyt og feilsøking i prosjektmappen.")

    def _run_analyses(self):
        df, cols = session.get_dataset()
        if df is None or cols is None:
            messagebox.showinfo("Analyser", "Bygg datasett først i fanen «Datasett».")
            return
        date_from, date_to = None, None
        try:
            date_from, date_to = self.page_analyse.get_current_period()
        except Exception:
            pass
        try:
            path = analysis_pkg.generate_analysis_workbook(df, cols, period_from=date_from, period_to=date_to)
            messagebox.showinfo("Analyser", f"Excel generert:\n{path}")
        except Exception as ex:
            messagebox.showerror("Analyser", f"Feil under analysegenerering:\n{ex}")

    def _on_dataset_ready(self, _e=None):
        try:
            self.page_analyse.refresh_from_session()
            self.page_logg.refresh()
            self.nb.select(self.page_analyse)
        except Exception as ex:
            messagebox.showwarning("Analyse", f"Klarte ikke å oppdatere analyse: {ex}")

if __name__ == "__main__":
    MainApp().mainloop()
