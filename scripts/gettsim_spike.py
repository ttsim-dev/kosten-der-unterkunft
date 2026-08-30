"""THROWAWAY exploration script for the D9 GETTSIM audit. Not part of the task graph.

Nothing imports this and no pytask task depends on it. It exists so the claims in
`docs/gettsim_audit.md` can be re-run and checked; delete it once P0.7 has real
tasks under `src/kdu/simulation/`.

Run with `pixi run python scripts/gettsim_spike.py`.

It covers:

1. how far GETTSIM's own Angemessenheitsgrenze truncates the recognised KdU,
2. that supplying `bürgergeld__kosten_der_unterkunft_m` as input data neutralises it,
3. the §12.1 K/W contrast end to end, checked against `Delta T(0) = K - W`,
4. the Karenzzeit switch (`bürgergeld__bezug_im_vorjahr`) D11 needs,
5. that the Anspruch is monotone in income, as D10's bisection requires,
6. that the override column is per-person, not per-household,
7. how long a realistic D10-sized batch takes.

The model household is §11.1 household 1: a single 35-year-old, Rechtsstand 2026,
Mietenstufe III, past the Karenzzeit.
"""

import time
import warnings
from typing import Any

import dags.tree as dt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

from gettsim import InputData, MainTarget, TTTargets, main  # noqa: E402

from kdu.simulation.kdu_cap import (  # noqa: E402
    GETTSIM_UNTERKUNFTSKOSTEN_COLUMN,
    fail_if_not_weakly_decreasing,
    kopfteil_m,
    unterkunftskosten_m,
)

POLICY_DATE = "2026-08-31"
HEIZKOSTEN_M = 90.0
WOHNFLAECHE_QM = 45.0
DTYPE_DEFAULTS = {"BoolColumn": False, "IntColumn": 0, "FloatColumn": 0.0}


def build_default_row(tt_targets: dict[str, Any]) -> dict[str, Any]:
    """Fill every input GETTSIM demands for `tt_targets` with a neutral value."""
    template = dt.flatten_to_qnames(
        main(
            main_target=MainTarget.templates.input_data_dtypes.tree,
            policy_date_str=POLICY_DATE,
            tt_targets=TTTargets(tree=tt_targets),  # ty: ignore[unknown-argument]
        )
    )
    return {name: DTYPE_DEFAULTS[str(dtype)] for name, dtype in template.items()}


def single_35(base: dict[str, Any], **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """§11.1 household 1: one erwerbsfähige person aged 35, past the Karenzzeit."""
    row = dict(base)
    row.update(
        {
            "p_id": 0,
            "hh_id": 0,
            "alter": 35,
            "geburtsjahr": 1991,
            "geburtsmonat": 1,
            "geburtstag": 1,
            "arbeitsstunden_w": 0.0,
            "lohnsteuer__steuerklasse": 1,
            "wohngeld__mietstufe_hh": 3,
            "wohnen__wohnfläche_hh": WOHNFLAECHE_QM,
            "wohnen__heizkosten_m_hh": HEIZKOSTEN_M,
            # Past month 12 of Bürgergeld receipt, so the cap is in force (D11).
            "bürgergeld__bezug_im_vorjahr": True,
            "sozialversicherung__rente__jahr_renteneintritt": 2026,
            "sozialversicherung__rente__monat_renteneintritt": 1,
        }
    )
    for name in row:
        if "p_id_" in name:
            row[name] = -1
    row.update(overrides)
    return row


def run(rows: list[dict[str, Any]], tt_targets: dict[str, Any]) -> pd.DataFrame:
    """Evaluate `tt_targets` for one row per person, all households at once."""
    # `TTTargets.tree` is both a dataclass field and a classmethod, and `main()` is
    # typed as returning `Any` through a beartype decorator, so ty cannot see either.
    df = pd.DataFrame(rows)
    return main(  # ty: ignore[invalid-return-type]
        main_target=MainTarget.results.df_with_mapper,
        policy_date_str=POLICY_DATE,
        input_data=InputData.df_with_qname_columns(df),
        tt_targets=TTTargets(tree=tt_targets),  # ty: ignore[unknown-argument]
    )


def show_gettsim_own_cap() -> None:
    """GETTSIM truncates the recognised KdU at 45 m² * 10 €/m² = 450 € warm."""
    targets = {
        "bürgergeld": {
            "anspruchshöhe_m": "anspruch_m",
            "kosten_der_unterkunft_m": "anerkannte_kdu_m",
            "regelsatz_m": "regelsatz_m",
        }
    }
    base = build_default_row(targets)
    rents = [200.0, 300.0, 360.0, 400.0, 500.0, 700.0]
    rows = [
        single_35(base, p_id=i, hh_id=i, wohnen__bruttokaltmiete_m_hh=rent)
        for i, rent in enumerate(rents)
    ]
    result = run(rows, targets).assign(bruttokaltmiete_m=rents)
    print("\n[1] GETTSIM's own Angemessenheitsgrenze, untouched")
    print(result.to_string(index=False))
    print(
        "    -> anerkannte_kdu_m saturates at 450 = 45 m2 * 10 EUR/m2, and it is a"
        " WARM cap: it swallows the 90 EUR Heizkosten too."
    )


def show_neutralised_cap() -> None:
    """Handing GETTSIM a finished amount removes its cap from the DAG entirely."""
    targets = {
        "bürgergeld": {
            "anspruchshöhe_m": "anspruch_m",
            "kosten_der_unterkunft_m": "anerkannte_kdu_m",
        }
    }
    base = build_default_row(targets)
    base[GETTSIM_UNTERKUNFTSKOSTEN_COLUMN] = 0.0
    rents = np.array([200.0, 300.0, 360.0, 400.0, 500.0, 700.0, 1500.0])
    # A cap equal to the rent itself never binds, so this isolates GETTSIM's
    # behaviour from our own min().
    ours = unterkunftskosten_m(rents, rents, np.full_like(rents, HEIZKOSTEN_M))
    rows = [
        single_35(
            base,
            p_id=i,
            hh_id=i,
            wohnen__bruttokaltmiete_m_hh=float(rent),
            **{GETTSIM_UNTERKUNFTSKOSTEN_COLUMN: float(amount)},
        )
        for i, (rent, amount) in enumerate(zip(rents, ours, strict=True))
    ]
    result = run(rows, targets).assign(bruttokaltmiete_m=rents, handed_over=ours)
    print(f"\n[2] {GETTSIM_UNTERKUNFTSKOSTEN_COLUMN} supplied as input data")
    print(result.to_string(index=False))
    matches = np.allclose(result["anerkannte_kdu_m"].to_numpy(), ours)
    print(f"    -> anerkannte_kdu_m == what we handed over: {matches}")


def show_scenario_contrast() -> None:
    """The K/W contrast of §12.1, at the obergrenzenbindende Miete of §12.2 V1."""
    targets = {"bürgergeld": {"anspruchshöhe_m": "anspruch_m"}}
    base = build_default_row(targets)
    base[GETTSIM_UNTERKUNFTSKOSTEN_COLUMN] = 0.0
    # Mietenstufe III, one person: W = 456 (WoGG Anlage 1), K = an illustrative
    # local Obergrenze 14 % above it.
    kdu_cap = np.array([520.0])
    wogg_cap = np.array([456.0])
    actual_rent = np.maximum(kdu_cap, wogg_cap)
    heizkosten = np.array([HEIZKOSTEN_M])
    anspruch = {}
    for label, cap in (("K", kdu_cap), ("W", wogg_cap)):
        amount = unterkunftskosten_m(actual_rent, cap, heizkosten)
        rows = [
            single_35(
                base,
                wohnen__bruttokaltmiete_m_hh=float(actual_rent[0]),
                **{GETTSIM_UNTERKUNFTSKOSTEN_COLUMN: float(amount[0])},
            )
        ]
        anspruch[label] = run(rows, targets)["anspruch_m"].to_numpy()[0]
    print("\n[3] K/W contrast at zero earnings, m = max(K, W)")
    print(f"    K = {kdu_cap[0]}, W = {wogg_cap[0]}, m = {actual_rent[0]}")
    print(f"    T^K(0) = {anspruch['K']}, T^W(0) = {anspruch['W']}")
    print(
        f"    Delta T(0) = {anspruch['K'] - anspruch['W']}"
        f" (expected K - W = {kdu_cap[0] - wogg_cap[0]})"
    )


def show_karenzzeit_switch() -> None:
    """D11: `bezug_im_vorjahr` is the switch that puts the cap in force."""
    targets = {"bürgergeld": {"kosten_der_unterkunft_m": "anerkannte_kdu_m"}}
    base = build_default_row(targets)
    rows = [
        single_35(
            base,
            p_id=i,
            hh_id=i,
            wohnen__bruttokaltmiete_m_hh=700.0,
            bürgergeld__bezug_im_vorjahr=flag,
        )
        for i, flag in enumerate([False, True])
    ]
    result = run(rows, targets).assign(bezug_im_vorjahr=[False, True])
    print("\n[4] Karenzzeit switch, m = 700, Heizkosten = 90")
    print(result.to_string(index=False))
    print(
        "    -> False (inside Karenzzeit) recognises 790 in full;"
        " True (post-Karenzzeit, D11) applies the cap."
    )


def show_income_ladder() -> None:
    """The Anspruch is weakly decreasing in gross earnings, as D10 requires."""
    targets = {"bürgergeld": {"anspruchshöhe_m": "anspruch_m"}}
    base = build_default_row(targets)
    base[GETTSIM_UNTERKUNFTSKOSTEN_COLUMN] = 0.0
    incomes = np.arange(0.0, 2600.0, 25.0)
    rows = [
        single_35(
            base,
            p_id=i,
            hh_id=i,
            arbeitsstunden_w=40.0,
            wohnen__bruttokaltmiete_m_hh=520.0,
            einnahmen__bruttolohn_m=float(income),
            **{GETTSIM_UNTERKUNFTSKOSTEN_COLUMN: 610.0},
        )
        for i, income in enumerate(incomes)
    ]
    anspruch = run(rows, targets)["anspruch_m"].to_numpy()
    fail_if_not_weakly_decreasing(anspruch, name="bürgergeld__anspruchshöhe_m")
    exit_income = incomes[np.argmax(anspruch <= 0.0)]
    print("\n[5] Income ladder, K scenario, 25 EUR steps")
    print(f"    monotone in income: yes ({len(incomes)} grid points)")
    print(f"    y* (first income with no Anspruch) = {exit_income} EUR/month")


def show_kopfteil() -> None:
    """The override column is per-person, so a household amount must be split."""
    targets = {
        "bürgergeld": {
            "kosten_der_unterkunft_m": "anerkannte_kdu_m",
            "regelbedarf_m": "regelbedarf_m",
        }
    }
    base = build_default_row(targets)
    base[GETTSIM_UNTERKUNFTSKOSTEN_COLUMN] = 0.0
    household_amount = np.array([690.0])
    per_person = kopfteil_m(household_amount, np.array([2]))
    rows = []
    for p_id, (alter, geburtsjahr) in enumerate([(35, 1991), (8, 2018)]):
        row = single_35(
            base,
            p_id=p_id,
            hh_id=0,
            alter=alter,
            geburtsjahr=geburtsjahr,
            wohnen__bruttokaltmiete_m_hh=600.0,
            wohnen__wohnfläche_hh=60.0,
            **{GETTSIM_UNTERKUNFTSKOSTEN_COLUMN: float(per_person[0])},
        )
        row["familie__alleinerziehend"] = p_id == 0
        if p_id == 1:
            row["familie__p_id_elternteil_1"] = 0
            row["kindergeld__p_id_empfänger"] = 0
        rows.append(row)
    result = run(rows, targets)
    print("\n[6] §11.1 household 2 (Alleinerziehend + child aged 8), Kopfteilprinzip")
    print(f"    household amount {household_amount[0]} -> {per_person[0]} per person")
    print(result.to_string())


def show_timings() -> None:
    """One `main()` call is a fixed ~2 s regardless of how many households it holds."""
    targets = {
        "bürgergeld": {"anspruchshöhe_m": "anspruch_m", "betrag_m": "betrag_m"},
        "wohngeld": {"betrag_m_wthh": "wohngeld_m"},
        "kinderzuschlag": {"betrag_m_bg": "kinderzuschlag_m"},
    }
    base = build_default_row(targets)
    base[GETTSIM_UNTERKUNFTSKOSTEN_COLUMN] = 0.0
    print("\n[7] Timings, full transfer integration (Bürgergeld + Wohngeld + KiZ)")
    for n_households in (1, 100, 1099, 2198, 10990):
        rows = [
            single_35(
                base,
                p_id=i,
                hh_id=i,
                wohnen__bruttokaltmiete_m_hh=float(300 + i % 400),
                wohngeld__mietstufe_hh=1 + i % 7,
                **{GETTSIM_UNTERKUNFTSKOSTEN_COLUMN: float(390 + i % 400)},
            )
            for i in range(n_households)
        ]
        start = time.perf_counter()
        run(rows, targets)
        elapsed = time.perf_counter() - start
        print(
            f"    n = {n_households:6d}   {elapsed:6.2f} s"
            f"   {elapsed / n_households * 1000:8.3f} ms/household"
        )


if __name__ == "__main__":
    show_gettsim_own_cap()
    show_neutralised_cap()
    show_scenario_contrast()
    show_karenzzeit_switch()
    show_income_ladder()
    show_kopfteil()
    show_timings()
