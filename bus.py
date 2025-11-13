from __future__ import annotations
# Enkel "bus" hvis vi trenger deling senere
_utvalg_page = None
_listeners = {}

def set_utvalg_page(page):
    """
    Set a reference to the current UtvalgPage. This allows other modules to
    retrieve the page and trigger updates directly. If called multiple times,
    the last page registered will be used.
    """
    global _utvalg_page
    _utvalg_page = page

def get_utvalg_page():
    """
    Return the current UtvalgPage instance if one has been registered via
    ``set_utvalg_page()``. Returns None if no page has been registered.
    """
    return _utvalg_page

def on(event_name: str, callback):
    """
    Register a callback for a named event. When :func:`emit` is called with the same
    event name, all registered callbacks will be invoked with the payload.

    Args:
        event_name: Name of the event to listen for.
        callback: Callable that accepts a single argument (payload).
    """
    global _listeners
    _listeners.setdefault(event_name, []).append(callback)

def emit(event_name: str, payload=None):
    """
    Emit a named event, invoking all registered callbacks. Also triggers an
    update of the UtvalgPage if the event relates to changes in the selected
    accounts. This supports older code paths where UtvalgPage is not updated
    via bus events.

    Args:
        event_name: Name of the event to emit.
        payload: Optional payload passed to callbacks.
    """
    # Invoke callbacks
    for cb in _listeners.get(event_name, []):
        try:
            cb(payload)
        except Exception:
            pass
    # If the event signals that accounts have changed, update the registered
    # UtvalgPage directly (if any). This ensures the view stays in sync even
    # if no listener has been registered.
    if event_name == "SELECTION_SET_ACCOUNTS":
        up = get_utvalg_page()
        if up is not None:
            try:
                # call apply_filters asynchronously via after if available
                if hasattr(up, "after"):
                    up.after(0, up.apply_filters)
                else:
                    up.apply_filters()
            except Exception:
                pass