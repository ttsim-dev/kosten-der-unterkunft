"""Build the measure and household-size controls that sit above the choropleth.

Plotly's own dropdown buttons carry fixed arguments, so two of them cannot
express a selection along two dimensions at once: a household-size button would
have to know which measure is showing, and a measure button which household
size. The controls are therefore two HTML `select` elements that hold the
selected pair themselves and restyle the single measure trace.

Holding one trace rather than one per combination matters for file size: the
boundary collection is serialised once per trace, and it is more than an order of
magnitude larger than one measure's values at every household size together.
"""

import json
from typing import Any

import pandas as pd

from kdu.maps import (
    build_colourscale,
    build_footnotes,
    build_hatch_layers,
    build_hovertemplate,
    build_measure_display,
    describe_household_size,
)
from kdu.measures import MeasureSpec

MEASURE_CONTROL_LABEL = "Kennzahl"
HOUSEHOLD_SIZE_CONTROL_LABEL = "Haushaltsgröße"


def build_control_script(
    *,
    geojson: dict[str, Any],
    frame: pd.DataFrame,
    measures: tuple[MeasureSpec, ...],
    household_sizes: tuple[int, ...],
    initial_measure: MeasureSpec,
    initial_household_size: int,
    vintage: str = "",
) -> str:
    """Return the JavaScript that adds the controls and switches the view.

    Args:
        geojson: Gemeinde feature collection carrying `fid` properties.
        frame: Map frame returned by `kdu.maps.build_map_frame`.
        measures: Measures the controls offer. A single measure omits the
            measure control and leaves only the household-size control.
        household_sizes: Household sizes the controls offer.
        initial_measure: Measure the map opens on.
        initial_household_size: Household size the map opens on.
        vintage: Range of document effective dates shown in the subtitle.

    Returns:
        JavaScript to hand to `plotly.graph_objects.Figure.write_html` as
        `post_script`.
    """
    payload = {
        "measures": [
            _describe_measure(
                geojson=geojson,
                frame=frame,
                spec=spec,
                household_sizes=household_sizes,
                vintage=vintage,
            )
            for spec in measures
        ],
        "householdSizes": [
            {"value": size, "label": describe_household_size(size)}
            for size in household_sizes
        ],
        "initialMeasure": initial_measure.key,
        "initialHouseholdSize": initial_household_size,
        "measureControlLabel": MEASURE_CONTROL_LABEL,
        "householdSizeControlLabel": HOUSEHOLD_SIZE_CONTROL_LABEL,
    }
    return _CONTROL_SCRIPT.replace("__PAYLOAD__", json.dumps(payload, allow_nan=False))


def _describe_measure(
    *,
    geojson: dict[str, Any],
    frame: pd.DataFrame,
    spec: MeasureSpec,
    household_sizes: tuple[int, ...],
    vintage: str,
) -> dict[str, Any]:
    """Assemble one measure's constant properties and its view at every size."""
    sizes = household_sizes if spec.varies_by_household_size else (1,)
    layers = build_hatch_layers(geojson=geojson, frame=frame, spec=spec)
    views = {}
    for size in sizes:
        display = build_measure_display(
            frame=frame,
            spec=spec,
            household_size=size,
            vintage=vintage,
        )
        views[str(size)] = {
            "z": display.measure_values,
            "zmin": display.lower,
            "zmax": display.upper,
            "title": display.title,
            "colorbar": display.colourbar,
        }
    return {
        "key": spec.key,
        "label": spec.label,
        "variesByHouseholdSize": spec.varies_by_household_size,
        "colorscale": build_colourscale(spec),
        "zmid": spec.diverging_midpoint,
        "hovertemplate": build_hovertemplate(spec),
        "layers": layers,
        "annotations": build_footnotes(layers=layers, spec=spec),
        "bySize": views,
    }


_CONTROL_SCRIPT = """
var plot = document.getElementById('{plot_id}');
var payload = __PAYLOAD__;
var selected = {
    measure: payload.initialMeasure,
    householdSize: payload.initialHouseholdSize
};

var bar = document.createElement('div');
bar.style.cssText = 'display:flex;gap:1.75rem;align-items:center;padding:10px 14px;'
    + 'font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#222;';

function addSelect(labelText, options, initialValue, onChange) {
    var wrapper = document.createElement('label');
    wrapper.style.cssText = 'display:flex;gap:0.5rem;align-items:center;';
    wrapper.appendChild(document.createTextNode(labelText));
    var select = document.createElement('select');
    select.style.cssText = 'font:inherit;padding:3px 6px;';
    options.forEach(function (option) {
        var element = document.createElement('option');
        element.value = String(option.value);
        element.textContent = option.label;
        if (String(option.value) === String(initialValue)) {
            element.selected = true;
        }
        select.appendChild(element);
    });
    select.addEventListener('change', function () { onChange(select.value); });
    wrapper.appendChild(select);
    bar.appendChild(wrapper);
    return select;
}

var measureSelect = null;
if (payload.measures.length > 1) {
    measureSelect = addSelect(
        payload.measureControlLabel,
        payload.measures.map(function (measure) {
            return {value: measure.key, label: measure.label};
        }),
        selected.measure,
        function (value) { selected.measure = value; render(); }
    );
}

var householdSizeSelect = addSelect(
    payload.householdSizeControlLabel,
    payload.householdSizes,
    selected.householdSize,
    function (value) { selected.householdSize = Number(value); render(); }
);

plot.parentNode.insertBefore(bar, plot);

function currentMeasure() {
    for (var index = 0; index < payload.measures.length; index += 1) {
        if (payload.measures[index].key === selected.measure) {
            return payload.measures[index];
        }
    }
    return payload.measures[0];
}

function render() {
    var measure = currentMeasure();
    var key = measure.variesByHouseholdSize ? String(selected.householdSize) : '1';
    var view = measure.bySize[key];
    householdSizeSelect.disabled = !measure.variesByHouseholdSize;
    Plotly.restyle(plot, {
        z: [view.z],
        zmin: [view.zmin],
        zmax: [view.zmax],
        zmid: [measure.zmid],
        colorscale: [measure.colorscale],
        colorbar: [view.colorbar],
        hovertemplate: [measure.hovertemplate]
    }, [1]);
    Plotly.relayout(plot, 'title.text', view.title);
    Plotly.relayout(plot, 'map.layers', measure.layers);
    Plotly.relayout(plot, 'annotations', measure.annotations);
}

render();
"""
