"""Build the P1.1 neighbour graph and every §13.4 border-jump table.

The task starts by auditing the committed, simplified boundary set against the
unsimplified source (A4). Grid snapping is a topological operation, so a
simplified geometry can fabricate and destroy adjacency at exactly the scale a
border-jump analysis measures. The audit is written to `bld/` as a table, and
the graph is always built on the unsimplified geometry.

**Nothing this task writes is a regression-discontinuity estimate.** Every
number is a description of how far the maximum recognisable Bruttokaltmiete
steps between two directly adjacent Gemeinden.

The unsimplified boundaries live at `bld/gemeinden_raw.geojson`, which
`pixi run prepare-gemeinden` downloads. It is gitignored, so a fresh clone must
run that command once before this task can build.
"""

import json
from pathlib import Path
from typing import Annotated, Any, cast

import numpy as np
import pandas as pd
from pytask import Product

from kdu.analysis.border_jumps import (
    GeometryFitness,
    assess_geometry_fitness,
    border_jump_table,
    comparison_group,
    contact_pairs,
    describe_pairs,
    drop_geometry_artefacts,
    gemeinde_ags,
    jump_distribution,
    neighbour_jump_flags,
    neighbour_pairs,
    polygon_metrics,
    project_laea,
    top_jumps,
)
from kdu.config import BLD, DATA_CATALOG, TABLES
from kdu.final.manifest import register_result

_MODULE = "P1.1"
_DATASET = "border_jumps.parquet"
_SCRIPT = "src/kdu/analysis/task_border_jumps.py"

# The one caveat every §13 output carries: an administrative discontinuity is
# never a regression discontinuity, and nothing here identifies an effect.
_RD_LIMITATION = (
    "Descriptive only: a jump documents an administrative discontinuity and is "
    "not a regression-discontinuity estimate of any effect of the border."
)

_GEMEINDEN_GEOJSON = cast("Path", DATA_CATALOG["gemeinden_geojson"])
_MUNICIPALITY_CROSSWALK = cast("Path", DATA_CATALOG["municipality_crosswalk"])
_ANALYSIS_SAMPLE_MAIN = cast("Path", DATA_CATALOG["analysis_sample_main"])

# The unsimplified OpenDataSoft export, fetched by `pixi run prepare-gemeinden`.
RAW_GEOJSON = cast("Path", DATA_CATALOG["gemeinden_raw_geojson"])
PROXY_ERROR_GEMEINDE_HOUSEHOLD = BLD / "proxy_error_gemeinde_household.parquet"
ZENSUS_RENTS_GEMEINDEN = BLD / "zensus_rents_gemeinden.parquet"

NEIGHBOUR_PAIRS = cast("Path", DATA_CATALOG["neighbour_pairs"])
BORDER_JUMPS = cast("Path", DATA_CATALOG["border_jumps"])
NEIGHBOUR_JUMP_FLAGS = cast("Path", DATA_CATALOG["neighbour_jump_flags"])
DETAIL_GEOMETRY = BLD / "border_jump_detail_geometry.parquet"

GEOMETRY_FITNESS_TABLE = TABLES / "border_jump_geometry_fitness.csv"
DISTRIBUTION_TABLE = TABLES / "border_jump_distribution.csv"
BORDER_TYPE_TABLE = TABLES / "border_jump_by_border_type.csv"
MIETENSTUFE_TABLE = TABLES / "border_jump_by_mietenstufe.csv"
TOP_TABLE = TABLES / "border_jump_top20.csv"
WITHOUT_ARTEFACTS_TABLE = TABLES / "border_jump_excluding_artefacts.csv"
COMPARISON_GROUP_TABLE = TABLES / "border_jump_comparison_group.csv"

# How many of the largest plausible jumps get a detail map (§13 figures).
N_DETAIL_MAPS = 10
# The Zensus measure the comparison group matches on. Bestandsmieten, never
# Angebotsmieten (A10).
ZENSUS_RENT_MEASURE = "bestandsmiete_nettokalt_eur_per_sqm_mean"


def task_border_jumps(
    raw_geojson_file: Path = RAW_GEOJSON,
    simplified_geojson_file: Path = _GEMEINDEN_GEOJSON,
    crosswalk_file: Path = _MUNICIPALITY_CROSSWALK,
    analysis_sample_file: Path = _ANALYSIS_SAMPLE_MAIN,
    proxy_error_file: Path = PROXY_ERROR_GEMEINDE_HOUSEHOLD,
    zensus_rent_file: Path = ZENSUS_RENTS_GEMEINDEN,
    pairs_file: Annotated[Path, Product] = NEIGHBOUR_PAIRS,
    jumps_file: Annotated[Path, Product] = BORDER_JUMPS,
    flags_file: Annotated[Path, Product] = NEIGHBOUR_JUMP_FLAGS,
    detail_geometry_file: Annotated[Path, Product] = DETAIL_GEOMETRY,
    fitness_file: Annotated[Path, Product] = GEOMETRY_FITNESS_TABLE,
    distribution_file: Annotated[Path, Product] = DISTRIBUTION_TABLE,
    border_type_file: Annotated[Path, Product] = BORDER_TYPE_TABLE,
    mietenstufe_file: Annotated[Path, Product] = MIETENSTUFE_TABLE,
    top_file: Annotated[Path, Product] = TOP_TABLE,
    without_artefacts_file: Annotated[Path, Product] = WITHOUT_ARTEFACTS_TABLE,
    comparison_group_file: Annotated[Path, Product] = COMPARISON_GROUP_TABLE,
) -> None:
    """Read the geometry and the caps, and write every §13 artefact."""
    for path in (pairs_file, fitness_file):
        path.parent.mkdir(parents=True, exist_ok=True)

    raw = _load_geojson(raw_geojson_file)
    fitness = assess_geometry_fitness(raw, _load_geojson(simplified_geojson_file))
    fitness.as_frame().to_csv(fitness_file, index=False)

    contacts = contact_pairs(raw)
    metrics = polygon_metrics(raw)
    described = describe_pairs(
        neighbour_pairs(raw),
        metrics,
        crosswalk=pd.read_parquet(crosswalk_file),
        zensus_rent=_zensus_rent(pd.read_parquet(zensus_rent_file)),
    )
    described = described.assign(
        n_point_contacts_excluded=int(
            (contacts["contact_type"] == "point").sum(),
        ),
        geometry_is_fit_for_adjacency=fitness.is_fit_for_adjacency,
    )
    described.to_parquet(pairs_file, index=False)

    caps = _caps(analysis_sample_file, proxy_error_file)
    jumps = border_jump_table(described, caps)
    jumps.to_parquet(jumps_file, index=False)

    plausible = drop_geometry_artefacts(jumps)
    jump_distribution(jumps).to_csv(distribution_file, index=False)
    jump_distribution(jumps, by=("border_type",)).to_csv(border_type_file, index=False)
    jump_distribution(jumps, by=("same_mietenstufe",)).to_csv(
        mietenstufe_file,
        index=False,
    )
    top_jumps(jumps).to_csv(top_file, index=False)
    jump_distribution(plausible, by=("border_type",)).to_csv(
        without_artefacts_file,
        index=False,
    )
    jump_distribution(comparison_group(plausible)).to_csv(
        comparison_group_file,
        index=False,
    )
    neighbour_jump_flags(jumps, universe=caps).to_parquet(flags_file, index=False)
    detail = detail_geometry(
        raw,
        top_jumps(plausible, n_per_household_size=N_DETAIL_MAPS),
    )
    detail.to_parquet(detail_geometry_file, index=False)
    _register_tables(fitness, jumps, plausible)


def _register_tables(
    fitness: GeometryFitness,
    jumps: pd.DataFrame,
    plausible: pd.DataFrame,
) -> None:
    """Record the seven §13 tables, each with its own reading and caveat."""
    entries = (
        (
            GEOMETRY_FITNESS_TABLE,
            f"The committed display geometry destroys "
            f"{fitness.n_destroyed:,} true neighbour pairs and fabricates "
            f"{fitness.n_fabricated:,}, and {fitness.n_overlapping_edges:,} "
            f"of its edges are shared by more than two polygons, so adjacency "
            f"is computed on the unsimplified export instead.",
            "A fitness comparison, not a validation of either geometry: the "
            "unsimplified export is a BKG derivative rather than VG250 itself, "
            "and its Gebietsstand is A4's reconstruction.",
        ),
        (
            DISTRIBUTION_TABLE,
            f"Across all {len(jumps) // jumps['household_size'].nunique():,} "
            f"neighbour pairs per household size the cap difference is zero for "
            f"the majority, because most neighbours share a policy region.",
            "Pooling border types hides the whole finding; read it beside the "
            "by-border-type table. " + _RD_LIMITATION,
        ),
        (
            BORDER_TYPE_TABLE,
            "The cap is flat inside a policy region and steps by tens to "
            "hundreds of euro across a Kreis or Bundesland boundary, and the "
            "step grows with household size.",
            _RD_LIMITATION,
        ),
        (
            MIETENSTUFE_TABLE,
            "Pairs sharing a Mietenstufe still step across a policy-region "
            "border, so the statutory rent level does not account for the "
            "discontinuity.",
            "The Mietenstufe split is descriptive and controls for nothing "
            "else. " + _RD_LIMITATION,
        ),
        (
            TOP_TABLE,
            "The largest cap steps between directly adjacent Gemeinden, named "
            "so each can be checked against its two source documents.",
            "Selected on the largest euro jump, so these are the tail of the "
            "distribution and not a typical border. " + _RD_LIMITATION,
        ),
        (
            WITHOUT_ARTEFACTS_TABLE,
            f"Dropping the pairs whose shared border is a suspected geometry "
            f"artefact leaves {len(plausible) // max(plausible['household_size'].nunique(), 1):,} "
            f"pairs per household size and moves nothing beyond the second "
            f"digit, so the finding does not rest on the boundary line work.",
            "An artefact flag is a suspicion about a short shared border, not "
            "a proven error. " + _RD_LIMITATION,
        ),
        (
            COMPARISON_GROUP_TABLE,
            "The §13.4 tight comparison group — same Mietenstufe, Zensus rent "
            "within ten percent, similar density, different policy region — "
            "does not close the gap.",
            "Narrowing the comparison does not make it exogenous: households "
            "sort across these borders and Kreise are not assigned their "
            "boundaries at random. " + _RD_LIMITATION,
        ),
    )
    for path, interpretation, limitation in entries:
        register_result(
            filename=path.name,
            analysis_module=_MODULE,
            dataset=_DATASET,
            script=_SCRIPT,
            interpretation=interpretation,
            limitation=limitation,
        )


def detail_geometry(
    geojson: dict[str, Any],
    top: pd.DataFrame,
    n_pairs: int = N_DETAIL_MAPS,
) -> pd.DataFrame:
    """Extract the projected outlines of the pairs that get a detail map.

    The figure task draws the two Gemeinden of each pair in the equal-area
    projection, so it needs their rings rather than the whole 58 MB boundary
    set. Ranking is by euro jump across all household sizes, keeping the
    largest household size per pair when a pair tops several.

    Args:
        geojson: The unsimplified `FeatureCollection`.
        top: The output of {func}`kdu.analysis.border_jumps.top_jumps`.
        n_pairs: How many pairs to extract.

    Returns:
        One row per vertex, keyed `pair_rank`, `ags`, `side` and `part`.

    """
    ranked = (
        top.sort_values("jump_eur", ascending=False)
        .drop_duplicates(subset=["ags_i", "ags_j"])
        .head(n_pairs)
        .reset_index(drop=True)
    )
    wanted: dict[str, list[tuple[int, str]]] = {}
    for rank, row in ranked.iterrows():
        for ags, side in ((row["ags_i"], "i"), (row["ags_j"], "j")):
            wanted.setdefault(ags, []).append((int(cast("int", rank)), side))
    frames = []
    for feature in geojson["features"]:
        ags = gemeinde_ags(feature)
        if ags not in wanted:
            continue
        for part, ring in enumerate(_outer_rings(feature["geometry"])):
            coordinates = np.asarray(ring, dtype=float)
            easting, northing = project_laea(coordinates[:, 0], coordinates[:, 1])
            frames.extend(
                pd.DataFrame(
                    {
                        "pair_rank": rank,
                        "ags": ags,
                        "side": side,
                        "part": part,
                        "x": easting,
                        "y": northing,
                    },
                )
                for rank, side in wanted[ags]
            )
    vertices = pd.concat(frames, ignore_index=True)
    labels = ranked.assign(pair_rank=ranked.index)
    return vertices.merge(labels, on="pair_rank", how="left")


def geometry_fitness_note(fitness: GeometryFitness) -> str:
    """State in one sentence whether the simplified geometry could be used."""
    if fitness.is_fit_for_adjacency:
        return (
            "The simplified boundary set reproduces the unsimplified neighbour "
            "graph exactly, so either geometry would give the same pairs."
        )
    return (
        f"The simplified boundary set destroys {fitness.n_destroyed} true "
        f"neighbour pairs and fabricates {fitness.n_fabricated}, and "
        f"{fitness.n_overlapping_edges} of its edges are shared by more than two "
        "polygons, which a planar partition cannot do. The neighbour graph is "
        "therefore built on the unsimplified boundaries."
    )


def _caps(analysis_sample_file: Path, proxy_error_file: Path) -> pd.DataFrame:
    sample = pd.read_parquet(
        analysis_sample_file,
        columns=["ags", "household_size", "kdu_bkc_cap", "wogg_linked_flag"],
    )
    proxy_error = pd.read_parquet(
        proxy_error_file,
        columns=["ags", "household_size", "benchmark_variant", "at_safety_markup"],
    )
    exact_ratio = proxy_error.loc[
        proxy_error["benchmark_variant"] == "base",
        ["ags", "household_size", "at_safety_markup"],
    ].drop_duplicates(subset=["ags", "household_size"])
    merged = sample.merge(exact_ratio, on=["ags", "household_size"], how="left")
    merged["at_safety_markup"] = merged["at_safety_markup"].fillna(value=False)
    return merged


def _zensus_rent(rents: pd.DataFrame) -> pd.DataFrame:
    mean_rent = rents.loc[rents["measure"] == ZENSUS_RENT_MEASURE]
    return (
        mean_rent.loc[:, ["ags_gemeinde", "value"]]
        .rename(columns={"ags_gemeinde": "ags", "value": "rent_eur_per_sqm"})
        .drop_duplicates(subset=["ags"])
        .reset_index(drop=True)
    )


def _outer_rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"][0]]
    return [polygon[0] for polygon in geometry["coordinates"]]


def _load_geojson(path: Path) -> dict[str, Any]:
    if not path.exists():
        msg = (
            f"boundary file not found: {path}. The unsimplified boundaries are "
            "gitignored; run `pixi run prepare-gemeinden` once to fetch them."
        )
        raise FileNotFoundError(msg)
    return json.loads(path.read_text(encoding="utf-8"))
