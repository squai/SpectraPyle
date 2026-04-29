import numpy as np
import pandas as pd
from astropy.io import fits
from pathlib import Path
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import spectraPyle


# Ordered list of stacking methods (first found is shown by default)
FLUX_COLUMN_NAMES = ["specMedian", "specMean", "specGeometricMean", "specWeightedMean"]

COLORS = {
    "specMedian":        "rgba(0, 180, 220, 1)",
    "specMean":          "rgba(230, 130, 0, 1)",
    "specWeightedMean":  "rgba(140, 0, 180, 1)",
    "specGeometricMean": "rgba(0, 160, 60, 1)",
}

FILL_COLORS = {
    "specMedian":        "rgba(0, 180, 220, 0.18)",
    "specMean":          "rgba(230, 130, 0, 0.18)",
    "specWeightedMean":  "rgba(140, 0, 180, 0.18)",
    "specGeometricMean": "rgba(0, 160, 60, 0.18)",
}

_GREEK = {
    r"$\alpha$": "α", r"$\beta$": "β",
    r"$\gamma$": "γ", r"$\delta$": "δ",
}


def _step_xy(x, y):
    """Convert (x, y) arrays to hv-step mode for Scattergl (no native line.shape)."""
    n = len(x)
    if n <= 1:
        return np.asarray(x, float), np.asarray(y, float)
    x_out = np.empty(2 * n - 1, float)
    y_out = np.empty(2 * n - 1, float)
    x_out[0::2] = x
    x_out[1::2] = x[1:]
    y_out[0::2] = y
    y_out[1::2] = y[:-1]
    return x_out, y_out


def _display_fig(fig):
    """Show figure inline in Jupyter; fall back to fig.show() elsewhere."""
    try:
        from IPython.display import display
        display(fig)
    except Exception:
        fig.show()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def plotting(output_filename, width=950, height=650):
    """Plot a SpectraPyle output FITS file.

    Displays inline when called from a Jupyter notebook cell (or inside an
    ipywidgets Output widget). Returns the Plotly figure for customisation.
    """
    print(f"Plotting {output_filename}")

    redshift, units, units_fscale = get_header(name_stack=output_filename)

    if units_fscale == 1:
        y_label = (f"Luminosity [{units}]" if units == "erg/s/cm2"
                   else f"Flux [{units}]")
    else:
        y_label = f"Flux [{units_fscale} {units}]"

    (counts_columns, wavelength_column, flux_columns,
     error_columns, dispersion_columns, _) = read_fits_and_select_columns(output_filename)

    # Wavelength: bin midpoints stored in Å → convert to nm
    wav_nm = np.asarray(wavelength_column["wavelength"], dtype=float) / 10.0

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.15, 0.85],
        vertical_spacing=0.05,
    )

    # ---- Top panel: pixel counts (4 traces) ----
    count_keys   = ["All spectra", "Used spectra", "Bad pixels", "Sigma clipped"]
    count_colors = ["black", "steelblue", "crimson", "grey"]
    for key, color in zip(count_keys, count_colors):
        visible = True if key in ("All spectra", "Used spectra") else "legendonly"
        cx, cy = _step_xy(wav_nm, np.asarray(counts_columns[key], dtype=float))
        fig.add_trace(go.Scattergl(
            x=cx, y=cy,
            mode="lines",
            name=key,
            visible=visible,
            line=dict(color=color, width=1),
            legendgroup=key,
            showlegend=True,
            hovertemplate="λ = %{x:.2f} nm<br>N = %{y:.0f}<extra>" + key + "</extra>",
        ), row=1, col=1)

    # ---- y-range for spectra panel ----
    all_finite = np.concatenate([
        v[np.isfinite(v)] for v in flux_columns.values()
    ]) if flux_columns else np.array([0.0, 1.0])

    if len(all_finite):
        y_min = float(np.nanpercentile(all_finite, 1))
        y_max = float(np.nanpercentile(all_finite, 99))
    else:
        y_min, y_max = 0.0, 1.0

    span = y_max - y_min if y_max != y_min else 1.0
    y_min -= 0.05 * span
    # extra headroom for emission-line labels
    y_max += 0.20 * span

    # ---- Spectral line markers — consolidated traces ----
    if redshift != "observed_frame":
        project_root = Path(spectraPyle.__file__).parent.parent.parent
        em_path  = project_root / "tables" / "emission_lines_vacuum_table.csv"
        abs_path = project_root / "tables" / "absorptions_table.csv"

        ref_key = next((k for k in FLUX_COLUMN_NAMES if k in flux_columns), None)
        if ref_key is not None:
            ref_flux = flux_columns[ref_key]
            try:
                if em_path.exists():
                    add_line_markers(fig, em_path, wav_nm, ref_flux, redshift,
                                     y_min=y_min, row=2, col=1)
            except Exception as e:
                print(f"Warning: emission line markers skipped — {e}")
            try:
                if abs_path.exists():
                    add_absorption_features(fig, abs_path, wav_nm, ref_flux, redshift,
                                            y_min=y_min, row=2, col=1)
            except Exception as e:
                print(f"Warning: absorption feature markers skipped — {e}")

    # ---- Bottom panel: stacked spectra (≤ 20 traces for 4 methods) ----
    first_method = next((k for k in FLUX_COLUMN_NAMES if k in flux_columns), None)

    for key in FLUX_COLUMN_NAMES:
        if key not in flux_columns:
            continue

        is_default = (key == first_method)
        base_vis   = True if is_default else "legendonly"
        flux       = np.asarray(flux_columns[key], dtype=float)
        fx, fy     = _step_xy(wav_nm, flux)

        hover = "λ = %{x:.2f} nm<br>Flux = %{y:.4g}<extra>" + key + "</extra>"

        err_key = key + "Error"
        dis_key = key + "Dispersion"

        if err_key in error_columns:
            err = np.asarray(error_columns[err_key], dtype=float)
            _, fy_lo = _step_xy(wav_nm, flux - err)
            _, fy_hi = _step_xy(wav_nm, flux + err)
            fig.add_trace(go.Scattergl(
                x=fx, y=fy_lo, mode="lines",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, hoverinfo="skip",
                legendgroup=f"{key}_error", visible=base_vis,
            ), row=2, col=1)
            fig.add_trace(go.Scattergl(
                x=fx, y=fy_hi, mode="lines",
                line=dict(color="rgba(0,0,0,0)"),
                fill="tonexty", fillcolor=FILL_COLORS[key],
                name=f"{key} ±1σ", visible=base_vis,
                legendgroup=f"{key}_error", showlegend=True, hoverinfo="skip",
            ), row=2, col=1)

        if dis_key in dispersion_columns:
            dis = np.asarray(dispersion_columns[dis_key], dtype=float)
            _, fy_lo = _step_xy(wav_nm, flux - dis)
            _, fy_hi = _step_xy(wav_nm, flux + dis)
            fig.add_trace(go.Scattergl(
                x=fx, y=fy_lo, mode="lines",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, hoverinfo="skip",
                legendgroup=f"{key}_dispersion", visible="legendonly",
            ), row=2, col=1)
            fig.add_trace(go.Scattergl(
                x=fx, y=fy_hi, mode="lines",
                line=dict(color="rgba(0,0,0,0)"),
                fill="tonexty", fillcolor=FILL_COLORS[key],
                name=f"{key} ±dispers.", visible="legendonly",
                legendgroup=f"{key}_dispersion", showlegend=True, hoverinfo="skip",
            ), row=2, col=1)

        fig.add_trace(go.Scattergl(
            x=fx, y=fy, mode="lines",
            line=dict(color=COLORS[key], width=1.5),
            name=key, visible=base_vis,
            legendgroup=key, showlegend=True,
            hovertemplate=hover,
        ), row=2, col=1)

    # ---- Layout ----
    x_range = [float(wav_nm[0]), float(wav_nm[-1])]
    fig.update_layout(
        uirevision="constant",          # preserves zoom/pan on trace toggles
        xaxis2_title="Wavelength (nm)",
        yaxis2_title=y_label,
        xaxis=dict(range=x_range),
        xaxis2=dict(range=x_range),
        yaxis2=dict(range=[y_min, y_max]),
        template="plotly_white",
        width=width,
        height=height,
        legend=dict(
            orientation="v",
            xanchor="left", x=1.02,
            yanchor="top",  y=1,
            bordercolor="lightgrey", borderwidth=1,
            tracegroupgap=4,
            groupclick="togglegroup",   # one click toggles the whole group
            itemsizing="constant",
        ),
        margin=dict(r=200),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )

    _display_fig(fig)
    return fig


# ---------------------------------------------------------------------------
# FITS reading
# ---------------------------------------------------------------------------

def read_fits_and_select_columns(fits_filename):
    """Read a SpectraPyle output FITS and return column dicts."""
    with fits.open(fits_filename) as hdul:
        hdu      = hdul["STACKING_RESULTS"]
        data     = hdu.data
        col_names = set(hdu.columns.names)

    counts_columns = {
        "All spectra":   np.asarray(data["initialPixelCount"], dtype=float),
        "Used spectra":  np.asarray(data["goodPixelCount"],    dtype=float),
        "Bad pixels":    np.asarray(data["badPixelCount"],     dtype=float),
        "Sigma clipped": np.asarray(data["sigmaClippedCount"], dtype=float),
    }

    wavelength_column = {"wavelength": np.asarray(data["wavelength"], dtype=float)}

    percentile_column_names = ["spec16th", "spec84th", "spec98th", "spec99th"]
    percentile_columns = {
        c: np.asarray(data[c], dtype=float)
        for c in percentile_column_names if c in col_names
    }

    flux_columns       = {}
    error_columns      = {}
    dispersion_columns = {}

    for col in FLUX_COLUMN_NAMES:
        if col not in col_names:
            continue
        arr = np.asarray(data[col], dtype=float)
        if np.all(~np.isfinite(arr)):
            continue
        flux_columns[col] = arr
        err_key = col + "Error"
        dis_key = col + "Dispersion"
        if err_key in col_names:
            error_columns[err_key] = np.asarray(data[err_key], dtype=float)
        if dis_key in col_names:
            dispersion_columns[dis_key] = np.asarray(data[dis_key], dtype=float)

    return (counts_columns, wavelength_column,
            flux_columns, error_columns, dispersion_columns,
            percentile_columns)


def get_header(name_stack):
    with fits.open(name_stack) as hdu:
        header = hdu[0].header
    return header["REDSHIFT"], header["UNITS"], header["FSCALE"]


# ---------------------------------------------------------------------------
# Spectral line markers — CONSOLIDATED: 2 traces per visibility group
# ---------------------------------------------------------------------------

def _greek(label):
    for k, v in _GREEK.items():
        label = label.replace(k, v)
    return label


def add_line_markers(fig, line_table_path, wav_nm, flux, redshift,
                     y_min=None, row=2, col=1):
    """
    Add emission line markers as two consolidated trace groups (shown / hidden).
    Each group uses a single NaN-separated Scatter for lines and a single
    Scatter(mode='text') for labels — far fewer DOM elements than one trace
    per line, which is critical for smooth rendering with many pixels.
    """
    z_term = 1.0 + redshift
    df_lines = pd.read_csv(line_table_path)

    wave_min, wave_max = wav_nm[0], wav_nm[-1]
    df_in = df_lines[
        (df_lines["wavelength_AA"] * z_term / 10 >= wave_min) &
        (df_lines["wavelength_AA"] * z_term / 10 <= wave_max)
    ].reset_index(drop=True)

    if df_in.empty:
        return

    wavs        = df_in["wavelength_AA"].values * z_term / 10
    flux_at     = np.interp(wavs, wav_nm, flux)
    text_offset = 0.05 * np.nanmax(np.abs(flux_at))
    y_base      = y_min if y_min is not None else 0.85 * np.nanmin(flux)
    text_ys     = flux_at + text_offset
    labels      = [_greek(r) for r in df_in["formatted_ion_simple"].values]
    show_flags  = df_in["show"].values == 1

    for is_shown in (True, False):
        mask = show_flags if is_shown else ~show_flags
        if not np.any(mask):
            continue

        grp_name = "Emission lines" if is_shown else "Emission lines (more)"
        vis      = True if is_shown else "legendonly"
        color    = "rgba(120,120,120,0.7)" if is_shown else "rgba(180,180,180,0.5)"

        sub_wavs   = wavs[mask]
        sub_text_y = text_ys[mask]
        sub_labels = [labels[i] for i, m in enumerate(mask) if m]

        # Vertical line segments — NaN-separated, ONE trace
        x_segs, y_segs = [], []
        hover_segs = []
        for w, ty, lbl in zip(sub_wavs, sub_text_y, sub_labels):
            x_segs += [w, w, None]
            y_segs += [y_base, ty, None]
            hover_segs += [lbl, lbl, None]

        fig.add_trace(go.Scatter(
            x=x_segs, y=y_segs,
            mode="lines",
            line=dict(dash="dot", color=color, width=1),
            name=grp_name,
            visible=vis,
            legendgroup=grp_name,
            showlegend=True,
            hoverinfo="skip",
        ), row=row, col=col)

        # Labels — ONE text trace
        fig.add_trace(go.Scatter(
            x=list(sub_wavs),
            y=list(sub_text_y),
            mode="text",
            text=sub_labels,
            textposition="top center",
            textfont=dict(size=9, color=color),
            name=grp_name,
            visible=vis,
            legendgroup=grp_name,
            showlegend=False,
            hovertemplate=[
                f"<b>{lbl}</b><br>λ = {w:.2f} nm<extra></extra>"
                for lbl, w in zip(sub_labels, sub_wavs)
            ],
        ), row=row, col=col)


def add_absorption_features(fig, absorption_table_path, wav_nm, flux, redshift,
                             y_min=None, row=2, col=1):
    """
    Add absorption feature bands as two consolidated trace groups (shown / hidden).
    Each group uses a single NaN-separated filled Scatter for rectangles and a
    single Scatter(mode='text') for labels.
    """
    z_term = 1.0 + redshift
    df_abs = pd.read_csv(absorption_table_path)

    wave_min, wave_max = wav_nm[0], wav_nm[-1]
    df_in = df_abs[
        (df_abs["Centre"] * z_term / 10 >= wave_min) &
        (df_abs["Centre"] * z_term / 10 <= wave_max)
    ].reset_index(drop=True)

    if df_in.empty:
        return

    centres     = df_in["Centre"].values * z_term / 10
    flux_at     = np.interp(centres, wav_nm, flux)
    text_offset = 0.05 * np.nanmax(np.abs(flux_at))
    y_base      = y_min if y_min is not None else 0.85 * np.nanmin(flux)
    text_ys     = flux_at + text_offset
    labels      = df_in["Index name"].values
    show_flags  = df_in.get("Show", pd.Series(np.ones(len(df_in)))).values == 1

    # Parse x-limits once
    x0s, x1s, valid = [], [], []
    for _, row_feat in df_in.iterrows():
        lims = str(row_feat["Line limits"]).replace("–", "-").split("-")
        try:
            x0 = float(lims[0].strip()) * z_term / 10
            x1 = float(lims[1].strip()) * z_term / 10
            x0s.append(x0); x1s.append(x1); valid.append(True)
        except (ValueError, IndexError):
            x0s.append(None); x1s.append(None); valid.append(False)

    for is_shown in (True, False):
        mask = [(show_flags[i] == is_shown) and valid[i]
                for i in range(len(show_flags))]
        if not any(mask):
            continue

        grp_name  = "Absorption features" if is_shown else "Absorption features (more)"
        vis       = True if is_shown else "legendonly"
        fillcolor = "rgba(173,216,230,0.25)"
        linecolor = "rgba(100,149,237,0.4)"

        x_rects, y_rects = [], []
        x_lbl, y_lbl, lbl_list = [], [], []

        for i, m in enumerate(mask):
            if not m:
                continue
            x0, x1 = x0s[i], x1s[i]
            ty = text_ys[i]
            x_rects += [x0, x1, x1, x0, x0, None]
            y_rects += [y_base, y_base, ty, ty, y_base, None]
            x_lbl.append((x0 + x1) / 2)
            y_lbl.append(ty)
            lbl_list.append(labels[i])

        fig.add_trace(go.Scatter(
            x=x_rects, y=y_rects,
            fill="toself", fillcolor=fillcolor,
            line=dict(color=linecolor, width=0.5),
            mode="lines",
            name=grp_name,
            visible=vis,
            legendgroup=grp_name,
            showlegend=True,
            hoverinfo="skip",
        ), row=row, col=col)

        fig.add_trace(go.Scatter(
            x=x_lbl, y=y_lbl,
            mode="text",
            text=lbl_list,
            textposition="top center",
            textfont=dict(size=9, color="steelblue"),
            name=grp_name,
            visible=vis,
            legendgroup=grp_name,
            showlegend=False,
            hovertemplate=[
                f"<b>{lbl}</b><br>λ = {x:.2f} nm<extra></extra>"
                for lbl, x in zip(lbl_list, x_lbl)
            ],
        ), row=row, col=col)
