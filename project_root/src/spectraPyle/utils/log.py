import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ipywidgets as widgets


_LEVEL_STYLE = {
    logging.DEBUG:    ("·", "color:#aaaaaa; font-size:0.85em;"),
    logging.INFO:     ("●", "color:#1a7a1a;"),
    logging.WARNING:  ("⚠", "color:#e07800;"),
    logging.ERROR:    ("✖", "color:#cc0000;"),
    logging.CRITICAL: ("✖", "color:#cc0000; font-size:1.1em;"),
}


class WidgetHandler(logging.Handler):
    def __init__(self, output_widget):
        super().__init__()
        self.out = output_widget

    def emit(self, record):
        from IPython.display import display, HTML
        msg = self.format(record).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        symbol, style = _LEVEL_STYLE.get(record.levelno, ("·", ""))
        html = f'<pre style="margin:2px 0; padding:0; font-family:monospace; {style}">{symbol} {msg}</pre>'
        with self.out:
            display(HTML(html))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    gui_output=None,
) -> None:
    root = logging.getLogger("spectraPyle")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)

    if gui_output is not None:
        wh = WidgetHandler(gui_output)
        wh.setLevel(getattr(logging, level.upper()))
        wh.setFormatter(fmt)
        root.addHandler(wh)
    else:
        sh = logging.StreamHandler()
        sh.setLevel(getattr(logging, level.upper()))
        sh.setFormatter(fmt)
        root.addHandler(sh)
