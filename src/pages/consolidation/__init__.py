"""Konsolidering-fanen.

Pilot 11 av frontend/backend-mappestrukturen. Claude's arbeidsområde
for bølge 2 (jf. memory: "Consolidation spec — Bølge 2 MVP slice 1
starting").

Struktur (bygges opp i 3 sub-piloter):
- ``backend/`` — beregningskjerne (motor, mapping, eliminering, eksport),
  ren Python uten Tk. Tidligere ``consolidation/``-mappa på toppnivå.
- ``frontend/`` — Tk-widgets (ConsolidationPage + 26 hjelpemoduler).
  Flyttes i 11B/11C.

Toppnivå-pakka ``consolidation`` er sys.modules-aliassert til
``backend/`` for bakoverkompat med 36 eksterne importerere.
"""
