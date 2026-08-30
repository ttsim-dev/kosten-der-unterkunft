"""Tests for the workshop deck selection and the consolidated results text."""

import pandas as pd
import pytest

from kdu.final.workshop import (
    MAIN_FIGURES,
    MAX_WORKSHOP_FIGURES,
    RESULTS_DOCUMENT,
    FigureStatus,
    MainFigure,
    build_deck_table,
    forbidden_term_hits,
    select_row,
    workshop_deck,
    wrap_markdown,
)


def make_figure(
    number: int = 1,
    *,
    in_deck: bool = True,
    status: FigureStatus = FigureStatus.BUILT,
) -> MainFigure:
    return MainFigure(
        number=number,
        title=f"Figure {number}",
        filename=f"fig_{number}.html",
        beitrag=1,
        status=status,
        in_deck=in_deck,
        reason="because",
        module="P0.3",
    )


def test_the_workshop_deck_holds_six_figures() -> None:
    """§19 admits six figures to the main talk, and six are selected."""
    assert len(workshop_deck()) == MAX_WORKSHOP_FIGURES


def test_every_selected_figure_carries_a_justification() -> None:
    """Each figure in the deck says in one line why it earns its slot."""
    assert all(figure.reason.strip() for figure in workshop_deck())


def test_the_figure_programme_covers_all_eight_main_figures() -> None:
    """§19 lists eight main figures, numbered 1 to 8, each appearing once."""
    assert sorted(figure.number for figure in MAIN_FIGURES) == list(range(1, 9))


def test_a_deck_of_more_than_six_figures_is_rejected() -> None:
    """A selection above the §19 cap fails rather than being silently trimmed."""
    figures = tuple(
        make_figure(number) for number in range(1, MAX_WORKSHOP_FIGURES + 2)
    )

    with pytest.raises(ValueError, match="at most"):
        workshop_deck(figures)


def test_a_figure_that_is_not_built_may_not_enter_the_deck() -> None:
    """A figure whose module has not run cannot be shown in the main talk."""
    figures = (make_figure(1, status=FigureStatus.AWAITING_MODULE),)

    with pytest.raises(ValueError, match="not built"):
        workshop_deck(figures)


def test_the_deck_table_records_every_main_figure_as_built() -> None:
    """Every §19 main figure has a producing module that has run."""
    table = build_deck_table()

    assert set(table["status"]) == {str(FigureStatus.BUILT)}


def test_select_row_returns_the_single_matching_row() -> None:
    """A number is read from exactly one identified row."""
    frame = pd.DataFrame({"size": [1, 4], "median": [46.0, 69.0]})

    assert select_row(frame, size=4)["median"] == pytest.approx(69.0)


@pytest.mark.parametrize("size", [2, 4])
def test_select_row_raises_when_the_row_is_not_unique(size: int) -> None:
    """A missing or duplicated row breaks the build instead of drifting."""
    frame = pd.DataFrame({"size": [1, 4, 4], "median": [46.0, 69.0, 70.0]})

    with pytest.raises(ValueError, match="exactly one row"):
        select_row(frame, size=size)


def test_a_forbidden_term_used_as_a_claim_is_reported() -> None:
    """§20 bans reading a high cap as generosity, so an assertion of it is a hit."""
    text = "A high cap shows the generosity of the Kreis."

    assert forbidden_term_hits(text)


def test_a_forbidden_term_inside_a_denial_is_allowed() -> None:
    """§21's fourth part must be able to name the reading it rules out."""
    text = "A high cap is not evidence that a Kreis is more generous."

    assert forbidden_term_hits(text) == ()


def test_the_results_document_passes_its_own_framing_check() -> None:
    """The committed results text uses no §20 term as a claim."""
    if not RESULTS_DOCUMENT.exists():
        pytest.skip("docs/results.md has not been built yet")

    assert forbidden_term_hits(RESULTS_DOCUMENT.read_text(encoding="utf-8")) == ()


def test_wrap_markdown_leaves_headings_untouched() -> None:
    """A heading stays on its own line however long it is."""
    heading = "## " + "word " * 40

    assert wrap_markdown(heading).strip() == heading.strip()


def test_wrap_markdown_keeps_one_line_per_list_item() -> None:
    """A two-item list stays two items after wrapping."""
    block = "- first item\n- second item"

    wrapped = wrap_markdown(block)

    assert [line for line in wrapped.splitlines() if line.startswith("-")] == [
        "- first item",
        "- second item",
    ]
