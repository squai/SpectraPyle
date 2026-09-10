"""Unified logging configuration for CLI and the ipywidgets GUI.

File logs keep full timestamps/module names.  GUI logs intentionally show only
WARNING+ records in a compact form; normal run progress is carried by a
separate structured callback rather than by parsing INFO messages.
"""

import html
import logging
from pathlib import Path


_LEVEL_STYLE = {
    logging.DEBUG: ("·", "color:#777;"),
    logging.INFO: ("●", "color:#1a7a1a;"),
    logging.WARNING: ("⚠", "color:#b36b00;"),
    logging.ERROR: ("✖", "color:#c62828;"),
    logging.CRITICAL: ("✖", "color:#c62828; font-weight:600;"),
}


class WidgetHandler(logging.Handler):
    """Render log records into an ``ipywidgets.Output`` widget."""

    def __init__(self, output_widget, record_callback=None, max_records=200):
        super().__init__()
        self.out = output_widget
        self.record_callback = record_callback
        self.max_records = max_records

    def emit(self, record):
        from IPython.display import HTML, display

        try:
            msg = html.escape(self.format(record))
            symbol, style = _LEVEL_STYLE.get(record.levelno, ("·", ""))
            rendered = (
                '<pre style="margin:3px 0;padding:0;white-space:pre-wrap;'
                f'font-family:monospace;{style}">{symbol} {msg}</pre>'
            )
            with self.out:
                display(HTML(rendered))
            if self.max_records and len(self.out.outputs) > self.max_records:
                self.out.outputs = self.out.outputs[-self.max_records:]
            if self.record_callback is not None:
                self.record_callback(record)
        except Exception:
            self.handleError(record)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger under the ``spectraPyle`` hierarchy."""
    return logging.getLogger(name)


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    gui_output=None,
    gui_level: str = "WARNING",
    gui_record_callback=None,
) -> None:
    """Initialize the ``spectraPyle`` logger hierarchy.

    Parameters
    ----------
    level : str, optional
        Console level when no GUI output is supplied.
    log_file : Path or None, optional
        Full log file.  It always receives DEBUG+ records.
    gui_output : ipywidgets.Output or None, optional
        Widget receiving compact GUI warnings/errors.
    gui_level : str, optional
        Minimum level shown in the GUI (default: WARNING).
    gui_record_callback : callable or None, optional
        Called with each record emitted to the GUI, useful for counters.
    """
    root = logging.getLogger("spectraPyle")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    for handler in root.handlers[:]:
        try:
            handler.close()
        finally:
            root.removeHandler(handler)

    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    if log_file:
        fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(file_fmt)
        root.addHandler(fh)

    if gui_output is not None:
        wh = WidgetHandler(gui_output, record_callback=gui_record_callback)
        wh.setLevel(getattr(logging, gui_level.upper()))
        wh.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(wh)
    else:
        sh = logging.StreamHandler()
        sh.setLevel(getattr(logging, level.upper()))
        sh.setFormatter(file_fmt)
        root.addHandler(sh)
