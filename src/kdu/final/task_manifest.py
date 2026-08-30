"""Guarantee that `bld/results_manifest.csv` exists with the §5.2 schema.

Figure and table tasks append to the manifest through
{func}`kdu.final.manifest.register_result`. This task creates the file if no
output has been registered yet and normalises whatever is there, so the
manifest is a valid seven-column CSV at every point in the build.
"""

from pathlib import Path
from typing import Annotated, cast

from pytask import Product

from kdu.config import DATA_CATALOG
from kdu.final.manifest import read_manifest, write_manifest

_RESULTS_MANIFEST = cast("Path", DATA_CATALOG["results_manifest"])


def task_results_manifest(
    manifest_file: Annotated[Path, Product] = _RESULTS_MANIFEST,
) -> None:
    """Write the manifest back in canonical column order, creating it if needed."""
    write_manifest(read_manifest(manifest_file), manifest_file)
