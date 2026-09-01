"""How far a local KdU cap departs from the Grenze ohne schlüssiges Konzept.

Where a Kreis publishes no schlüssiges Konzept, the Angemessenheitsgrenze is
the Wohngeld table plus a Sicherheitszuschlag of 10 % (BSG, 12.12.2013 -
B 4 AS 87/12 R), read here as the Anlage 1 Höchstbetrag together with the
Klimakomponente of § 12 Absatz 7 WoGG. {mod}`kdu.data_management.clean_wohngeld`
builds that Grenze ohne schlüssiges Konzept and records the case law it rests
on. It is the standard every local rule is measured against here, in two ways:

- the departure at a given household size, as a euro difference, a ratio and a
  log ratio;
- the spread of that ratio across household sizes within one Gemeinde, which
  states how far a single per-Gemeinde correction factor can carry a
  tax-transfer model that has only the Grenze ohne schlüssiges Konzept.

The functions here are pure: they take frames and return frames or figures.
{mod}`kdu.kdu_vs_wohngeld.task_cap_comparison` owns the reading and writing.
"""

from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from kdu.config import WeightingScheme
from kdu.joins import merge_without_duplicating
from kdu.weighting import (
    ExtremeAllocation,
    allocate_group_total_to_extreme_value,
    weighted_mean,
    weighted_quantile,
    weighted_share,
    weighted_standard_deviation,
)

pio.templates.default = "plotly_white"

# Household sizes over which the ratio's spread within a Gemeinde is measured.
# Sizes above four are published by too few Träger to compare across regions.
SPREAD_HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4)

# A spread of this many ratio points or more means no single correction factor
# per Gemeinde reproduces the local cap at every household size.
MATERIAL_SPREAD_THRESHOLD = 0.05

# The unemphasised series and the one carrying the claim.
NEUTRAL_COLOUR = "#5f6368"
ACCENT_COLOUR = "#c25e12"

# The household size the euro departure is drawn at. It is the size at which
# every Träger publishes a cap, and the one the single-adult Modellhaushalt of
# {data}`kdu.config.MODEL_HOUSEHOLDS` reads.
ONE_PERSON_HOUSEHOLD_SIZE = 1

# Bins over the euro departure. Enough to show that the distribution has a body
# either side of the Grenze ohne schlüssiges Konzept, few enough that a bar
# survives projection.
DIFFERENCE_HISTOGRAM_BINS = 60

# The deciles drawn on the figure, and the side of their line the label sits
# on. Three carry the claim — the body of the distribution and both tails — and
# every one of them is labelled; further deciles would add lines a reader
# cannot name and one of them would fall next to the line marking the Grenze
# ohne schlüssiges Konzept. The median is the one below that line, so its label
# goes left, away from it and from its own annotations.
DRAWN_DECILE_LABEL_SIDES: MappingProxyType[float, str] = MappingProxyType(
    {
        0.10: "right",
        0.50: "left",
        0.90: "left",
    },
)

# A departure smaller than this counts as none at all. Local caps are published
# to the cent, so the smallest departure a Träger can express is one cent,
# while `wohngeld_fallback_cap` is a floating-point product and carries a
# residue of the order of 1e-13 euro. Any threshold between those two separates
# the same two groups; half a cent is stated because it is the resolution of
# the published figures rather than an artefact of the arithmetic.
BENCHMARK_IDENTITY_TOLERANCE_EUR = 0.005

# Empty margin kept either side of the drawn range, in euro per month.
DIFFERENCE_AXIS_PADDING_EUR = 15.0

# Type sizes for a figure read from the back of a lecture room, where the
# rendered image is 1600 by 900 pixels wide on the slide.
PROJECTED_BODY_FONT_SIZE = 20
PROJECTED_AXIS_TITLE_FONT_SIZE = 24
PROJECTED_ANNOTATION_FONT_SIZE = 20

# Empty space kept above the tallest bar, as a multiple of its height, so the
# annotations sit clear of the data rather than on top of it.
DIFFERENCE_HEADROOM_FACTOR = 1.85

# The plot area's own colour, put behind a label so that a decile line crossing
# it does not run through the type.
ANNOTATION_BACKGROUND = "rgba(255, 255, 255, 0.85)"

# Where each annotation sits in the empty band above the bars, in fractions of
# the plot area. The deciles share the top line; the two annotations that both
# belong to the line marking the Grenze ohne schlüssiges Konzept take one line
# each below it, because their text is long enough to reach across a labelled
# decile.
DECILE_LABEL_HEIGHT = 0.99
BENCHMARK_LABEL_HEIGHT = 0.86
POINT_MASS_LABEL_HEIGHT = 0.75


def build_cap_comparison(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> pd.DataFrame:
    """Join the local cap to the Grenze ohne schlüssiges Konzept and measure the gap.

    Args:
        caps: The local caps, keyed `ags` by `household_size`.
        fallback: The Angemessenheitsgrenze ohne schlüssiges Konzept, keyed the
            same way.
        gemeinden: Gemeinde names, Kreis, Bundesland and population, keyed `ags`.

    Returns:
        One row per `ags` and `household_size`, carrying `cap_difference_eur`,
        `cap_ratio` and `log_cap_ratio` alongside the inputs they derive from.
        A row without a Mietenstufe has no Grenze ohne schlüssiges Konzept and
        so no comparison; the three measures are missing there rather than
        dropped.

    """
    _fail_if_columns_absent(caps, ("ags", "household_size", "kdu_cap"))
    _fail_if_columns_absent(
        fallback,
        ("ags", "household_size", "wohngeld_fallback_cap"),
    )
    _fail_if_columns_absent(gemeinden, ("ags", "district_ags", "state_code"))

    frame = merge_without_duplicating(
        caps,
        fallback,
        on=("ags", "household_size"),
    )
    frame = merge_without_duplicating(frame, gemeinden, on=("ags",))
    return frame.assign(
        cap_difference_eur=lambda df: df["kdu_cap"] - df["wohngeld_fallback_cap"],
        cap_ratio=lambda df: df["kdu_cap"] / df["wohngeld_fallback_cap"],
        log_cap_ratio=lambda df: _natural_log(df["cap_ratio"]),
    )


def cap_ratio_spread_across_household_sizes(frame: pd.DataFrame) -> pd.DataFrame:
    """Measure how far a Gemeinde's departure moves with household size.

    For each Gemeinde the ratio of the local cap to the Grenze ohne schlüssiges
    Konzept is read at household sizes one to four and the spread is the largest
    minus the smallest. A Gemeinde whose rule is a constant multiple of that
    Grenze has a spread of zero; a large spread means the local rule and the
    statutory table rise with household size at different rates.

    The measure is taken on the ratio itself rather than its logarithm, so it
    reads directly as ratio points of the Grenze ohne schlüssiges Konzept.

    Args:
        frame: The output of {func}`build_cap_comparison`.

    Returns:
        One row per Gemeinde observed at every size in
        {data}`SPREAD_HOUSEHOLD_SIZES`, with `cap_ratio_spread`. Gemeinden
        missing any of those sizes are absent, because a spread over a subset
        is not comparable with one over all four.

    """
    _fail_if_columns_absent(frame, ("ags", "household_size", "cap_ratio"))
    observed = frame.loc[
        frame["household_size"].isin(SPREAD_HOUSEHOLD_SIZES),
        ["ags", "household_size", "cap_ratio"],
    ].dropna(subset=["cap_ratio"])

    by_size = observed.pivot_table(
        index="ags",
        columns="household_size",
        values="cap_ratio",
        aggfunc="mean",
    ).reindex(columns=list(SPREAD_HOUSEHOLD_SIZES))
    complete = by_size.dropna()
    spread = (complete.max(axis=1) - complete.min(axis=1)).rename("cap_ratio_spread")
    return spread.reset_index()


def bedarfsgemeinschaft_weights(wohnkostenstatistik: pd.DataFrame) -> pd.DataFrame:
    """Return SGB II Bedarfsgemeinschaften per Kreis and household size.

    Several Jobcenter can serve one Kreis, so their stocks are added together.

    Args:
        wohnkostenstatistik: The cleaned Bundesagentur table.

    Returns:
        One row per `district_ags` and `household_size`, with
        `bedarfsgemeinschaften`.

    """
    _fail_if_columns_absent(
        wohnkostenstatistik,
        ("district_ags", "household_size", "bedarfsgemeinschaften"),
    )
    return (
        wohnkostenstatistik.groupby(["district_ags", "household_size"], as_index=False)[
            "bedarfsgemeinschaften"
        ]
        .sum()
        .astype({"household_size": "int64"})
    )


def allocate_bedarfsgemeinschaften_to_gemeinden(
    weights: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> pd.DataFrame:
    """Spread each Kreis caseload over its Gemeinden by resident population.

    The Bundesagentur publishes Bedarfsgemeinschaften at Jobcenter and so at
    Kreis level; where within a Kreis its claimants live is not observed. The
    Kreis stock at a household size is therefore split in proportion to
    resident population,

        weight(gemeinde, size) = stock(kreis, size) * population(gemeinde)
                                 / total population of the kreis,

    which assumes a claimant rate constant within the Kreis. The denominator
    runs over every Gemeinde the Kreis contains, whether or not its cap is
    known, so a Gemeinde with no cap withholds its share rather than passing it
    to its neighbours.

    Args:
        weights: The output of {func}`bedarfsgemeinschaft_weights`.
        gemeinden: Every Gemeinde with `ags`, `district_ags` and `population`.

    Returns:
        One row per `ags` and `household_size` the Bundesagentur reports, with
        the allocated weight under the name of
        `WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION`. Because
        the shares within a Kreis sum to one, the allocated total at a
        household size equals the reported stock of every Kreis the Gemeinde
        table covers, and never exceeds the national stock.

    """
    _fail_if_columns_absent(
        weights,
        ("district_ags", "household_size", "bedarfsgemeinschaften"),
    )
    _fail_if_columns_absent(gemeinden, ("ags", "district_ags", "population"))

    shares = gemeinden[["ags", "district_ags", "population"]].assign(
        population_share=lambda df: (
            df["population"] / df.groupby("district_ags")["population"].transform("sum")
        ),
    )
    allocated = shares.merge(weights, on="district_ags", how="inner")
    scheme = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION.value
    return allocated.assign(
        **{
            scheme: lambda df: df["bedarfsgemeinschaften"] * df["population_share"],
        },
    ).loc[:, ["ags", "household_size", scheme]]


def allocate_bedarfsgemeinschaften_to_extreme_departure_gemeinde(
    frame: pd.DataFrame,
    district_stock: pd.DataFrame,
    extreme: ExtremeAllocation,
) -> pd.Series:
    """Place each Kreis caseload wholly on its most or least favourable Gemeinde.

    Where within a Kreis its claimants live is unobserved, so the population
    allocation of
    {func}`allocate_bedarfsgemeinschaften_to_gemeinden` is an assumption rather
    than a measurement. This is the pair of allocations that brackets it: the
    Kreis stock at a household size goes entirely to the Gemeinde whose euro
    departure from the Grenze ohne schlüssiges Konzept is smallest, and entirely
    to the Gemeinde whose departure is largest. Between them lies the mean
    departure of every placement of the published stock over that Kreis's
    Gemeinden.

    The extreme is taken on `cap_difference_eur` rather than on the cap itself,
    because that is the quantity the bracket is a bracket on: a Kreis whose
    Mietenstufe varies across its Gemeinden can hold its lowest cap and its
    lowest departure in different Gemeinden. Gemeinden tied on the departure
    share the stock equally, which leaves every statistic of that departure
    unmoved by the tie.

    A Gemeinde without a cap, or without a Mietenstufe and so without a Grenze
    ohne schlüssiges Konzept, is no candidate. A Kreis in which no Gemeinde is a
    candidate allocates nothing, matching the population allocation, whose
    weights on such a Kreis carry no comparison and so drop out of every
    statistic.

    Args:
        frame: The output of {func}`build_cap_comparison`, carrying
            `district_ags`, `household_size` and `cap_difference_eur`.
        district_stock: Bedarfsgemeinschaften per `district_ags` and
            `household_size`, as {func}`bedarfsgemeinschaft_weights` returns
            them.
        extreme: Which end of the Kreis's departures to allocate to.

    Returns:
        A weight per row of `frame`, aligned with its index.

    """
    _fail_if_columns_absent(
        frame,
        ("district_ags", "household_size", "cap_difference_eur"),
    )
    _fail_if_columns_absent(
        district_stock,
        ("district_ags", "household_size", "bedarfsgemeinschaften"),
    )
    with_stock = merge_without_duplicating(
        frame[["district_ags", "household_size", "cap_difference_eur"]],
        district_stock,
        on=("district_ags", "household_size"),
    ).set_index(frame.index)
    return allocate_group_total_to_extreme_value(
        values=with_stock["cap_difference_eur"],
        groups=_kreis_and_household_size(with_stock),
        group_totals=with_stock["bedarfsgemeinschaften"],
        extreme=extreme,
    )


def attach_weights(
    frame: pd.DataFrame, allocated_weights: pd.DataFrame
) -> pd.DataFrame:
    """Attach every weighting scheme as a column named after it.

    Args:
        frame: The output of {func}`build_cap_comparison`.
        allocated_weights: The output of
            {func}`allocate_bedarfsgemeinschaften_to_gemeinden`.

    Returns:
        `frame` with one column per member of
        {class}`kdu.config.WeightingScheme`. A Gemeinde in a Kreis the
        Bundesagentur does not report carries a Bedarfsgemeinschaft weight of
        zero under all three Bedarfsgemeinschaft schemes, so it drops out of
        those without dropping out of the Gemeinde weight.

    """
    by_population = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION.value
    attached = merge_without_duplicating(
        frame,
        allocated_weights,
        on=("ags", "household_size"),
    ).assign(
        **{
            WeightingScheme.GEMEINDE_UNWEIGHTED.value: 1.0,
            by_population: lambda df: df[by_population].fillna(0.0),
        },
    )
    district_stock = _recover_district_stock(attached, allocated_weights)
    return attached.assign(
        **{
            WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_TO_LOWEST_DEPARTURE.value: (
                allocate_bedarfsgemeinschaften_to_extreme_departure_gemeinde(
                    attached,
                    district_stock,
                    ExtremeAllocation.LOWEST,
                )
            ),
            WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_TO_HIGHEST_DEPARTURE.value: (
                allocate_bedarfsgemeinschaften_to_extreme_departure_gemeinde(
                    attached,
                    district_stock,
                    ExtremeAllocation.HIGHEST,
                )
            ),
        },
    )


def summarise_cap_ratio(frame: pd.DataFrame) -> pd.DataFrame:
    """Describe the ratio of local cap to Grenze ohne schlüssiges Konzept by size.

    Args:
        frame: The output of {func}`attach_weights`.

    Returns:
        A long table with one row per measure, weighting scheme, household
        size and statistic.

    """
    _fail_if_columns_absent(frame, ("household_size", "cap_ratio"))
    rows: list[dict[str, object]] = []
    for scheme in WeightingScheme:
        for household_size, part in frame.groupby("household_size", dropna=False):
            values = part["cap_ratio"]
            weight = part[scheme.value]
            rows.extend(
                {
                    "measure": "cap_ratio",
                    "weighting_scheme": scheme.value,
                    "household_size": household_size,
                    "statistic": statistic,
                    "value": value,
                }
                for statistic, value in _cap_ratio_statistics(values, weight).items()
            )
    return pd.DataFrame(rows)


def summarise_cap_difference_eur(frame: pd.DataFrame) -> pd.DataFrame:
    """Describe the euro gap to the Grenze ohne schlüssiges Konzept by size.

    The ratio says how far a cap departs in proportional terms; the euro
    difference says what that is worth per month, which is the figure a
    Bedarfsgemeinschaft's budget is stated in.

    Args:
        frame: The output of {func}`attach_weights`.

    Returns:
        A long table shaped like {func}`summarise_cap_ratio`, carrying the
        mean, every decile from `p10` to `p90`, and the share of the
        distribution below the Grenze ohne schlüssiges Konzept.

    """
    _fail_if_columns_absent(frame, ("household_size", "cap_difference_eur"))
    rows: list[dict[str, object]] = []
    for scheme in WeightingScheme:
        for household_size, part in frame.groupby("household_size", dropna=False):
            values = part["cap_difference_eur"]
            weight = part[scheme.value]
            rows.extend(
                {
                    "measure": "cap_difference_eur",
                    "weighting_scheme": scheme.value,
                    "household_size": household_size,
                    "statistic": statistic,
                    "value": value,
                }
                for statistic, value in _cap_difference_statistics(
                    values,
                    weight,
                ).items()
            )
    return pd.DataFrame(rows)


def summarise_cap_ratio_spread(spread: pd.DataFrame) -> pd.DataFrame:
    """Describe the spread of the ratio across household sizes.

    Args:
        spread: The output of {func}`cap_ratio_spread_across_household_sizes`.

    Returns:
        A long table shaped like {func}`summarise_cap_ratio`, with the
        household size left missing because the measure spans sizes one to
        four.

    """
    _fail_if_columns_absent(spread, ("cap_ratio_spread",))
    values = spread["cap_ratio_spread"]
    weight = pd.Series(1.0, index=spread.index)
    statistics = {
        "n": float(values.notna().sum()),
        "median": weighted_quantile(values, weight, 0.5),
        "p10": weighted_quantile(values, weight, 0.10),
        "p90": weighted_quantile(values, weight, 0.90),
        "share_above_material_threshold": weighted_share(
            values > MATERIAL_SPREAD_THRESHOLD,
            weight,
        ),
    }
    return pd.DataFrame(
        {
            "measure": "cap_ratio_spread_across_household_sizes",
            "weighting_scheme": WeightingScheme.GEMEINDE_UNWEIGHTED.value,
            "household_size": pd.NA,
            "statistic": statistic,
            "value": value,
        }
        for statistic, value in statistics.items()
    )


@dataclass(frozen=True)
class BenchmarkPointMass:
    """The Gemeinden whose one-person cap is the Grenze ohne schlüssiges Konzept."""

    count: int
    """Gemeinden whose euro departure from that Grenze is zero."""
    compared: int
    """Gemeinden with both a cap and that Grenze at household size one."""

    @property
    def share(self) -> float:
        """`count` as a fraction of `compared`, or zero if nothing is compared."""
        return self.count / self.compared if self.compared else 0.0


def count_gemeinden_at_benchmark(frame: pd.DataFrame) -> BenchmarkPointMass:
    """Count the one-person caps that coincide with the Grenze ohne schlüssiges Konzept.

    A Träger that has adopted the construction the Angemessenheitsgrenze ohne
    schlüssiges Konzept is built from — Anlage 1 Höchstbetrag plus
    Klimakomponente, the sum times 1.10 — publishes that Grenze itself, and its
    departure is an arithmetic identity rather than a finding. Those Gemeinden
    are the point mass at zero in the distribution of `cap_difference_eur`, and
    this states how many of them there are.

    Coincidence is read as `np.isclose` with an absolute tolerance of
    {data}`BENCHMARK_IDENTITY_TOLERANCE_EUR` and no relative term, not as exact
    equality. `wohngeld_fallback_cap` is a floating-point product, so a Träger
    publishing the same euro amount lands a residue of the order of 1e-13 euro
    away from it, which exact equality would count as a departure. The published
    caps carry two decimals, so the smallest departure a Träger can express is
    one cent, and no observed departure falls between the two: the count is the
    same for every tolerance from 1e-13 up to a cent.

    Args:
        frame: The output of {func}`build_cap_comparison`.

    Returns:
        The count and the number of Gemeinden it is a count out of, both at
        household size one. Rows without a cap or without a Grenze ohne
        schlüssiges Konzept are neither counted nor compared.

    """
    _fail_if_columns_absent(frame, ("household_size", "cap_difference_eur"))
    differences = _one_person_differences(frame)["cap_difference_eur"]
    at_benchmark = np.isclose(
        differences.to_numpy(dtype="float64"),
        0.0,
        rtol=0.0,
        atol=BENCHMARK_IDENTITY_TOLERANCE_EUR,
    )
    return BenchmarkPointMass(count=int(at_benchmark.sum()), compared=len(differences))


def plot_cap_ratio_distribution(frame: pd.DataFrame) -> go.Figure:
    """Draw the ratio of local cap to Grenze ohne schlüssiges Konzept by size.

    Args:
        frame: The output of {func}`build_cap_comparison`.

    Returns:
        A box plot per household size, with the Grenze ohne schlüssiges Konzept
        drawn as a reference line at one.

    """
    figure = px.box(
        frame.dropna(subset=["cap_ratio"]),
        x="household_size",
        y="cap_ratio",
        color_discrete_sequence=[ACCENT_COLOUR],
        points=False,
        labels={
            "household_size": "Household size",
            "cap_ratio": "Local cap ÷ Grenze ohne schlüssiges Konzept",
        },
    )
    figure.add_hline(
        y=1.0,
        line_dash="dot",
        line_color=NEUTRAL_COLOUR,
        annotation_text="Angemessenheitsgrenze ohne schlüssiges Konzept",
        annotation_position="top left",
        annotation_font_size=PROJECTED_ANNOTATION_FONT_SIZE,
    )
    figure.update_layout(
        showlegend=False,
        boxgap=0.4,
        font_size=PROJECTED_BODY_FONT_SIZE,
    )
    figure.update_xaxes(
        tickfont_size=PROJECTED_BODY_FONT_SIZE,
        title_font_size=PROJECTED_AXIS_TITLE_FONT_SIZE,
    )
    figure.update_yaxes(
        tickformat=".2f",
        tickfont_size=PROJECTED_BODY_FONT_SIZE,
        title_font_size=PROJECTED_AXIS_TITLE_FONT_SIZE,
    )
    return figure


def plot_cap_difference_distribution(frame: pd.DataFrame) -> go.Figure:
    """Draw the one-person euro departure from the Grenze ohne schlüssiges Konzept.

    The figure is the euro counterpart of the summary
    {func}`summarise_cap_difference_eur` writes: the same measure, the same
    household size and the same weighting, so a decile read off the figure is
    the decile in the table.

    Args:
        frame: The output of {func}`build_cap_comparison`.

    Returns:
        A histogram of `cap_difference_eur` at household size one under one
        Gemeinde one weight. The tenth, fiftieth and ninetieth percentile are
        drawn and labelled, the Grenze ohne schlüssiges Konzept is marked at
        zero by a heavier dashed line, and the Gemeinden sitting on it are
        counted beside that line. Every label sits in a band of empty space
        above the tallest bar. The axis titles carry the estimand, the unit,
        the weighting and the number of Gemeinden, the last read from `frame`
        rather than fixed.

    """
    _fail_if_columns_absent(frame, ("household_size", "cap_difference_eur"))
    differences = _one_person_differences(frame)
    values = differences["cap_difference_eur"]
    figure = px.histogram(
        differences,
        x="cap_difference_eur",
        nbins=DIFFERENCE_HISTOGRAM_BINS,
        color_discrete_sequence=[ACCENT_COLOUR],
        labels={
            "cap_difference_eur": (
                "Local one-person KdU cap minus Grenze ohne schlüssiges Konzept, "
                "EUR per month"
            ),
        },
    )
    _mark_deciles(figure, values)
    figure.add_vline(
        x=0.0,
        line_width=3,
        line_dash="dash",
        line_color=NEUTRAL_COLOUR,
    )
    _annotate_benchmark(figure, count_gemeinden_at_benchmark(frame))
    figure.update_layout(
        yaxis_title=(f"Gemeinden (one Gemeinde one weight; n = {len(differences):,})"),
        showlegend=False,
        bargap=0.05,
        font_size=PROJECTED_BODY_FONT_SIZE,
    )
    figure.update_xaxes(
        tickfont_size=PROJECTED_BODY_FONT_SIZE,
        title_font_size=PROJECTED_AXIS_TITLE_FONT_SIZE,
        ticksuffix=" €",
        range=[
            values.min() - DIFFERENCE_AXIS_PADDING_EUR,
            values.max() + DIFFERENCE_AXIS_PADDING_EUR,
        ],
    )
    figure.update_yaxes(
        tickfont_size=PROJECTED_BODY_FONT_SIZE,
        title_font_size=PROJECTED_AXIS_TITLE_FONT_SIZE,
        range=[0.0, _tallest_bar(values) * DIFFERENCE_HEADROOM_FACTOR],
    )
    return figure


def plot_cap_ratio_spread_distribution(spread: pd.DataFrame) -> go.Figure:
    """Draw how far the ratio moves across household sizes within a Gemeinde.

    Args:
        spread: The output of {func}`cap_ratio_spread_across_household_sizes`.

    Returns:
        An empirical cumulative distribution with the material threshold
        marked.

    """
    figure = px.ecdf(
        spread.dropna(subset=["cap_ratio_spread"]),
        x="cap_ratio_spread",
        color_discrete_sequence=[ACCENT_COLOUR],
        labels={
            "cap_ratio_spread": (
                "Largest minus smallest ratio of local cap to Grenze ohne "
                "schlüssiges Konzept,<br>over household sizes 1 to 4"
            ),
        },
    )
    figure.add_vline(
        x=MATERIAL_SPREAD_THRESHOLD,
        line_dash="dot",
        line_color=NEUTRAL_COLOUR,
        annotation_text=f"{MATERIAL_SPREAD_THRESHOLD:.2f} ratio points",
        annotation_position="top right",
        annotation_font_size=PROJECTED_ANNOTATION_FONT_SIZE,
    )
    figure.update_layout(
        yaxis_title="Share of Gemeinden at or below",
        showlegend=False,
        font_size=PROJECTED_BODY_FONT_SIZE,
    )
    figure.update_xaxes(
        range=[0, 0.3],
        tickfont_size=PROJECTED_BODY_FONT_SIZE,
        title_font_size=PROJECTED_AXIS_TITLE_FONT_SIZE,
    )
    figure.update_yaxes(
        tickfont_size=PROJECTED_BODY_FONT_SIZE,
        title_font_size=PROJECTED_AXIS_TITLE_FONT_SIZE,
    )
    return figure


def _one_person_differences(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the euro departures observed at household size one."""
    return (
        frame.loc[
            frame["household_size"].eq(ONE_PERSON_HOUSEHOLD_SIZE),
            ["cap_difference_eur"],
        ]
        .dropna()
        .astype({"cap_difference_eur": "float64"})
    )


def _mark_deciles(figure: go.Figure, differences: pd.Series) -> None:
    """Draw and label the three deciles the euro summary is quoted from."""
    weight = pd.Series(1.0, index=differences.index)
    for decile, side in DRAWN_DECILE_LABEL_SIDES.items():
        value = weighted_quantile(differences, weight, decile)
        figure.add_vline(
            x=value,
            line_width=2,
            line_dash="dot",
            line_color=NEUTRAL_COLOUR,
        )
        _add_label(
            figure,
            x=value,
            y=DECILE_LABEL_HEIGHT,
            text=f"p{round(decile * 100)}<br>{value:+.0f} €",
            side=side,
        )


def _annotate_benchmark(figure: go.Figure, point_mass: BenchmarkPointMass) -> None:
    """Name the reference line and count the Gemeinden that sit on it."""
    _add_label(
        figure,
        x=0.0,
        y=BENCHMARK_LABEL_HEIGHT,
        text="Angemessenheitsgrenze ohne schlüssiges Konzept",
        side="right",
    )
    gemeinde_word = "Gemeinde" if point_mass.count == 1 else "Gemeinden"
    _add_label(
        figure,
        x=0.0,
        y=POINT_MASS_LABEL_HEIGHT,
        text=(
            f"{point_mass.count:,} {gemeinde_word} "
            f"({point_mass.share:.1%}) exactly on that Grenze"
        ),
        side="right",
    )


def _add_label(figure: go.Figure, x: float, y: float, text: str, side: str) -> None:
    """Place one label beside a vertical line, at `y` of the plot area's height."""
    figure.add_annotation(
        x=x,
        y=y,
        yref="paper",
        text=text,
        showarrow=False,
        xanchor="left" if side == "right" else "right",
        yanchor="top",
        xshift=6 if side == "right" else -6,
        align="left" if side == "right" else "right",
        font_size=PROJECTED_ANNOTATION_FONT_SIZE,
        font_color=NEUTRAL_COLOUR,
        bgcolor=ANNOTATION_BACKGROUND,
        borderpad=4,
    )


def _tallest_bar(differences: pd.Series) -> float:
    """Return the height of the histogram's tallest bar.

    Plotly bins the values itself when the figure is drawn, so the count is
    taken here over bins of the same number and range. A bin boundary landing
    elsewhere than Plotly puts it moves the height by a bar or two, which the
    headroom the caller adds absorbs.
    """
    counts, _ = np.histogram(
        differences.to_numpy(dtype="float64"),
        bins=DIFFERENCE_HISTOGRAM_BINS,
    )
    return float(counts.max())


def _recover_district_stock(
    frame: pd.DataFrame,
    allocated_weights: pd.DataFrame,
) -> pd.DataFrame:
    """Return the published Kreis stock the population allocation was built from.

    {func}`allocate_bedarfsgemeinschaften_to_gemeinden` splits each Kreis stock
    over every Gemeinde of that Kreis in shares that sum to one, so adding those
    shares back up over a Kreis returns the stock the Bundesagentur published
    for it. Reading it back this way keeps the extreme allocations on exactly
    the totals the population allocation used.

    Args:
        frame: A frame carrying `ags` and `district_ags` for every Gemeinde the
            allocation covers.
        allocated_weights: The output of
            {func}`allocate_bedarfsgemeinschaften_to_gemeinden`.

    Returns:
        One row per `district_ags` and `household_size`, with
        `bedarfsgemeinschaften`.

    Raises:
        ValueError: If the allocation covers a Gemeinde `frame` does not place
            in a Kreis, which would lose part of that Kreis's stock.

    """
    by_population = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION.value
    districts = frame[["ags", "district_ags"]].drop_duplicates()
    joined = merge_without_duplicating(allocated_weights, districts, on=("ags",))
    _fail_if_kreis_unknown(joined)
    per_kreis = joined.groupby(["district_ags", "household_size"], as_index=False)
    return (
        per_kreis[by_population]
        .sum()
        .rename(
            columns={by_population: "bedarfsgemeinschaften"},
        )
    )


def _kreis_and_household_size(frame: pd.DataFrame) -> pd.Series:
    """Return each row's Kreis and household size as one grouping label.

    The allocation groups on the pair, because the Bundesagentur publishes one
    stock per Kreis and household size. The label is local to that grouping and
    is never a key of any stored table.
    """
    return (
        frame["district_ags"].astype("string")
        + " "
        + frame["household_size"].astype("string")
    )


def _fail_if_kreis_unknown(frame: pd.DataFrame) -> None:
    """Raise if any allocated Gemeinde could not be placed in a Kreis."""
    unplaced = frame.loc[frame["district_ags"].isna(), "ags"]
    if not unplaced.empty:
        msg = (
            f"{len(unplaced)} allocated Gemeinde(n) are absent from the comparison "
            f"frame and so carry no Kreis; examples: {sorted(unplaced)[:5]}"
        )
        raise ValueError(msg)


def _cap_ratio_statistics(
    values: pd.Series,
    weight: pd.Series,
) -> dict[str, float]:
    """Return the statistics reported for one household size."""
    return {
        "n": float(values.notna().sum()),
        "mean": weighted_mean(values, weight),
        "median": weighted_quantile(values, weight, 0.5),
        "p10": weighted_quantile(values, weight, 0.10),
        "p90": weighted_quantile(values, weight, 0.90),
        "standard_deviation": weighted_standard_deviation(values, weight),
        "share_below_fallback": weighted_share(values < 1.0, weight),
    }


def _cap_difference_statistics(
    values: pd.Series,
    weight: pd.Series,
) -> dict[str, float]:
    """Return the euro statistics reported for one household size."""
    deciles = {
        f"p{decile}0": weighted_quantile(values, weight, decile / 10)
        for decile in range(1, 10)
    }
    return {
        "n": float(values.notna().sum()),
        "mean": weighted_mean(values, weight),
        "median": weighted_quantile(values, weight, 0.5),
        **deciles,
        "share_below_fallback": weighted_share(values < 0.0, weight),
    }


def _natural_log(values: pd.Series) -> pd.Series:
    """Return the natural logarithm, missing where the argument is not positive."""
    numeric = pd.to_numeric(values, errors="coerce").astype("Float64")
    positive = numeric.where(numeric > 0)
    return pd.Series(
        np.log(positive.to_numpy(dtype="float64")),
        index=values.index,
        dtype="Float64",
    )


def _fail_if_columns_absent(frame: pd.DataFrame, required: tuple[str, ...]) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        msg = f"frame is missing required column(s) {missing}"
        raise ValueError(msg)
