# debug_log.py
from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import traceback
from functools import wraps

_LOGGER: logging.Logger | None = None

def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER:
        return _LOGGER

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / "utvalg.log"

    logger = logging.getLogger("utvalg")
    logger.setLevel(logging.DEBUG)

    fh = RotatingFileHandler(logfile, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logger.addHandler(fh)
    logger.addHandler(sh)

    _LOGGER = logger
    return logger

log = get_logger()

def log_exceptions(func):
    """Dekoratør som logger uventede unntak i UI‑handlers."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SystemExit:
            raise
        except Exception as e:
            log.exception("Uventet feil i %s: %s", func.__name__, e)
            # I UI kan du evt. vise messagebox her (unngå sirkelavhengighet)
            return None
    return wrapper

def install_excepthook():
    def _hook(exc_type, exc, tb):
        log.error("Ufanget unntak: %s", exc_type.__name__)
        log.error("Detaljer: %s", exc)
        for line in traceback.format_tb(tb):
            log.error(line.rstrip())
    sys.excepthook = _hook
