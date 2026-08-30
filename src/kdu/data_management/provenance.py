"""Resolve every `source_document` string to a document in the Sciebo corpus.

`data/kdu_gemeinden.csv` cites its sources as free text: a filename, a URL, a
descriptive phrase, or several of those joined by `" + "`. The corpus itself
lives outside the repository (never copied in) and is indexed by filename. This
module turns the free text into a component-level register carrying, per source,
its type, its location, a sha256 of the file, and the dates that can be
evidenced.

Two facts govern the matching and are visible in the output rather than hidden:

- A citation component is only ever matched by an exact filename (after Unicode
  and whitespace normalisation). Near misses are reported as unmatched, never
  guessed at.
- Some filenames contain `" + "` themselves, so the whole citation is tested
  against the index before it is split.
"""

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType

import pandas as pd

# Directories under `kdu_pdfs/` that hold source documents.
CORPUS_SUBDIRECTORIES = ("thome", "own_research", "ocr_searchable")

# Separator the collectors used to cite several documents in one cell.
COMPONENT_SEPARATOR = " + "

_ID_LENGTH = 8
_SLUG_LENGTH = 48
_MAX_INSTITUTIONS = 3


class SourceKind(Enum):
    """How a single citation component resolves against the corpus."""

    CORPUS_FILE = "corpus_file"
    """An exact filename match against a document held in the corpus."""
    WEB_PAGE = "web_page"
    """A URL or an explicitly described web page; no file is held."""
    UNMATCHED = "unmatched"
    """A document the citation names but the corpus does not contain."""


@dataclass(frozen=True)
class CorpusLayout:
    """Locations inside the Sciebo corpus root."""

    root: Path
    """Corpus root directory, `.../RA-SOPHIA/KdU`."""

    @property
    def pdf_root(self) -> Path:
        """Directory holding every source document and its derivatives."""
        return self.root / "kdu_pdfs"

    @property
    def converted_text(self) -> Path:
        """Directory of `pdftotext -layout` extractions, one per thome PDF."""
        return self.pdf_root / "converted_text"

    @property
    def manifest(self) -> Path:
        """`kdu_manifest.csv`: region, doc type, Wirksamkeitsdatum, filename, URL."""
        return self.root / "kdu_manifest.csv"

    @property
    def region_to_kreis(self) -> Path:
        """`kdu_region_to_kreis.csv`: region name to Kreis AGS, with a confidence."""
        return self.root / "kdu_region_to_kreis.csv"

    @property
    def document_directories(self) -> tuple[Path, ...]:
        """Every directory searched for a cited document, in precedence order."""
        return tuple(self.pdf_root / name for name in CORPUS_SUBDIRECTORIES)


def load_corpus_layout() -> CorpusLayout:
    """Return the corpus layout rooted at the configured Sciebo directory."""
    from kdu.config import corpus_root  # noqa: PLC0415

    return CorpusLayout(root=corpus_root())


def normalise_name(value: str) -> str:
    """Fold a filename or citation to its comparison form.

    Applies NFC normalisation, collapses runs of whitespace, and lowercases, so
    that `"KdU  Celle LK - 01.01.2025.PDF"` and the file on disk compare equal.
    """
    return unicodedata.normalize("NFC", " ".join(value.split())).lower()


def index_corpus_files(layout: CorpusLayout) -> MappingProxyType[str, Path]:
    """Map every corpus document's normalised filename to its path.

    A document present in more than one subdirectory (a scan and its OCR'd
    twin) resolves to the first hit in `CORPUS_SUBDIRECTORIES` order, so the
    original always takes precedence over the derived copy.
    """
    index: dict[str, Path] = {}
    for directory in layout.document_directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            index.setdefault(normalise_name(path.name), path)
    return MappingProxyType(index)


def index_converted_text(layout: CorpusLayout) -> MappingProxyType[str, Path]:
    """Map the normalised stem of every extracted `.txt` to its path."""
    directory = layout.converted_text
    if not directory.is_dir():
        return MappingProxyType({})
    return MappingProxyType(
        {
            normalise_name(path.stem): path
            for path in sorted(directory.iterdir())
            if path.suffix.lower() == ".txt"
        },
    )


def split_source_document(
    citation: str,
    index: Mapping[str, Path],
) -> tuple[str, ...]:
    """Split a citation cell into its components.

    The whole string is tested against the corpus index first, because some
    filenames contain the separator (`"KdU Straubing Stadt + Straubing-Bogen LK
    - 01.01.2023.pdf"` is one document, not two).
    """
    if normalise_name(citation) in index:
        return (citation,)
    if COMPONENT_SEPARATOR in citation:
        return tuple(part.strip() for part in citation.split(COMPONENT_SEPARATOR))
    return (citation.strip(),)


def classify_component(component: str, index: Mapping[str, Path]) -> SourceKind:
    """Classify one citation component against the corpus."""
    if normalise_name(component) in index:
        return SourceKind.CORPUS_FILE
    if component.lower().startswith(("http://", "https://", "www.")):
        return SourceKind.WEB_PAGE
    if _looks_like_a_filename(component):
        return SourceKind.UNMATCHED
    return SourceKind.WEB_PAGE


def make_source_id(component: str) -> str:
    """Build a stable, readable identifier for a citation component."""
    normalised = normalise_name(component)
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:_ID_LENGTH]
    slug = "".join(
        character if character.isalnum() else "_" for character in normalised
    )
    slug = "_".join(part for part in slug.split("_") if part)[:_SLUG_LENGTH]
    return f"{slug}_{digest}" if slug else digest


def sha256_file(path: Path) -> str:
    """Return the hex sha256 digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def build_component_map(
    citations: Iterable[str],
    index: Mapping[str, Path],
) -> pd.DataFrame:
    """Explode citation cells into one row per (citation, component).

    Returns columns `source_document`, `component`, `source_id`, `source_kind`,
    and `component_position`.
    """
    records = []
    for citation in sorted({value for value in citations if isinstance(value, str)}):
        for position, component in enumerate(split_source_document(citation, index)):
            records.append(
                {
                    "source_document": citation,
                    "component": component,
                    "source_id": make_source_id(component),
                    "source_kind": classify_component(component, index).value,
                    "component_position": position,
                },
            )
    return pd.DataFrame.from_records(
        records,
        columns=[
            "source_document",
            "component",
            "source_id",
            "source_kind",
            "component_position",
        ],
    )


def build_source_register(
    component_map: pd.DataFrame,
    index: Mapping[str, Path],
    manifest: pd.DataFrame,
    institutions: Mapping[str, str] | None = None,
    *,
    hash_files: bool = True,
) -> pd.DataFrame:
    """Build the component-level provenance register.

    Args:
        component_map: Output of {func}`build_component_map`.
        index: Normalised filename to corpus path.
        manifest: `kdu_manifest.csv`, supplying `label`, `url`, `valid_from_iso`.
        institutions: Optional `source_id` to responsible-body label mapping.
        hash_files: Compute a sha256 per held file. Disable in fast tests.

    Returns:
        One row per distinct `source_id`, carrying the §6.2 provenance fields.
    """
    manifest_by_name = _manifest_by_normalised_filename(manifest)
    unique = component_map.drop_duplicates(subset="source_id").sort_values("source_id")
    records = []
    for row in unique.to_dict(orient="records"):
        component = str(row["component"])
        key = normalise_name(component)
        path = index.get(key)
        entry = manifest_by_name.get(key, {})
        records.append(
            _register_record(
                source_id=str(row["source_id"]),
                component=component,
                kind=SourceKind(str(row["source_kind"])),
                path=path,
                manifest_entry=entry,
                institution=(institutions or {}).get(str(row["source_id"])),
                hash_files=hash_files,
            ),
        )
    register = pd.DataFrame.from_records(records, columns=_REGISTER_COLUMNS)
    return register.sort_values("source_id").reset_index(drop=True)


def responsible_institutions(
    kdu: pd.DataFrame,
    component_map: pd.DataFrame,
    kreis_names: Mapping[str, str],
) -> MappingProxyType[str, str]:
    """Name the Kreise that cite each source, as its issuing institution.

    The manifest carries a URL only for the harald-thome.de documents, so for
    everything else the responsible Träger is the only evidenced institution.
    """
    citing = kdu[["source_document", "ags_kreis"]].dropna().drop_duplicates()
    merged = citing.merge(
        component_map[["source_document", "source_id"]],
        on="source_document",
        how="inner",
    )
    merged["kreis_name"] = merged["ags_kreis"].map(kreis_names)
    grouped = (
        merged.dropna(subset="kreis_name")
        .groupby("source_id")["kreis_name"]
        .apply(lambda names: _join_institutions(sorted(set(names))))
    )
    return MappingProxyType(dict(grouped))


def count_unmatched_documents(component_map: pd.DataFrame) -> pd.DataFrame:
    """Summarise, per `source_document`, how its components resolved."""
    kinds = component_map.groupby("source_document")["source_kind"]
    summary = pd.DataFrame(
        {
            "n_components": kinds.size(),
            "n_corpus_files": kinds.apply(
                lambda values: int((values == SourceKind.CORPUS_FILE.value).sum()),
            ),
            "n_web_pages": kinds.apply(
                lambda values: int((values == SourceKind.WEB_PAGE.value).sum()),
            ),
            "n_unmatched": kinds.apply(
                lambda values: int((values == SourceKind.UNMATCHED.value).sum()),
            ),
        },
    )
    summary["fully_matched"] = summary["n_corpus_files"] == summary["n_components"]
    summary["has_any_file"] = summary["n_corpus_files"] > 0
    return summary.reset_index()


_REGISTER_COLUMNS = (
    "source_id",
    "source_title",
    "source_institution",
    "source_type",
    "source_kind",
    "source_location",
    "publication_date",
    "retrieval_date",
    "valid_from",
    "valid_to",
    "source_hash",
    "has_converted_text",
)


def _register_record(
    *,
    source_id: str,
    component: str,
    kind: SourceKind,
    path: Path | None,
    manifest_entry: Mapping[str, object],
    institution: str | None,
    hash_files: bool,
) -> dict[str, object]:
    label = manifest_entry.get("label")
    return {
        "source_id": source_id,
        "source_title": label if isinstance(label, str) and label else component,
        "source_institution": institution,
        "source_type": _source_type(path),
        "source_kind": kind.value,
        "source_location": _source_location(component, path, manifest_entry),
        # No collection step recorded a publication date; the manifest's date is
        # the Wirksamkeitsdatum, which is carried as `valid_from` instead.
        "publication_date": None,
        "retrieval_date": _retrieval_date(path),
        "valid_from": manifest_entry.get("valid_from_iso"),
        # Open-ended: every document in the register is the one in force at the
        # Analysestichtag for the regions citing it.
        "valid_to": None,
        "source_hash": (
            sha256_file(path) if (path is not None and hash_files) else None
        ),
        "has_converted_text": None,
    }


def _source_type(path: Path | None) -> str | None:
    if path is None:
        return None
    parent = path.parent.name
    return "thome" if parent in {"thome", "ocr_searchable"} else "own_research"


def _source_location(
    component: str,
    path: Path | None,
    manifest_entry: Mapping[str, object],
) -> str:
    url = manifest_entry.get("url")
    if isinstance(url, str) and url:
        return url
    if component.lower().startswith(("http://", "https://")):
        return component
    if path is not None:
        return str(Path("kdu_pdfs") / path.parent.name / path.name)
    return component


def _retrieval_date(path: Path | None) -> str | None:
    if path is None:
        return None
    stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return stamp.date().isoformat()


def _manifest_by_normalised_filename(
    manifest: pd.DataFrame,
) -> Mapping[str, Mapping[str, object]]:
    entries: dict[str, Mapping[str, object]] = {}
    for record in manifest.to_dict(orient="records"):
        filename = record.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        entries.setdefault(normalise_name(filename), record)
    return entries


def _join_institutions(names: Sequence[str]) -> str:
    if len(names) <= _MAX_INSTITUTIONS:
        return " | ".join(names)
    shown = " | ".join(names[:_MAX_INSTITUTIONS])
    return f"{shown} | (+{len(names) - _MAX_INSTITUTIONS} further Kreise)"


def _looks_like_a_filename(component: str) -> bool:
    suffix = Path(component).suffix.lower()
    return suffix in {".pdf", ".html", ".htm", ".docx", ".doc", ".xlsx", ".xls"}


def amount_pattern(amount: float) -> re.Pattern[str]:
    """Build a regex matching one euro amount as a German document prints it.

    Covers the thousands separator (`1.080`), both decimal marks, an omitted
    decimal part, and the `,-` shorthand. The amount must not be embedded in a
    longer number, so `486` never matches inside `1486` or `486,50`.
    """
    whole = int(amount)
    cents = round((amount - whole) * 100)
    wholes = {str(whole), f"{whole:,}".replace(",", ".")}
    stem = "|".join(re.escape(value) for value in sorted(wholes))
    if cents == 0:
        tail = r"(?:[.,]0{1,2}|,-)?"
    elif cents % 10 == 0:
        tail = rf"[.,](?:{cents // 10}|{cents:02d})"
    else:
        tail = rf"[.,]{cents:02d}"
    return re.compile(rf"(?<![\d.,])(?:{stem}){tail}(?![\d])(?![.,]\d)")


def scan_printed_amounts(
    amounts_by_document: Mapping[str, frozenset[float]],
    index: Mapping[str, Path],
    text_index: Mapping[str, Path],
) -> MappingProxyType[tuple[str, float], str]:
    """Look for each cited amount in the extracted text of its own sources.

    Args:
        amounts_by_document: Every `kdu_bkc_cap` cited under each
            `source_document` value.
        index: Normalised filename to corpus path, used to split citations.
        text_index: Normalised document stem to extracted `.txt` path.

    Returns:
        `(source_document, amount)` to one of `"found_in_text"`,
        `"not_found_in_text"`, or `"no_text_available"`. Only the harald-thome
        documents have an extracted text layer, so roughly half the Gemeinden
        resolve to `"no_text_available"` — an honest gap, not a failure.

    """
    evidence: dict[tuple[str, float], str] = {}
    for document, amounts in amounts_by_document.items():
        texts = [
            text_index[key].read_text(errors="replace")
            for key in (
                normalise_name(Path(component).stem)
                for component in split_source_document(document, index)
            )
            if key in text_index
        ]
        if not texts:
            for amount in amounts:
                evidence[document, amount] = "no_text_available"
            continue
        found = {
            amount: any(amount_pattern(amount).search(text) for text in texts)
            for amount in amounts
        }
        # A document whose extraction contains none of its own cap amounts has
        # an unreadable table - a scanned or image-only page - so its misses are
        # evidence about the extraction, not about the data.
        readable = any(found.values())
        for amount, hit in found.items():
            if hit:
                evidence[document, amount] = "found_in_text"
            else:
                evidence[document, amount] = (
                    "not_found_in_text" if readable else "no_amounts_in_text"
                )
    return MappingProxyType(evidence)
