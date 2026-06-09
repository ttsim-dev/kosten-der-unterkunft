"""Tests for the AGS lookup table."""

import pytest

from kdu.lookup import build_gemeinde_lookup

RAW = {
    "features": [
        {
            "properties": {
                "gem_code": ["146270060060"],
                "gem_name": ["Stadt Großenhain"],
                "gem_name_short": ["Großenhain"],
                "krs_name": ["Landkreis Meißen"],
                "lan_name": ["Sachsen"],
            },
        },
        {
            "properties": {
                "gem_code": ["011110000000"],
                "gem_name": ["Kiel"],
                "gem_name_short": ["Kiel"],
                "krs_name": ["Kiel"],
                "lan_name": ["Schleswig-Holstein"],
            },
        },
    ],
}


def test_build_gemeinde_lookup_maps_ags_to_names() -> None:
    # Input: two features (see RAW above).
    # Expected: AGS-sorted rows with unwrapped scalar names.
    expected_first = {
        "ags": "011110000000",
        "gemeinde": "Kiel",
        "kreis": "Kiel",
        "bundesland": "Schleswig-Holstein",
    }
    # Result.
    result = build_gemeinde_lookup(RAW)
    # Assert.
    assert list(result.columns) == ["ags", "gemeinde", "kreis", "bundesland"]
    assert result.iloc[0].to_dict() == expected_first


def test_build_gemeinde_lookup_raises_on_duplicate_ags() -> None:
    # Input: same AGS twice.
    raw = {"features": [RAW["features"][0], RAW["features"][0]]}
    # Expected / Result / Assert.
    with pytest.raises(ValueError, match="unique"):
        build_gemeinde_lookup(raw)
