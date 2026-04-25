"""Revisjonshandlinger — cross-cutting analyse-feature-pakker.

Mens ``src/pages/`` inneholder fane-sider (visning), inneholder
``src/audit_actions/`` revisjonshandlinger (logikk + UI som kalles fra
flere faner).

Pakker her:
- ``motpost/`` — motpost-analyse (kalles fra Statistikk og Analyse)

Dette er distinkt fra:
- ``page_revisjonshandlinger.py`` — selve revisjonshandlinger-fanen
- ``page_*_actions.py`` — knappklikk-handlinger på en fane-side
"""
