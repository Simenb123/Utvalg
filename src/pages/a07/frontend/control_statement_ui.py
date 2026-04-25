from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from a07_feature.control.statement_view_state import A07PageControlStatementViewStateMixin

from .control_statement_panel_ui import A07PageControlStatementPanelMixin
from .control_statement_window_ui import A07PageControlStatementWindowMixin


class A07PageControlStatementMixin(
    A07PageControlStatementViewStateMixin,
    A07PageControlStatementWindowMixin,
    A07PageControlStatementPanelMixin,
):
    pass
