"""Tests for the P1.1 neighbour graph and border-jump measures.

The fixtures are hand-built squares whose adjacency is known by
construction, so the assertions pin the definition of §13.2 — a shared
boundary *line*, never a point contact — rather than any property of the
German geometry.
"""

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest

from kdu.analysis.border_jumps import (
    SHORT_BOUNDARY_THRESHOLD_M,
    BorderType,
    ContactType,
    assess_geometry_fitness,
    border_jump_table,
    contact_pairs,
    describe_pairs,
    drop_geometry_artefacts,
    neighbour_pairs,
    polygon_metrics,
    project_laea,
)

# Authalic radius of GRS80, the sphere of equal surface area. Used only to
# derive an independent expected area for the fixture squares.
_AUTHALIC_RADIUS_M = 6_371_007.2


def _spherical_quadrangle_area(*, lat0: float, side: float) -> float:
    return (
        _AUTHALIC_RADIUS_M**2
        * math.radians(side)
        * (math.sin(math.radians(lat0 + side)) - math.sin(math.radians(lat0)))
    )


def _square(ags: str, *, lon0: float, lat0: float, side: float) -> dict[str, Any]:
    ring = [
        [lon0, lat0],
        [lon0 + side, lat0],
        [lon0 + side, lat0 + side],
        [lon0, lat0 + side],
        [lon0, lat0],
    ]
    return {
        "type": "Feature",
        "properties": {"gem_code": f"{ags[:5]}0000{ags[5:]}"},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def _collection(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


@pytest.fixture
def edge_sharing_squares() -> dict[str, Any]:
    """Two unit squares sharing their whole vertical edge."""
    return _collection(
        _square("01001000", lon0=10.0, lat0=52.0, side=0.1),
        _square("01002000", lon0=10.1, lat0=52.0, side=0.1),
    )


@pytest.fixture
def corner_touching_squares() -> dict[str, Any]:
    """Two unit squares meeting in exactly one corner point."""
    return _collection(
        _square("01001000", lon0=10.0, lat0=52.0, side=0.1),
        _square("01002000", lon0=10.1, lat0=52.1, side=0.1),
    )


def test_project_laea_maps_the_projection_origin_to_the_false_origin() -> None:
    """ETRS89/LAEA Europe puts 52°N 10°E at (4 321 000, 3 210 000) metres."""
    x, y = project_laea(np.array([10.0]), np.array([52.0]))
    np.testing.assert_allclose([x[0], y[0]], [4_321_000.0, 3_210_000.0], atol=1e-6)


def test_polygon_metrics_reproduces_the_area_of_a_known_square() -> None:
    """An equal-area projection returns the spherical area of a lon/lat square."""
    metrics = polygon_metrics(
        _collection(_square("01001000", lon0=10.0, lat0=52.0, side=0.1)),
    )
    expected = _spherical_quadrangle_area(lat0=52.0, side=0.1)
    assert metrics.loc[0, "area_sqm"] == pytest.approx(expected, rel=0.01)


def test_squares_sharing_an_edge_are_neighbours(
    edge_sharing_squares: dict[str, Any],
) -> None:
    """A shared boundary line makes two Gemeinden neighbours (§13.2)."""
    pairs = neighbour_pairs(edge_sharing_squares)
    assert pairs.loc[:, ["ags_i", "ags_j"]].to_numpy().tolist() == [
        ["01001000", "01002000"],
    ]


def test_squares_meeting_at_a_corner_are_not_neighbours(
    corner_touching_squares: dict[str, Any],
) -> None:
    """A point contact is excluded from the neighbour graph (§13.2)."""
    assert neighbour_pairs(corner_touching_squares).empty


def test_corner_contact_is_still_recorded_as_a_point_contact(
    corner_touching_squares: dict[str, Any],
) -> None:
    """Point contacts are counted, so the exclusion is visible rather than silent."""
    contacts = contact_pairs(corner_touching_squares)
    assert contacts.loc[:, "contact_type"].tolist() == [ContactType.POINT.value]


def test_shared_boundary_length_matches_the_shared_edge(
    edge_sharing_squares: dict[str, Any],
) -> None:
    """The recorded length is the length of the common edge, not of a polygon."""
    length = neighbour_pairs(edge_sharing_squares).loc[0, "shared_boundary_m"]
    assert length == pytest.approx(0.1 * 111_000.0, rel=0.05)


def test_each_pair_is_stored_exactly_once() -> None:
    """A row of three squares in a line yields two pairs, each listed once."""
    pairs = neighbour_pairs(
        _collection(
            _square("01001000", lon0=10.0, lat0=52.0, side=0.1),
            _square("01002000", lon0=10.1, lat0=52.0, side=0.1),
            _square("01003000", lon0=10.2, lat0=52.0, side=0.1),
        ),
    )
    assert len(pairs) == 2
    assert not pairs.duplicated(subset=["ags_i", "ags_j"]).any()
    assert (pairs["ags_i"] < pairs["ags_j"]).all()


def test_a_pair_is_listed_once_even_when_its_border_is_split_in_two_parts() -> None:
    """Two squares meeting along two separate stretches still form one pair."""
    left: dict[str, Any] = {
        "type": "Feature",
        "properties": {"gem_code": "010010000000"},
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [10.0, 52.0],
                        [10.1, 52.0],
                        [10.1, 52.1],
                        [10.0, 52.1],
                        [10.0, 52.0],
                    ],
                ],
                [
                    [
                        [10.0, 52.2],
                        [10.1, 52.2],
                        [10.1, 52.3],
                        [10.0, 52.3],
                        [10.0, 52.2],
                    ],
                ],
            ],
        },
    }
    right: dict[str, Any] = {
        "type": "Feature",
        "properties": {"gem_code": "010020000000"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [10.1, 52.0],
                    [10.2, 52.0],
                    [10.2, 52.3],
                    [10.1, 52.3],
                    [10.1, 52.2],
                    [10.1, 52.1],
                    [10.1, 52.0],
                ],
            ],
        },
    }
    pairs = neighbour_pairs(_collection(left, right))
    assert len(pairs) == 1


def _pair_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ags_i": ["01001000", "01001000"],
            "ags_j": ["01002000", "01003000"],
            "shared_boundary_m": [5_000.0, 40.0],
            "contact_type": [ContactType.LINE.value, ContactType.LINE.value],
        },
    )


def _cap_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ags": ["01001000", "01002000", "01003000"] * 2,
            "household_size": [1, 1, 1, 2, 2, 2],
            "kdu_bkc_cap": [400.0, 500.0, 400.0, 480.0, 600.0, 480.0],
            "at_safety_markup": [False] * 6,
            "wogg_linked_flag": [False] * 6,
        },
    )


def test_jump_measures_are_symmetric_in_the_two_sides() -> None:
    """`J` and `J^€` are absolute differences, so swapping the caps changes nothing."""
    forward = border_jump_table(_pair_frame(), _cap_frame())
    reversed_pairs = _pair_frame().rename(
        columns={"ags_i": "ags_j", "ags_j": "ags_i"},
    )
    backward = border_jump_table(reversed_pairs, _cap_frame())
    for measure in ("jump_eur", "jump_log"):
        np.testing.assert_allclose(
            forward.sort_values(["household_size", "cap_i", "cap_j"])[measure],
            backward.sort_values(["household_size", "cap_j", "cap_i"])[measure],
        )


def test_log_jump_is_the_absolute_log_ratio_of_the_two_caps() -> None:
    """`J = |log K_i − log K_j|`, computed on the euro caps themselves."""
    jumps = border_jump_table(_pair_frame(), _cap_frame())
    row = jumps.query("ags_j == '01002000' and household_size == 1").iloc[0]
    assert row["jump_log"] == pytest.approx(abs(math.log(400.0) - math.log(500.0)))


def test_artefact_filter_removes_the_short_boundary_pair() -> None:
    """A 40 m common border is below the threshold and drops out (§13.4 point 5)."""
    described = describe_pairs(
        _pair_frame(),
        polygon_metrics(
            _collection(
                _square("01001000", lon0=10.0, lat0=52.0, side=0.1),
                _square("01002000", lon0=10.1, lat0=52.0, side=0.1),
                _square("01003000", lon0=10.2, lat0=52.0, side=0.1),
            ),
        ),
        crosswalk=pd.DataFrame(
            {
                "ags": ["01001000", "01002000", "01003000"],
                "policy_region_id": ["01001", "01002", "01003"],
                "ags_kreis": ["01001", "01002", "01003"],
                "bundesland": ["Schleswig-Holstein"] * 3,
                "mietenstufe": pd.array([3, 3, 3], dtype="Int64"),
                "population": [1000.0, 1000.0, 1000.0],
                "area_sqkm": [10.0, 10.0, 10.0],
            },
        ),
        zensus_rent=pd.DataFrame(
            {
                "ags": ["01001000", "01002000", "01003000"],
                "rent_eur_per_sqm": [7.0] * 3,
            },
        ),
    )
    assert described["possible_geometry_artefact"].tolist() == [False, True]
    kept = drop_geometry_artefacts(described)
    assert kept.loc[:, "ags_j"].tolist() == ["01002000"]
    assert SHORT_BOUNDARY_THRESHOLD_M > 40.0


def test_border_type_separates_within_from_between_policy_regions() -> None:
    """Pairs are typed by whether they cross a policy region and a Bundesland."""
    described = describe_pairs(
        _pair_frame(),
        polygon_metrics(
            _collection(
                _square("01001000", lon0=10.0, lat0=52.0, side=0.1),
                _square("01002000", lon0=10.1, lat0=52.0, side=0.1),
                _square("01003000", lon0=10.2, lat0=52.0, side=0.1),
            ),
        ),
        crosswalk=pd.DataFrame(
            {
                "ags": ["01001000", "01002000", "01003000"],
                "policy_region_id": ["01001", "01001", "02003"],
                "ags_kreis": ["01001", "01001", "02003"],
                "bundesland": ["Schleswig-Holstein", "Schleswig-Holstein", "Hamburg"],
                "mietenstufe": pd.array([3, 4, 3], dtype="Int64"),
                "population": [1000.0, 1000.0, 1000.0],
                "area_sqkm": [10.0, 10.0, 10.0],
            },
        ),
        zensus_rent=pd.DataFrame(
            {
                "ags": ["01001000", "01002000", "01003000"],
                "rent_eur_per_sqm": [7.0] * 3,
            },
        ),
    )
    assert described["border_type"].tolist() == [
        BorderType.WITHIN_POLICY_REGION.value,
        BorderType.BETWEEN_BUNDESLAENDER.value,
    ]


def test_geometry_fitness_reports_both_destroyed_and_fabricated_adjacency() -> None:
    """Snapping that merges two corner-touching squares is caught as fabrication."""
    truthful = _collection(
        _square("01001000", lon0=10.0, lat0=52.0, side=0.1),
        _square("01002000", lon0=10.1004, lat0=52.0, side=0.1),
    )
    snapped = _collection(
        _square("01001000", lon0=10.0, lat0=52.0, side=0.1),
        _square("01002000", lon0=10.1, lat0=52.0, side=0.1),
    )
    fitness = assess_geometry_fitness(truthful, snapped)
    assert fitness.n_fabricated == 1
    assert fitness.n_destroyed == 0
    assert not fitness.is_fit_for_adjacency
