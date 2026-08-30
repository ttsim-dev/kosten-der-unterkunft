import hashlib
from pathlib import Path

import pandas as pd
import pytest

from kdu.data_management.provenance import (
    CorpusLayout,
    SourceKind,
    amount_pattern,
    build_component_map,
    build_source_register,
    classify_component,
    count_unmatched_documents,
    index_converted_text,
    index_corpus_files,
    make_source_id,
    normalise_name,
    responsible_institutions,
    scan_printed_amounts,
    sha256_file,
    split_source_document,
)


@pytest.fixture
def corpus(tmp_path: Path) -> CorpusLayout:
    layout = CorpusLayout(root=tmp_path)
    (layout.pdf_root / "thome").mkdir(parents=True)
    (layout.pdf_root / "own_research").mkdir(parents=True)
    layout.converted_text.mkdir(parents=True)
    (layout.pdf_root / "thome" / "KdU Musterkreis - 01.01.2026.pdf").write_bytes(
        b"a pdf",
    )
    (layout.pdf_root / "thome" / "KdU A + B LK - 01.01.2023.pdf").write_bytes(b"b pdf")
    (layout.pdf_root / "own_research" / "Musterstadt_Flyer.pdf").write_bytes(b"c pdf")
    (layout.converted_text / "KdU Musterkreis - 01.01.2026.txt").write_text(
        "Bruttokaltmiete 1 Person   486,00 EUR\nzwei Personen 1.080,20 EUR\n",
        encoding="utf-8",
    )
    return layout


def test_normalise_name_folds_case_and_whitespace() -> None:
    assert normalise_name("KdU  Celle LK.PDF") == "kdu celle lk.pdf"


def test_index_corpus_files_finds_every_document(corpus: CorpusLayout) -> None:
    assert len(index_corpus_files(corpus)) == 3


def test_index_converted_text_is_keyed_by_stem(corpus: CorpusLayout) -> None:
    assert "kdu musterkreis - 01.01.2026" in index_converted_text(corpus)


def test_split_source_document_keeps_a_filename_containing_the_separator(
    corpus: CorpusLayout,
) -> None:
    index = index_corpus_files(corpus)
    citation = "KdU A + B LK - 01.01.2023.pdf"
    assert split_source_document(citation, index) == (citation,)


def test_split_source_document_splits_a_genuine_compound_citation(
    corpus: CorpusLayout,
) -> None:
    index = index_corpus_files(corpus)
    citation = "KdU Musterkreis - 01.01.2026.pdf + Musterstadt_Flyer.pdf"
    assert split_source_document(citation, index) == (
        "KdU Musterkreis - 01.01.2026.pdf",
        "Musterstadt_Flyer.pdf",
    )


def test_classify_component_recognises_a_held_file(corpus: CorpusLayout) -> None:
    index = index_corpus_files(corpus)
    kind = classify_component("Musterstadt_Flyer.pdf", index)
    assert kind is SourceKind.CORPUS_FILE


def test_classify_component_recognises_a_url(corpus: CorpusLayout) -> None:
    kind = classify_component("https://example.org/kdu", index_corpus_files(corpus))
    assert kind is SourceKind.WEB_PAGE


def test_classify_component_reports_a_named_but_absent_document(
    corpus: CorpusLayout,
) -> None:
    kind = classify_component("Nicht_Vorhanden.pdf", index_corpus_files(corpus))
    assert kind is SourceKind.UNMATCHED


def test_make_source_id_is_stable_across_spelling_variants() -> None:
    assert make_source_id("KdU  X.PDF") == make_source_id("kdu x.pdf")


def test_sha256_file_hashes_the_bytes(corpus: CorpusLayout) -> None:
    path = corpus.pdf_root / "thome" / "KdU Musterkreis - 01.01.2026.pdf"
    assert sha256_file(path) == hashlib.sha256(b"a pdf").hexdigest()


def test_build_component_map_gives_one_row_per_component(corpus: CorpusLayout) -> None:
    index = index_corpus_files(corpus)
    citations = ["KdU Musterkreis - 01.01.2026.pdf + Musterstadt_Flyer.pdf"]
    assert len(build_component_map(citations, index)) == 2


def test_count_unmatched_documents_reports_a_citation_with_no_file(
    corpus: CorpusLayout,
) -> None:
    index = index_corpus_files(corpus)
    component_map = build_component_map(["https://example.org/kdu"], index)
    summary = count_unmatched_documents(component_map)
    assert not bool(summary.loc[0, "has_any_file"])


def test_build_source_register_carries_the_hash_of_a_held_file(
    corpus: CorpusLayout,
) -> None:
    index = index_corpus_files(corpus)
    component_map = build_component_map(["Musterstadt_Flyer.pdf"], index)
    manifest = pd.DataFrame(columns=["filename", "url", "label", "valid_from_iso"])
    register = build_source_register(component_map, index, manifest)
    assert register.loc[0, "source_hash"] == sha256_file(
        corpus.pdf_root / "own_research" / "Musterstadt_Flyer.pdf",
    )


def test_build_source_register_labels_the_thome_collection(
    corpus: CorpusLayout,
) -> None:
    index = index_corpus_files(corpus)
    component_map = build_component_map(["KdU Musterkreis - 01.01.2026.pdf"], index)
    manifest = pd.DataFrame(columns=["filename", "url", "label", "valid_from_iso"])
    register = build_source_register(component_map, index, manifest)
    assert register.loc[0, "source_type"] == "thome"


def test_build_source_register_leaves_a_web_citation_without_a_hash(
    corpus: CorpusLayout,
) -> None:
    index = index_corpus_files(corpus)
    component_map = build_component_map(["https://example.org/kdu"], index)
    manifest = pd.DataFrame(columns=["filename", "url", "label", "valid_from_iso"])
    register = build_source_register(component_map, index, manifest)
    assert pd.isna(register.loc[0, "source_hash"])


def test_responsible_institutions_names_the_citing_kreis(corpus: CorpusLayout) -> None:
    index = index_corpus_files(corpus)
    component_map = build_component_map(["Musterstadt_Flyer.pdf"], index)
    kdu = pd.DataFrame(
        {"source_document": ["Musterstadt_Flyer.pdf"], "ags_kreis": ["09999"]},
    )
    institutions = responsible_institutions(
        kdu, component_map, {"09999": "Musterkreis"}
    )
    assert next(iter(institutions.values())) == "Musterkreis"


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        (486.0, "486,00 EUR"),
        (486.0, "486 EUR"),
        (486.0, "486,- EUR"),
        (1080.2, "1.080,20 EUR"),
        (474.5, "474,50"),
        (474.5, "474,5"),
    ],
)
def test_amount_pattern_matches_a_printed_amount(amount: float, text: str) -> None:
    assert amount_pattern(amount).search(text) is not None


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        (486.0, "1486,00 EUR"),
        (486.0, "486,50 EUR"),
        (486.0, "1.486,50 EUR"),
        (486.0, "486.75"),
        (48.0, "486 EUR"),
        (1486.5, "486,50 EUR"),
    ],
)
def test_amount_pattern_rejects_a_different_amount(amount: float, text: str) -> None:
    assert amount_pattern(amount).search(text) is None


def test_scan_printed_amounts_finds_a_printed_cap(corpus: CorpusLayout) -> None:
    index = index_corpus_files(corpus)
    evidence = scan_printed_amounts(
        {"KdU Musterkreis - 01.01.2026.pdf": frozenset({486.0})},
        index,
        index_converted_text(corpus),
    )
    assert evidence["KdU Musterkreis - 01.01.2026.pdf", 486.0] == "found_in_text"


def test_scan_printed_amounts_reports_an_absent_cap(corpus: CorpusLayout) -> None:
    index = index_corpus_files(corpus)
    evidence = scan_printed_amounts(
        {"KdU Musterkreis - 01.01.2026.pdf": frozenset({486.0, 999.0})},
        index,
        index_converted_text(corpus),
    )
    assert evidence["KdU Musterkreis - 01.01.2026.pdf", 999.0] == "not_found_in_text"


def test_scan_printed_amounts_reports_an_unreadable_extraction(
    corpus: CorpusLayout,
) -> None:
    """A text carrying none of a document's own caps says nothing about them."""
    index = index_corpus_files(corpus)
    evidence = scan_printed_amounts(
        {"KdU Musterkreis - 01.01.2026.pdf": frozenset({999.0})},
        index,
        index_converted_text(corpus),
    )
    assert evidence["KdU Musterkreis - 01.01.2026.pdf", 999.0] == "no_amounts_in_text"


def test_scan_printed_amounts_reports_a_document_without_a_text_layer(
    corpus: CorpusLayout,
) -> None:
    index = index_corpus_files(corpus)
    evidence = scan_printed_amounts(
        {"Musterstadt_Flyer.pdf": frozenset({500.0})},
        index,
        index_converted_text(corpus),
    )
    assert evidence["Musterstadt_Flyer.pdf", 500.0] == "no_text_available"
