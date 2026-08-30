"""The Gemeinde-level crosswalk joining geography, policy region, and population.

`municipality_crosswalk.parquet` (§5.2) is the one table every other module
uses to move between a Gemeinde, its policy region, and the weights and
subgroups the analysis reports by. Building it is the only place where the
three key formats of this project meet:

- `gemeinde_lookup.arrow` keys on the 12-digit Regionalschlüssel, whose
  eight-digit AGS is its first five and last three characters — the four
  Verbandsgemeinde digits in between are not part of the AGS.
- `kdu_gemeinden.csv` keys on the eight-digit AGS but lost the leading zero of
  every Gemeinde in Schleswig-Holstein through a numeric round trip, so its
  keys are zero-padded back to eight characters on read.
- `gemeinde_population.arrow` already keys on the eight-digit AGS.

AGS is a string throughout, with leading zeros preserved (§6.2). The policy
region is the Kreis (D1), so `policy_region_id` is the five-digit `ags_kreis`.
"""

from pathlib import Path

import pandas as pd

# Schema of `bld/municipality_crosswalk.parquet`.
CROSSWALK_COLUMNS: tuple[str, ...] = (
    "ags",
    "gemeinde",
    "policy_region_id",
    "ags_kreis",
    "kreis",
    "bundesland",
    "is_kreisfrei",
    "mietenstufe",
    "population",
    "area_sqkm",
    "gemeinde_size_class",
    "is_small_gemeinde",
    "jobcenter_id",
)

# Digits in the Gemeinde AGS.
AGS_LENGTH = 8

# Digits in the Kreis AGS, which is also the `policy_region_id` (D1).
KREIS_AGS_LENGTH = 5

_KREISFREI_PREFIXES: tuple[str, ...] = ("Kreisfreie", "Stadtkreis")

# Insel Lütje Hörn, a gemeindefreies Gebiet on the North Sea.
#
# The OpenDataSoft export names it, but its polygon vanishes when the boundaries
# are snapped to the ~1 km grid, so it is absent from `gemeinden.geo.json` and
# from `kdu_gemeinden.csv`. It is dropped from the lookup by name here rather
# than by a silent inner join, so that any other lookup-only AGS raises.
LOOKUP_ONLY_AGS: tuple[str, ...] = ("03457501",)


def build_crosswalk(
    kdu_gemeinden: pd.DataFrame,
    gemeinde_lookup: pd.DataFrame,
    gemeinde_population: pd.DataFrame,
) -> pd.DataFrame:
    """Join the three Gemeinde-keyed inputs into the §5.2 crosswalk.

    Args:
        kdu_gemeinden: The raw wide `kdu_gemeinden.csv`, read as strings.
        gemeinde_lookup: The 12-digit-keyed name and Kreis lookup.
        gemeinde_population: The committed population and area table.

    Returns:
        One row per Gemeinde with `CROSSWALK_COLUMNS`, sorted by AGS.
        `jobcenter_id` is a typed placeholder the BA module fills in later.

    Raises:
        ValueError: If the three inputs do not describe the same Gemeinden.

    """
    kdu = _normalise_kdu(kdu_gemeinden)
    lookup = _normalise_lookup(gemeinde_lookup)
    population = gemeinde_population.assign(
        ags=gemeinde_population["ags"].astype("string"),
    )
    _fail_if_keys_disagree(kdu["ags"], lookup["ags"], population["ags"])

    frame = kdu.merge(lookup, on="ags", how="left", validate="one_to_one").merge(
        population,
        on="ags",
        how="left",
        validate="one_to_one",
    )
    frame["is_kreisfrei"] = _is_kreisfrei(frame["kreis"], frame["ags"])
    frame["jobcenter_id"] = pd.Series(pd.NA, index=frame.index, dtype="string")
    return (
        frame.loc[:, list(CROSSWALK_COLUMNS)]
        .sort_values("ags")
        .reset_index(
            drop=True,
        )
    )


def load_crosswalk(path: Path) -> pd.DataFrame:
    """Load the crosswalk with AGS keys read back as strings."""
    return pd.read_parquet(path)


def to_gemeinde_ags(regionalschluessel: pd.Series) -> pd.Series:
    """Reduce the 12-digit Regionalschlüssel to the eight-digit Gemeinde AGS."""
    codes = regionalschluessel.astype("string")
    return codes.str[:KREIS_AGS_LENGTH] + codes.str[-3:]


def pad_ags(ags: pd.Series) -> pd.Series:
    """Return the AGS as an eight-character string, leading zeros included.

    `data/kdu_gemeinden.csv` stores the AGS correctly as text, so reading it
    with `dtype=str` already yields eight characters. Reading it without
    `dtype=str` makes pandas infer `int64` and drop the leading zero of every
    Schleswig-Holstein AGS, which would then join against nothing. This guards
    that path (plan §6.2: the AGS is a string and joins never run on names).
    """
    return ags.astype("string").str.zfill(AGS_LENGTH)


def _normalise_kdu(kdu_gemeinden: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(index=kdu_gemeinden.index)
    frame["ags"] = pad_ags(kdu_gemeinden["ags_gemeinde"])
    frame["ags_kreis"] = (
        kdu_gemeinden["ags_kreis"].astype("string").str.zfill(KREIS_AGS_LENGTH)
    )
    frame["policy_region_id"] = frame["ags_kreis"]
    frame["mietenstufe"] = pd.to_numeric(
        kdu_gemeinden["wogv_mietstufe"].replace("", None),
        errors="coerce",
    ).astype("Int64")
    _fail_if_kreis_prefix_mismatch(frame)
    return frame


def _normalise_lookup(gemeinde_lookup: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(index=gemeinde_lookup.index)
    frame["ags"] = to_gemeinde_ags(gemeinde_lookup["ags"])
    frame["gemeinde"] = gemeinde_lookup["gemeinde"].astype("string")
    frame["kreis"] = gemeinde_lookup["kreis"].astype("string")
    frame["bundesland"] = gemeinde_lookup["bundesland"].astype("string")
    return frame.loc[~frame["ags"].isin(LOOKUP_ONLY_AGS)].reset_index(drop=True)


def _is_kreisfrei(kreis: pd.Series, ags: pd.Series) -> pd.Series:
    """Flag kreisfreie Städte, cross-checking the name against the AGS.

    A kreisfreie Stadt is the only Gemeinde in its Kreis and carries Gemeinde
    digits `000`; the Kreis is also named "Kreisfreie Stadt …" or, in
    Baden-Württemberg, "Stadtkreis …". Both signals must agree.
    """
    by_name = kreis.str.startswith(_KREISFREI_PREFIXES).fillna(value=False)
    sole_gemeinde = ags.groupby(ags.str[:KREIS_AGS_LENGTH]).transform("size").eq(1)
    by_ags = sole_gemeinde & ags.str.endswith("000")
    disagreeing = ags[by_name != by_ags].tolist()
    if disagreeing:
        msg = (
            "kreisfrei detection disagrees between the Kreis name and the AGS "
            f"for {len(disagreeing)} Gemeinden: {disagreeing[:10]}"
        )
        raise ValueError(msg)
    return by_name


def _fail_if_kreis_prefix_mismatch(frame: pd.DataFrame) -> None:
    mismatched = frame.loc[
        frame["ags"].str[:KREIS_AGS_LENGTH] != frame["ags_kreis"],
        "ags",
    ].tolist()
    if mismatched:
        msg = (
            "ags_kreis must be the first five digits of ags; it is not for "
            f"{len(mismatched)} rows: {mismatched[:10]}"
        )
        raise ValueError(msg)


def _fail_if_keys_disagree(*keys: pd.Series) -> None:
    reference = set(keys[0])
    for other in keys[1:]:
        missing = sorted(reference - set(other))
        extra = sorted(set(other) - reference)
        if missing or extra:
            msg = (
                "crosswalk inputs must cover the same Gemeinden; "
                f"{len(missing)} missing {missing[:10]}, "
                f"{len(extra)} extra {extra[:10]}"
            )
            raise ValueError(msg)
