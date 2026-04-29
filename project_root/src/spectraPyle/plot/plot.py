import numpy as np
import pandas as pd
from astropy.io import fits
from pathlib import Path
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import spectraPyle


# Ordered list of stacking methods to plot (first found will be default-visible)
FLUX_COLUMN_NAMES = ["specMedian", "specMean", "specGeometricMean", "specWeightedMean"]

COLORS = {
    "specMedian":        "cyan",
    "specMean":          "orange",
    "specWeightedMean":  "purple",
    "specGeometricMean": "green",
}

FILL_COLORS = {
    "specMedian":        "rgba(0, 255, 255, 0.2)",
    "specMean":          "rgba(255, 165, 0, 0.2)",
    "specWeightedMean":  "rgba(128, 0, 128, 0.2)",
    "specGeometricMean": "rgba(0, 128, 0, 0.2)",
}


def _step_xy(x, y):
    """Convert (x, y) to hv-step mode for Scattergl (which lacks line.shape)."""
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


def plotting(output_filename, width=950, height=650):
    """Plot a SpectraPyle output FITS file.

    Displays inline when called from a Jupyter notebook cell.
    Returns the Plotly figure for further customisation.
    """
    print(f"Plotting {output_filename}")

    redshift, units, units_fscale = get_header(name_stack=output_filename)

    if units_fscale == 1:
        if units == "erg/s/cm2":
            y_label = f"Luminosity [{units}]"
        elif units == "arbitrary units":
            y_label = f"Flux [{units}]"
        else:
            y_label = f"Flux [{units}]"
    else:
        y_label = f"Flux [{units_fscale} {units}]"

    (counts_columns, wavelength_column, flux_columns,
     error_columns, dispersion_columns, _) = read_fits_and_select_columns(output_filename)

    # Wavelength column already contains bin midpoints (Å → nm)
    wav_nm = np.asarray(wavelength_column["wavelength"], dtype=float) / 10.0

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.15, 0.85],
        vertical_spacing=0.05,
    )

    # ---- Top panel: pixel counts ----
    count_keys   = ["All spectra", "Used spectra", "Bad pixels", "Sigma clipped"]
    count_colors = ["black",       "blue",          "red",        "grey"]
    for key, color in zip(count_keys, count_colors):
        visible = True if key in ("All spectra", "Used spectra") else "legendonly"
        cx, cy = _step_xy(wav_nm, np.asarray(counts_columns[key], dtype=float))
        fig.add_trace(go.Scattergl(
            x=cx, y=cy,
            mode="lines",
            name=key,
            visible=visible,
            line=dict(color=color),
            legendgroup=key,
            showlegend=True,
        ), row=1, col=1)

    # ---- Spectral line markers (added before spectra so they sit behind) ----
    if redshift != "observed_frame":
        project_root = Path(spectraPyle.__file__).parent.parent.parent
        em_path  = project_root / "tables" / "emission_lines_vacuum_table.csv"
        abs_path = project_root / "tables" / "absorptions_table.csv"

        ref_key  = next((k for k in FLUX_COLUMN_NAMES if k in flux_columns), None)
        if ref_key is not None:
            ref_flux = flux_columns[ref_key]
            if em_path.exists():
                add_line_markers(fig, em_path, wav_nm, ref_flux, redshift, row=2, col=1)
            if abs_path.exists():
                add_absorption_features(fig, abs_path, wav_nm, ref_flux, redshift, row=2, col=1)

    # ---- y-range: 2nd–98th percentile of available flux values ----
    all_finite = np.concatenate([
        v[np.isfinite(v)] for v in flux_columns.values()
    ]) if flux_columns else np.array([0.0, 1.0])

    if len(all_finite):
        y_min = 0.9 * float(np.nanpercentile(all_finite, 2))
        y_max = 1.1 * float(np.nanpercentile(all_finite, 98))
    else:
        y_min, y_max = 0.0, 1.0
    if y_min == y_max:
        y_min -= 0.1; y_max += 0.1

    # ---- Bottom panel: stacked spectra ----
    first_method = next((k for k in FLUX_COLUMN_NAMES if k in flux_columns), None)

    for key in FLUX_COLUMN_NAMES:
        if key not in flux_columns:
            continue

        is_default = (key == first_method)
        base_vis   = True if is_default else "legendonly"

        flux  = np.asarray(flux_columns[key], dtype=float)
        fx, fy = _step_xy(wav_nm, flux)

        err_key = key + "Error"
        dis_key = key + "Dispersion"

        # Error band
        if err_key in error_columns:
            err = np.asarray(error_columns[err_key], dtype=float)
            _, fy_lo = _step_xy(wav_nm, flux - err)
            _, fy_hi = _step_xy(wav_nm, flux + err)
            # Lower bound (invisible baseline for fill)
            fig.add_trace(go.Scattergl(
                x=fx, y=fy_lo,
                mode="lines", line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, hoverinfo="skip",
                legendgroup=f"{key}_error", visible=base_vis,
            ), row=2, col=1)
            # Upper bound + fill back to lower
            fig.add_trace(go.Scattergl(
                x=fx, y=fy_hi,
                mode="lines", line=dict(color="rgba(0,0,0,0)"),
                fill="tonexty", fillcolor=FILL_COLORS[key],
                name=f"{key} ±1σ",
                visible=base_vis,
                legendgroup=f"{key}_error", showlegend=True, hoverinfo="skip",
            ), row=2, col=1)

        # Dispersion band
        if dis_key in dispersion_columns:
            dis = np.asarray(dispersion_columns[dis_key], dtype=float)
            _, fy_lo = _step_xy(wav_nm, flux - dis)
            _, fy_hi = _step_xy(wav_nm, flux + dis)
            fig.add_trace(go.Scattergl(
                x=fx, y=fy_lo,
                mode="lines", line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, hoverinfo="skip",
                legendgroup=f"{key}_dispersion", visible="legendonly",
            ), row=2, col=1)
            fig.add_trace(go.Scattergl(
                x=fx, y=fy_hi,
                mode="lines", line=dict(color="rgba(0,0,0,0)"),
                fill="tonexty", fillcolor=FILL_COLORS[key],
                name=f"{key} ±dispers.",
                visible="legendonly",
                legendgroup=f"{key}_dispersion", showlegend=True, hoverinfo="skip",
            ), row=2, col=1)

        # Main flux line (on top of bands)
        fig.add_trace(go.Scattergl(
            x=fx, y=fy,
            mode="lines", line=dict(color=COLORS[key]),
            name=key,
            visible=base_vis,
            legendgroup=key, showlegend=True,
        ), row=2, col=1)

    # ---- Layout ----
    x_range = [float(wav_nm[0]), float(wav_nm[-1])]
    fig.update_layout(
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
            tracegroupgap=5,
            groupclick="toggleitem",
            itemsizing="trace",
        ),
        margin=dict(r=200),
    )

    _display_fig(fig)
    return fig


def read_fits_and_select_columns(fits_filename):
    """Read a SpectraPyle output FITS and return column dicts."""
    with fits.open(fits_filename) as hdul:
        hdu  = hdul["STACKING_RESULTS"]
        data = hdu.data
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
        for c in percentile_column_names
        if c in col_names
    }

    flux_columns        = {}
    error_columns       = {}
    dispersion_columns  = {}

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


def add_line_markers(fig, line_table_path, wav_nm, flux, redshift, row=2, col=1):
    z_term = 1.0 + redshift

    df_lines = pd.read_csv(line_table_path)

    wave_min, wave_max = wav_nm[0], wav_nm[-1]
    df_vis = df_lines[
        (df_lines["wavelength_AA"] * z_term / 10 >= wave_min) &
        (df_lines["wavelength_AA"] * z_term / 10 <= wave_max)
    ].reset_index(drop=True)

    if df_vis.empty:
        return

    flux_interp  = np.interp(df_vis["wavelength_AA"] * z_term / 10, wav_nm, flux)
    text_offset  = 0.05 * np.nanmax(np.abs(flux_interp))
    y_base       = 0.85 * np.nanmin(flux)

    for idx, row_line in df_vis.iterrows():
        wavelength = row_line["wavelength_AA"] * z_term / 10
        ion_label  = (row_line["formatted_ion_simple"]
                      .replace(r"$\alpha$", "α")
                      .replace(r"$\beta$",  "β")
                      .replace(r"$\gamma$", "γ")
                      .replace(r"$\delta$", "δ"))
        visible_default = row_line["show"] == 1
        vis = True if visible_default else "legendonly"

        flux_y = float(flux_interp[idx])
        text_y = flux_y + text_offset
        trace_name = f"{ion_label}-{int(round(row_line['wavelength_AA'], 0))}"

        fig.add_trace(go.Scatter(
            x=[wavelength, wavelength],
            y=[y_base, text_y],
            mode="lines",
            line=dict(dash="dot", color="grey", width=1),
            name=trace_name,
            showlegend=True,
            visible=vis,
            legendgroup=trace_name,
        ), row=row, col=col)

        fig.add_trace(go.Scatter(
            x=[wavelength],
            y=[text_y],
            mode="text",
            text=[ion_label],
            textposition="top center",
            textfont=dict(size=10),
            name=trace_name,
            showlegend=False,
            visible=vis,
            legendgroup=trace_name,
            hoverinfo="skip",
        ), row=row, col=col)


def add_absorption_features(fig, absorption_table_path, wav_nm, flux, redshift, row=2, col=1):
    z_term = 1.0 + redshift

    df_abs = pd.read_csv(absorption_table_path)

    wave_min, wave_max = wav_nm[0], wav_nm[-1]
    df_vis = df_abs[
        (df_abs["Centre"] * z_term / 10 >= wave_min) &
        (df_abs["Centre"] * z_term / 10 <= wave_max)
    ].reset_index(drop=True)

    if df_vis.empty:
        return

    flux_interp = np.interp(df_vis["Centre"] * z_term / 10, wav_nm, flux)
    text_offset = 0.05 * np.nanmax(np.abs(flux_interp))
    y_base      = 0.85 * np.nanmin(flux)

    for idx, row_feat in df_vis.iterrows():
        centre = row_feat["Centre"] * z_term / 10
        label  = row_feat["Index name"]
        visible_default = row_feat.get("Show", 1) == 1
        vis = True if visible_default else "legendonly"

        flux_y = float(flux_interp[idx])
        text_y = flux_y + text_offset
        trace_name = f"{label}-{int(round(row_feat['Centre'], 0))}"

        line_limits = str(row_feat["Line limits"]).replace("–", "-").split("-")
        if len(line_limits) != 2:
            continue
        try:
            x0 = float(line_limits[0].strip()) * z_term / 10
            x1 = float(line_limits[1].strip()) * z_term / 10
        except ValueError:
            continue

        fig.add_trace(go.Scatter(
            x=[x0, x1, x1, x0, x0],
            y=[y_base, y_base, text_y, text_y, y_base],
            fill="toself",
            fillcolor="LightBlue",
            line=dict(color="LightBlue"),
            opacity=0.3,
            mode="lines",
            name=trace_name,
            showlegend=True,
            visible=vis,
            legendgroup=trace_name,
            hoverinfo="skip",
        ), row=row, col=col)

        fig.add_trace(go.Scatter(
            x=[(x0 + x1) / 2],
            y=[text_y],
            mode="text",
            text=[label],
            textposition="top center",
            textfont=dict(size=10),
            name=trace_name,
            showlegend=False,
            visible=vis,
            legendgroup=trace_name,
            hoverinfo="skip",
        ), row=row, col=col)
