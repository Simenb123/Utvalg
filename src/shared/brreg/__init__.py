"""BRREG-integrasjon — cross-cutting utility (brukt av flere faner).

Pilot 23 av frontend/backend-mappestrukturen.

Moduler:
- ``client.py`` — BRREG-API-klient (Enhetsregisteret + Regnskapsregisteret)
  med lokal cache, async oppslag, registrertIMvaregisteret osv.
- ``fjor_fallback.py`` — fallback til BRREG-årsregnskap når SAF-T fjor
  mangler
- ``mapping_config.py`` — konfig for BRREG → vår RL-mapping
- ``rl_comparison.py`` — sammenligning vår RL-pivot vs BRREG-årsregnskap

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Verifiseres av
``tests/test_shared_brreg_no_tk.py``.
"""

from . import client, fjor_fallback, mapping_config, rl_comparison  # noqa: F401

__all__ = ["client", "fjor_fallback", "mapping_config", "rl_comparison"]
