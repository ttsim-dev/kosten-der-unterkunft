@.ai-instructions/profiles/tier-b-research.md

# AGENTS.md

This file provides guidance to AI coding tools (Claude Code, Gemini CLI, Codex, Copilot,
Cursor) when working with this repository.

## Overview

`kdu` measures how far the maximum rent a local Jobcenter will recognise under SGB II
and SGB XII departs from the statutory fallback a tax-transfer model substitutes when it
has no local figure, and what that departure changes.

The caps come from roughly 400 municipal Richtlinien collected by hand. The benchmark is
the Wohngeld-Höchstbetrag times 1.10 — the standard the Bundessozialgericht prescribes
where a Kreis has published no schlüssiges Konzept. The project reports six results and
one interactive map.

The central finding: at household size one the median Gemeinde's cap sits 0.2 % above
the fallback while the tenth and ninetieth percentiles sit 16.7 % below and 23.4 % above
it, and the statutory Mietenstufe cannot repair that, because it accounts for 41 % of
the variation in local caps while the residual variation still tracks actual market
rents.

## Build and test

```bash
pixi install                       # create the environment
pixi run pytask                    # build everything into bld/
pixi run pytest                    # run tests
pixi run ty                        # type checking
pixi run prek run --all-files      # pre-commit hooks
```

The pytask graph never touches the network. `scripts/fetch_*.py` refresh the committed
inputs in `data/` and are run by hand when a new data vintage appears; their output is
committed.

## The six results

| package                  | question                                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `kdu_vs_wohngeld`        | How far do local caps depart from the statutory fallback, in level and across household sizes within one Gemeinde? |
| `kdu_vs_wohngeld`        | How much variation in local caps does the Mietenstufe leave unaccounted for? *(lead result)*                       |
| `market_rent_comparison` | Do local caps track actual local market rents where the fallback structurally cannot?                              |
| `market_rent_comparison` | How much of the local rented stock does each cap price above itself?                                               |
| `eligibility`            | By how much does the choice of cap move the gross income at which a household leaves the transfer system?          |
| `validation`             | Do the collected caps agree with what Jobcenter actually recognise?                                                |

## Architecture

Committed inputs, read by the graph and never fetched during a build:

- `data/kdu_gemeinden.csv` — the collected caps, keyed by eight-digit Gemeinde AGS.
  `data/kdu_codebook.md` defines its columns.
- `data/gemeinden.geo.json` — Gemeinde boundaries, simplified to about a 1 km grid.
- `data/wogg_parameters.csv` — Anlage 1 Höchstbeträge and Mietenstufen.
- `data/ba_wohnkosten/` — the Wohnkostenstatistik of the Bundesagentur für Arbeit.
- `data/zensus/` — Zensus 2022 rents at Gemeinde level.

Source layout:

- `src/kdu/config.py` — paths, the Rechtsstand and Gebietsstand the whole project is
  pinned to, the Modellhaushalte, and the pytask data catalog.
- `src/kdu/weighting.py` — weighted mean, quantile, standard deviation and share. The
  only two weighting schemes are one Gemeinde one weight, and weighting by
  Bedarfsgemeinschaften.
- `src/kdu/data_management/` — five cleaning modules producing the narrow tables in
  `bld/data/` that every analysis reads.
- `src/kdu/kdu_vs_wohngeld/`, `market_rent_comparison/`, `eligibility/`, `validation/` —
  one package per question, each owning both its numbers and its figures.
- `src/kdu/final/` — the map alone.

A `task_` module contains only its pytask function and the reading and writing of files.
Every computation and every figure is a pure function in a sibling module.

## The data model

`bld/data/` holds four narrow tables rather than one wide one:

| table                       | key                     | holds                                              |
| --------------------------- | ----------------------- | -------------------------------------------------- |
| `kdu_caps.parquet`          | `ags`, `household_size` | the local cap and the terms it was published under |
| `wohngeld_fallback.parquet` | `ags`, `household_size` | Mietenstufe, Höchstbetrag, and the fallback cap    |
| `gemeinden.parquet`         | `ags`                   | names, Kreis, Bundesland, population               |
| `kdu_sources.parquet`       | `source_id`             | the document each cap was read from                |

`bld/data/wohnkostenstatistik.parquet` and `bld/data/zensus_rents.parquet` carry the two
external sources. Every other subdirectory of `bld/` belongs to one package and holds
only what that package produces. All of `bld/` is disposable: nothing in it takes long
to rebuild, because nothing in it is downloaded.

## Conventions that are not negotiable

**The join key is the official AGS** derived from `gem_code`. Region names repeat across
Germany and are never keys. The synthetic `fid` connects the joined frame to Plotly's
GeoJSON features. Every join is guarded against silently duplicating or dropping rows.

**Caps vary within a Kreis.** 209 of 357 Kreise publish Gemeinde-specific figures —
Kreis Steinfurt has 24 Gemeinden and 23 distinct caps under a single directive. The
Kreis is the Träger that decides; it is not the unit at which the rule applies. Do not
treat a Kreis as one observation without saying why.

**Some Kreise are suspected of applying the fallback unchanged.** Where a cap equals the
Wohngeld-Höchstbetrag times 1.10 the departure is an arithmetic identity rather than a
finding. We have not located those documents, so this is a suspicion, not a fact:
`wohngeld_rule_suspected` marks them and every result is reported both including and
excluding them, as co-equal versions.

**Language.** No abbreviations in identifiers or prose. German legal terms of art —
Bruttokaltmiete, Mietenstufe, Bedarfsgemeinschaft, Härtefallregelung — stay German and
stay spelled out. The map is in German because its readers are; everything else is in
English. The word "proxy" is not used.
