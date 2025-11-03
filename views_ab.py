# ... toppen av filen uendret ...
from preferences import load_preferences, set_last_export_dir  # NYTT

# ... inni _run_export(...)
def _run_export(parent: tk.Tk, left: DatasetPane, right: DatasetPane, cfg: ABAnalysisConfig):
    # Sørg for at A og B er bygget
    dfA, cA = left.build_dataset()
    dfB, cB = right.build_dataset()
    if dfA is None or dfA.empty or dfB is None or dfB.empty:
        messagebox.showwarning("Datasett", "Bygg begge datasett før eksport."); return

    pref = load_preferences()  # NYTT
    path = filedialog.asksaveasfilename(
        title="Lagre A‑B analyser (Excel)",
        defaultextension=".xlsx",
        filetypes=[("Excel", "*.xlsx")],
        initialdir=(pref.last_export_dir or ""),  # NYTT
        parent=parent
    )
    if not path: return

    sheets: Dict[str, pd.DataFrame] = {}
    summary = []
    # ... (resten av funksjonen er identisk) ...

    try:
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            oppsum.to_excel(xw, AB._sheet("Oppsummering (A-B)"), index=False)
            dfA.to_excel(xw, AB._sheet("Datasett A (grunnlag)"), index=False)
            dfB.to_excel(xw, AB._sheet("Datasett B (grunnlag)"), index=False)
            for nm, frame in sheets.items():
                (frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)).to_excel(xw, AB._sheet(nm), index=False)
        try:
            set_last_export_dir(Path(path).parent.as_posix())  # NYTT
        except Exception:
            pass
        messagebox.showinfo("Lagret", f"Eksportert til\n{path}")
    except Exception as e:
        messagebox.showerror("Eksportfeil", str(e))
