"""Eksport-orkestrering for revisor-arbeidspapirer.

Pilot 30 av frontend/backend-mappestrukturen. Disse modulene er eksport-
laget rundt Excel-builderne i ``src/shared/workpapers/`` (klientinfo) og
rotnivå (``hb_version_diff_excel``, ``ib_ub_control_excel``).

Hver eksport-funksjon:
- Henter klient/år/data fra ``session``
- Viser eventuelle valg-dialoger (Tk)
- Kaller den underliggende builderen
- Viser ``filedialog.asksaveasfilename`` og lagrer

Modulene har Tk-imports og hører IKKE hjemme i ``src/shared/workpapers/``
(som er Tk-fri pr. pilot 25). De ligger her i ``src/audit_actions/``
sammen med motpost- og statistikk-handlingene.

Moduler:
- ``hb_diff.py``    — HB versjonsdiff
- ``ib_ub.py``      — SB/HB-avstemming + IB/UB-kontinuitet
- ``klientinfo.py`` — Klientinfo, roller og eierskap
- ``motpost.py``    — Motpost-flytdiagram (HTML/PDF)
- ``rl.py``         — Regnskapsoppstilling og nøkkeltallsrapport
"""
