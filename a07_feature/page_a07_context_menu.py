from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .page_a07_context_menu_base import A07PageContextMenuBaseMixin
from .page_a07_context_menu_codes import A07PageCodeAndGroupContextMenuMixin
from .page_a07_context_menu_control import A07PageControlContextMenuMixin


class A07PageContextMenuMixin(
    A07PageContextMenuBaseMixin,
    A07PageControlContextMenuMixin,
    A07PageCodeAndGroupContextMenuMixin,
):
    pass
