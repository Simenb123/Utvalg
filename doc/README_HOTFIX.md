# Hotfix v1.38.3 – Analyse autoload fra session

**Problem:** Analyse får ikke data når `EventBus` ikke fyrer dataset‑event.  
**Løsning:** Analyse poller nå `session` periodisk og kaller `set_dataset(df)` når et bygd datasett oppdages.

## Fil i denne patchen
- `page_analyse.py` – oppdatert med `self.after(..., _autoload_from_session)` og metoden `_autoload_from_session()`.

## Bruk
1. Erstatt `page_analyse.py` i prosjektet med denne versjonen.
2. Start appen → Datasett → *Bygg datasett*.
3. Gå til **Analyse** – pivot og transaksjoner skal fylles (også uten bus).

Versjonen er kompatibel med tidligere patcher (1.38.1/1.38.2).