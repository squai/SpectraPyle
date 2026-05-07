"""
SpectraPyle GUI — pure ipywidgets, no local server needed.

Usage (in a notebook cell):
    from gui import start
    start()
"""

import json
import os
import contextlib
import importlib
import sys
import threading
import time
import traceback
from pathlib import Path

import ipywidgets as w
from IPython.display import display, clear_output
from ipyfilechooser import FileChooser
from pydantic import TypeAdapter, BaseModel  # noqa: F401

import spectraPyle as stsp
import spectraPyle.stacking.stacking as stack
from spectraPyle.runtime.runtime_adapter import (
    build_config_from_widgets,
    export_config_to_json,
    export_config_to_yaml,
)
from spectraPyle.schema.schema import StackingConfig, StackingConfigResolver

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

PACKAGE_ROOT = Path(stsp.__file__).parent.parent.parent

MODE_INDIVIDUAL = "individual fits"
MODE_METADATA = "metadata path"
MODE_COMBINED = "combined fits"

style = {"description_width": "initial"}

INSTRUMENT_EXTRA_QC = {
    "euclid": {"bad_pixels": True, "dithers": True},
    "desi": {"bad_pixels": False, "dithers": False},
}


# ---------------------------------------------------------------------------
# Module-level helpers (no widget state)
# ---------------------------------------------------------------------------

def section(title):
    return w.HTML(f"<h3 style='color:#2c3e50'>{title}</h3>")


def advanced_box(content, title="⚙️ Advanced"):
    acc = w.Accordion(children=[w.VBox(content)])
    acc.set_title(0, title)
    acc.selected_index = None
    return acc


class Tee:
    """Write to a log file and optionally mirror to stdout."""
    def __init__(self, file, debug=False):
        self.file = file
        self.debug = debug
        self.original_stdout = sys.__stdout__

    def write(self, msg):
        self.file.write(msg)
        if self.debug:
            self.original_stdout.write(msg)

    def flush(self):
        self.file.flush()
        if self.debug:
            self.original_stdout.flush()


# ---------------------------------------------------------------------------
# Mutable state shared across callbacks
# ---------------------------------------------------------------------------

class _State:
    validated_cfg = None
    current_path = None
    last_dir = None
    lambda_norm_rest_value = None
    interval_norm_statistics_value = None
    conservation_value = None
    pixel_size_mode_value = None
    pixel_size_value = None
    n_nyq_value = None


# ---------------------------------------------------------------------------
# start() — build and display the full widget UI
# ---------------------------------------------------------------------------

def start():
    # -----------------------------------------------------------------------
    # Initialise mutable path state
    # -----------------------------------------------------------------------
    _State.current_path = PACKAGE_ROOT

    # -----------------------------------------------------------------------
    # Load instrument rules
    # -----------------------------------------------------------------------
    module_dir = os.path.dirname(stsp.__file__)
    rules_path = os.path.join(module_dir, "instruments", "instruments_rules.json")
    with open(rules_path) as f:
        RULES = json.load(f)

    # -----------------------------------------------------------------------
    # Instrument dropdowns + grism state
    # -----------------------------------------------------------------------

    def get_current_path():
        return str(Path(_State.current_path).resolve())

    def get_last_dir():
        return _State.last_dir if _State.last_dir else get_current_path()

    instrument_w = w.Dropdown(
        options=["euclid", "desi", "generic"],
        value="euclid",
        description="Instrument",
        style=style,
    )
    survey_w = w.Dropdown(description="Survey", style=style)
    datarelease_w = w.Dropdown(description="Data release", style=style)

    grism_checkboxes = {}
    grism_dir_widgets = {}
    grism_file_widgets = {}
    grism_dir_rows = {}
    grism_file_rows = {}

    grism_checkboxes_box = w.VBox()
    grism_dirs_box = w.VBox()
    grism_files_box = w.VBox(layout=w.Layout(display="none"))

    def _build_dir_row(g):
        text_w = w.Text(
            description=f"{g.capitalize()} dir",
            value=get_current_path(),
            style=style,
            layout=w.Layout(width="80%", display="none"),
        )
        fc = FileChooser(
            path=get_last_dir(),
            title=f"Select {g.upper()} spectra directory",
            select_default=False,
        )
        fc.show_only_dirs = True

        def _on_selected(chooser, _t=text_w):
            if chooser.selected:
                _t.value = str(Path(chooser.selected).resolve())
                _State.last_dir = _t.value
                for _w2 in grism_dir_widgets.values():
                    if _w2["fc"] is not chooser and _w2["fc"].selected is None:
                        _w2["fc"].reset(path=_State.last_dir)
                for _w2 in grism_file_widgets.values():
                    if _w2["fc"] is not chooser and _w2["fc"].selected is None:
                        _w2["fc"].reset(path=_State.last_dir)
                try:
                    if file_fc.selected is None:
                        file_fc.reset(path=_State.last_dir)
                except NameError:
                    pass

        fc.register_callback(_on_selected)
        row = w.VBox(
            [w.HTML(f"<b style='color:#2c7fb8'>{g.upper()}</b>"), fc],
            layout=w.Layout(border="1px solid #eee", padding="6px", margin="2px 0"),
        )
        return text_w, fc, row

    def _build_file_row(g, dir_text_w):
        file_text_w = w.Text(layout=w.Layout(display="none"))
        fc = FileChooser(
            path=get_last_dir(),
            title=f"Select {g.upper()} combined FITS file",
            select_default=False,
        )
        fc.filter_pattern = "*.fits"
        fc.show_only_files = True

        def _on_selected(chooser, _ft=file_text_w, _dt=dir_text_w):
            if chooser.selected:
                full = chooser.selected
                _ft.value = os.path.splitext(os.path.basename(full))[0]
                _dt.value = os.path.dirname(full)
                _State.last_dir = os.path.dirname(full)
                for _w2 in grism_dir_widgets.values():
                    if _w2["fc"] is not chooser and _w2["fc"].selected is None:
                        _w2["fc"].reset(path=_State.last_dir)
                for _w2 in grism_file_widgets.values():
                    if _w2["fc"] is not chooser and _w2["fc"].selected is None:
                        _w2["fc"].reset(path=_State.last_dir)
                try:
                    if file_fc.selected is None:
                        file_fc.reset(path=_State.last_dir)
                except NameError:
                    pass

        fc.register_callback(_on_selected)
        row = w.VBox(
            [w.HTML(f"<b style='color:#2c7fb8'>{g.upper()}</b>"), fc],
            layout=w.Layout(border="1px solid #eee", padding="6px", margin="2px 0"),
        )
        return file_text_w, fc, row

    def _on_grism_toggle(change, _g):
        show = change["new"]
        if _g in grism_dir_rows:
            grism_dir_rows[_g].layout.display = "" if show else "none"
        if _g in grism_file_rows:
            grism_file_rows[_g].layout.display = "" if show else "none"

    def rebuild_grism_ui(*_):
        inst = instrument_w.value
        survey = survey_w.value
        if not survey:
            return
        available = RULES[inst]["surveys"][survey]["grisms"]
        only_one = len(available) == 1

        grism_checkboxes.clear()
        grism_dir_widgets.clear()
        grism_file_widgets.clear()
        grism_dir_rows.clear()
        grism_file_rows.clear()

        cb_children = []
        dir_children = []
        file_children = []

        for g in available:
            cb = w.Checkbox(
                value=only_one,
                description=g.capitalize(),
                style={"description_width": "initial"},
            )
            cb.observe(lambda change, _g=g: _on_grism_toggle(change, _g), names="value")
            grism_checkboxes[g] = cb
            cb_children.append(cb)

            dir_text, dir_fc, dir_row = _build_dir_row(g)
            dir_row.layout.display = "" if cb.value else "none"
            grism_dir_widgets[g] = {"text": dir_text, "fc": dir_fc}
            grism_dir_rows[g] = dir_row
            dir_children.append(dir_row)

            file_text, file_fc, file_row = _build_file_row(g, dir_text)
            file_row.layout.display = "" if cb.value else "none"
            grism_file_widgets[g] = {"dir_text": dir_text, "file_text": file_text, "fc": file_fc}
            grism_file_rows[g] = file_row
            file_children.append(file_row)

        grism_checkboxes_box.children = cb_children
        grism_dirs_box.children = dir_children
        grism_files_box.children = file_children

    def update_instrument(*_):
        inst = instrument_w.value
        rules = RULES[inst]
        survey_w.options = list(rules["surveys"].keys())
        survey_w.value = rules["defaults"]["survey"]
        update_survey()

    def update_survey(*_):
        inst = instrument_w.value
        survey = survey_w.value
        survey_rules = RULES[inst]["surveys"][survey]
        datarelease_w.options = survey_rules["data_release"]
        datarelease_w.value = RULES[inst]["defaults"]["data_release"]
        rebuild_grism_ui()

    instrument_w.observe(update_instrument, names="value")
    survey_w.observe(update_survey, names="value")

    update_instrument()

    # -----------------------------------------------------------------------
    # Catalogue chooser
    # -----------------------------------------------------------------------

    dirIn_w = w.Text()
    fileIn_w = w.Text()
    fileExt_w = w.Text()
    VALID_EXT = {"fits", "csv", "npz"}

    file_fc = FileChooser(
        path=get_current_path(),
        title="Select catalogue file (csv, fits, npz)",
        filter_pattern=["*.fits", "*.npz", "*.csv"],
        select_default=False,
    )
    file_fc.show_only_files = True

    catalogue_label = w.HTML()

    def update_catalogue_label():
        if dirIn_w.value and fileIn_w.value and fileExt_w.value:
            catalogue_label.value = (
                f"<b>Current catalogue:</b> "
                f"{dirIn_w.value}/{fileIn_w.value}.{fileExt_w.value}"
            )
        else:
            catalogue_label.value = "<b>Current catalogue:</b> None"

    def set_catalogue_selection(path):
        if not path:
            return
        directory, filename = os.path.split(path)
        name, ext = os.path.splitext(filename)
        ext = ext.replace(".", "").lower()
        if ext not in VALID_EXT:
            return
        dirIn_w.value = directory
        fileIn_w.value = name
        fileExt_w.value = ext
        file_fc.path = directory
        update_catalogue_label()

    def on_file_selected(chooser):
        if chooser.selected:
            set_catalogue_selection(chooser.selected)
            _State.current_path = Path(dirIn_w.value)
            _State.last_dir = dirIn_w.value
            sync_current_path_to_spectra(_State.current_path)
            update_output_dir(dirIn_w.value)
            update_catalogue_columns()

    file_fc.register_callback(on_file_selected)

    def sync_catalogue_to_ui(directory, filename, ext):
        path = os.path.join(directory, f"{filename}.{ext}")
        set_catalogue_selection(path)
        _State.current_path = Path(dirIn_w.value)
        sync_current_path_to_spectra(_State.current_path)
        update_output_dir(dirIn_w.value)
        update_catalogue_columns()

    update_catalogue_label()

    # -----------------------------------------------------------------------
    # Output dir widgets
    # -----------------------------------------------------------------------

    def update_output_dir(input_dir):
        dirOut_w.value = os.path.join(input_dir, "output")

    dirOut_w = w.Text(description="Output directory:", style=style)
    override_output_w = w.Checkbox(value=False, description="Customize output directory")

    def toggle_output_edit(change):
        dirOut_w.disabled = not override_output_w.value

    override_output_w.observe(toggle_output_edit, names="value")
    dirOut_w.disabled = True

    # -----------------------------------------------------------------------
    # Output filename
    # -----------------------------------------------------------------------

    output_name_mode_w = w.Checkbox(
        value=False, description="Use custom output filename", style=style
    )
    output_name_custom_w = w.Text(
        placeholder="e.g. stacked_Halpha_Euclid_Q1",
        description="Custom name",
        style=style,
    )
    output_name_w = w.Text(value="AUTO", layout=w.Layout(display="none"))
    output_name_box = w.VBox()

    def update_output_name(change=None):
        if not output_name_mode_w.value:
            output_name_box.children = []
            output_name_w.value = "AUTO"
        else:
            output_name_box.children = [output_name_custom_w]
            output_name_w.value = output_name_custom_w.value.strip()

    def update_custom_name(change):
        if output_name_mode_w.value:
            output_name_w.value = output_name_custom_w.value.strip()

    output_name_custom_w.observe(update_custom_name, names="value")
    output_name_mode_w.observe(update_output_name, names="value")
    update_output_name()

    # -----------------------------------------------------------------------
    # Spectra format
    # -----------------------------------------------------------------------

    spectra_format_w = w.RadioButtons(
        options=[MODE_INDIVIDUAL, MODE_COMBINED, MODE_METADATA],
        value=MODE_INDIVIDUAL,
        layout={"width": "max-content"},
        description="Spectra format",
        style=style,
    )

    # -----------------------------------------------------------------------
    # Spectra dir/file choosers + full sync_current_path_to_spectra
    # -----------------------------------------------------------------------

    spectra_dir_w = w.Text(
        description="Spectra Directory",
        value=get_current_path(),
        layout=w.Layout(display="none"),
    )
    spectra_dir_fc = FileChooser(
        path=get_current_path(),
        title="Select spectra directory",
        select_default=False,
    )
    spectra_dir_fc.show_only_dirs = True

    spectra_datafile_w = w.Text(
        description="Spectra filename (FITS)",
        placeholder="COMBINED_spectra",
        layout=w.Layout(display="none"),
    )
    spectra_file_fc = FileChooser(
        path=get_current_path(),
        title="Select FITS file",
        select_default=False,
    )
    spectra_file_fc.filter_pattern = "*.fits"
    spectra_file_fc.show_only_files = True

    def set_dir_selection(path):
        path_str = str(Path(path).resolve())
        spectra_dir_w.value = path_str
        try:
            spectra_dir_fc._selected_files = []
            spectra_dir_fc._selected_path = None
            spectra_dir_fc.reset(path=path_str)
        except Exception:
            pass

    def sync_current_path_to_spectra(path):
        path_str = str(Path(path).resolve())
        set_dir_selection(path_str)
        try:
            spectra_file_fc.reset(path=path_str)
        except Exception:
            pass
        for g, wdg in grism_dir_widgets.items():
            wdg["text"].value = path_str
            try:
                fc = wdg["fc"]
                fc._selected_files = []
                fc._selected_path = None
                fc.reset(path=path_str)
            except Exception:
                pass
        for g, wdg in grism_file_widgets.items():
            try:
                fc = wdg["fc"]
                fc._selected_files = []
                fc._selected_path = None
                fc.reset(path=path_str)
            except Exception:
                pass

    def update_spectra_dir(change=None):
        mode = spectra_format_w.value
        if mode == MODE_INDIVIDUAL:
            grism_dirs_box.layout.display = ""
            grism_files_box.layout.display = "none"
            for g, row in grism_dir_rows.items():
                row.layout.display = (
                    "" if grism_checkboxes.get(g, w.Checkbox(value=True)).value else "none"
                )
        elif mode == MODE_COMBINED:
            grism_dirs_box.layout.display = "none"
            grism_files_box.layout.display = ""
            for g, row in grism_file_rows.items():
                row.layout.display = (
                    "" if grism_checkboxes.get(g, w.Checkbox(value=True)).value else "none"
                )
        else:
            grism_dirs_box.layout.display = "none"
            grism_files_box.layout.display = "none"

    def update_spectra_datafile(change=None):
        mode = spectra_format_w.value
        if mode == MODE_METADATA:
            spectra_datafile_w.value = "metadata"
        elif mode != MODE_COMBINED:
            spectra_datafile_w.value = ""

    set_dir_selection(get_current_path())
    update_spectra_dir()
    update_spectra_datafile()

    # -----------------------------------------------------------------------
    # Cosmology
    # -----------------------------------------------------------------------

    cosmo_H0 = w.FloatText(value=70, description=r"H$_0$")
    cosmo_Om0 = w.FloatText(value=0.3, description="$\\Omega_0$")

    # -----------------------------------------------------------------------
    # Redshift
    # -----------------------------------------------------------------------

    ztype_w = w.Dropdown(
        options=[
            ("Rest frame", "rest_frame"),
            ("Observed frame", "observed_frame"),
            ("Minimum z", "minimum_z"),
            ("Maximum z", "maximum_z"),
            ("Median z", "median_z"),
            ("Custom value", "custom"),
        ],
        value="rest_frame",
        description="Redshift type",
        style=style,
    )
    z_custom_w = w.FloatText(value=None, description="Custom z", style=style)
    z_custom_box = w.VBox()

    def update_ztype(change=None):
        if ztype_w.value == "custom":
            z_custom_box.children = [z_custom_w]
        else:
            z_custom_box.children = []

    # -----------------------------------------------------------------------
    # Normalization
    # -----------------------------------------------------------------------

    norm_w = w.Dropdown(
        options=["no_normalization", "custom", "median", "interval", "integral", "template"],
        value="median",
        description="Normalization",
        style=style,
    )
    conservation_w = w.Dropdown(
        options=["flux", "luminosity"],
        value="luminosity",
        description="Conservation",
        style=style,
        layout=w.Layout(display="none"),
    )

    def update_normalization(change=None):
        if norm_w.value == "no_normalization":
            conservation_w.layout.display = ""
            conservation_w.disabled = False
        else:
            conservation_w.layout.display = "none"

    # -----------------------------------------------------------------------
    # Interval normalization widgets
    # -----------------------------------------------------------------------

    _State.lambda_norm_rest_value = None
    _State.interval_norm_statistics_value = None
    _State.conservation_value = None

    lambda_min_w = w.FloatText(value=None, description="λ min", style=style)
    lambda_max_w = w.FloatText(value=None, description="λ max", style=style)
    interval_stat_w = w.Dropdown(
        options=["median", "mean", "maximum", "minimum"],
        value="median",
        description="Statistic",
        style=style,
    )

    regular_box = w.VBox([w.HTML("<b>Flux conservation mode</b>"), conservation_w])
    interval_box = w.VBox([
        w.HTML("<b>Normalization wavelength interval (rest-frame)</b>"),
        w.HBox([lambda_min_w, lambda_max_w]),
        interval_stat_w,
    ])
    norm_dynamic_box = w.VBox()

    def update_norm_ui(change=None):
        mode = norm_w.value
        if mode == "no_normalization":
            norm_dynamic_box.children = [regular_box]
            _State.conservation_value = conservation_w.value
            _State.lambda_norm_rest_value = None
            _State.interval_norm_statistics_value = None
        elif mode == "interval":
            norm_dynamic_box.children = [interval_box]
            _State.conservation_value = None
            _State.lambda_norm_rest_value = [
                float(lambda_min_w.value),
                float(lambda_max_w.value),
            ]
            _State.interval_norm_statistics_value = interval_stat_w.value
        else:
            norm_dynamic_box.children = []
            _State.conservation_value = None
            _State.lambda_norm_rest_value = None
            _State.interval_norm_statistics_value = None

    def update_regular_values(change=None):
        if norm_w.value == "no_normalization":
            _State.conservation_value = conservation_w.value

    def update_interval_values(change=None):
        if norm_w.value == "interval":
            _State.lambda_norm_rest_value = [
                float(lambda_min_w.value),
                float(lambda_max_w.value),
            ]
            _State.interval_norm_statistics_value = interval_stat_w.value

    conservation_w.observe(update_regular_values, names="value")
    update_regular_values()
    lambda_min_w.observe(update_interval_values, names="value")
    update_interval_values()
    lambda_max_w.observe(update_interval_values, names="value")
    update_interval_values()
    interval_stat_w.observe(update_interval_values, names="value")
    update_interval_values()

    # -----------------------------------------------------------------------
    # Resampling
    # -----------------------------------------------------------------------

    resampling_w = w.Dropdown(
        options=[
            ("Linear λ sampling", "lambda"),
            ("Log λ sampling", "log_lambda"),
            ("Shifted λ sampling", "lambda_shifted"),
            ("No resampling (observed frame only)", None),
        ],
        value="lambda",
        description="Resampling",
        style=style,
    )
    resampling_note = w.HTML(
        "<i>Note: None allowed only in observed_frame and requires identical wavelength grids.</i>"
    )
    pixel_type_w = w.RadioButtons(
        options=[("Manual pixel size", "manual"), ("Instrumental resolution", "instrumental")],
        value="manual",
        description="Pixel mode",
        style=style,
    )
    instrumental_resolution_note = w.HTML(
        "<i> Note: 'Instrumental resolution': the pixel size will be calculated according to "
        "the instrumental resolution provided in the instrument file.</i>"
    )
    pixel_size_w = w.FloatText(value=6, description="Δλ [Å]", style=style)
    n_nyq_w = w.FloatText(value=5, description="Nyquist sampling N", style=style)

    _State.pixel_size_mode_value = None
    _State.pixel_size_value = None
    _State.n_nyq_value = None

    pixel_manual_box = w.VBox([pixel_size_w])
    pixel_instr_box = w.VBox([n_nyq_w])
    pixel_dynamic_box = w.VBox()
    resampling_dynamic_box = w.VBox()

    def update_resampling(change=None):
        if ztype_w.value != "observed_frame" and resampling_w.value is None:
            resampling_w.value = "lambda"
            return
        if resampling_w.value is None:
            resampling_dynamic_box.children = []
            _State.pixel_size_mode_value = None
            _State.pixel_size_value = None
            _State.n_nyq_value = None
        else:
            resampling_dynamic_box.children = [pixel_type_w, pixel_dynamic_box]
            update_pixel_mode()

    def update_pixel_mode(change=None):
        if resampling_w.value is None:
            return
        if pixel_type_w.value == "manual":
            pixel_dynamic_box.children = [pixel_manual_box]
            _State.pixel_size_mode_value = "manual"
            _State.pixel_size_value = float(pixel_size_w.value)
            _State.n_nyq_value = None
        else:
            pixel_dynamic_box.children = [pixel_instr_box]
            _State.pixel_size_mode_value = "instrumental"
            _State.pixel_size_value = None
            _State.n_nyq_value = float(n_nyq_w.value)

    def update_manual_value(change=None):
        if pixel_type_w.value == "manual":
            _State.pixel_size_value = float(pixel_size_w.value)

    def update_instr_value(change=None):
        if pixel_type_w.value == "instrumental":
            _State.n_nyq_value = float(n_nyq_w.value)

    resampling_w.observe(update_resampling, names="value")
    pixel_type_w.observe(update_pixel_mode, names="value")
    pixel_size_w.observe(update_manual_value, names="value")
    n_nyq_w.observe(update_instr_value, names="value")
    update_resampling()

    # -----------------------------------------------------------------------
    # Wavelength extent + edge crop
    # -----------------------------------------------------------------------

    lambda_banner = w.HTML("""
<div style="border-left:6px solid #2c7fb8; background:#eef6fb; padding:10px;">
Optional wavelength restriction for the stacked spectrum.<br><br>
If enabled, the stacked spectrum will only include wavelengths between:<br>
<b>left_edge × (1+z_stacking)</b> and <b>right_edge × (1+z_stacking)</b><br><br>
Useful to focus on emission lines or specific spectral regions.
</div>
""")
    lambda_enable_w = w.Checkbox(
        value=False, description="Limit wavelength range", style=style
    )
    left_edge_w = w.FloatText(value=6150, description="Left edge", style=style)
    right_edge_w = w.FloatText(value=6750, description="Right edge", style=style)
    lambda_box = w.VBox()

    def update_lambda_box(change=None):
        if lambda_enable_w.value:
            lambda_box.children = [lambda_banner, left_edge_w, right_edge_w]
        else:
            lambda_box.children = []

    lambda_enable_w.observe(update_lambda_box, names="value")
    update_lambda_box()

    edges_banner = w.HTML("""
<div style="border-left:6px solid #f28e2b; background:#fff4e6; padding:10px;">
Optional cropping of spectrum edges.<br><br>
Removes the first N and last M pixels before stacking.<br><br>
Uses Python slicing rules.<br>
Example: first=10, last=-10 → keeps spectrum[10:-10]
</div>
""")
    edges_enable_w = w.Checkbox(
        value=False, description="Crop spectrum edges", style=style
    )
    first_pixel_w = w.IntText(value=10, description="First pixel", style=style)
    last_pixel_w = w.IntText(value=-10, description="Last pixel", style=style)
    edges_box = w.VBox()

    def update_edges_box(change=None):
        if edges_enable_w.value:
            edges_box.children = [edges_banner, first_pixel_w, last_pixel_w]
        else:
            edges_box.children = []

    edges_enable_w.observe(update_edges_box, names="value")
    update_edges_box()

    # -----------------------------------------------------------------------
    # Reset helpers (reference cell-19 widgets via closure)
    # -----------------------------------------------------------------------

    def reset_widget(widget):
        try:
            if isinstance(widget, w.Dropdown):
                if UI_EMPTY in widget.options:
                    widget.value = UI_EMPTY
                else:
                    widget.value = widget.options[0]
            else:
                widget.value = ""
        except Exception:
            pass

    def reset_metadata_fields():
        for wdg in [metadata_path_w, metadata_file_w, metadata_indx_w]:
            reset_widget(wdg)

    def reset_redshift_field():
        reset_widget(redshift_column_input_w)

    def reset_gal_ext_field():
        reset_widget(gal_ext_name_input_w)

    def reset_custom_norm_field():
        reset_widget(custom_norm_input_w)

    # -----------------------------------------------------------------------
    # Catalogue column mapping
    # -----------------------------------------------------------------------

    redshift_box = w.VBox()
    metadata_box = w.VBox()
    gal_ext_box = w.VBox()
    custom_norm_box = w.VBox()

    UI_EMPTY = "-- select column --"
    EMPTY_OPTION = ["-- select catalogue first --"]

    def get_catalogue_columns(path):
        if not path:
            return []
        path = Path(path)
        ext = path.suffix.lower()
        try:
            if ext == ".csv":
                import pandas as pd
                return sorted(list(pd.read_csv(path, nrows=0).columns))
            elif ext == ".fits":
                from astropy.io import fits
                with fits.open(path) as hdul:
                    for hdu in hdul:
                        if hasattr(hdu, "columns"):
                            return sorted(list(hdu.columns.names))
                    return []
            elif ext == ".npz":
                import numpy as np
                with np.load(path) as data:
                    return sorted(list(data.keys()))
            return []
        except Exception as e:
            print(f"Failed reading catalogue: {e}")
            return []

    def guess_column(available_cols, candidates):
        for c in candidates:
            if c in available_cols:
                return c
        return None

    def make_dropdown(description):
        return w.Dropdown(
            options=EMPTY_OPTION,
            value=EMPTY_OPTION[0],
            description=description,
            style=style,
        )

    ID_column_w = make_dropdown("ID column")
    redshift_column_input_w = make_dropdown("Redshift column")
    metadata_path_w = make_dropdown("Metadata path")
    metadata_file_w = make_dropdown("Metadata file")
    metadata_indx_w = make_dropdown("Metadata HDU")
    gal_ext_name_input_w = make_dropdown("E(B-V) column")
    custom_norm_input_w = make_dropdown("Custom norm. column")

    COLUMN_CANDIDATES = {
        "id": ["object_id", "source_id", "ID", "IDS"],
        "redshift": ["z", "Z", "spe_z", "ext_z", "redshift", "redsh"],
        "meta_path": ["datalabs_path"],
        "meta_file": ["file_name"],
        "meta_indx": ["hdu_index"],
        "ebv": ["ebv_gal", "E(B-V)", "EBV", "ebv"],
        "custom": [],
    }

    def update_catalogue_columns():
        if not (dirIn_w.value and fileIn_w.value and fileExt_w.value):
            columns = EMPTY_OPTION
        else:
            full_path = os.path.join(dirIn_w.value, f"{fileIn_w.value}.{fileExt_w.value}")
            cols = get_catalogue_columns(full_path)
            columns = [UI_EMPTY] + cols if cols else ["-- no columns found --"]

        widgets_list = [
            ID_column_w, redshift_column_input_w, metadata_path_w,
            metadata_file_w, metadata_indx_w, gal_ext_name_input_w, custom_norm_input_w,
        ]
        candidate_keys = ["id", "redshift", "meta_path", "meta_file", "meta_indx", "ebv", "custom"]

        for widget, key in zip(widgets_list, candidate_keys):
            current = widget.value
            widget.options = columns
            if current in columns and current != UI_EMPTY:
                widget.value = current
            else:
                guessed = guess_column(columns, COLUMN_CANDIDATES[key])
                widget.value = (
                    guessed if guessed is not None
                    else (UI_EMPTY if UI_EMPTY in columns else columns[0])
                )

    def update_redshift_column(change=None):
        if ztype_w.value != "observed_frame":
            redshift_box.children = [redshift_column_input_w]
        else:
            reset_redshift_field()
            redshift_box.children = []

    def update_metadata(change=None):
        if spectra_format_w.value == MODE_METADATA:
            metadata_box.children = [
                w.HTML("<b>Metadata column names mapping</b>"),
                metadata_path_w,
                metadata_file_w,
                metadata_indx_w,
            ]
        else:
            reset_metadata_fields()
            metadata_box.children = []

    gal_ext_corr_w = w.Checkbox(value=False, description="Galactic extinction correction")
    gal_ext_banner = w.HTML(
        """
    <div style="
        border-left: 6px solid #2c7fb8;
        background-color: #eef6fb;
        padding: 12px;
        margin-top: 10px;
        border-radius: 6px;
    ">
    <b>Galactic extinction corrections</b><br><br>
    Uses <b>Gordon+23 extinction curve</b> via <i>dust_extinction</i>.<br><br>
    Please cite the G23 model if used:<br>
    <a href="https://dust-extinction.readthedocs.io/en/latest/dust_extinction/references.html"
       target="_blank">
       dust_extinction reference page
    </a>
    </div>
    """,
        layout=w.Layout(display="none"),
    )

    def update_gal_ext(change=None):
        if gal_ext_corr_w.value:
            gal_ext_box.children = [
                w.HTML("<i>Make sure E(B-V) column exists in catalogue</i>"),
                w.HTML("<i></i>"),
                gal_ext_name_input_w,
            ]
            gal_ext_banner.layout.display = "block"
        else:
            reset_gal_ext_field()
            gal_ext_box.children = []
            gal_ext_banner.layout.display = "none"

    def update_custom_norm(change=None):
        if norm_w.value == "custom":
            custom_norm_box.children = [
                w.HTML("<i>Make sure custom column exists in catalogue</i>"),
                custom_norm_input_w,
            ]
        else:
            reset_custom_norm_field()
            custom_norm_box.children = []

    ztype_w.observe(update_redshift_column, names="value")
    spectra_format_w.observe(update_metadata, names="value")
    gal_ext_corr_w.observe(update_gal_ext, names="value")
    norm_w.observe(update_custom_norm, names="value")

    update_redshift_column()
    update_metadata()
    update_gal_ext()
    update_custom_norm()

    # -----------------------------------------------------------------------
    # QC widgets
    # -----------------------------------------------------------------------

    sigma_w = w.FloatSlider(
        value=4.0, min=0.0, max=5.0, step=0.25,
        description="Sigma Clip", style=style,
    )
    pixel_mask_select_w = w.SelectMultiple(
        options=list(range(7)), value=(0, 6), rows=7,
        description="Bad pixel bits", style=style,
    )
    bad_pixel_note = w.HTML(
        "<i> Note: Multiple values can be selected with shift and/or ctrl "
        "(or command) pressed and mouse clicks or arrow keys.</i>"
    )
    dither_banner = w.HTML("""
<div style="border-left:6px solid #2c7fb8; background:#eef6fb; padding:10px;">
Minimum number of dithers in the coadded 1D spectrum.<br>
Higher is better.<br><br> Note: Euclid Q1 max dithers = 4 (recommended ≥ 2).
</div>
""")
    dither_w = w.IntSlider(value=2, min=1, max=50, step=1, description="Min dithers", style=style)
    instrument_qc_box = w.VBox()

    def update_instrument_qc(change=None):
        inst = instrument_w.value
        caps = INSTRUMENT_EXTRA_QC.get(inst, {})
        children = []
        if caps.get("bad_pixels", False):
            children += [bad_pixel_note, pixel_mask_select_w]
        if caps.get("dithers", False):
            children += [dither_banner, dither_w]
        instrument_qc_box.children = children

    instrument_w.observe(update_instrument_qc, names="value")
    update_instrument_qc()

    # -----------------------------------------------------------------------
    # Bootstrap / parallel / plot
    # -----------------------------------------------------------------------

    bootstrap_R = w.BoundedIntText(value=300, min=0, max=1000, description="Bootstrap R")
    parallel_enabled = w.Checkbox(value=True, description="Enable Multiprocessing")
    parallel_cpu_frac = w.FloatSlider(value=0.9, min=0.1, max=0.95, step=0.05, description="CPU Fraction")
    plot_enabled = w.Checkbox(value=True, description="Plot stacked spectrum")

    # -----------------------------------------------------------------------
    # Umbrella observer wiring
    # -----------------------------------------------------------------------

    def update_all_spectra_format_w(change=None):
        update_spectra_dir()
        update_spectra_datafile()
        update_metadata()

    def update_all_ztype_w(change=None):
        update_ztype()
        update_resampling()
        update_redshift_column()

    def update_all_norm_w(change=None):
        update_normalization()
        update_norm_ui()
        update_custom_norm()

    spectra_format_w.observe(update_all_spectra_format_w, names="value")
    ztype_w.observe(update_all_ztype_w, names="value")
    norm_w.observe(update_all_norm_w, names="value")

    # -----------------------------------------------------------------------
    # Load / restore from .gui file
    # -----------------------------------------------------------------------

    path_to_config_dir = PACKAGE_ROOT / "configs" / "GUI"
    validation_load_gui = w.Output()

    load_GUI_fc = FileChooser(
        path=str(path_to_config_dir),
        title="Select GUI file (.gui)",
        filter_pattern="*.gui",
        select_default=False,
    )
    load_GUI_fc.reset()
    selected_gui_label = w.HTML()

    load_GUI_btn = w.Button(description="Load GUI", button_style="primary", disabled=True)

    def on_gui_file_selected(chooser):
        if chooser.selected:
            selected_gui_label.value = f"<b>Selected:</b> {Path(chooser.selected).name}"
            load_GUI_btn.disabled = False
        else:
            selected_gui_label.value = ""
            load_GUI_btn.disabled = True

    load_GUI_fc.register_callback(on_gui_file_selected)

    def restore_widgets_from_gui_dict(_):
        validation_load_gui.clear_output()
        with validation_load_gui:
            full_path = load_GUI_fc.selected
            if not full_path:
                print("No file selected.")
                return
            full_path = Path(full_path)
            if not full_path.exists():
                print(f"File not found: {full_path}")
                return
            try:
                with open(full_path) as f:
                    payload = json.load(f)
                cfg = payload.get("gui_state", payload)
            except Exception as e:
                print(f"Failed loading config: {e}")
                return

            def safe_set(widget, value):
                try:
                    if value in ("", None):
                        if hasattr(widget, "options") and UI_EMPTY in widget.options:
                            widget.value = UI_EMPTY
                        else:
                            widget.value = widget.options[0]
                    else:
                        widget.value = value
                except Exception:
                    if hasattr(widget, "options") and value not in widget.options:
                        print(f"⚠️  Saved column '{value}' not found in catalogue — please re-select.")

            def safe_set_2(widget_tuple, value_tuple):
                try:
                    if isinstance(widget_tuple, (list, tuple)) and isinstance(value_tuple, (list, tuple)):
                        if len(widget_tuple) == len(value_tuple):
                            for wgt, v in zip(widget_tuple, value_tuple):
                                wgt.value = v
                    else:
                        widget_tuple.value = value_tuple
                except Exception:
                    pass

            # Phase 1 — control variables
            safe_set(instrument_w, cfg.get("instrument_name", instrument_w.value))
            update_instrument()
            safe_set(survey_w, cfg.get("survey_name", survey_w.value))
            safe_set(datarelease_w, cfg.get("data_release", datarelease_w.value))
            safe_set(spectra_format_w, cfg.get("spectra_mode", spectra_format_w.value))
            safe_set(ztype_w, cfg.get("z_type", ztype_w.value))
            safe_set(norm_w, cfg.get("spectra_normalization", norm_w.value))

            # Phase 2 — trigger UI updates
            update_all_spectra_format_w()
            update_all_ztype_w()
            update_all_norm_w()
            update_catalogue_columns()

            # Phase 3 — dependent values
            sync_catalogue_to_ui(
                cfg.get("input_dir", ""),
                cfg.get("filename_in", ""),
                cfg.get("filename_in_extention", "csv"),
            )
            safe_set(dirOut_w, cfg.get("output_dir", ""))

            saved_grisms = cfg.get("grisms", [])
            saved_grism_io = cfg.get("grism_io", {})
            for g, cb in grism_checkboxes.items():
                cb.value = g in saved_grisms
            for g, wdg in grism_dir_widgets.items():
                gcfg = saved_grism_io.get(g, {})
                val = str(gcfg.get("spectra_dir", "") or "").strip()
                if val:
                    wdg["text"].value = val
                    try:
                        wdg["fc"].path = val
                        wdg["fc"]._selected_path = val
                        wdg["fc"]._apply_selection()
                    except Exception:
                        pass
            for g, wdg in grism_file_widgets.items():
                gcfg = saved_grism_io.get(g, {})
                val = str(gcfg.get("spectra_datafile", "") or "").strip()
                if val:
                    wdg["file_text"].value = val
                    dir_val = str(saved_grism_io.get(g, {}).get("spectra_dir", "") or "").strip()
                    full = str(Path(dir_val) / f"{val}.fits") if dir_val else val
                    try:
                        wdg["fc"]._selected_path = full
                        wdg["fc"]._apply_selection()
                    except Exception:
                        pass
            update_spectra_dir()

            filename_out = cfg.get("filename_out", "AUTO")
            if filename_out == "AUTO":
                safe_set(output_name_mode_w, "default")
            else:
                safe_set(output_name_mode_w, "custom")
                safe_set(output_name_custom_w, filename_out)
            update_output_name()

            safe_set(ID_column_w, cfg.get("ID_column_name", ""))
            safe_set(redshift_column_input_w, cfg.get("redshift_column_name", ""))
            safe_set(metadata_path_w, cfg.get("metadata_path_column_name", ""))
            safe_set(metadata_file_w, cfg.get("metadata_file_column_name", ""))
            safe_set(metadata_indx_w, cfg.get("metadata_indx_column_name", ""))
            safe_set(gal_ext_name_input_w, cfg.get("gal_ext_column_name", ""))
            safe_set(custom_norm_input_w, cfg.get("custom_column_name", ""))

            safe_set(cosmo_H0, cfg.get("cosmo_H0", cosmo_H0.value))
            safe_set(cosmo_Om0, cfg.get("cosmo_Om0", cosmo_Om0.value))
            safe_set(z_custom_w, cfg.get("z_value", z_custom_w.value))
            safe_set(conservation_w, cfg.get("conservation", conservation_w.value))
            safe_set(
                _State.interval_norm_statistics_value,
                cfg.get("interval_norm_statistics", _State.interval_norm_statistics_value),
            )
            safe_set_2(
                (lambda_min_w, lambda_max_w),
                cfg.get("lambda_norm_rest", _State.lambda_norm_rest_value),
            )
            safe_set(resampling_w, cfg.get("pixel_resampling_type", resampling_w.value))
            safe_set(pixel_type_w, cfg.get("pixel_size_type", pixel_type_w.value))
            safe_set(pixel_size_w, cfg.get("pixel_resampling", pixel_size_w.value))
            safe_set(n_nyq_w, cfg.get("nyquist_sampling", n_nyq_w.value))
            safe_set(sigma_w, cfg.get("sigma_clipping_conditions", sigma_w.value))
            safe_set(bootstrap_R, cfg.get("bootstrapping_R", bootstrap_R.value))
            safe_set(
                pixel_mask_select_w,
                tuple(cfg.get("pixel_mask", list(pixel_mask_select_w.value))),
            )
            safe_set(dither_w, cfg.get("n_min_dithers", dither_w.value))
            safe_set(parallel_enabled, cfg.get("multiprocessing", parallel_enabled.value))
            safe_set(parallel_cpu_frac, cfg.get("max_cpu_fraction", parallel_cpu_frac.value))

            lambda_edges = cfg.get("lambda_edges_rest", False)
            if lambda_edges:
                lambda_enable_w.value = True
                left_edge_w.value = lambda_edges[0]
                right_edge_w.value = lambda_edges[1]
            else:
                lambda_enable_w.value = False

            spectrum_edges = cfg.get("spectrum_edges", False)
            if spectrum_edges:
                edges_enable_w.value = True
                first_pixel_w.value = spectrum_edges[0]
                last_pixel_w.value = spectrum_edges[1]
            else:
                edges_enable_w.value = False

            safe_set(plot_enabled, cfg.get("plot_results", plot_enabled.value))
            update_gal_ext()
            print("✅ GUI loaded successfully")

    load_GUI_btn.on_click(restore_widgets_from_gui_dict)

    # -----------------------------------------------------------------------
    # Config builder + preview
    # -----------------------------------------------------------------------

    def clean_value(widget):
        if isinstance(widget, w.Dropdown):
            if widget.value in (None, UI_EMPTY, "-- select catalogue first --", "-- no columns found --"):
                return ""
        return widget.value

    def build_wavelength_config():
        if lambda_enable_w.value:
            lambda_edges_rest = [float(left_edge_w.value), float(right_edge_w.value)]
        else:
            lambda_edges_rest = None
        if edges_enable_w.value:
            spectrum_edges = [int(first_pixel_w.value), int(last_pixel_w.value)]
        else:
            spectrum_edges = None
        return lambda_edges_rest, spectrum_edges

    def build_user_config():
        lambda_edges_rest_value, spectrum_edges_value = build_wavelength_config()
        return dict(
            input_dir=dirIn_w.value,
            output_dir=dirOut_w.value,
            filename_in=fileIn_w.value,
            filename_in_extention=fileExt_w.value,
            filename_out=output_name_w.value,
            spectra_mode=spectra_format_w.value,
            ID_column_name=clean_value(ID_column_w),
            redshift_column_name=clean_value(redshift_column_input_w),
            metadata_path_column_name=clean_value(metadata_path_w),
            metadata_file_column_name=clean_value(metadata_file_w),
            metadata_indx_column_name=clean_value(metadata_indx_w),
            galactic_extinction=gal_ext_corr_w.value,
            gal_ext_column_name=clean_value(gal_ext_name_input_w),
            custom_column_name=clean_value(custom_norm_input_w),
            instrument_name=instrument_w.value,
            survey_name=survey_w.value,
            grisms=[g for g, cb in grism_checkboxes.items() if cb.value],
            grism_io={
                g: {
                    "spectra_dir": grism_dir_widgets[g]["text"].value or None,
                    "spectra_datafile": grism_file_widgets[g]["file_text"].value or None,
                }
                for g, cb in grism_checkboxes.items()
                if cb.value
            },
            data_release=datarelease_w.value,
            cosmo_H0=cosmo_H0.value,
            cosmo_Om0=cosmo_Om0.value,
            z_type=ztype_w.value,
            z_value=z_custom_w.value,
            spectra_normalization=norm_w.value,
            conservation=_State.conservation_value,
            spectrum_edges=spectrum_edges_value,
            lambda_edges_rest=lambda_edges_rest_value,
            interval_norm_statistics=_State.interval_norm_statistics_value,
            lambda_norm_rest=_State.lambda_norm_rest_value,
            pixel_resampling_type=resampling_w.value,
            pixel_size_type=_State.pixel_size_mode_value,
            pixel_resampling=_State.pixel_size_value,
            nyquist_sampling=_State.n_nyq_value,
            sigma_clipping_conditions=sigma_w.value,
            bootstrapping_R=bootstrap_R.value,
            pixel_mask=list(pixel_mask_select_w.value),
            n_min_dithers=dither_w.value,
            multiprocessing=parallel_enabled.value,
            max_cpu_fraction=parallel_cpu_frac.value,
            plot_results=plot_enabled.value,
        )

    preview_out = w.Output()
    preview_btn = w.Button(description="Preview Config", style=dict(button_color="orange"))

    def preview_config(_):
        with preview_out:
            clear_output()
            cfg = build_user_config()
            print(cfg)

    preview_btn.on_click(preview_config)

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    _State.validated_cfg = None

    def run_validation():
        try:
            cfg = build_config_from_widgets(build_user_config)
            cfg = StackingConfigResolver.resolve(cfg)
            _State.validated_cfg = cfg
            return cfg, None
        except Exception as e:
            _State.validated_cfg = None
            return None, str(e)

    validate_btn = w.Button(
        description="Check Config",
        button_style="",
        tooltip="Validate the current configuration without running",
    )
    validation_output = w.Output()

    def on_validate(_):
        validation_output.clear_output()
        cfg, err = run_validation()
        with validation_output:
            if err:
                print("❌ Validation failed!")
                print(err)
            else:
                print("✅ Config valid!")
                print(f"Config version: {cfg.config_version}")

    validate_btn.on_click(on_validate)

    # -----------------------------------------------------------------------
    # Export GUI
    # -----------------------------------------------------------------------

    export_GUI_output = w.Output()
    save_GUI_name_w = w.Text(description="GUI filename", style=style)
    save_GUI_btn = w.Button(description="Save config (GUI)", style=dict(button_color="antiquewhite"))

    def on_export_GUI(_):
        export_GUI_output.clear_output()
        gui_dir = PACKAGE_ROOT / "configs" / "GUI"
        gui_dir.mkdir(parents=True, exist_ok=True)
        try:
            cfg, err = run_validation()
            if err:
                with export_GUI_output:
                    print(f"❌ Validation failed — config not exported.\n{err}")
                return
            gui_cfg = build_user_config()
            filename = save_GUI_name_w.value.strip()
            if not filename:
                raise ValueError("Filename is empty")
            if not filename.endswith(".gui"):
                filename += ".gui"
            full_path = gui_dir / filename
            export_payload = {
                "gui_state": gui_cfg,
                "validated_config": _State.validated_cfg.model_dump(mode="json"),
            }
            with open(full_path, "w") as f:
                json.dump(export_payload, f, indent=2)
            with export_GUI_output:
                print(f"✅ GUI exported correctly: {full_path}")
        except Exception as e:
            with export_GUI_output:
                print("❌ Export GUI failed! see Log...")
            print("Export failed:", e)

    save_GUI_btn.on_click(on_export_GUI)

    # -----------------------------------------------------------------------
    # Common config filename + export JSON/YAML
    # -----------------------------------------------------------------------

    save_config_name_w = w.Text(description="Config filename", style=style)

    export_JSON_output = w.Output()
    save_JSON_btn = w.Button(description="Save config (JSON)", style=dict(button_color="lightgreen"))

    def on_export_JSON(_):
        export_JSON_output.clear_output()
        json_dir = PACKAGE_ROOT / "configs" / "JSON"
        json_dir.mkdir(parents=True, exist_ok=True)
        try:
            cfg, err = run_validation()
            if err:
                with export_JSON_output:
                    print(f"❌ Validation failed — config not exported.\n{err}")
                return
            filename = save_config_name_w.value.strip()
            if not filename:
                raise ValueError("Filename is empty")
            if not filename.endswith(".json"):
                filename += ".json"
            export_config_to_json(_State.validated_cfg, json_dir / filename)
            with export_JSON_output:
                print(f"✅ Export to JSON done: {json_dir / filename}")
        except Exception as e:
            with export_JSON_output:
                print("❌ Export to JSON failed! see Log...")
            print("Export failed:", e)

    save_JSON_btn.on_click(on_export_JSON)

    export_YAML_output = w.Output()
    save_YAML_btn = w.Button(description="Save config (YAML)", style=dict(button_color="lightgreen"))

    def on_export_YAML(_):
        export_YAML_output.clear_output()
        yaml_dir = PACKAGE_ROOT / "configs" / "YAML"
        yaml_dir.mkdir(parents=True, exist_ok=True)
        try:
            cfg, err = run_validation()
            if err:
                with export_YAML_output:
                    print(f"❌ Validation failed — config not exported.\n{err}")
                return
            filename = save_config_name_w.value.strip()
            if not filename:
                raise ValueError("Filename is empty")
            if not filename.endswith(".yaml"):
                filename += ".yaml"
            export_config_to_yaml(_State.validated_cfg, yaml_dir / filename)
            with export_YAML_output:
                print(f"✅ Export to YAML done: {yaml_dir / filename}")
        except Exception as e:
            with export_YAML_output:
                print("❌ Export to YAML failed! see Log...")
            print("Export failed:", e)

    save_YAML_btn.on_click(on_export_YAML)

    # -----------------------------------------------------------------------
    # Run handler
    # -----------------------------------------------------------------------

    run_spec_output = w.Output()
    progress_bar = w.IntProgress(
        value=0, min=0, max=100, description="Running:",
        bar_style="", style={"bar_color": "#2196F3"}, orientation="horizontal",
    )
    progress_label = w.HTML(value="Starting...")
    final_report = w.HTML(value="")
    log_path_w = w.Text(value="", layout=w.Layout(display="none"))
    DEBUG_MODE = False

    def get_unique_log_path(base_path: Path, suffix: str = ".log") -> Path:
        base_path.parent.mkdir(parents=True, exist_ok=True)
        if not base_path.exists():
            return base_path
        stem = base_path.stem
        counter = 1
        while True:
            new_path = base_path.parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

    def run_spectraPyle(_):
        run_spec_output.clear_output()
        final_report.value = ""
        progress_bar.value = 0
        progress_bar.bar_style = ""
        progress_label.value = "Initializing..."

        progress_label.value = "Validating config..."
        cfg, err = run_validation()
        if err:
            with run_spec_output:
                print(f"❌ Validation failed — cannot run.\n{err}")
            return
        progress_label.value = "Initializing..."

        with run_spec_output:
            display(progress_bar)
            display(progress_label)
            display(final_report)

        start_time = time.time()
        stop_flag = {"done": False}

        def animate_progress():
            while not stop_flag["done"]:
                progress_bar.value = (progress_bar.value + 5) % 100
                elapsed = int(time.time() - start_time)
                progress_label.value = f"Running... {elapsed}s elapsed"
                time.sleep(0.5)

        thread = threading.Thread(target=animate_progress)
        thread.start()

        try:
            from spectraPyle.runtime.runtime_adapter import flatten_schema_model as _fsm
            from spectraPyle.io.filename_builder import build_filename as _bfn

            _flat_pre = _fsm(_State.validated_cfg)
            _pre_name = _bfn(_flat_pre) if _flat_pre["filename_out"] == "AUTO" else _flat_pre["filename_out"]
            pre_output_filename = str(Path(_flat_pre["output_dir"]) / f"{_pre_name}.fits")

            log_stem = Path(pre_output_filename).stem
            path_to_log_file = get_unique_log_path(
                Path(_flat_pre["output_dir"]) / f"{log_stem}.log"
            )
            log_path_w.value = str(path_to_log_file)

            with run_spec_output:
                print(f"📝 Logging to: {path_to_log_file}")

            with open(path_to_log_file, "w") as logfile:
                tee = Tee(logfile, debug=DEBUG_MODE)
                with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
                    print("=== spectraPyle run started ===")
                    print(f"Timestamp: {time.ctime()}")
                    print(f"Config: {_State.validated_cfg}")

                    importlib.reload(stack)
                    from spectraPyle.utils.log import setup_logging
                    import ipywidgets as widgets

                    log_widget = widgets.Output()
                    with run_spec_output:
                        display(log_widget)

                    setup_logging(level="INFO", log_file=path_to_log_file, gui_output=log_widget)
                    stack.main(_State.validated_cfg)
                    print("=== spectraPyle run completed ===")

            if _State.validated_cfg.plot.plot_results and pre_output_filename:
                try:
                    with run_spec_output:
                        import spectraPyle.plot.plot as _spl_mod
                        importlib.reload(_spl_mod)
                        _spl_mod.plotting(pre_output_filename)
                except Exception as _plot_err:
                    with run_spec_output:
                        print(f"⚠️  Plot failed: {_plot_err}")

            stop_flag["done"] = True
            thread.join()
            progress_bar.value = 100
            progress_bar.bar_style = "success"
            elapsed = round(time.time() - start_time, 2)
            final_report.value = f"""
        <div style="border:1px solid #4CAF50;padding:10px;border-radius:6px;background-color:#E8F5E9;">
            <b>✅ spectraPyle finished successfully</b><br>
            Total runtime: {elapsed} seconds<br>
            Log file: <code>{path_to_log_file}</code>
        </div>
        """

        except Exception as e:
            stop_flag["done"] = True
            thread.join()
            progress_bar.bar_style = "danger"
            elapsed = round(time.time() - start_time, 2)
            tb = traceback.format_exc()
            try:
                with open(path_to_log_file, "a") as logfile:
                    logfile.write("\n\n=== ERROR TRACEBACK ===\n")
                    logfile.write(tb)
            except Exception:
                pass
            short_error = str(e)
            final_report.value = f"""
        <div style="border:1px solid #F44336;padding:10px;border-radius:6px;background-color:#FFEBEE;">
            <b>❌ spectraPyle failed</b><br>
            Runtime before failure: {elapsed} seconds<br>
            Error: {short_error}<br>
            Log file: <code>{path_to_log_file}</code>
        </div>
        """
            if DEBUG_MODE:
                with run_spec_output:
                    print("\n🔍 FULL TRACEBACK:\n")
                    print(tb)

    run_spectraPyle_btn = w.Button(description="RUN spectraPyle", button_style="danger")
    run_spectraPyle_btn.on_click(run_spectraPyle)

    # -----------------------------------------------------------------------
    # Log viewer
    # -----------------------------------------------------------------------

    show_log_btn = w.Button(description="Show log")
    log_output = w.Output(layout={"border": "1px solid black", "height": "300px", "overflow": "auto"})

    def show_log(_):
        log_output.clear_output()
        path = log_path_w.value
        if not path or not Path(path).exists():
            with log_output:
                print("❌ No log file available")
            return
        with open(path) as f:
            with log_output:
                print(f.read())

    show_log_btn.on_click(show_log)

    # -----------------------------------------------------------------------
    # Layout assembly
    # -----------------------------------------------------------------------

    instrument_tab = w.VBox([
        section("Instrument (*)"),
        instrument_w,
        survey_w,
        w.HTML("<b>Grisms</b>"),
        grism_checkboxes_box,
        datarelease_w,
        advanced_box([instrument_qc_box]),
    ])

    processing_tab = w.VBox([
        section("Processing"),
        section("Redshift"),
        ztype_w,
        z_custom_box,
        section("Normalization"),
        norm_w,
        norm_dynamic_box,
        section("Resampling"),
        resampling_w,
        resampling_note,
        resampling_dynamic_box,
        instrumental_resolution_note,
        section("Refining wavelength range"),
        advanced_box([lambda_enable_w, lambda_box, edges_enable_w, edges_box]),
        section("Performance"),
        advanced_box([
            section("Sigma clipping"), sigma_w,
            section("Bootstrap"), bootstrap_R,
            section("Parallel"), parallel_enabled, parallel_cpu_frac,
            section("Plot"), plot_enabled,
        ]),
        section("Cosmology"),
        advanced_box([section("Cosmology"), cosmo_H0, cosmo_Om0]),
    ])

    io_tab = w.VBox([
        section("Input/Output (*)"),
        section("Catalogue"),
        catalogue_label,
        file_fc,
        section("Input spectra format"),
        spectra_format_w,
        section("Spectra"),
        grism_dirs_box,
        grism_files_box,
        advanced_box([
            section("Output directory"),
            override_output_w,
            dirOut_w,
            section("Output filename. Default: AUTO"),
            output_name_mode_w,
            output_name_box,
        ]),
    ])

    catalogue_tab = w.VBox([
        section("Catalogue (*)"),
        ID_column_w,
        redshift_box,
        metadata_box,
        advanced_box([
            section("Galactic extintion"),
            gal_ext_corr_w,
            gal_ext_box,
            gal_ext_banner,
            section("Custom normalization parameter"),
            custom_norm_box,
        ]),
    ])

    load_config_section = w.Accordion(children=[
        w.VBox([load_GUI_fc, load_GUI_btn, validation_load_gui])
    ])
    load_config_section.set_title(0, "📂 Load Existing Config")
    load_config_section.selected_index = None

    main_tabs = w.Tab(children=[instrument_tab, io_tab, catalogue_tab, processing_tab])
    main_tabs.set_title(0, "Instrument (*)")
    main_tabs.set_title(1, "Input/Output (*)")
    main_tabs.set_title(2, "Catalogue (*)")
    main_tabs.set_title(3, "Stack Params")

    run_spectraPyle_btn.layout = w.Layout(width="220px", height="40px")
    run_section = w.VBox([
        w.HBox([run_spectraPyle_btn, validate_btn], layout=w.Layout(align_items="center", gap="12px")),
        validation_output,
        run_spec_output,
    ])

    export_section = w.Accordion(children=[
        w.VBox([
            section("Save GUI (.gui)"),
            w.HBox([save_GUI_name_w, save_GUI_btn]),
            export_GUI_output,
            section("Save JSON / YAML"),
            w.HBox([save_config_name_w, save_JSON_btn, save_YAML_btn]),
            export_JSON_output,
            export_YAML_output,
        ])
    ])
    export_section.set_title(0, "💾 Export Config")
    export_section.selected_index = None

    preview_section = w.Accordion(children=[w.VBox([preview_btn, preview_out])])
    preview_section.set_title(0, "🔍 Preview Config")
    preview_section.selected_index = None

    log_section = w.Accordion(children=[w.VBox([show_log_btn, log_output])])
    log_section.set_title(0, "📋 Show Log")
    log_section.selected_index = None

    ui = w.VBox([
        load_config_section,
        main_tabs,
        run_section,
        export_section,
        preview_section,
        log_section,
    ])

    display(ui)
