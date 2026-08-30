"""Measure how far the KdU cap steps across a shared Gemeinde boundary (P1.1).

**This module is descriptive. It is not a regression-discontinuity design and
supports no causal claim.** A large jump documents an *administrative
discontinuity*: two directly adjacent Gemeinden, sometimes two sides of one
street, read their maximum recognisable Bruttokaltmiete off different
Richtlinien. Nothing here identifies an effect *of* the border, on rents, on
mobility, or on anything else. The Gemeinden either side of a Kreis boundary
are not balanced on anything, the assignment to a policy region is not local to
the border, and no bandwidth, running variable or continuity assumption appears
anywhere in this file. §20 forbids the phrase "causal effect" in translation
too, and every output of this module inherits that ban.

What the module computes, following §13:

- §13.2 the neighbour graph: two Gemeinden are neighbours when their polygons
  share a boundary *line*. Point contacts are recorded and excluded. Every pair
  is stored once, keyed `ags_i < ags_j`. Lengths, areas and centroid distances
  are computed in ETRS89/LAEA Europe (EPSG:3035), the equal-area projection
  §13.1 prescribes.
- §13.3 the jump measures `J = |log K_i − log K_j|` and `J^€ = |K_i − K_j|`,
  per household size.
- §13.4 the six analyses, each reported for the three D7/A12 linkage groups.

The D7/A12 obligation bites hard here. Within-Kreis pairs are `J = 0` wherever
a Kreis publishes one cap for its whole territory, and for the WoGG-linked
Kreise the cap is the § 12 WoGG table times 1.10, so a pair of two linked
Kreise differs *only* by its Mietenstufe. Both `exact_ratio` and `linked_union`
exclusions are therefore reported beside the pooled figure, and the pooled
figure alone is never a finding.
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd

# The projection §13.1 prescribes, named for figure and table notes.
PROJECTION_NAME = "ETRS89 / LAEA Europe (EPSG:3035)"

# Shared borders shorter than this are flagged as possible geometry artefacts
# (§13.2). The boundary source is generalised line work, so a common stretch of
# a few line segments can be an artefact of that generalisation rather than a
# real common border. The threshold is deliberately generous; every analysis is
# reported with and without the flagged pairs.
SHORT_BOUNDARY_THRESHOLD_M = 250.0

# Decimal places the boundary coordinates are matched on when building the
# topology. Seven places is about a centimetre, far below the precision of the
# source line work, so this matches identical vertices without snapping
# distinct ones together.
COORDINATE_MATCH_DECIMALS = 7

# How close two Gemeinden must be to count as a §13.4 point 6 comparison pair:
# a log difference in mean Zensus Bestandsmiete per m² and in inhabitants per
# km². 0.10 is about a 10 % rent difference; 0.50 about a factor 1.65 in
# density, which is tight for a variable spanning four orders of magnitude.
RENT_SIMILARITY_LOG_TOLERANCE = 0.10
DENSITY_SIMILARITY_LOG_TOLERANCE = 0.50

# Quantiles every distribution table reports.
JUMP_QUANTILES: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75, 0.90, 0.99)

# Euro thresholds the distribution tables report shares above.
JUMP_EUR_THRESHOLDS: tuple[float, ...] = (50.0, 100.0, 200.0)

# GRS80, the ellipsoid ETRS89 is defined on.
_SEMI_MAJOR_AXIS_M = 6_378_137.0
_INVERSE_FLATTENING = 298.257222101
# EPSG:3035 projection parameters.
_LATITUDE_OF_ORIGIN_DEG = 52.0
_LONGITUDE_OF_ORIGIN_DEG = 10.0
_FALSE_EASTING_M = 4_321_000.0
_FALSE_NORTHING_M = 3_210_000.0

_Vertex = tuple[float, float]
_Edge = tuple[_Vertex, _Vertex]


class ContactType(StrEnum):
    """How two Gemeinde polygons touch."""

    LINE = "line"
    """A shared boundary line: the §13.2 definition of a neighbour."""
    POINT = "point"
    """A shared vertex only, with no common segment. Excluded from the graph."""


class BorderType(StrEnum):
    """The administrative status of the border a pair straddles."""

    WITHIN_POLICY_REGION = "within_policy_region"
    """Both Gemeinden read the same Richtlinie (D1: the policy region is the Kreis)."""
    BETWEEN_POLICY_REGIONS = "between_policy_regions"
    """Two Kreise inside one Bundesland, so two independent policy decisions."""
    BETWEEN_BUNDESLAENDER = "between_bundeslaender"
    """Two Kreise in different Bundesländer, the largest administrative step."""


class PairLinkage(StrEnum):
    """Which WoGG-linked pairs a table keeps (D7, A12).

    Both exclusions drop a pair when *either* side is linked, because a jump
    with one linked side is still half definitional.
    """

    ALL = "all"
    """Pooled. Never to be read as an empirical regularity (D7)."""
    EXCLUDING_EXACT_RATIO = "excluding_exact_ratio"
    """Drops pairs touching a Gemeinde whose `K/W` is 1.100 within 5e-4 (A12)."""
    EXCLUDING_LINKED_UNION = "excluding_linked_union"
    """Drops pairs touching a Gemeinde flagged by either D7 detector (A8, A12)."""


@dataclass(frozen=True)
class GeometryFitness:
    """Whether a simplified boundary set can carry an adjacency analysis (A4).

    Adjacency is a topological property, and grid snapping is a topological
    operation: it welds polygons that merely came close and tears apart
    polygons whose shared vertices rounded to different cells. This compares a
    candidate boundary set against an unsimplified reference and reports how
    much of the neighbour graph survives.
    """

    n_features_reference: int
    """Polygons in the unsimplified reference geometry."""
    n_features_candidate: int
    """Polygons in the candidate geometry."""
    n_pairs_reference: int
    """Neighbour pairs the reference geometry yields, on the common AGS."""
    n_pairs_candidate: int
    """Neighbour pairs the candidate geometry yields, on the common AGS."""
    n_destroyed: int
    """Reference pairs the candidate loses."""
    n_fabricated: int
    """Candidate pairs the reference does not have."""
    n_overlapping_edges: int
    """Candidate edges shared by more than two polygons — impossible in a
    planar partition, so a direct count of broken topology."""
    n_lost_features: int
    """AGS present in the reference and absent from the candidate."""

    @property
    def recall(self) -> float:
        """Share of true neighbour pairs the candidate keeps."""
        return (self.n_pairs_reference - self.n_destroyed) / self.n_pairs_reference

    @property
    def precision(self) -> float:
        """Share of candidate pairs that are true neighbours."""
        return (self.n_pairs_candidate - self.n_fabricated) / self.n_pairs_candidate

    @property
    def is_fit_for_adjacency(self) -> bool:
        """Whether the candidate may be used to build the neighbour graph.

        The bar is exactness, not a high score. A neighbour graph is the
        analysis object here, not an input to a smoothing step, so a single
        fabricated pair is a fabricated border jump and a single destroyed pair
        is a jump that silently never gets measured.
        """
        return (
            self.n_destroyed == 0
            and self.n_fabricated == 0
            and self.n_overlapping_edges == 0
            and self.n_lost_features == 0
        )

    def as_frame(self) -> pd.DataFrame:
        """Render the audit as the one-row table the module writes to `bld/`."""
        return pd.DataFrame(
            [
                {
                    "n_features_reference": self.n_features_reference,
                    "n_features_candidate": self.n_features_candidate,
                    "n_pairs_reference": self.n_pairs_reference,
                    "n_pairs_candidate": self.n_pairs_candidate,
                    "n_destroyed": self.n_destroyed,
                    "n_fabricated": self.n_fabricated,
                    "n_overlapping_edges": self.n_overlapping_edges,
                    "n_lost_features": self.n_lost_features,
                    "recall": self.recall,
                    "precision": self.precision,
                    "is_fit_for_adjacency": self.is_fit_for_adjacency,
                },
            ],
        )


def project_laea(
    longitude: np.ndarray,
    latitude: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Project geographic coordinates to ETRS89/LAEA Europe (EPSG:3035).

    The ellipsoidal Lambert azimuthal equal-area projection on GRS80, with the
    EPSG:3035 origin at 52°N 10°E and its false easting and northing. Areas are
    exact and lengths near Germany are distorted by well under a percent, which
    is what §13.1 asks for.

    Args:
        longitude: Longitudes in degrees east.
        latitude: Latitudes in degrees north.

    Returns:
        Easting and northing in metres.

    """
    flattening = 1.0 / _INVERSE_FLATTENING
    eccentricity_squared = flattening * (2.0 - flattening)
    eccentricity = math.sqrt(eccentricity_squared)

    def authalic_numerator(sin_latitude: np.ndarray) -> np.ndarray:
        return (1.0 - eccentricity_squared) * (
            sin_latitude / (1.0 - eccentricity_squared * sin_latitude**2)
            - (1.0 / (2.0 * eccentricity))
            * np.log(
                (1.0 - eccentricity * sin_latitude)
                / (1.0 + eccentricity * sin_latitude),
            )
        )

    q_pole = float(authalic_numerator(np.array(1.0 - 1e-16)))
    latitude_origin = math.radians(_LATITUDE_OF_ORIGIN_DEG)
    sin_origin = math.sin(latitude_origin)
    beta_origin = math.asin(
        float(authalic_numerator(np.array(sin_origin))) / q_pole,
    )
    radius_q = _SEMI_MAJOR_AXIS_M * math.sqrt(q_pole / 2.0)
    scale_origin = math.cos(latitude_origin) / math.sqrt(
        1.0 - eccentricity_squared * sin_origin**2,
    )
    ratio = _SEMI_MAJOR_AXIS_M * scale_origin / (radius_q * math.cos(beta_origin))

    latitude_rad = np.radians(np.asarray(latitude, dtype=float))
    delta_longitude = np.radians(np.asarray(longitude, dtype=float)) - math.radians(
        _LONGITUDE_OF_ORIGIN_DEG,
    )
    beta = np.arcsin(authalic_numerator(np.sin(latitude_rad)) / q_pole)
    denominator = (
        1.0
        + math.sin(beta_origin) * np.sin(beta)
        + math.cos(beta_origin) * np.cos(beta) * np.cos(delta_longitude)
    )
    factor = radius_q * np.sqrt(2.0 / denominator)
    easting = _FALSE_EASTING_M + factor * ratio * np.cos(beta) * np.sin(
        delta_longitude,
    )
    northing = _FALSE_NORTHING_M + (factor / ratio) * (
        math.cos(beta_origin) * np.sin(beta)
        - math.sin(beta_origin) * np.cos(beta) * np.cos(delta_longitude)
    )
    return easting, northing


def polygon_metrics(geojson: Mapping[str, Any]) -> pd.DataFrame:
    """Return the projected area and centroid of every Gemeinde polygon.

    Areas come from the shoelace formula in the equal-area projection, so
    interior rings subtract themselves and multi-part Gemeinden add up. The
    centroid is the area-weighted centroid of the signed parts, which is what
    §13.2's centroid distance is measured between.

    Args:
        geojson: A Gemeinde `FeatureCollection` carrying `gem_code`.

    Returns:
        One row per AGS with `area_sqm`, `centroid_x` and `centroid_y`.

    """
    records = []
    for feature in geojson["features"]:
        area = 0.0
        moment_x = 0.0
        moment_y = 0.0
        for ring in _rings(feature["geometry"]):
            coordinates = np.asarray(ring, dtype=float)
            easting, northing = project_laea(coordinates[:, 0], coordinates[:, 1])
            cross = easting[:-1] * northing[1:] - easting[1:] * northing[:-1]
            ring_area = 0.5 * float(cross.sum())
            area += ring_area
            if ring_area != 0.0:
                moment_x += float(((easting[:-1] + easting[1:]) * cross).sum()) / 6.0
                moment_y += float(((northing[:-1] + northing[1:]) * cross).sum()) / 6.0
        records.append(
            {
                "ags": gemeinde_ags(feature),
                "area_sqm": area,
                "centroid_x": moment_x / area if area else math.nan,
                "centroid_y": moment_y / area if area else math.nan,
            },
        )
    return pd.DataFrame.from_records(records)


def contact_pairs(geojson: Mapping[str, Any]) -> pd.DataFrame:
    """Return every pair of polygons that touch, typed line or point.

    Both kinds are returned so that the §13.2 exclusion of point contacts is a
    visible, countable decision rather than a silent omission.

    Args:
        geojson: A Gemeinde `FeatureCollection` carrying `gem_code`.

    Returns:
        One row per unordered pair with `ags_i < ags_j`, `contact_type` and
        `shared_boundary_m` (zero for a point contact).

    """
    codes = [gemeinde_ags(feature) for feature in geojson["features"]]
    _fail_if_ags_not_unique(codes)
    edge_owners: dict[_Edge, set[int]] = defaultdict(set)
    vertex_owners: dict[_Vertex, set[int]] = defaultdict(set)
    for index, feature in enumerate(geojson["features"]):
        for ring in _rings(feature["geometry"]):
            vertices = _match_key_ring(ring)
            for vertex in vertices:
                vertex_owners[vertex].add(index)
            for start, end in pairwise(vertices):
                if start != end:
                    edge_owners[_undirected(start, end)].add(index)

    lengths = _edge_lengths(edge_owners)
    shared: dict[tuple[str, str], float] = defaultdict(float)
    for edge, owners in edge_owners.items():
        if len(owners) < 2:  # noqa: PLR2004
            continue
        for key in _unordered_keys(owners, codes):
            shared[key] += lengths[edge]
    point_only = {
        key
        for owners in vertex_owners.values()
        if len(owners) >= 2  # noqa: PLR2004
        for key in _unordered_keys(owners, codes)
    } - set(shared)

    records = [
        {
            "ags_i": key[0],
            "ags_j": key[1],
            "contact_type": ContactType.LINE.value,
            "shared_boundary_m": length,
        }
        for key, length in shared.items()
    ]
    records.extend(
        {
            "ags_i": key[0],
            "ags_j": key[1],
            "contact_type": ContactType.POINT.value,
            "shared_boundary_m": 0.0,
        }
        for key in point_only
    )
    frame = pd.DataFrame.from_records(
        records,
        columns=["ags_i", "ags_j", "contact_type", "shared_boundary_m"],
    )
    return frame.sort_values(["ags_i", "ags_j"]).reset_index(drop=True)


def neighbour_pairs(geojson: Mapping[str, Any]) -> pd.DataFrame:
    """Return the §13.2 neighbour graph: shared boundary lines only.

    Args:
        geojson: A Gemeinde `FeatureCollection` carrying `gem_code`.

    Returns:
        One row per neighbouring pair, `ags_i < ags_j`, never repeated.

    """
    contacts = contact_pairs(geojson)
    lines = contacts.loc[contacts["contact_type"] == ContactType.LINE.value]
    return lines.reset_index(drop=True)


def assess_geometry_fitness(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> GeometryFitness:
    """Compare a candidate boundary set's neighbour graph against a reference.

    Args:
        reference: Unsimplified boundaries, treated as the truth.
        candidate: The boundaries whose fitness is in question.

    Returns:
        The audit, whose `is_fit_for_adjacency` decides whether the candidate
        may be used.

    """
    reference_pairs = _pair_keys(reference)
    candidate_pairs = _pair_keys(candidate)
    reference_codes = {gemeinde_ags(f) for f in reference["features"]}
    candidate_codes = {gemeinde_ags(f) for f in candidate["features"]}
    common = reference_codes & candidate_codes
    restricted_reference = {p for p in reference_pairs if _both_in(p, common)}
    restricted_candidate = {p for p in candidate_pairs if _both_in(p, common)}
    return GeometryFitness(
        n_features_reference=len(reference["features"]),
        n_features_candidate=len(candidate["features"]),
        n_pairs_reference=len(restricted_reference),
        n_pairs_candidate=len(restricted_candidate),
        n_destroyed=len(restricted_reference - restricted_candidate),
        n_fabricated=len(restricted_candidate - restricted_reference),
        n_overlapping_edges=_count_overlapping_edges(candidate),
        n_lost_features=len(reference_codes - candidate_codes),
    )


def describe_pairs(
    pairs: pd.DataFrame,
    metrics: pd.DataFrame,
    crosswalk: pd.DataFrame,
    zensus_rent: pd.DataFrame,
) -> pd.DataFrame:
    """Attach the §13.2 pair attributes to the neighbour graph.

    Args:
        pairs: The neighbour graph from {func}`neighbour_pairs`.
        metrics: Projected areas and centroids from {func}`polygon_metrics`.
        crosswalk: `municipality_crosswalk`, keyed `ags`.
        zensus_rent: One row per `ags` with `rent_eur_per_sqm`, the mean Zensus
            2022 Bestandsmiete. Never an Angebotsmiete (A10).

    Returns:
        The pairs with `same_policy_region`, `same_kreis`, `same_bundesland`,
        `same_mietenstufe`, `border_type`, `centroid_distance_m`,
        `possible_geometry_artefact` and the rent and density attributes the
        §13.4 comparison group needs.

    """
    attributes = _side_attributes(metrics, crosswalk, zensus_rent)
    frame = pairs.copy()
    for side in ("i", "j"):
        frame = frame.merge(
            attributes.add_suffix(f"_{side}"),
            left_on=f"ags_{side}",
            right_index=True,
            how="left",
        )
    frame["same_policy_region"] = _same(frame, "policy_region_id")
    frame["same_kreis"] = _same(frame, "ags_kreis")
    frame["same_bundesland"] = _same(frame, "bundesland")
    frame["same_mietenstufe"] = _same(frame, "mietenstufe")
    frame["border_type"] = _border_type(frame)
    frame["centroid_distance_m"] = np.hypot(
        frame["centroid_x_i"] - frame["centroid_x_j"],
        frame["centroid_y_i"] - frame["centroid_y_j"],
    )
    frame["possible_geometry_artefact"] = (
        frame["shared_boundary_m"] < SHORT_BOUNDARY_THRESHOLD_M
    )
    frame["rent_log_gap"] = _log_gap(frame, "rent_eur_per_sqm")
    frame["density_log_gap"] = _log_gap(frame, "population_per_sqkm")
    return frame.reset_index(drop=True)


def drop_geometry_artefacts(pairs: pd.DataFrame) -> pd.DataFrame:
    """Return only the pairs whose shared border is long enough to trust."""
    return pairs.loc[~pairs["possible_geometry_artefact"]].reset_index(drop=True)


def border_jump_table(pairs: pd.DataFrame, caps: pd.DataFrame) -> pd.DataFrame:
    """Compute the §13.3 jump measures for every pair and household size.

    `J = |log K_i − log K_j|` and `J^€ = |K_i − K_j|`. Both are absolute
    differences, so both are symmetric in the two sides by construction, and a
    pair with no cap on one side drops out.

    Args:
        pairs: Neighbour pairs, described or bare.
        caps: Long cap table with `ags`, `household_size`, `kdu_bkc_cap`,
            `at_safety_markup` and `wogg_linked_flag`.

    Returns:
        One row per pair and household size, carrying every column of `pairs`
        plus `cap_i`, `cap_j`, `jump_eur`, `jump_log` and the two linkage
        markers.

    """
    columns = ["ags", "household_size", "kdu_bkc_cap"]
    markers = ["at_safety_markup", "wogg_linked_flag"]
    slim = caps.loc[:, [*columns, *markers]]
    frame = pairs.merge(
        slim.rename(columns={"ags": "ags_i"}).add_suffix("_i"),
        left_on="ags_i",
        right_on="ags_i_i",
        how="inner",
    ).drop(columns=["ags_i_i"])
    frame = frame.merge(
        slim.rename(columns={"ags": "ags_j"}).add_suffix("_j"),
        left_on=["ags_j", "household_size_i"],
        right_on=["ags_j_j", "household_size_j"],
        how="inner",
    ).drop(columns=["ags_j_j", "household_size_j"])
    frame = frame.rename(
        columns={
            "household_size_i": "household_size",
            "kdu_bkc_cap_i": "cap_i",
            "kdu_bkc_cap_j": "cap_j",
        },
    )
    frame["jump_eur"] = (frame["cap_i"] - frame["cap_j"]).abs()
    frame["jump_log"] = (np.log(frame["cap_i"]) - np.log(frame["cap_j"])).abs()
    frame["either_at_safety_markup"] = frame["at_safety_markup_i"].astype(
        bool,
    ) | frame["at_safety_markup_j"].astype(bool)
    frame["either_wogg_linked"] = frame["wogg_linked_flag_i"].astype(bool) | frame[
        "wogg_linked_flag_j"
    ].astype(bool)
    return frame.sort_values(["household_size", "ags_i", "ags_j"]).reset_index(
        drop=True,
    )


def linkage_masks(jumps: pd.DataFrame) -> Mapping[PairLinkage, pd.Series]:
    """Return the row mask each D7/A12 linkage group selects."""
    return {
        PairLinkage.ALL: pd.Series(data=True, index=jumps.index),
        PairLinkage.EXCLUDING_EXACT_RATIO: ~jumps["either_at_safety_markup"],
        PairLinkage.EXCLUDING_LINKED_UNION: ~jumps["either_wogg_linked"],
    }


def jump_distribution(
    jumps: pd.DataFrame,
    by: Sequence[str] = (),
) -> pd.DataFrame:
    """Summarise the jump distribution per household size and linkage group.

    Args:
        jumps: The output of {func}`border_jump_table`.
        by: Extra grouping columns, for example `("border_type",)`.

    Returns:
        One row per household size, linkage group and `by` combination.

    """
    grouping = ["household_size", *by]
    frames = []
    for linkage, mask in linkage_masks(jumps).items():
        subset = jumps.loc[mask]
        if subset.empty:
            continue
        summary = (
            subset.groupby(grouping, dropna=False)
            .apply(_summarise_group, include_groups=False)
            .reset_index()
        )
        summary.insert(0, "linkage", linkage.value)
        frames.append(summary)
    return pd.concat(frames, ignore_index=True)


def top_jumps(jumps: pd.DataFrame, n_per_household_size: int = 20) -> pd.DataFrame:
    """Return the largest euro jumps per household size (§13.4 point 4).

    A row here is an administrative discontinuity to be looked at, not an
    estimate. It says two adjacent Gemeinden differ by this much, and nothing
    about why.
    """
    kept = [
        "household_size",
        "ags_i",
        "ags_j",
        "gemeinde_i",
        "gemeinde_j",
        "kreis_i",
        "kreis_j",
        "bundesland_i",
        "bundesland_j",
        "mietenstufe_i",
        "mietenstufe_j",
        "border_type",
        "cap_i",
        "cap_j",
        "jump_eur",
        "jump_log",
        "shared_boundary_m",
        "centroid_distance_m",
        "possible_geometry_artefact",
        "either_at_safety_markup",
        "either_wogg_linked",
    ]
    available = [column for column in kept if column in jumps.columns]
    return (
        jumps.sort_values(["household_size", "jump_eur"], ascending=[True, False])
        .groupby("household_size", as_index=False)
        .head(n_per_household_size)
        .loc[:, available]
        .reset_index(drop=True)
    )


def comparison_group(jumps: pd.DataFrame) -> pd.DataFrame:
    """Select the §13.4 point 6 comparison group.

    Pairs in different policy regions, on the same Mietenstufe, with a similar
    mean Zensus Bestandsmiete and a similar population density. Holding those
    three fixed narrows what an observed step can plausibly be attributed to,
    but it does **not** identify an effect: the Kreise either side still differ
    on everything else, including the Vergleichsraum definition that produced
    the cap. This is a descriptive comparison group, not a control group.
    """
    similar = (
        ~jumps["same_policy_region"].fillna(value=False).astype(bool)
        & jumps["same_mietenstufe"].fillna(value=False).astype(bool)
        & (jumps["rent_log_gap"] <= RENT_SIMILARITY_LOG_TOLERANCE)
        & (jumps["density_log_gap"] <= DENSITY_SIMILARITY_LOG_TOLERANCE)
    )
    return jumps.loc[similar].reset_index(drop=True)


def neighbour_jump_flags(
    jumps: pd.DataFrame,
    universe: pd.DataFrame | None = None,
    quantile: float = 0.95,
) -> pd.DataFrame:
    """Flag Gemeinden whose cap steps unusually far across a real border.

    This replaces P0.1's surrogate flag, which had no adjacency to work with
    and so ranked Kreise within a Bundesland instead. The flag now means what
    its name says: this Gemeinde has at least one directly adjacent Gemeinde,
    in a different policy region and across a boundary long enough to trust,
    whose cap differs by more than the `quantile` of all such steps at that
    household size.

    A flagged row is a row worth looking at, not a row that is wrong.

    Args:
        jumps: The output of {func}`border_jump_table`, described.
        universe: Every `ags` and `household_size` the flag must cover.
            Gemeinden with no eligible cross-border neighbour — an island, a
            Gemeinde whose whole Kreis boundary is a suspected artefact — get
            `has_cross_border_neighbour = False` rather than dropping out.
        quantile: Cut-off within each household size.

    Returns:
        One row per `ags` and `household_size` with `large_neighbour_jump`,
        the largest cross-border step, and the threshold it was judged against.

    """
    eligible = jumps.loc[
        ~jumps["possible_geometry_artefact"]
        & ~jumps["same_policy_region"].fillna(value=False).astype(bool)
    ]
    thresholds = eligible.groupby("household_size")["jump_eur"].quantile(quantile)
    sides = pd.concat(
        [
            eligible.loc[:, ["ags_i", "household_size", "jump_eur"]].rename(
                columns={"ags_i": "ags"},
            ),
            eligible.loc[:, ["ags_j", "household_size", "jump_eur"]].rename(
                columns={"ags_j": "ags"},
            ),
        ],
        ignore_index=True,
    )
    largest = (
        sides.groupby(["ags", "household_size"], as_index=False)["jump_eur"]
        .max()
        .rename(columns={"jump_eur": "max_cross_border_jump_eur"})
    )
    if universe is not None:
        largest = (
            universe.loc[:, ["ags", "household_size"]]
            .drop_duplicates()
            .merge(largest, on=["ags", "household_size"], how="left")
        )
    largest["has_cross_border_neighbour"] = largest["max_cross_border_jump_eur"].notna()
    largest["jump_threshold_eur"] = largest["household_size"].map(thresholds)
    largest["large_neighbour_jump"] = (
        largest["max_cross_border_jump_eur"] > largest["jump_threshold_eur"]
    ).fillna(value=False)
    largest["threshold_quantile"] = quantile
    return largest.sort_values(["ags", "household_size"]).reset_index(drop=True)


def interpretation(
    distribution: pd.DataFrame,
    by_border_type: pd.DataFrame,
    comparison: pd.DataFrame,
    top: pd.DataFrame,
    fitness: GeometryFitness,
    household_size: int = 4,
) -> str:
    """Write the §21 four-part reading of the border-jump figure.

    Every number is taken from the computed tables, so the document contains no
    placeholder. Part four is the §13 interpretation guard, stated as strongly
    as §13 states it: this is not an RD design.

    Args:
        distribution: Output of {func}`jump_distribution` with no `by`.
        by_border_type: Output of {func}`jump_distribution` by `border_type`.
        comparison: {func}`jump_distribution` on the §13.4 comparison group.
        top: Output of {func}`top_jumps`.
        fitness: The A4 geometry audit.
        household_size: Household size the headline numbers are quoted for.

    Returns:
        A markdown document with no placeholders left in it.

    """
    linkage = PairLinkage.EXCLUDING_LINKED_UNION.value
    overall = _row(distribution, linkage=linkage, household_size=household_size)
    within = _row(
        by_border_type,
        linkage=linkage,
        household_size=household_size,
        border_type=BorderType.WITHIN_POLICY_REGION.value,
    )
    between = _row(
        by_border_type,
        linkage=linkage,
        household_size=household_size,
        border_type=BorderType.BETWEEN_POLICY_REGIONS.value,
    )
    across_states = _row(
        by_border_type,
        linkage=linkage,
        household_size=household_size,
        border_type=BorderType.BETWEEN_BUNDESLAENDER.value,
    )
    tighter = _row(comparison, linkage=linkage, household_size=household_size)
    largest = top.loc[
        (top["household_size"] == household_size)
        & ~top["possible_geometry_artefact"].astype(bool)
    ].iloc[0]
    return _INTERPRETATION_TEMPLATE.format(
        household_size=household_size,
        n_pairs=int(overall["n_pairs"]),
        projection=PROJECTION_NAME,
        threshold=int(SHORT_BOUNDARY_THRESHOLD_M),
        within_n=int(within["n_pairs"]),
        within_zero_share=100.0 * within["share_zero_jump"],
        within_mean=within["mean_jump_eur"],
        between_n=int(between["n_pairs"]),
        between_median=between["p50_jump_eur"],
        between_mean=between["mean_jump_eur"],
        between_p90=between["p90_jump_eur"],
        between_above_100=100.0 * between["share_above_100_eur"],
        states_n=int(across_states["n_pairs"]),
        states_mean=across_states["mean_jump_eur"],
        states_above_100=100.0 * across_states["share_above_100_eur"],
        tighter_n=int(tighter["n_pairs"]),
        tighter_median=tighter["p50_jump_eur"],
        tighter_above_100=100.0 * tighter["share_above_100_eur"],
        top_i=largest["gemeinde_i"],
        top_j=largest["gemeinde_j"],
        top_kreis_i=largest["kreis_i"],
        top_kreis_j=largest["kreis_j"],
        top_jump=largest["jump_eur"],
        top_boundary_km=largest["shared_boundary_m"] / 1000.0,
        n_destroyed=fitness.n_destroyed,
        n_fabricated=fitness.n_fabricated,
        rent_tolerance=100.0 * RENT_SIMILARITY_LOG_TOLERANCE,
    )


def gemeinde_ags(feature: Mapping[str, Any]) -> str:
    """Return the eight-digit Gemeinde AGS of a boundary feature.

    The source keys on the twelve-digit Regionalschlüssel, sometimes wrapped in
    a single-element list. The eight-digit AGS is its first five and last three
    characters, never its first eight.
    """
    code = feature["properties"]["gem_code"]
    if isinstance(code, list):
        code = code[0]
    text = str(code)
    return text[:5] + text[-3:]


# The §21 four-part reading, filled from computed numbers only.
_INTERPRETATION_TEMPLATE = """# P1.1 — Administrative border jumps

*Household size {household_size}. Every figure below excludes pairs touching a
WoGG-linked Gemeinde (the `linked_union` group of A12), because there the cap is
the § 12 WoGG table times 1.10 and a step across the border would only restate
the Mietenstufe. The pooled `all` row and the narrower `exact_ratio` exclusion
are in the same tables and are never presented on their own.*

## 1. What is measured

For every pair of Gemeinden that share a boundary **line** — point contacts
excluded — the absolute difference in the maximum recognisable Bruttokaltmiete,
`J^€ = |K_i − K_j|`, and its log counterpart `J = |log K_i − log K_j|`. Shared
boundary lengths, areas and centroid distances are computed in {projection}.
Pairs whose common border is shorter than {threshold} m are flagged as possible
geometry artefacts and every analysis is repeated without them. {n_pairs} pairs
enter at this household size.

## 2. The central quantitative finding

Inside a policy region the cap barely moves: {within_zero_share:.0f} % of the
{within_n} within-Kreis pairs have exactly the same cap, and the mean step is
{within_mean:.0f} €. Across a policy-region border it jumps. The median of the
{between_n} pairs that straddle two Kreise in one Bundesland is
{between_median:.0f} €, the mean {between_mean:.0f} €, the 90th percentile
{between_p90:.0f} €, and {between_above_100:.0f} % of them differ by more than
100 € a month. The {states_n} pairs that also cross a Bundesland border step
further still: {states_mean:.0f} € on average, {states_above_100:.0f} % above
100 €. Holding the Mietenstufe, the mean Zensus Bestandsmiete (within
{rent_tolerance:.0f} %) and the population density fixed does not close the gap:
those {tighter_n} pairs still show a median step of {tighter_median:.0f} € and
{tighter_above_100:.0f} % above 100 €. The largest single step at this household
size is {top_i} against {top_j} ({top_kreis_i} against {top_kreis_j}),
{top_jump:.0f} € apart along {top_boundary_km:.1f} km of common border.

## 3. Why this matters for tax-transfer simulation

A model that assigns one national KdU parameter, or a Wohngeld-derived one,
places two adjacent Gemeinden on the same recognised Unterkunftsbedarf when the
administrations that actually decide differ by more than 100 € a month in
{between_above_100:.0f} % of the cross-border cases. Regional aggregation to the
Bundesland or to a Raumordnungsregion averages precisely over the steps
documented here, and any
simulated Anspruch, Erwerbsanreiz or exit threshold inherits that error.

## 4. What may not be concluded

**This is not a regression-discontinuity design and contains no causal claim.**
A jump documents an administrative discontinuity: two adjacent Gemeinden read
their cap off different Richtlinien. It does not measure an effect of the border
on rents, on housing, on mobility or on take-up, and no bandwidth, running
variable or continuity assumption is used anywhere. Nor is a higher cap
"generosity": the cap is endogenous to the local housing market, to the
Vergleichsraum the Kreis defined, and to the vintage of its Richtlinie. The
comparison group of part 2 narrows what a step can plausibly reflect; it does
not control for what produced it.

## Geometry note

The committed simplified boundaries cannot carry this analysis: against the
unsimplified source they destroy {n_destroyed} true neighbour pairs and
fabricate {n_fabricated}. The graph is therefore built on the unsimplified
boundaries, whose topology is exact.
"""


def _row(frame: pd.DataFrame, **conditions: object) -> pd.Series:
    mask = pd.Series(data=True, index=frame.index)
    for column, value in conditions.items():
        mask &= frame[column] == value
    matched = frame.loc[mask]
    if len(matched) != 1:
        msg = f"expected exactly one row for {conditions}, found {len(matched)}"
        raise ValueError(msg)
    return matched.iloc[0]


def _summarise_group(group: pd.DataFrame) -> pd.Series:
    quantiles = group["jump_eur"].quantile(list(JUMP_QUANTILES))
    values = {
        "n_pairs": float(len(group)),
        "mean_jump_eur": float(group["jump_eur"].mean()),
        "mean_jump_log": float(group["jump_log"].mean()),
        "share_zero_jump": float((group["jump_eur"] == 0.0).mean()),
    }
    values.update(
        {
            f"p{round(q * 100):02d}_jump_eur": float(quantiles.loc[q])
            for q in JUMP_QUANTILES
        },
    )
    values.update(
        {
            f"share_above_{int(threshold)}_eur": float(
                (group["jump_eur"] > threshold).mean(),
            )
            for threshold in JUMP_EUR_THRESHOLDS
        },
    )
    return pd.Series(values)


def _side_attributes(
    metrics: pd.DataFrame,
    crosswalk: pd.DataFrame,
    zensus_rent: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "ags",
        "policy_region_id",
        "ags_kreis",
        "bundesland",
        "mietenstufe",
        "population",
        "area_sqkm",
    ]
    optional = [name for name in ("gemeinde", "kreis") if name in crosswalk.columns]
    frame = crosswalk.loc[:, [*columns, *optional]].copy()
    frame["population_per_sqkm"] = frame["population"] / frame["area_sqkm"]
    frame = frame.merge(
        metrics.loc[:, ["ags", "centroid_x", "centroid_y", "area_sqm"]],
        on="ags",
        how="left",
    )
    frame = frame.merge(
        zensus_rent.loc[:, ["ags", "rent_eur_per_sqm"]],
        on="ags",
        how="left",
    )
    return frame.set_index("ags")


def _same(frame: pd.DataFrame, column: str) -> pd.Series:
    left = frame[f"{column}_i"]
    right = frame[f"{column}_j"]
    result = left == right
    return result.mask(left.isna() | right.isna()).astype("boolean")


def _border_type(frame: pd.DataFrame) -> pd.Series:
    return pd.Series(
        np.where(
            frame["same_policy_region"].fillna(value=False).to_numpy(dtype=bool),
            BorderType.WITHIN_POLICY_REGION.value,
            np.where(
                frame["same_bundesland"].fillna(value=False).to_numpy(dtype=bool),
                BorderType.BETWEEN_POLICY_REGIONS.value,
                BorderType.BETWEEN_BUNDESLAENDER.value,
            ),
        ),
        index=frame.index,
        dtype="string",
    )


def _log_gap(frame: pd.DataFrame, column: str) -> pd.Series:
    left = pd.to_numeric(frame[f"{column}_i"], errors="coerce").to_numpy(
        dtype=float,
        na_value=np.nan,
    )
    right = pd.to_numeric(frame[f"{column}_j"], errors="coerce").to_numpy(
        dtype=float,
        na_value=np.nan,
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        gap = np.abs(np.log(left) - np.log(right))
    return pd.Series(
        np.where((left > 0) & (right > 0), gap, np.nan),
        index=frame.index,
    )


def _rings(geometry: Mapping[str, Any]) -> Iterator[Sequence[Sequence[float]]]:
    kind = geometry["type"]
    if kind == "Polygon":
        yield from geometry["coordinates"]
    elif kind == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            yield from polygon
    else:
        msg = f"unsupported geometry type: {kind}"
        raise ValueError(msg)


def _match_key_ring(ring: Sequence[Sequence[float]]) -> list[_Vertex]:
    return [
        (
            round(point[0], COORDINATE_MATCH_DECIMALS),
            round(point[1], COORDINATE_MATCH_DECIMALS),
        )
        for point in ring
    ]


def _undirected(start: _Vertex, end: _Vertex) -> _Edge:
    return (start, end) if start <= end else (end, start)


def _unordered_keys(
    owners: Iterable[int],
    codes: Sequence[str],
) -> Iterator[tuple[str, str]]:
    labels = sorted({codes[index] for index in owners})
    for position, left in enumerate(labels):
        for right in labels[position + 1 :]:
            yield (left, right)


def _edge_lengths(edge_owners: Mapping[_Edge, set[int]]) -> dict[_Edge, float]:
    shared = [edge for edge, owners in edge_owners.items() if len(owners) >= 2]  # noqa: PLR2004
    if not shared:
        return {}
    starts = np.array([edge[0] for edge in shared], dtype=float)
    ends = np.array([edge[1] for edge in shared], dtype=float)
    start_x, start_y = project_laea(starts[:, 0], starts[:, 1])
    end_x, end_y = project_laea(ends[:, 0], ends[:, 1])
    lengths = np.hypot(end_x - start_x, end_y - start_y)
    return dict(zip(shared, lengths.tolist(), strict=True))


def _pair_keys(geojson: Mapping[str, Any]) -> set[tuple[str, str]]:
    pairs = neighbour_pairs(geojson)
    return set(zip(pairs["ags_i"], pairs["ags_j"], strict=True))


def _both_in(pair: tuple[str, str], codes: set[str]) -> bool:
    return pair[0] in codes and pair[1] in codes


def _count_overlapping_edges(geojson: Mapping[str, Any]) -> int:
    edge_owners: dict[_Edge, set[int]] = defaultdict(set)
    for index, feature in enumerate(geojson["features"]):
        for ring in _rings(feature["geometry"]):
            for start, end in pairwise(_match_key_ring(ring)):
                if start != end:
                    edge_owners[_undirected(start, end)].add(index)
    return sum(1 for owners in edge_owners.values() if len(owners) > 2)  # noqa: PLR2004


def _fail_if_ags_not_unique(codes: Sequence[str]) -> None:
    duplicated = pd.Series(codes)[pd.Series(codes).duplicated()].tolist()
    if duplicated:
        msg = (
            "boundary features must carry unique eight-digit AGS; "
            f"found duplicates: {sorted(set(duplicated))[:5]}"
        )
        raise ValueError(msg)
