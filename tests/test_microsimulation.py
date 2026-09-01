"""Deduplication, case construction and bracketing for the exit threshold."""

import numpy as np
import pandas as pd
import pytest

from kdu.eligibility.microsimulation import (
    CASE_COLUMNS,
    SCENARIO_FALLBACK,
    SCENARIO_LOCAL_CAP,
    EntitlementProfile,
    _bracket_from_ladder,
    _plot_ceiling_eur_per_month,
    assign_cap_pairs,
    build_cases,
    distinct_cap_pairs,
    national_heizkosten_eur_per_month,
    plot_entitlement_profile,
    plot_exit_threshold_distribution,
    summarise_exit_thresholds,
    wohnflaeche_sqm,
)


@pytest.fixture
def sample() -> pd.DataFrame:
    """Four Gemeinden, two of which share a cap and a Mietenstufe."""
    return pd.DataFrame(
        {
            "ags": ["01001000", "01002000", "01003000", "01004000"],
            "household_size": [1, 1, 1, 1],
            "kdu_cap": [486.0, 486.0, 500.0, 400.0],
            "mietenstufe": [3, 3, 3, 1],
            "wohngeld_fallback_cap": [501.6, 501.6, 501.6, 390.5],
        },
    )


def test_distinct_cap_pairs_collapses_gemeinden_that_share_a_cap(
    sample: pd.DataFrame,
) -> None:
    """Four Gemeinden with three distinct cap and Mietenstufe pairs yield three rows."""
    assert len(distinct_cap_pairs(sample, 1)) == 3


def test_distinct_cap_pairs_counts_the_gemeinden_behind_each_pair(
    sample: pd.DataFrame,
) -> None:
    """The pair shared by two Gemeinden records both of them."""
    pairs = distinct_cap_pairs(sample, 1)
    shared = pairs.query("kdu_cap == 486.0 and mietenstufe == 3")
    assert int(shared["n_gemeinden"].iloc[0]) == 2


def test_assign_cap_pairs_returns_one_row_per_gemeinde(
    sample: pd.DataFrame,
) -> None:
    """Joining the pairs back never duplicates or drops a Gemeinde."""
    assigned = assign_cap_pairs(sample, distinct_cap_pairs(sample, 1), 1)
    assert len(assigned) == 4


def test_build_cases_yields_two_scenarios_per_cap_pair(
    sample: pd.DataFrame,
) -> None:
    """Each cap pair enters the simulation once under each cap."""
    pairs = distinct_cap_pairs(sample, 1)
    rent = np.full(len(pairs), 900.0)
    cases = build_cases(pairs, "single_35", rent, 67.76, np.zeros(len(pairs)))
    assert len(cases) == 2 * len(pairs)


def test_build_cases_recognises_each_scenario_s_own_cap(
    sample: pd.DataFrame,
) -> None:
    """With a rent above both caps, each scenario recognises exactly its cap."""
    pairs = distinct_cap_pairs(sample, 1).query("kdu_cap == 486.0")
    rent = np.full(len(pairs), 900.0)
    cases = build_cases(pairs, "single_35", rent, 0.0, np.zeros(len(pairs)))
    recognised = cases.set_index("scenario")["recognised_bruttokaltmiete"]
    assert recognised[SCENARIO_LOCAL_CAP] == 486.0
    assert recognised[SCENARIO_FALLBACK] == 501.6


def test_build_cases_produces_every_required_column(sample: pd.DataFrame) -> None:
    """`evaluate` reads a fixed set of columns and `build_cases` supplies them."""
    pairs = distinct_cap_pairs(sample, 1)
    cases = build_cases(
        pairs,
        "single_35",
        np.full(len(pairs), 900.0),
        67.76,
        np.zeros(len(pairs)),
    )
    assert tuple(cases.columns) == CASE_COLUMNS


def test_bracket_from_ladder_encloses_the_income_where_the_claim_vanishes() -> None:
    """The bracket is the last income with a claim and the first without."""
    claims = np.array([[300.0, 200.0, 100.0, 0.0, 0.0]])
    ladder = np.array([0.0, 500.0, 1000.0, 1500.0, 2000.0])
    lower, upper = _bracket_from_ladder(claims, ladder)
    np.testing.assert_allclose(lower, [1000.0])
    np.testing.assert_allclose(upper, [1500.0])


def test_bracket_from_ladder_returns_zero_when_no_claim_exists_at_all() -> None:
    """A household with no claim even at zero income exits at zero."""
    claims = np.array([[0.0, 0.0]])
    ladder = np.array([0.0, 500.0])
    lower, upper = _bracket_from_ladder(claims, ladder)
    np.testing.assert_allclose(lower, [0.0])
    np.testing.assert_allclose(upper, [0.0])


def test_wohnflaeche_grows_by_fifteen_square_metres_per_further_person() -> None:
    """A four-person household is credited 45 plus three times 15 square metres."""
    assert wohnflaeche_sqm(4) == 90.0


def test_national_heizkosten_weights_jobcenter_by_their_stock() -> None:
    """A large Jobcenter moves the national mean more than a small one."""
    statistic = pd.DataFrame(
        {
            "jobcenter_id": ["t01", "t02"],
            "household_size": [1, 1],
            "recognised_heizkosten": [100.0, 200.0],
            "bedarfsgemeinschaften": [300.0, 100.0],
        },
    )

    heating = national_heizkosten_eur_per_month(statistic)

    # (300 * 100 + 100 * 200) / 400 = 125
    assert heating.per_household_size[1] == 125.0


def test_summarise_exit_thresholds_reports_the_amplification() -> None:
    """The amplification is the median ratio over Gemeinden where the caps differ."""
    thresholds = pd.DataFrame(
        {
            "household_key": ["single_35"] * 3,
            "cap_difference": [10.0, 100.0, 0.0],
            "exit_threshold_difference": [20.0, 200.0, 0.0],
        },
    )
    summary = summarise_exit_thresholds(thresholds)
    assert summary["amplification"].iloc[0] == 2.0


def test_plot_ceiling_clears_the_higher_exit_threshold() -> None:
    """The income axis extends past the later of the two zero crossings."""
    assert _plot_ceiling_eur_per_month([2071.0, 2459.0]) > 2459.0


def test_plot_ceiling_snaps_to_a_round_income() -> None:
    """The income axis ends on a multiple of fifty euro."""
    assert _plot_ceiling_eur_per_month([2071.0, 2459.0]) % 50.0 == 0.0


@pytest.fixture
def profile() -> EntitlementProfile:
    """Bad Homburg v.d.Höhe: a claim that falls linearly to zero under each cap."""
    incomes = np.linspace(0.0, 2800.0, 15)
    curves = pd.concat(
        [
            pd.DataFrame(
                {
                    "scenario": scenario,
                    "gross_income": incomes,
                    "anspruch": np.maximum(
                        claim_at_zero * (1.0 - incomes / exit_), 0.0
                    ),
                },
            )
            for scenario, claim_at_zero, exit_ in (
                (SCENARIO_LOCAL_CAP, 1100.0, 2071.0),
                (SCENARIO_FALLBACK, 1330.0, 2459.0),
            )
        ],
        ignore_index=True,
    )
    return EntitlementProfile(
        curves=curves,
        ags="06434001",
        household_key="single_35",
        local_cap=539.0,
        wohngeld_fallback_cap=765.82,
        exit_threshold_local_cap=2071.0,
        exit_threshold_fallback=2459.0,
    )


def test_entitlement_profile_reports_the_rent_not_recognised(
    profile: EntitlementProfile,
) -> None:
    """The local cap of Bad Homburg recognises 226.82 EUR less rent per month."""
    assert profile.rent_not_recognised == pytest.approx(226.82)


def test_entitlement_profile_reports_the_shift_of_the_exit(
    profile: EntitlementProfile,
) -> None:
    """The exit falls by 388 EUR of gross income when the local cap applies."""
    assert profile.exit_threshold_shift == pytest.approx(388.0)


def test_entitlement_profile_amplification_is_the_local_ratio(
    profile: EntitlementProfile,
) -> None:
    """This Gemeinde's ratio is 388 / 226.82, not the median across Gemeinden."""
    assert profile.amplification == pytest.approx(388.0 / 226.82)


def test_plot_entitlement_profile_draws_one_line_per_scenario(
    profile: EntitlementProfile,
) -> None:
    """Both ceilings appear as their own claim-over-income line."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    lines = [trace for trace in figure.data if trace.mode == "lines"]
    assert len(lines) == 2


def test_plot_entitlement_profile_carries_no_title(
    profile: EntitlementProfile,
) -> None:
    """The slide supplies the heading, so the figure carries none."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    assert figure.layout.title.text is None


def test_plot_entitlement_profile_labels_the_local_cap_on_the_plot(
    profile: EntitlementProfile,
) -> None:
    """The local ceiling is written next to its own line rather than in a legend."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    texts = [annotation.text for annotation in figure.layout.annotations]
    assert any(
        "Local Kosten der Unterkunft cap" in text and "539.00 EUR" in text
        for text in texts
    )


def test_plot_entitlement_profile_writes_both_ceilings_to_the_cent(
    profile: EntitlementProfile,
) -> None:
    """Both ceiling labels carry cents, because one of the two ceilings has them."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    texts = [annotation.text for annotation in figure.layout.annotations]
    labelled = [text for text in texts if "recognises" in text]
    assert sorted(labelled) == sorted(
        [
            "Local Kosten der Unterkunft cap<br>recognises 539.00 EUR of rent",
            "Grenze ohne schlüssiges Konzept<br>recognises 765.82 EUR of rent",
        ],
    )


def test_plot_entitlement_profile_measures_the_gap_below_the_claim_axis(
    profile: EntitlementProfile,
) -> None:
    """The measuring bracket sits below zero, where no claim line can reach it."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    brackets = [
        trace
        for trace in figure.data
        if trace.mode == "lines+markers" and tuple(trace.x) == (2071.0, 2459.0)
    ]
    assert brackets[0].y[0] < 0.0


def test_plot_entitlement_profile_writes_the_gap_below_its_bracket(
    profile: EntitlementProfile,
) -> None:
    """The sentence explaining the gap sits below the bracket, clear of both lines."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    written = [
        annotation
        for annotation in figure.layout.annotations
        if "388 EUR" in annotation.text
    ]
    assert written[0].y < 0.0


def test_plot_entitlement_profile_labels_the_grenze_on_the_plot(
    profile: EntitlementProfile,
) -> None:
    """The Grenze ohne schlüssiges Konzept is written next to its own line."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    texts = [annotation.text for annotation in figure.layout.annotations]
    assert any(
        "Grenze ohne schlüssiges Konzept" in text and "765.82 EUR" in text
        for text in texts
    )


def test_plot_entitlement_profile_shows_no_legend(
    profile: EntitlementProfile,
) -> None:
    """Direct labels replace the legend box."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    assert figure.layout.showlegend is False


def test_plot_entitlement_profile_marks_both_zero_crossings(
    profile: EntitlementProfile,
) -> None:
    """Both exit thresholds are marked on the income axis."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    marked = [
        tuple(trace.x)
        for trace in figure.data
        if trace.mode is not None and "markers" in trace.mode and trace.y == (0.0, 0.0)
    ]
    assert marked == [(2071.0, 2459.0)]


def test_plot_entitlement_profile_annotates_the_distance_between_the_crossings(
    profile: EntitlementProfile,
) -> None:
    """The horizontal gap is written out as 388 EUR of gross income."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    texts = [annotation.text for annotation in figure.layout.annotations]
    assert any("388 EUR" in text for text in texts)


def test_plot_entitlement_profile_names_the_gemeinde(
    profile: EntitlementProfile,
) -> None:
    """The figure carries no title, so the Gemeinde is named in an annotation."""
    figure = plot_entitlement_profile(profile, gemeinde_name="Bad Homburg v.d.Höhe")
    texts = [annotation.text for annotation in figure.layout.annotations]
    assert any("Bad Homburg v.d.Höhe" in text for text in texts)


def test_plot_exit_threshold_distribution_carries_no_title() -> None:
    """The slide supplies the heading, so the figure carries none."""
    thresholds = pd.DataFrame(
        {
            "household_key": ["single_35", "single_35"],
            "cap_difference": [-226.82, 10.0],
            "exit_threshold_difference": [-388.0, 20.0],
        },
    )
    figure = plot_exit_threshold_distribution(thresholds)
    assert figure.layout.title.text is None


def test_plot_exit_threshold_distribution_names_the_grenze_in_its_axis_title() -> None:
    """The horizontal axis names the Grenze ohne schlüssiges Konzept."""
    thresholds = pd.DataFrame(
        {
            "household_key": ["single_35", "single_35"],
            "cap_difference": [-226.82, 10.0],
            "exit_threshold_difference": [-388.0, 20.0],
        },
    )
    figure = plot_exit_threshold_distribution(thresholds)
    assert "Grenze ohne schlüssiges Konzept" in figure.layout.xaxis.title.text
