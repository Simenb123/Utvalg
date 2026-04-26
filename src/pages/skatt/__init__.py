"""Skatt-fanen.

Pilot 14 av frontend/backend-mappestrukturen. Skatteanalyse — beregner
nominell skatt, bokført skattekostnad, effektiv skattesats og avvik
basert på data fra Analyse-fanen.

Kun én fil — ingen backend-skille nødvendig (siden er en ren visnings-
side som leser fra ``self._analyse_page`` og preferences).
"""

from .page import SkattPage

__all__ = ["SkattPage"]
