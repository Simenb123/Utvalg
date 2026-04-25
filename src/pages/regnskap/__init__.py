"""Regnskap-fanen.

Pilot 8 av frontend/backend-mappestrukturen. Kun frontend foreløpig —
``regnskap_*.py``-utility-filene på toppnivå (``regnskap_data``,
``regnskap_export``, ``regnskap_klient``, ``regnskap_noter``,
``regnskap_mapping``, ``regnskapslinje_mapping_service`` osv.) brukes
av flere faner og hører kanskje hjemme i ``src/shared/regnskap/``
i en senere runde.
"""

from .frontend.page import RegnskapPage

__all__ = ["RegnskapPage"]
