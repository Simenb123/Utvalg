"""page_analyse_sb.py

Saldobalansevisning for Analyse-fanen.

Egen Treeview (_sb_tree) med egne kolonner, vist som alternativ til
transaksjonslisten (_tx_tree). Toggling skjer via show_sb_tree / show_tx_tree.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import formatting


from analyse_sb_tree import (  # noqa: E402,F401
    SB_COLS,
    SB_DEFAULT_VISIBLE,
    _SB_CENTER_COLS,
    _SB_COL_HEADINGS,
    _SB_COL_WIDTHS,
    _SB_NUMERIC_COLS,
    _hide_all_views,
    create_sb_tree,
    show_nk_view,
    show_sb_tree,
    show_tx_tree,
)
from analyse_sb_refresh import (  # noqa: E402,F401
    _capture_sb_selection,
    _clear_tree,
    _get_selected_regnr,
    _get_selected_rl_name,
    _resolve_sb_columns,
    _resolve_target_kontoer,
    _restore_sb_selection,
    refresh_sb_view,
)



from analyse_sb_remap import (  # noqa: E402,F401
    _DRAG_THRESHOLD_PX,
    _bind_sb_drag_drop,
    _bind_sb_header_rightclick,
    _bind_sb_once,
    _bind_sb_rightclick,
    _check_rl_has_active_kontoer,
    _execute_drag_remap,
    _remap_multiple_sb_accounts,
    _show_sb_header_menu,
    remap_sb_account,
    show_sb_account_transactions,
)




from analyse_sb_konto_review import (  # noqa: E402,F401
    _action_link_menu_label,
    _add_attachments_to_kontoer,
    _edit_comment,
    _open_action_link_dialog,
    _open_path,
    _refresh_sb_after_review_change,
    _resolve_regnr_by_konto,
    _session_client_year,
    _set_accounts_ok,
    _show_attachments_dialog,
)



from analyse_sb_konto_details import (  # noqa: E402,F401
    _collect_konto_details,
    _fmt_nok,
    _parse_norwegian_number,
    _resolve_raw_kontonavn,
    show_kontodetaljer_dialog,
)



from analyse_sb_motpost import (  # noqa: E402,F401
    MP_COLS,
    _MP_COL_WIDTHS,
    create_mp_account_tree,
    create_mp_tree,
    refresh_mp_account_view,
    refresh_mp_view,
    show_mp_account_tree,
    show_mp_tree,
)
