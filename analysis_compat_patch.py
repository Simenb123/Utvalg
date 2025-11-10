"""
analysis_compat_patch.py
--------------------------------
Sikrer bakoverkompatibilitet for AnalysePage ved å injecte en
`refresh_from_session()`-metode dersom den mangler.
Kan trygt importeres flere ganger (idempotent).
"""
from __future__ import annotations
import pandas as pd

def _pull_df_from_session():
    try:
        import session as SM
    except Exception:
        return None, ""
    for name in ("dataset","df","dataframe","dataset_df","built_df","current_df"):
        try:
            v = getattr(SM, name, None)
            if isinstance(v, pd.DataFrame) and len(v)>0:
                return v.copy(), f"session.{name}"
        except Exception:
            pass
    return None, ""

def _inject_refresh():
    try:
        import page_analyse as PA
        AP = getattr(PA, "AnalysePage", None)
        if AP is None:
            return False
        if hasattr(AP, "refresh_from_session"):
            return True  # allerede ok
        def refresh_from_session(self):
            df, src = _pull_df_from_session()
            if df is not None:
                try:
                    # standard felt i AnalysePage
                    setattr(self, "_df", df)
                except Exception:
                    pass
            # forsøk å trigge redraw med de metodene som finnes
            for m in ("apply_filters", "_rebuild_view", "refresh"):
                fn = getattr(self, m, None)
                if callable(fn):
                    try:
                        fn()
                        return
                    except Exception:
                        continue
        setattr(AP, "refresh_from_session", refresh_from_session)
        return True
    except Exception:
        return False

# Kjør patch ved import
_inject_refresh()