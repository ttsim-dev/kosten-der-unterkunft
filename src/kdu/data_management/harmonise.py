"""Turn the wide KdU table into the canonical long table and the two samples.

`data/kdu_gemeinden.csv` is wide: one row per Gemeinde, with a column per
household size for each of four rent concepts. The canonical analysis table is
long, keyed `ags by household_size` (D14), and carries the §6.2 schema together
with the provenance the register supplies.

The three constructions that carry the analytical weight are:

- {func}`build_kdu_bkc_cap` — §6.3's hierarchy, stopping where the source stops.
  A cap is either published as a Bruttokaltmiete or summed from two published
  components. Nothing is multiplied out, scaled, or imputed from a national
  average, because several collectors recorded an explicit Ableitungsverbot.
- {func}`classify_derived_values` — whether each cap was printed in the source
  or computed from components, with `"unknown"` wherever the corpus cannot
  settle it.
- {func}`detect_wogg_linked` — the two independent detectors of D7, kept
  separate so their disagreements stay visible.
"""

import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType

import numpy as np
import pandas as pd

from kdu.config import (
    ANALYSIS_DATE,
    HOUSEHOLD_SIZES,
    LEGAL_VINTAGE,
    MAIN_SAMPLE_HOUSEHOLD_SIZES,
    WOGG_SAFETY_MARKUP,
    WOGG_SAFETY_MARKUP_TOLERANCE,
    ExclusionReason,
)
from kdu.data_management.ba import add_jobcenter_id

# Digits in the Gemeinde AGS, leading zeros included.
AGS_LENGTH = 8

# Digits in the Kreis AGS.
KREIS_AGS_LENGTH = 5

# Digits in the 12-digit Regionalschlüssel used by the boundary source.
SOURCE_AGS_LENGTH = 12

# Two euro amounts count as equal when they differ by less than half a cent.
CENT_TOLERANCE = 0.005

# Household sizes for which the wide table already carries a Höchstbetrag.
# `h = 3` and `h = 5` are added by P0.2 from the same 2026 Anlage 1 (D6);
# until then `wogg_base_cap` is missing for them and every `K/W` object says so.
WOGG_HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 4)

# How many household sizes must show `K/W` at the markup before the ratio
# detector fires.
MIN_WOGG_RATIOS_FOR_DETECTION = 2


class DerivedValueFlag(StrEnum):
    """Whether a `kdu_bkc_cap` was printed in the source or computed from it."""

    PRINTED = "printed"
    """The euro amount appears in the source document itself."""
    COMPUTED = "computed"
    """Summed from a printed Nettokaltmiete and a printed cold-cost cap."""
    UNKNOWN = "unknown"
    """The corpus cannot settle it; never guessed at."""


class PrintedEvidence(StrEnum):
    """Why {class}`DerivedValueFlag` took the value it did."""

    COMPONENTS_SUM = "components_sum"
    """Cap equals the printed Nettokaltmiete plus the printed cold-cost cap."""
    FOUND_IN_TEXT = "found_in_text"
    """The amount was located in the extracted text of a cited document."""
    NOT_FOUND_IN_TEXT = "not_found_in_text"
    """Text exists for the cited document but does not contain the amount."""
    NO_TEXT_AVAILABLE = "no_text_available"
    """No cited document has an extracted text layer."""
    NO_AMOUNTS_IN_TEXT = "no_amounts_in_text"
    """Text exists but contains none of the document's caps, so the table is an image."""
    NO_CAP = "no_cap"
    """There is no cap to classify."""


class CalculationMethod(StrEnum):
    """How `kdu_bkc_cap` was constructed, following §6.3's hierarchy."""

    PUBLISHED_GROSS_COLD_TOTAL = "published_gross_cold_total"
    """§6.3 rule 1: a Bruttokaltmiete total taken over unchanged."""
    SUM_OF_PUBLISHED_COMPONENTS = "sum_of_published_components"
    """§6.3 rule 2: printed Nettokaltmiete plus printed kalte Betriebskosten."""
    NETTO_ONLY_SCENARIO = "netto_only_cold_opex_scenario"
    """Extended sample only: a Nettokaltmiete cap under a cold-opex band."""
    NOT_CONSTRUCTED = "not_constructed"
    """§6.3 rules 5 and 6: no admissible Bruttokaltmiete cap exists."""


class QualityTier(StrEnum):
    """§6.4 quality tiers."""

    A = "A"
    B = "B"
    C = "C"


class QualityTierReason(StrEnum):
    """The single fact that fixed a row's {class}`QualityTier`."""

    PRINTED_GROSS_COLD_VERIFIED = "printed_gross_cold_verified"
    """Tier A: the printed cap was located in the source's own text."""
    COMPONENTS_REPRODUCIBLE = "components_reproducible"
    """Tier B: the cap is the sum of two figures the document prints."""
    GROSS_COLD_UNVERIFIED = "gross_cold_unverified"
    """Tier B: a primary document is held but has no text layer to check."""
    NO_PRIMARY_DOCUMENT = "no_primary_document"
    """Tier C: the citation resolves to no document in the corpus."""
    REGION_ASSIGNMENT_AMBIGUOUS = "region_assignment_ambiguous"
    """Tier C: the region-to-Kreis crosswalk is not `high` confidence."""
    NO_EFFECTIVE_DATE = "no_effective_date"
    """Tier C: no `valid_from` could be evidenced for the rule."""
    HOUSEHOLD_SIZES_INCOMPLETE = "household_sizes_incomplete"
    """Tier C: the document does not cover h = 1…5."""
    COST_CONCEPT_NOT_HARMONISABLE = "cost_concept_not_harmonisable"
    """Tier C: only a Nettokaltmiete cap exists, so a scenario is required."""
    NO_CAP_VALUE = "no_cap_value"
    """Tier C: no cap of either concept."""


class MainSampleExclusionReason(StrEnum):
    """Why a Gemeinde with data is still outside `analysis_sample_main`.

    D3's `ExclusionReason` codes describe Gemeinden with no admissible rule at
    all. These describe Gemeinden that hold a rule the main sample cannot use.
    """

    NUR_NETTOKALTMIETE = "nur_nettokaltmiete"
    """A Nettokaltmiete cap only; extended sample under a cold-opex band (D3)."""
    HAUSHALTSGROESSEN_UNVOLLSTAENDIG = "haushaltsgroessen_unvollstaendig"
    """A Bruttokaltmiete cap, but not for all of h = 1…4."""


def household_suffix(household_size: int) -> str:
    """Return the wide table's column suffix for a household size."""
    return f"{household_size}p"


def load_kdu_wide(path) -> pd.DataFrame:  # noqa: ANN001
    """Read `kdu_gemeinden.csv` with both AGS columns as zero-padded strings."""
    frame = pd.read_csv(path, engine="pyarrow")
    frame["ags_gemeinde"] = frame["ags_gemeinde"].astype("string").str.zfill(AGS_LENGTH)
    frame["ags_kreis"] = frame["ags_kreis"].astype("string").str.zfill(KREIS_AGS_LENGTH)
    return frame


def derive_ags_8(value: object) -> str:
    """Convert a 12-digit Regionalschlüssel to the 8-digit AGS."""
    code = value[0] if isinstance(value, list) else value
    text = str(code)
    if len(text) <= AGS_LENGTH:
        return text.zfill(AGS_LENGTH)
    text = text.zfill(SOURCE_AGS_LENGTH)
    return f"{text[:5]}{text[-3:]}"


def build_geography(
    lookup: pd.DataFrame,
    jobcenter_kreis: pd.DataFrame,
) -> pd.DataFrame:
    """Build the §6.2 geography block from the AGS lookup table.

    `policy_region_id` is the Kreis AGS, because the Kreis is the Träger that
    publishes the Richtlinie (D1). `jobcenter_id` travels down from the
    Jobcenter-to-Kreis crosswalk, because a Gemeinde is served by the Jobcenter
    of its Kreis. Berlin is the one place that fails: twelve Bezirks-Jobcenter
    serve the single Gemeinde Berlin, so no one id describes it and the column
    stays missing there (A10).

    Args:
        lookup: The 12-digit-keyed AGS lookup with names, Kreis and Bundesland.
        jobcenter_kreis: `bld/jobcenter_kreis_crosswalk.parquet`, one row per
            Jobcenter and covered Kreis.

    """
    geography = pd.DataFrame(index=lookup.index)
    geography["ags"] = lookup["ags"].map(derive_ags_8)
    geography["municipality_name"] = lookup["gemeinde"]
    geography["district_ags"] = geography["ags"].str[:KREIS_AGS_LENGTH]
    geography["district_name"] = lookup["kreis"]
    geography["state_code"] = geography["ags"].str[:2]
    geography["state_name"] = lookup["bundesland"]
    geography["municipality_type"] = lookup["gem_type"]
    geography["policy_region_id"] = geography["district_ags"]
    geography["policy_region_name"] = geography["district_name"]
    geography["geometry_vintage"] = LEGAL_VINTAGE.gebietsstand.isoformat()
    geography = add_jobcenter_id(
        geography.rename(columns={"district_ags": "ags_kreis"}),
        jobcenter_kreis,
    ).rename(columns={"ags_kreis": "district_ags"})
    return geography.drop_duplicates(subset="ags").reset_index(drop=True)


def melt_to_long(kdu: pd.DataFrame) -> pd.DataFrame:
    """Reshape the wide cap columns to one row per `ags by household_size`."""
    per_size = []
    for household_size in HOUSEHOLD_SIZES:
        suffix = household_suffix(household_size)
        block = pd.DataFrame(
            {
                "ags": kdu["ags_gemeinde"],
                "household_size": household_size,
                "max_area_sqm": kdu[f"max_wohnflaeche_sqm_{suffix}"],
                "net_cold_cap_total": kdu[f"max_nettokaltmiete_eur_{suffix}"],
                "cold_opex_cap_total": kdu[f"max_kalte_bk_eur_{suffix}"],
                "gross_cold_cap_total": kdu[f"max_bruttokaltmiete_eur_{suffix}"],
            },
        )
        per_size.append(block)
    long = pd.concat(per_size, ignore_index=True)

    per_gemeinde = pd.DataFrame(
        {
            "ags": kdu["ags_gemeinde"],
            "net_cold_cap_per_sqm": kdu["max_nettokaltmiete_eur_sqm"],
            "cold_opex_cap_per_sqm": kdu["max_kalte_bk_eur_sqm"],
            "gross_cold_cap_per_sqm": kdu["max_bruttokaltmiete_eur_sqm"],
            "additional_person_amount": kdu["max_bruttokaltmiete_eur_addl"],
            "additional_person_area_sqm": kdu["max_wohnflaeche_sqm_addl"],
            "kdu_region": kdu["kdu_region"],
            "source_document": kdu["source_document"],
            "valid_from": kdu["valid_from"],
            "notes": kdu["notes"],
            "wogg_mietstufe": kdu["wogg_mietstufe"],
            "wogv_mietstufe": kdu["wogv_mietstufe"],
            "haertefall_regelung": kdu["haertefall_regelung"],
        },
    )
    long = long.merge(per_gemeinde, on="ags", how="left", validate="many_to_one")

    # Heating is outside the Bruttokaltmiete concept and was never collected;
    # the columns exist so the §6.2 schema is complete and visibly empty.
    long["heating_cap_total"] = pd.NA
    long["gross_warm_cap_total"] = pd.NA
    long["valid_to"] = pd.NA
    long["analysis_date"] = ANALYSIS_DATE.isoformat()
    return long.sort_values(["ags", "household_size"]).reset_index(drop=True)


def build_kdu_bkc_cap(long: pd.DataFrame) -> pd.DataFrame:
    """Apply §6.3's hierarchy and return `kdu_bkc_cap` and `calculation_method`.

    Only rules 1 and 2 ever fire:

    - rule 1, a published Bruttokaltmiete total, taken over unchanged
    - rule 2, a published Nettokaltmiete plus a published cold-cost cap

    Rule 3 (multiplying a €/m² figure by an area cap) is deliberately not
    applied. The collectors already worked the sources through that rule and
    left the cell empty wherever the document forbids the derivation, recording
    the Ableitungsverbot in `notes`. Re-deriving here would overwrite that
    judgement with a worse one. Rules 4 to 6 produce no value by construction.
    """
    gross = long["gross_cold_cap_total"]
    components = long["net_cold_cap_total"] + long["cold_opex_cap_total"]

    cap = gross.where(gross.notna(), components)
    method = pd.Series(
        CalculationMethod.NOT_CONSTRUCTED.value,
        index=long.index,
        dtype="string",
    )
    method[components.notna()] = CalculationMethod.SUM_OF_PUBLISHED_COMPONENTS.value
    method[gross.notna()] = CalculationMethod.PUBLISHED_GROSS_COLD_TOTAL.value
    method[cap.isna()] = CalculationMethod.NOT_CONSTRUCTED.value
    return pd.DataFrame({"kdu_bkc_cap": cap, "calculation_method": method})


def classify_derived_values(
    long: pd.DataFrame,
    printed_evidence: Mapping[tuple[str, float], str] | None = None,
) -> pd.DataFrame:
    """Classify each cap as printed, computed, or unknown.

    A cap is `computed` when it equals the sum of a printed Nettokaltmiete and
    a printed cold-cost cap to the cent — the one case the wide table settles on
    its own. Everything else is decided by looking for the euro amount in the
    extracted text of the documents the row cites; where no text exists, or the
    amount is not in it, the flag stays `unknown`.

    Args:
        long: Long table carrying `kdu_bkc_cap` and the component columns.
        printed_evidence: Maps `(source_document, amount)` to a
            {class}`PrintedEvidence` value. Pass `None` to skip the text scan.

    Returns:
        Columns `derived_value_flag` and `printed_evidence`.

    """
    cap = long["kdu_bkc_cap"]
    components = long["net_cold_cap_total"] + long["cold_opex_cap_total"]
    is_computed = (
        cap.notna() & components.notna() & (cap - components).abs().le(CENT_TOLERANCE)
    )

    flag = pd.Series(DerivedValueFlag.UNKNOWN.value, index=long.index, dtype="string")
    evidence = pd.Series(
        PrintedEvidence.NO_TEXT_AVAILABLE.value,
        index=long.index,
        dtype="string",
    )

    if printed_evidence is not None:
        looked_up = [
            printed_evidence.get((document, amount))
            for document, amount in zip(long["source_document"], cap, strict=True)
        ]
        found = pd.Series(looked_up, index=long.index, dtype="object")
        evidence = evidence.mask(found.notna(), found.astype("string"))
        flag[evidence.eq(PrintedEvidence.FOUND_IN_TEXT.value)] = (
            DerivedValueFlag.PRINTED.value
        )

    flag[is_computed] = DerivedValueFlag.COMPUTED.value
    evidence[is_computed] = PrintedEvidence.COMPONENTS_SUM.value
    flag[cap.isna()] = DerivedValueFlag.UNKNOWN.value
    evidence[cap.isna()] = PrintedEvidence.NO_CAP.value
    return pd.DataFrame({"derived_value_flag": flag, "printed_evidence": evidence})


WOGG_LINK_NOTES_PATTERN = re.compile(
    r"sicherheitszuschlag"
    r"|sicherungszuschlag"
    r"|wohngeldtabelle"
    r"|wogg[\s\-]?tabelle"
    r"|§\s*12\s*wogg"
    r"|wogg\s*mietstufe"
    r"|wogg\s*\d{2}\.\d{2}\.\d{4}"
    r"|(?:inkl\.?|zzgl\.?|\+)\s*10\s*%\s*(?:sicherheits|sicherungs)?zuschlag"
    r"|wohngeld.{0,20}h(?:ö|oe)chstbetr",
    re.IGNORECASE,
)


def detect_wogg_linked(long: pd.DataFrame) -> pd.DataFrame:
    """Run D7's two independent WoGG-link detectors and cross-validate them.

    Detector 1 reads `notes` for the Sicherheitszuschlag wording. Detector 2
    tests whether `K/W` sits at the 10 % markup for every household size where
    both a cap and a Hoechstbetrag exist. A Gemeinde is flagged when either
    fires; the two flags are kept as their own columns so the rows where they
    disagree can be listed for manual review rather than silently resolved.

    Args:
        long: Long table carrying `ags`, `notes`, `kdu_bkc_cap`, and
            `wogg_base_cap`.

    Returns:
        One row per Gemeinde with columns `ags`, `wogg_linked_notes`,
        `wogg_linked_ratio`, `wogg_linked_flag`, `wogg_link_detectors_agree`,
        and `n_wogg_ratios`.

    """
    notes = long["notes"].fillna("")
    by_notes = notes.str.contains(WOGG_LINK_NOTES_PATTERN, regex=True)

    ratio = long["kdu_bkc_cap"] / long["wogg_base_cap"]
    at_markup = (ratio - WOGG_SAFETY_MARKUP).abs().le(WOGG_SAFETY_MARKUP_TOLERANCE)
    per_ags = (
        pd.DataFrame(
            {
                "ags": long["ags"],
                "notes_hit": by_notes.to_numpy(),
                "has_ratio": ratio.notna().to_numpy(),
                "at_markup": (at_markup & ratio.notna()).to_numpy(),
            },
        )
        .groupby("ags", as_index=False)
        .agg(
            wogg_linked_notes=("notes_hit", "any"),
            n_wogg_ratios=("has_ratio", "sum"),
            n_at_markup=("at_markup", "sum"),
        )
    )
    per_ags["wogg_linked_ratio"] = per_ags["n_wogg_ratios"].ge(
        MIN_WOGG_RATIOS_FOR_DETECTION,
    ) & per_ags["n_at_markup"].eq(per_ags["n_wogg_ratios"])
    per_ags["wogg_linked_flag"] = (
        per_ags["wogg_linked_notes"] | per_ags["wogg_linked_ratio"]
    )
    per_ags["wogg_link_detectors_agree"] = (
        per_ags["wogg_linked_notes"] == per_ags["wogg_linked_ratio"]
    )
    return per_ags[
        [
            "ags",
            "wogg_linked_notes",
            "wogg_linked_ratio",
            "wogg_linked_flag",
            "wogg_link_detectors_agree",
            "n_wogg_ratios",
        ]
    ]


def wogg_link_disagreements(
    long: pd.DataFrame,
) -> pd.DataFrame:
    """List the Gemeinden where the two WoGG-link detectors disagree.

    D7 requires these to go to manual review rather than be resolved by
    preferring one detector.
    """
    columns = [
        "ags",
        "municipality_name",
        "policy_region_id",
        "policy_region_name",
        "wogg_linked_notes",
        "wogg_linked_ratio",
        "n_wogg_ratios",
        "source_document",
        "notes",
    ]
    disagreeing = long.loc[~long["wogg_link_detectors_agree"], columns]
    return (
        disagreeing.drop_duplicates(subset="ags")
        .sort_values(["policy_region_id", "ags"])
        .reset_index(drop=True)
    )


def assign_quality_tier(long: pd.DataFrame) -> pd.DataFrame:
    """Assign the §6.4 quality tier and the single reason that fixed it.

    Tier A wants a printed Bruttokaltmiete; tier B wants one that is
    reproducible from printed components. A third case exists in this corpus and
    is not in §6.4: a primary document is held, the cap is a Bruttokaltmiete
    total, but the document has no text layer, so `derived_value_flag` is
    `unknown`. Those rows are placed in tier B under the reason
    `gross_cold_unverified`, which keeps them countable and separable from the
    rows §6.4 means by tier B.
    """
    reason = pd.Series(index=long.index, dtype="string")

    has_cap = long["kdu_bkc_cap"].notna()
    printed = long["derived_value_flag"].eq(DerivedValueFlag.PRINTED.value)
    computed = long["derived_value_flag"].eq(DerivedValueFlag.COMPUTED.value)

    reason[has_cap & printed] = QualityTierReason.PRINTED_GROSS_COLD_VERIFIED.value
    reason[has_cap & computed] = QualityTierReason.COMPONENTS_REPRODUCIBLE.value
    reason[has_cap & ~printed & ~computed] = (
        QualityTierReason.GROSS_COLD_UNVERIFIED.value
    )

    # Tier C conditions, applied in increasing order of severity.
    incomplete = ~long["household_sizes_complete"]
    reason[has_cap & incomplete] = QualityTierReason.HOUSEHOLD_SIZES_INCOMPLETE.value
    reason[has_cap & long["valid_from"].isna()] = (
        QualityTierReason.NO_EFFECTIVE_DATE.value
    )
    reason[has_cap & ~long["region_assignment_high_confidence"]] = (
        QualityTierReason.REGION_ASSIGNMENT_AMBIGUOUS.value
    )
    reason[has_cap & ~long["has_primary_document"]] = (
        QualityTierReason.NO_PRIMARY_DOCUMENT.value
    )
    netto_only = ~has_cap & long["net_cold_cap_total"].notna()
    reason[netto_only] = QualityTierReason.COST_CONCEPT_NOT_HARMONISABLE.value
    reason[~has_cap & ~netto_only] = QualityTierReason.NO_CAP_VALUE.value

    tier_by_reason = {
        QualityTierReason.PRINTED_GROSS_COLD_VERIFIED.value: QualityTier.A.value,
        QualityTierReason.COMPONENTS_REPRODUCIBLE.value: QualityTier.B.value,
        QualityTierReason.GROSS_COLD_UNVERIFIED.value: QualityTier.B.value,
    }
    tier = reason.map(tier_by_reason).fillna(QualityTier.C.value).astype("string")
    return pd.DataFrame({"quality_tier": tier, "quality_tier_reason": reason})


def cold_opex_scenario_band(kdu: pd.DataFrame) -> MappingProxyType[str, float]:
    """Derive a low / mid / high cold-opex band in €/m² from local figures alone.

    D3 sends the Netto-only Gemeinden to the extended sample under an explicit
    three-scenario band. §6.3 forbids importing a nationwide average to convert
    them, so the band is read off the €/m² cold-cost caps the KdU documents
    themselves publish: the 10th, 50th, and 90th percentile of the observed
    local figures. It is a band, never a point estimate, and no headline uses it.
    """
    published = kdu["max_kalte_bk_eur_sqm"].dropna()
    implied = (
        (kdu["max_bruttokaltmiete_eur_1p"] - kdu["max_nettokaltmiete_eur_1p"])
        / kdu["max_wohnflaeche_sqm_1p"]
    ).dropna()
    pooled = pd.concat([published, implied], ignore_index=True)
    low, mid, high = pooled.quantile([0.10, 0.50, 0.90]).to_numpy()
    return MappingProxyType(
        {"low": float(low), "mid": float(mid), "high": float(high)},
    )


def apply_cold_opex_scenarios(
    long: pd.DataFrame,
    band: Mapping[str, float],
) -> pd.DataFrame:
    """Add scenario Bruttokaltmiete caps for the Netto-only rows.

    Each scenario adds the band's €/m² figure times the row's own admissible
    Wohnfläche to the published Nettokaltmiete. Where a Gemeinde publishes its
    own €/m² cold-cost figure, that local value replaces the band's mid point.
    """
    netto_only = long["kdu_bkc_cap"].isna() & long["net_cold_cap_total"].notna()
    area = long["max_area_sqm"]
    scenarios = pd.DataFrame(index=long.index)
    for name, rate in band.items():
        per_sqm = pd.Series(rate, index=long.index, dtype="float64")
        if name == "mid":
            per_sqm = long["cold_opex_cap_per_sqm"].fillna(rate)
        scenarios[f"kdu_bkc_cap_scenario_{name}"] = (
            long["net_cold_cap_total"] + per_sqm * area
        ).where(netto_only)
    scenarios["cold_opex_scenario_applied"] = netto_only & area.notna()
    return scenarios


def aggregate_to_policy_region(long: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the long table to Kreis by household size (D1).

    The Kreis is the policy region, but 210 of the 400 Kreise define
    Vergleichsräume internally, so a Kreis is summarised by its dispersion as
    well as its centre. `kdu_bkc_cap` is the unweighted Gemeinde median: no
    population weights exist in the repository yet (D8).
    """
    grouped = long.groupby(["policy_region_id", "household_size"], dropna=False)
    aggregated = grouped.agg(
        policy_region_name=("policy_region_name", "first"),
        state_code=("state_code", "first"),
        state_name=("state_name", "first"),
        n_municipalities=("ags", "size"),
        n_municipalities_with_cap=("kdu_bkc_cap", "count"),
        kdu_bkc_cap=("kdu_bkc_cap", "median"),
        kdu_bkc_cap_min=("kdu_bkc_cap", "min"),
        kdu_bkc_cap_max=("kdu_bkc_cap", "max"),
        n_distinct_caps=("kdu_bkc_cap", "nunique"),
        wogg_base_cap=("wogg_base_cap", "median"),
        share_wogg_linked=("wogg_linked_flag", "mean"),
        share_quality_tier_c=(
            "quality_tier",
            lambda values: float(values.eq(QualityTier.C.value).mean()),
        ),
        valid_from=("valid_from", "first"),
    ).reset_index()
    aggregated["kdu_bkc_cap_range"] = (
        aggregated["kdu_bkc_cap_max"] - aggregated["kdu_bkc_cap_min"]
    )
    aggregated["is_uniform_within_region"] = aggregated["n_distinct_caps"].le(1)
    aggregated["analysis_date"] = ANALYSIS_DATE.isoformat()
    return aggregated


def balanced_municipalities(
    long: pd.DataFrame,
    household_sizes: Sequence[int],
) -> pd.Index:
    """Return the AGS whose `kdu_bkc_cap` is present for every listed size."""
    subset = long[long["household_size"].isin(household_sizes)]
    counts = subset.groupby("ags")["kdu_bkc_cap"].count()
    return counts[counts.eq(len(household_sizes))].index


def build_analysis_samples(long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the long table into the main and extended analysis samples (D3).

    The main sample is the Gemeinden with a Bruttokaltmiete cap for all of
    h = 1…4, restricted to those household sizes. The extended sample adds every
    Gemeinde that holds any usable rule — the unbalanced ones and the Netto-only
    ones under their cold-opex scenario band — each labelled by its stratum.
    """
    main_ags = balanced_municipalities(long, MAIN_SAMPLE_HOUSEHOLD_SIZES)
    main = long[
        long["ags"].isin(main_ags)
        & long["household_size"].isin(MAIN_SAMPLE_HOUSEHOLD_SIZES)
    ].reset_index(drop=True)

    has_any_cap = long.groupby("ags")["kdu_bkc_cap"].transform("count").gt(0)
    has_netto = long.groupby("ags")["net_cold_cap_total"].transform("count").gt(0)
    extended = long[has_any_cap | has_netto].copy()
    extended["sample_stratum"] = np.where(
        extended["ags"].isin(main_ags),
        "main_balanced_h1_h4",
        np.where(
            extended["kdu_bkc_cap"].notna()
            | extended.groupby("ags")["kdu_bkc_cap"].transform("count").gt(0),
            "gross_cold_unbalanced",
            "netto_only_scenario",
        ),
    )
    return main, extended.reset_index(drop=True)


def build_exclusion_log(long: pd.DataFrame) -> pd.DataFrame:
    """Record every Gemeinde outside `analysis_sample_main` and why (D3).

    Gemeinden with no admissible rule of either concept take a D3 reason code
    read off `notes`. Gemeinden that hold a rule the main sample cannot use take
    a {class}`MainSampleExclusionReason` instead, so the two situations never
    get conflated in a coverage table.
    """
    by_ags = long.drop_duplicates(subset="ags").set_index("ags")
    n_caps = long.groupby("ags")["kdu_bkc_cap"].count()
    n_netto = long.groupby("ags")["net_cold_cap_total"].count()
    main_ags = set(balanced_municipalities(long, MAIN_SAMPLE_HOUSEHOLD_SIZES))

    records = []
    for ags, row in by_ags.iterrows():
        if ags in main_ags:
            continue
        if n_caps[ags] > 0:
            reason = MainSampleExclusionReason.HAUSHALTSGROESSEN_UNVOLLSTAENDIG.value
            scope = "main_sample_only"
        elif n_netto[ags] > 0:
            reason = MainSampleExclusionReason.NUR_NETTOKALTMIETE.value
            scope = "main_sample_only"
        else:
            reason = classify_exclusion_reason(row["notes"], row["municipality_type"])
            scope = "all_samples"
        records.append(
            {
                "ags": ags,
                "municipality_name": row["municipality_name"],
                "policy_region_id": row["policy_region_id"],
                "policy_region_name": row["policy_region_name"],
                "state_name": row["state_name"],
                "exclusion_scope": scope,
                "exclusion_reason": reason,
                "n_household_sizes_with_cap": int(n_caps[ags]),
                "n_household_sizes_with_net_cold": int(n_netto[ags]),
                "source_document": row["source_document"],
                "notes": row["notes"],
            },
        )
    return pd.DataFrame.from_records(records).sort_values("ags").reset_index(drop=True)


_EXCLUSION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"ableitungsverbot", re.IGNORECASE),
        ExclusionReason.ABLEITUNGSVERBOT.value,
    ),
    (
        re.compile(r"gemeindefrei", re.IGNORECASE),
        ExclusionReason.GEMEINDEFREIES_GEBIET.value,
    ),
    (
        re.compile(r"bruttowarm|gesamtangemessenheit", re.IGNORECASE),
        ExclusionReason.NUR_BRUTTOWARM.value,
    ),
    (
        re.compile(
            r"nicht\s+(?:ö|oe)ffentlich|nur auf anfrage|kein.{0,20}zugang",
            re.IGNORECASE,
        ),
        ExclusionReason.NICHT_OEFFENTLICH.value,
    ),
    (
        re.compile(
            r"(?:€|eur)\s*/?\s*(?:pro\s*)?(?:qm|m²)|je\s*(?:qm|m²)", re.IGNORECASE
        ),
        ExclusionReason.NUR_EUR_PRO_QM_OHNE_FLAECHE.value,
    ),
)


def classify_exclusion_reason(notes: object, municipality_type: object) -> str:
    """Map a Gemeinde's `notes` to one of D3's reason codes."""
    if (
        isinstance(municipality_type, str)
        and "gemeindefrei" in municipality_type.lower()
    ):
        return ExclusionReason.GEMEINDEFREIES_GEBIET.value
    if not isinstance(notes, str) or not notes.strip():
        return ExclusionReason.KEIN_DOKUMENT.value
    for pattern, reason in _EXCLUSION_PATTERNS:
        if pattern.search(notes):
            return reason
    return ExclusionReason.KEIN_DOKUMENT.value
