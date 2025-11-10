from __future__ import annotations
# Enkel "bus" hvis vi trenger deling senere
_utvalg_page = None
def set_utvalg_page(page):
    global _utvalg_page; _utvalg_page = page
def get_utvalg_page():
    return _utvalg_page