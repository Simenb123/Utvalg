from __future__ import annotations

__all__ = ["A07Page"]


def __getattr__(name: str):
    if name == "A07Page":
        from .page import A07Page

        return A07Page
    raise AttributeError(name)
