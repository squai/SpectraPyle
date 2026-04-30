import os
import spectraPyle
import matplotlib as mpl
from astropy.io import fits
import numpy as np
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path

def plotting(output_filename, width=550, height=550):

    print(f"Plotting {output_filename} stack results")
    
    redshift, units, units_fscale = get_header(name_stack=output_filename)
    
    if units_fscale == 1:
        if units == "erg/s/cm2":
            units = f"Luminosity [{units}]"
        elif units == "arbitrary units":
            units = f"Flux [{units}]"
        else:
            print ('units ', units, ' not understood!')
            units = f"Flux (units not understood!)"
    else:
        units = f"Flux [{units_fscale} {units}]"
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.15, 0.85],
        vertical_spacing=0.05
    )

    # Read stacking results
    #(counts_columns, wavelength_column, flux_columns, error_columns,
    # dispersion_columns, percentile_columns) = ploti.read_fits_and_select_columns(output_filename)
    (counts_columns, wavelength_column, flux_columns, error_columns,
     dispersion_columns, percentile_columns) = read_fits_and_select_columns(output_filename)

    # Wavelength bin midpoints
    wavelength_nanom = wavelength_column['wavelength'] / 10
    bin_width = np.diff(wavelength_nanom).mean()
    spectral_axis_midpoints = wavelength_nanom - (bin_width / 2)

    # Define display order and colors
    display_order = ["All spectra", "Used spectra", "Bad pixels", "Sigma clipped"]
    colors = ['black', 'blue', 'red', 'grey']
    
    # show the count statistics in the top panel:
    for key, color in zip(display_order, colors):
        is_visible = key in ["All spectra", "Used spectra"]  # Show only these by default
        fig.add_trace(go.Scatter(
            x=spectral_axis_midpoints,
            y=counts_columns[key],
            mode='lines',
            name=key,
            visible=True if is_visible else 'legendonly',
            line=dict(color=color, shape='hv'),
            legendgroup=key,  # Individual toggle groups
            showlegend=True,
        ), row=1, col=1)
    
    # show the stacked spectra:
    display_order = [
        "specMean",
        "specMedian",
        "specWeightedMean",
        "specGeometricMean"
    ]

    colors = {
        "specMean": "orange",                 # RGB(255, 165, 0)
        "specMedian": "cyan",                  # RGB(0, 255, 255)
        "specWeightedMean": "purple",          # RGB(128, 0, 128)
        "specGeometricMean": "green"           # RGB(0, 128, 0)
    }

    error_fillcolors = {
        "specMean": "rgba(255, 165, 0, 0.2)",      # transparent orange
        "specMedian": "rgba(0, 255, 255, 0.2)",    # transparent cyan
        "specWeightedMean": "rgba(128, 0, 128, 0.2)",  # transparent purple
        "specGeometricMean": "rgba(0, 128, 0, 0.2)"    # transparent green
    }
    
    y_min = 0.9*np.nanmin((np.nanmin(flux_columns["specMean"]), 
                      np.nanmin(flux_columns["specMedian"])))
    
    y_max = 1.1*np.nanmax((np.nanmax(flux_columns["specMean"]), 
                      np.nanmax(flux_columns["specMedian"])))
    
    # add emission lines:
    main_flux = flux_columns["specMedian"]  
    
    if redshift != 'observed_frame':
        #module_dir = os.path.dirname(spectraPyle.__file__)
        #em_line_table_path = os.path.join(module_dir, "tables", "emission_lines_vacuum_table.csv")
        project_root = Path(spectraPyle.__file__).parent.parent.parent
        em_line_table_path = project_root / "tables" / "emission_lines_vacuum_table.csv"
        add_line_markers(fig, em_line_table_path, spectral_axis_midpoints, main_flux, redshift, row=2, col=1)

        # addabsorption features:
        #abs_feat_table_path = os.path.join(module_dir, "tables", "absorptions_table.csv")
        abs_feat_table_path = project_root / "tables" / "absorptions_table.csv"
        add_absorption_features(fig, abs_feat_table_path, spectral_axis_midpoints, main_flux, redshift, row=2, col=1)

    for key in display_order:
        is_visible = key == "specMedian"
        base_visibility = True if is_visible else "legendonly"
        error_visibility = True if is_visible else "legendonly"

        # Lower error bound (invisible line)
        fig.add_trace(go.Scatter(
            x=spectral_axis_midpoints,
            y=flux_columns[key] - error_columns[f"{key}Error"],
            mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            showlegend=False,
            hoverinfo="skip",
            #visible=error_visibility,
            legendgroup=f"{key}_error"
        ), row=2, col=1)

        # Upper error bound + fill
        fig.add_trace(go.Scatter(
            x=spectral_axis_midpoints,
            y=flux_columns[key] + error_columns[f"{key}Error"],
            mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            fill='tonexty',
            fillcolor=error_fillcolors[key],
            name=f"{key} ± 1σ",
            visible=error_visibility,
            legendgroup=f"{key}_error",
            showlegend=True,
            hoverinfo="skip"
        ), row=2, col=1)
        
        # Lower dispersion bound (invisible line)
        fig.add_trace(go.Scatter(
            x=spectral_axis_midpoints,
            y=flux_columns[key] - dispersion_columns[f"{key}Dispersion"],
            mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            showlegend=False,
            hoverinfo="skip",
            #visible="legendonly",
            legendgroup=f"{key}_dispersion"
        ), row=2, col=1)

        # Upper dispersion bound + fill
        fig.add_trace(go.Scatter(
            x=spectral_axis_midpoints,
            y=flux_columns[key] + dispersion_columns[f"{key}Dispersion"],
            mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            fill='tonexty',
            fillcolor=error_fillcolors[key],
            name=f"{key} ± dispers.",
            visible="legendonly",
            legendgroup=f"{key}_dispersion",
            showlegend=True,
            hoverinfo="skip"
        ), row=2, col=1)
        
        # Main flux line
        fig.add_trace(go.Scatter(
            x=spectral_axis_midpoints,
            y=flux_columns[key],
            mode='lines',
            line=dict(color=colors[key], shape='hv'),
            name=key,
            visible=base_visibility,
            legendgroup=key,
            showlegend=True
        ), row=2, col=1)
        
    
    
    # Layout
    fig.update_layout(
        xaxis2_title="Wavelength (nm)",
        #yaxis_title="#Spectra",
        yaxis2_title=f"{units}",
        xaxis=dict(range=(spectral_axis_midpoints[0], spectral_axis_midpoints[-1])),
        xaxis2=dict(range=(spectral_axis_midpoints[0], spectral_axis_midpoints[-1])),
        #yaxis=dict(fixedrange=False),
        yaxis2=dict(range=(y_min, y_max)),
        #yaxis2=dict(fixedrange=False),
        barmode="overlay",
        template="plotly_white",
        width=width,
        height=height,
        legend=dict(
        orientation="v",
        xanchor="left",
        x=1.02,  # Places the legend to the right of the plot area
        y=1,
        yanchor="top",
        bordercolor="lightgrey",
        borderwidth=1,
        tracegroupgap=5,
        groupclick="toggleitem",
        itemsizing="trace",
        ),
        margin=dict(r=200),  # Make space on the right side of the figure for the legend
        )

    fig.show()
    

    
def read_fits_and_select_columns(fits_filename):
    """
    Read the FITS file and prompt the user to select the spectra columns they want.

    Args:
        fits_filename (str): Path to the FITS file.

    Returns:
        selected_columns (dict): Dictionary containing the selected columns (wavelength and others).
    """
       
    # Open the FITS file
    with fits.open(fits_filename) as hdul:
        # Extract stacking results table and stack array (image)
        stacking_results_hdu = hdul['STACKING_RESULTS']
        #stackArr_hdu = hdul['STACK_ARRAY']

        # Extract the column names from the stacking results table
        column_names = stacking_results_hdu.columns.names
        #print(f"Available columns in 'STACKING_RESULTS': {column_names}")
        
        counts_columns = {'All spectra': stacking_results_hdu.data['initialPixelCount']}
        counts_columns['Used spectra'] = stacking_results_hdu.data['goodPixelCount']
        counts_columns['Bad pixels'] = stacking_results_hdu.data['badPixelCount']
        counts_columns['Sigma clipped'] = stacking_results_hdu.data['sigmaClippedCount']
        
        # Mandatory wavelength column
        wavelength_column = {'wavelength': stacking_results_hdu.data['wavelength']}
        
        flux_columns = {}
        error_columns = {}
        dispersion_columns = {}
        percentile_columns = {}
        
        # Filter out columns that contain "Error" or "Dispersion"
        filtered_columns = [col for col in column_names[5:-4] if "Error" not in col and "Dispersion" not in col]
        for column in filtered_columns:
            flux_columns[column] = stacking_results_hdu.data[column]
            error_columns[column + 'Error'] = stacking_results_hdu.data[column + 'Error']
            dispersion_columns[column + 'Dispersion'] = stacking_results_hdu.data[column + 'Dispersion']
            
        
        filtered_columns = [col for col in column_names[1:5]]
        for column in filtered_columns:
            percentile_columns[column] = stacking_results_hdu.data[column]
        
    return  counts_columns, wavelength_column, flux_columns, error_columns, dispersion_columns, percentile_columns

def get_header(name_stack):
    from astropy.io import fits
    with fits.open(name_stack) as hdu:
        header = hdu[0].header
    return header['REDSHIFT'], header['UNITS'], header['FSCALE']

def add_line_markers(fig, line_table_path, spectral_axis_midpoints, flux, redshift, row=2, col=1):
    z_term = (1 + redshift)
    df_lines = pd.read_csv(line_table_path)

    wave_min, wave_max = spectral_axis_midpoints[0], spectral_axis_midpoints[-1]
    df_active = df_lines[
        (df_lines["show"] == 1) &
        (df_lines["wavelength_AA"] * z_term / 10 >= wave_min) &
        (df_lines["wavelength_AA"] * z_term / 10 <= wave_max)
    ].reset_index(drop=True)

    if len(df_active) == 0:
        return

    flux_min = np.nanmin(flux)
    y_min = 0.85 * flux_min
    flux_interp = np.interp(df_active["wavelength_AA"] * z_term / 10, spectral_axis_midpoints, flux)
    text_offset = 0.05 * np.nanmax(flux_interp)

    def _ion_label(raw):
        for src, tgt in [(r"$\alpha$", "α"), (r"$\beta$", "β"),
                         (r"$\gamma$", "γ"), (r"$\delta$", "δ")]:
            raw = raw.replace(src, tgt)
        return raw

    # Single trace: bottom point (no text) + top point (label) + None separator per line.
    # mode="lines+text" keeps line and label in the same trace → legend toggle hides both.
    x_all, y_all, texts = [], [], []
    for i, (_, row_line) in enumerate(df_active.iterrows()):
        wavelength = row_line["wavelength_AA"] * z_term / 10
        ion_label = _ion_label(row_line["formatted_ion_simple"])
        text_y = flux_interp[i] + text_offset
        x_all.extend([wavelength, wavelength, None])
        y_all.extend([y_min, text_y, None])
        texts.extend(["", ion_label, ""])

    fig.add_trace(go.Scatter(
        x=x_all, y=y_all,
        mode="lines+text",
        text=texts,
        textposition="top center",
        textfont=dict(size=10, color="grey"),
        line=dict(dash="dot", color="grey", width=1),
        name="Emission lines", showlegend=True, visible=True,
        legendgroup="em_lines", hoverinfo="skip",
    ), row=row, col=col)


def add_absorption_features(fig, absorption_table_path, spectral_axis_midpoints, flux, redshift, row=2, col=1):
    z_term = (1 + redshift)
    df_absorp = pd.read_csv(absorption_table_path)

    wave_min, wave_max = spectral_axis_midpoints[0], spectral_axis_midpoints[-1]
    if "Show" in df_absorp.columns:
        df_absorp = df_absorp[df_absorp["Show"] == 1]
    df_active = df_absorp[
        (df_absorp["Centre"] * z_term / 10 >= wave_min) &
        (df_absorp["Centre"] * z_term / 10 <= wave_max)
    ].reset_index(drop=True)

    if len(df_active) == 0:
        return

    flux_min = np.nanmin(flux)
    y_min = 0.85 * flux_min
    flux_interp = np.interp(df_active["Centre"] * z_term / 10, spectral_axis_midpoints, flux)
    text_offset = 0.05 * np.nanmax(flux_interp)

    # Single trace per category: pentagon polygon (rectangle + center-top anchor for the label)
    # + None separator between features. fill="toself" fills each sub-polygon independently.
    # mode="lines+text" keeps fill and label in one trace → legend toggle hides both.
    x_all, y_all, texts = [], [], []
    for i, (_, row_feat) in enumerate(df_active.iterrows()):
        label = row_feat["Index name"]
        text_y = flux_interp[i] + text_offset
        parts = str(row_feat["Line limits"]).replace("–", "-").split("-")
        if len(parts) != 2:
            continue
        s = float(parts[0].strip()) * z_term / 10
        e = float(parts[1].strip()) * z_term / 10
        cx = (s + e) / 2
        # Pentagon: bottom-left → bottom-right → top-right → center-top (label anchor)
        #           → top-left → bottom-left, then None separator
        x_all.extend([s, e, e, cx, s, s, None])
        y_all.extend([y_min, y_min, text_y, text_y, text_y, y_min, None])
        texts.extend(["", "", "", label, "", "", ""])

    if not x_all:
        return

    fig.add_trace(go.Scatter(
        x=x_all, y=y_all,
        mode="lines+text",
        text=texts,
        textposition="top center",
        textfont=dict(size=10),
        fill="toself",
        fillcolor="rgba(173, 216, 230, 0.25)",
        line=dict(color="rgba(100, 149, 237, 0.5)", width=1),
        name="Absorption features", showlegend=True, visible=True,
        legendgroup="abs_feats", hoverinfo="skip",
    ), row=row, col=col)

