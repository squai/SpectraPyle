import os
from pathlib import Path
import numpy as np
import pandas as pd
from astropy.io import fits

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dash import Dash, dcc, html, Input, Output

# ----------------------------
# DATA LOADING (unchanged core)
# ----------------------------

def read_fits_and_select_columns(fits_filename):
    with fits.open(fits_filename) as hdul:
        stacking_results_hdu = hdul['STACKING_RESULTS']
        column_names = stacking_results_hdu.columns.names

        counts_columns = {
            'All spectra': stacking_results_hdu.data['initialPixelCount'],
            'Used spectra': stacking_results_hdu.data['goodPixelCount'],
            'Bad pixels': stacking_results_hdu.data['badPixelCount'],
            'Sigma clipped': stacking_results_hdu.data['sigmaClippedCount']
        }

        wavelength_column = {'wavelength': stacking_results_hdu.data['wavelength']}

        flux_columns, error_columns, dispersion_columns = {}, {}, {}

        filtered_columns = [col for col in column_names[5:-4]
                            if "Error" not in col and "Dispersion" not in col]

        for column in filtered_columns:
            flux_columns[column] = stacking_results_hdu.data[column]
            error_columns[column + 'Error'] = stacking_results_hdu.data[column + 'Error']
            dispersion_columns[column + 'Dispersion'] = stacking_results_hdu.data[column + 'Dispersion']

    return counts_columns, wavelength_column, flux_columns, error_columns, dispersion_columns


def get_header(name_stack):
    with fits.open(name_stack) as hdu:
        header = hdu[0].header
    return header['REDSHIFT'], header['UNITS'], header['FSCALE']


# ----------------------------
# FIGURE BUILDER
# ----------------------------

def build_figure(data, selected_spec="specMedian", show_error=True, show_dispersion=False):
    counts_columns, wavelength_column, flux_columns, error_columns, dispersion_columns, units = data

    wavelength_nanom = wavelength_column['wavelength'] / 10
    bin_width = np.diff(wavelength_nanom).mean()
    x = wavelength_nanom - (bin_width / 2)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.25, 0.75],
        vertical_spacing=0.03
    )

    # ---- TOP PANEL ----
    for key, color in zip(
        ["All spectra", "Used spectra", "Bad pixels", "Sigma clipped"],
        ['black', 'blue', 'red', 'grey']
    ):
        fig.add_trace(go.Scatter(
            x=x,
            y=counts_columns[key],
            mode='lines',
            name=key,
            line=dict(color=color),
        ), row=1, col=1)

    # ---- BOTTOM PANEL ----
    y = flux_columns[selected_spec]

    # error band
    if show_error:
        fig.add_trace(go.Scatter(
            x=x,
            y=y - error_columns[selected_spec + "Error"],
            mode='lines',
            line=dict(width=0),
            showlegend=False
        ), row=2, col=1)

        fig.add_trace(go.Scatter(
            x=x,
            y=y + error_columns[selected_spec + "Error"],
            fill='tonexty',
            mode='lines',
            name="±1σ",
            opacity=0.3
        ), row=2, col=1)

    # dispersion band
    if show_dispersion:
        fig.add_trace(go.Scatter(
            x=x,
            y=y - dispersion_columns[selected_spec + "Dispersion"],
            mode='lines',
            line=dict(width=0),
            showlegend=False
        ), row=2, col=1)

        fig.add_trace(go.Scatter(
            x=x,
            y=y + dispersion_columns[selected_spec + "Dispersion"],
            fill='tonexty',
            mode='lines',
            name="Dispersion",
            opacity=0.2
        ), row=2, col=1)

    # main line
    fig.add_trace(go.Scatter(
        x=x,
        y=y,
        mode='lines',
        name=selected_spec,
        line=dict(width=2)
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_white",
        height=800,
        margin=dict(l=50, r=50, t=40, b=40),
        legend=dict(orientation="h"),
    )

    fig.update_xaxes(title="Wavelength (nm)", row=2, col=1)
    fig.update_yaxes(title=units, row=2, col=1)

    return fig


# ----------------------------
# DASH APP
# ----------------------------

def run_dashboard(fits_file):

    redshift, units, units_fscale = get_header(fits_file)

    counts_columns, wavelength_column, flux_columns, error_columns, dispersion_columns = \
        read_fits_and_select_columns(fits_file)

    if units_fscale != 1:
        units = f"{units_fscale} {units}"

    data = (counts_columns, wavelength_column, flux_columns,
            error_columns, dispersion_columns, units)

    app = Dash(__name__)

    app.layout = html.Div([
        html.H2("Spectra Dashboard"),

        html.Div([
            html.Label("Spectrum:"),
            dcc.Dropdown(
                options=[{"label": k, "value": k} for k in flux_columns.keys()],
                value="specMedian",
                id="spec-dropdown"
            ),

            dcc.Checklist(
                options=[
                    {"label": "Show Error", "value": "error"},
                    {"label": "Show Dispersion", "value": "disp"}
                ],
                value=["error"],
                id="toggle-options"
            )
        ], style={"width": "30%", "display": "inline-block"}),

        dcc.Graph(id="main-graph")
    ])

    @app.callback(
        Output("main-graph", "figure"),
        Input("spec-dropdown", "value"),
        Input("toggle-options", "value")
    )
    def update_plot(spec, toggles):
        return build_figure(
            data,
            selected_spec=spec,
            show_error="error" in toggles,
            show_dispersion="disp" in toggles
        )

    app.run(debug=True)


# ----------------------------
# ENTRY POINT
# ----------------------------

if __name__ == "__main__":
    run_dashboard("your_file.fits")