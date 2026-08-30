# Results

Kommunale KdU-Obergrenzen as the missing regional parameter of German tax-transfer
models. This is the consolidated results text §22's Gate 2 asks for, extended to cover
the simulation of P0.6 and P0.7. It is organised around the five Beiträge of §2, and
every §19 main figure is read in the four parts §21 prescribes.

Every number below is read from a built artefact in `bld/` by
`src/kdu/final/task_workshop_deck.py`. Nothing here is typed by hand, so the document
cannot drift away from the pytask build that produced it.

**What is measured.** `K` is the local maximum recognisable Bruttokaltmiete a Kreis
publishes under § 22 SGB II and § 35 SGB XII. `W` is the Höchstbetrag of § 12 WoGG for
the Gemeinde's statutory Mietenstufe, in the Fassung in force since 2025-01-01 (A1),
**times the 10 % Sicherheitszuschlag** (D15). That product, not the bare table, is the
value a model without a local parameter should substitute: such a model is by
construction in the situation § 22 SGB II case law addresses, and the fallback the BSG
prescribes there is the WoGG table plus the Zuschlag. Numbers against the bare table are
reported throughout as the `base` robustness variant. `D = K − W`, and `L = 100 (log K −
log W)`. Both are caps on what may be recognised, not amounts anyone is paid. Where a
need level is reported it is the administrative Bruttokaltbedarf before income
offsetting, which excludes heating.

**Sample.** 9,442 Gemeinden across 357 Kreise, balanced over household sizes 1 to 4, at
the Analysestichtag 2026-08-31 (D2, D3). The `K − W` comparison runs on 9,323 of them,
because 119 are gemeindefreie Gebiete that the Anlage zur WoGV does not list, so no
Wohngeld benchmark exists for them under the statute (A2). Both numbers appear wherever
coverage is stated.

## Coverage, and where the evidence stops

The main sample covers 9,442 of 10,980 Gemeinden and 89.2 % of the population. Coverage
by Bundesland is itself a finding rather than noise: it runs from 66.9 % of Gemeinden in
Mecklenburg-Vorpommern to 100.0 % in Schleswig-Holstein, and the shortfall falls in
Kreise that publish a Nettokaltmiete cap only or publish nothing at all.

43.1 % of main-sample Gemeinden are quality tier A and 9.4 % are tier C; 94.9 % rest on
a Bruttokaltmiete the document prints outright rather than on one summed from published
components. Tier C Gemeinden are inside the main sample because D3 defines the sample by
completeness of the Bruttokaltmiete, not by tier, and every table can condition on
`quality_tier`.

§6.6's census of manual re-checks was waived on the data owner's judgement (A9). What
stands in its place is the automated validation that was possible against the corpus
text layer: 2,209 observations checked, 1,990 passing, a 90.1 % agreement rate on the
checkable subset out of a 14,462-row worklist. That rate is the measured agreement on
the subset a text layer existed for, and it is not extrapolated to the rest of the
table.

## Beitrag 1 — the Wohngeld-Höchstbetrag is not a precise proxy

**How to read the medians below.** Against the correct fallback of D15 the median gap is
close to zero at every household size. That is the point, not a null result: it says the
§ 12 WoGG table plus the Sicherheitszuschlag is approximately unbiased *on average over
Germany*, and therefore that the whole of the proxy error is dispersion. A level bias
would be repairable with one constant; dispersion is not, and it is what the per-
Gemeinde quantiles, the share of Gemeinden more than 100 € from the benchmark, and the
mean absolute gap measure. Against the bare table (`base`) the same medians sit roughly
10 % higher, because that comparison charges the Sicherheitszuschlag to the local Kreis
as if it were an error.

Figures 1 and 2 of §19 are one object: two maps of `L` on a shared, zero-centred colour
scale, so the same colour means the same log gap at both household sizes.

### Figure 1 — Map of the log proxy error, household size 1

**What is measured.** For each of the 9,323 Gemeinden with both a local Bruttokaltmiete
cap and a statutory Mietenstufe, `L = 100 (log K − log W)` at household size 1: the log
gap between the local cap and the value a tax-transfer model would substitute for it.

**The central quantitative finding.** The unweighted median Gemeinde sits +1 € above the
Wohngeld benchmark, or +0.2 log points; the population-weighted median is -4 € and the
Bedarfsgemeinschaft-weighted median -23 €. The spread is wide, from -74 € at the tenth
percentile to +98 € at the ninetieth, and the sign is not uniform: `D` is negative in
35.7 % of Gemeinden and exactly zero in 10.3 %. The mean absolute gap is 46 € per month,
and it exceeds 100 € in 13.0 % of Gemeinden.

**The same finding with the WoGG-linked Gemeinden set aside.** Their gap is zero by
construction under D15, so every pooled figure above is a mixture of them and the rest,
and both readings are given side by side throughout. Excluding the `exact_ratio` group
(8,120 Gemeinden remain, 12.9 % excluded) the median is +16 €, the mean absolute gap 53
€ and the share beyond 100 € 14.9 %. Excluding the broader `linked_union` group (8,047
remain, 13.7 % excluded) the median is +9 €, the mean absolute gap 53 € and the share
beyond 100 € 15.0 %. Setting the group aside raises the median rather than lowering it,
and raises the dispersion with it.

**Why it matters for tax-transfer simulation.** A model substituting `W` for `K` does
not make one nationwide error but a spatially structured one, running in opposite
directions in different regions. It therefore does not average out across a national
sample, and it cannot be absorbed into a constant or into a Bundesland fixed effect.

**What may not be concluded.** A high cap is not evidence that a Kreis is more generous
and a low one is not evidence that it is more restrictive: the cap is endogenous to the
local housing market, to administrative procedure, and to how a Kreis draws its
Vergleichsräume. Nothing here identifies a causal effect of any policy. Neither `K` nor
`W` is an actual KdU payment; both are caps, and what is recognised is the lesser of the
cap and the actual Bruttokaltmiete. Nothing here speaks to housing availability, which
no cap can measure. In the `exact_ratio` group the colour reports the definitional
identity `K = 1.10 × W` that BSG case law permits a Kreis without a schlüssiges Konzept
to adopt, and not an empirical regularity — which is why both the with and the without
reading are given above.

### Figure 2 — Map of the log proxy error, household size 4

**What is measured.** For each of the 9,323 Gemeinden with both a local Bruttokaltmiete
cap and a statutory Mietenstufe, `L = 100 (log K − log W)` at household size 4: the log
gap between the local cap and the value a tax-transfer model would substitute for it.

**The central quantitative finding.** The unweighted median Gemeinde sits +0 € above the
Wohngeld benchmark, or +0.0 log points; the population-weighted median is +0 € and the
Bedarfsgemeinschaft-weighted median -12 €. The spread is wide, from -89 € at the tenth
percentile to +155 € at the ninetieth, and the sign is not uniform: `D` is negative in
42.2 % of Gemeinden and exactly zero in 3.4 %. The mean absolute gap is 73 € per month,
and it exceeds 100 € in 27.2 % of Gemeinden.

**The same finding with the WoGG-linked Gemeinden set aside.** Their gap is zero by
construction under D15, so every pooled figure above is a mixture of them and the rest,
and both readings are given side by side throughout. Excluding the `exact_ratio` group
(7,981 Gemeinden remain, 14.4 % excluded) the median is +18 €, the mean absolute gap 85
€ and the share beyond 100 € 31.8 %. Excluding the broader `linked_union` group (8,047
remain, 13.7 % excluded) the median is +8 €, the mean absolute gap 83 € and the share
beyond 100 € 31.5 %. Setting the group aside raises the median rather than lowering it,
and raises the dispersion with it.

**Why it matters for tax-transfer simulation.** A model substituting `W` for `K` does
not make one nationwide error but a spatially structured one, running in opposite
directions in different regions. It therefore does not average out across a national
sample, and it cannot be absorbed into a constant or into a Bundesland fixed effect.

**What may not be concluded.** A high cap is not evidence that a Kreis is more generous
and a low one is not evidence that it is more restrictive: the cap is endogenous to the
local housing market, to administrative procedure, and to how a Kreis draws its
Vergleichsräume. Nothing here identifies a causal effect of any policy. Neither `K` nor
`W` is an actual KdU payment; both are caps, and what is recognised is the lesser of the
cap and the actual Bruttokaltmiete. Nothing here speaks to housing availability, which
no cap can measure. In the `exact_ratio` group the colour reports the definitional
identity `K = 1.10 × W` that BSG case law permits a Kreis without a schlüssiges Konzept
to adopt, and not an empirical regularity — which is why both the with and the without
reading are given above.

### Figure 7 — BA validation: recognition rate by decile of K/W

**What is measured.** Against the Statistik der Bundesagentur für Arbeit's "Wohn- und
Kostensituation" for the reference month, `R^BA` is the share of actual Bruttokaltmiete
a Jobcenter recognises and `N^BA = 1 − R^BA` the non-recognised share. `N^BA` is
regressed on `log(K/W)` and on `log(M/K)`, with household-size and Bundesland fixed
effects and standard errors clustered on the Jobcenter, over 1,412 Jobcenter-by-
household-size rows in 353 clusters.

**The central quantitative finding, and it is a conditional one.** A higher local cap
relative to the Wohngeld Höchstbetrag goes with a lower non-recognised share: β on
`log(K/W)` is -0.0361 with a Jobcenter-clustered standard error of 0.0066, and -0.0332
(0.0066) once the `linked_union` Jobcenter are dropped. Greater market pressure relative
to the cap goes the other way, β on `log(M/K)` = +0.0496 (0.0081). **The association is
conditional and not raw:** across deciles of `K/W` the mean ratio rises 0.835 to 1.365,
a log distance of 0.49, while the mean recognition rate moves only 0.23 percentage
points where the fitted β implies 1.78. The Bundesland fixed effects carry most of it,
because Kreise with high caps are disproportionately Kreise with expensive housing and
the two pull `N^BA` in opposite directions. The decile figure may never be shown without
the coefficient beside it (A20).

**Why it matters for tax-transfer simulation.** The sign is the one the design predicts,
on data collected by a different institution for a different purpose, so the local cap
the project measures is picking up something the administrative record also sees. That
is what an external validation is for: it does not add precision to the proxy error, it
tests whether `K` behaves like the constraint it is claimed to be.

**What may not be concluded.** Nothing here is a causal effect: a Jobcenter's
recognition rate and its Kreis's cap are jointly determined by the same local housing
market. Within the `exact_ratio` group the regressor is degenerate — `sd(log K/W)` is
0.1367 overall against a clustered β of +0.3615 with a standard error of 0.6098 on 155
rows — which is no evidence either way, exactly as D7 predicts. `M` is a Zensus
Bestandsmiete measured net-cold against a gross-cold cap, so `M/K` understates market
pressure and speaks to no housing availability. Neither `K` nor the recognised amount is
an actual KdU payment.

## Beitrag 2 — the deviation is household-specific

### Figure 4 — Familien-Tilt against the average relative KdU level

**What is measured.** The Familien-Tilt `F = log(K4/W4) − log(K1/W1)` per Gemeinde,
against the average of `log(K/W)` over household sizes 1 to 4. `F` is positive where the
local cap sits relatively higher for a four-person household than for a single, and it
is zero by construction wherever `K` is a fixed multiple of `W` at both sizes.

**The central quantitative finding.** The unweighted median tilt is +0.0000 log points
with a P10–P90 range of -0.0894 to +0.0958; 12.2 % of Gemeinden sit exactly at zero.
Excluding the `linked_union` group the median is +0.0007 and the range widens to -0.0988
to +0.1079; weighting by Bedarfsgemeinschaften instead of counting Gemeinden gives a
median of +0.0208. The same movement shows in the euro gap itself, which runs from a
median of +1 € at household size 1 to +0 € at size 4, and in the ranking: the Spearman
correlation of the proxy error between the two sizes is 0.842, and 20.9 % of Gemeinden
move at least two deciles between them.

**Why it matters for tax-transfer simulation.** The mismeasurement is correlated with
household composition. A correction calibrated on single-person households carries the
wrong magnitude, and for a substantial minority of Gemeinden the wrong sign, when the
same model simulates a family. No Gemeinde-level fixed effect can absorb an error that
changes inside the Gemeinde.

**What may not be concluded.** A steeply rising cap schedule is not evidence of family-
friendly local policy. A Kreis facing a market where large dwellings are relatively
expensive must set a steeper schedule to recognise the same housing standard, so the
tilt is endogenous to the local housing stock and to the Vergleichsraum definition. The
flagged group's tilt is 76.0 % exactly zero and never exceeds 0.0127 in absolute value;
that residual is the rounding of caps published in whole euro, and it is not a finding
about those Kreise.

## Beitrag 3 — the Mietenstufen compress substantial local heterogeneity

### Figure 3 — Boxplots of K/W within the Wohngeld-Mietenstufen

**What is measured.** The distribution of `K/W` within each of the seven statutory
Mietenstufen, one box per Mietenstufe and household size, over the 9,323 Gemeinden in
357 Kreise that carry both values. The companion table reports how much of the variation
in `log K` a Mietenstufe classification accounts for.

**The central quantitative finding.** A Mietenstufe classification accounts for 40.6 %
of the variation in `log K` at household size 1 and 46.1 % at size 4, leaving residual
standard deviations of 0.142 and 0.137 log points. Inside a single Mietenstufe the
typical P90 − P10 spread of the single-person cap is 168 €, and it reaches 234 € in
Mietenstufe 7, which holds 11 Gemeinden. 37.8 % of Gemeinden sit more than 50 € from the
median of their own Mietenstufe and 12.1 % more than 100 €. Excluding the `linked_union`
group, whose `K/W` is pinned beside 1.10 by construction, the explained share falls to
36.2 % at household size 1 and the residual standard deviation rises to 0.152.

**Why it matters for tax-transfer simulation.** The Mietenstufe is the only regional
housing parameter such models currently carry. Assigning needs by Mietenstufe therefore
gives Gemeinden whose published caps differ by the amounts above the same administrative
Bruttokaltbedarf before income offsetting, and the residual spread inside one
Mietenstufe is of the same order as the differences between adjacent Mietenstufen. Where
the residual is large, the simulated Bedarf, the simulated Anspruch and the simulated
exit threshold inherit the whole mismeasurement. For Gemeinden below 10,000 inhabitants
the statutory rent level is determined Kreis-wide, which is the institutional reason the
compression is not evenly distributed.

**What may not be concluded.** Dispersion within a Mietenstufe is not evidence that any
Kreis is misapplying the law, and it is not a causal effect of the Mietenstufe
classification. The ratio of 1.10 in the flagged group follows from BSG case law and is
a definition, not a regularity. Nothing in the boxplots speaks to housing availability:
they compare two administrative parameters, not markets.

### Figure 8 — Administrative border jumps

**What is measured.** Every pair of directly adjacent Gemeinden, matched on the shared
edges of the unsimplified boundary source, classified by whether the two sit in one
policy region, in two Kreise of one Bundesland, or in two Bundesländer. `J` is the
absolute euro difference between their caps. The headline figures exclude the
`linked_union` Gemeinden and the pairs flagged as possible geometry artefacts; the
pooled counterparts are given beside them.

**The central quantitative finding.** Inside a policy region the cap is flat: 82 % of
the 18,272 within-region pairs carry an identical four-person cap and the median `J` is
0 €. Across a Kreis boundary the median four-person household faces a monthly step of 81
€ over 3,555 pairs, and 38.1 % of those pairs exceed 100 €. Across a Bundesland boundary
the median is 97 € and 46.8 % exceed 100 €, over 825 pairs. The step grows with
household size: at size 1 the same Kreis-boundary median is 40 €. The §13.4 tight
comparison group — same Mietenstufe, Zensus rent within ten percent, similar density,
different policy region — retains 685 pairs and does **not** close the gap: median 71 €
with 30 % above 100 €.

**The same finding with the WoGG-linked Gemeinden left in.** Two linked Kreise in one
Mietenstufe carry identical caps by construction, so pooling adds pairs that cannot
jump. It barely moves the Kreis-boundary step, which is 81 € over 4,775 pairs with 39.0
% beyond 100 €, against 81 € and 38.1 % excluding them. It bites on the §13.4 tight
comparison group, where matching on Mietenstufe selects the linked pairs
disproportionately: 63 € over 904 pairs pooled, against 71 € over 685 excluding them.
The headline uses the excluding reading for that reason.

**Why it matters for tax-transfer simulation.** The cap is an administrative step
function on the map, constant inside a Kreis and discontinuous at its edge, which is
exactly the shape a Mietenstufe-based or a national parameter cannot reproduce. Two
Gemeinden that a model treats as one housing environment can carry an administrative
Bruttokaltbedarf before income offsetting that differs by more than the median step one
additional person adds to the cap.

**What may not be concluded. This is an administrative discontinuity, never a regression
discontinuity.** Nothing here is a causal effect, and no design in this project
identifies one: households sort across these borders, Kreise are not assigned their
boundaries at random, and the tight comparison group narrows the comparison without
making it exogenous. The step is not evidence that either side is applying the law
wrongly, and a cap is not an actual KdU payment.

## Beitrag 4 — the proxy error moves simulated claims and exit thresholds

The simulation runs GETTSIM 1.3 at Rechtsstand 2026 on the four §11.1 Modellhaushalte,
twice per Gemeinde: once with the local cap and once with the Wohngeld-Höchstbetrag.
GETTSIM's own 10 €/m² warm housing rule is replaced rather than reconfigured, because
left in place it would have truncated both scenarios to the same value and produced a
false null (A6). All households are declared beyond month 12, so the cap is in force.

As in Beitrag 1, the median shift is near zero because D15 benchmarks against the
fallback a correctly specified model would already apply. What moves the simulation is
the spread: the P10–P90 range of `Δy*` and the share of Gemeinden whose exit threshold
moves by more than 100 € in either direction. A model substituting `W` is not wrong on
average — it is wrong in a particular place, and the sign of the error depends on which
place.

### Figure 5 — Distribution of the simulated exit-threshold shift

**What is measured.** `Δy* = y*^K − y*^W`, the shift in the gross monthly income at
which the simulated SGB II claim runs out, located by bisection to one euro in each of
889 distinct simulation cells and joined back to 9,323 Gemeinden. The figure shows its
distribution for each Modellhaushalt.

**The central quantitative finding.** For Couple (35, 35) with children aged 8 and 14
the median shift is +1 € per month (P10 -141 €, P90 +255 €), which is 0.0 weekly working
hours at the 2026 Mindestlohn; it exceeds 100 € in absolute value in 42.8 % of
Gemeinden, and it rises to +13 € once the `linked_union` group is set aside. The single
adult sees +2 € and the pensioner +1 €. The population-weighted median for the headline
household is +0 €. The claim difference at zero income is +0 € per month, and the
maximum claim difference is the same quantity measured a second time — they are one
outcome, not two independent pieces of evidence, because the Bedarf difference is the
constant `K − W` and both scenarios apply an identical Anrechnung schedule (A16).
Holding the cold cap fixed and moving heating costs from 101 € to 168 € leaves the claim
difference unchanged at +0 € and moves the median exit threshold by 0 €; that is a
confirmation that the design isolates the cold cap, and it carries no information beyond
that.

**Why it matters for tax-transfer simulation.** The exit threshold is where transfer
withdrawal ends and the tax system takes over. A model substituting `W` for `K`
therefore misstates not only the level of the simulated claim but the income range over
which it is paid at all, and with it every participation tax rate, caseload count and
labour-supply margin computed from that range.

**What may not be concluded.** None of these Δ is a causal effect: they are the
difference between two ways of parameterising the same simulation, not the consequence
of any policy change. They are not a statement about what any Bedarfsgemeinschaft
receives, since `K` is a cap. Every Δ is conditional on the cap being in force: inside
the twelve-month Karenzzeit of § 22 Abs. 1 S. 2–3 SGB II actual Unterkunftskosten are
recognised in full and the proxy error is identically zero (D11). The Vorrangprüfung
between SGB II, Wohngeld and Kinderzuschlag assumes the wohngeldrechtlicher Teilhaushalt
coincides with the Bedarfsgemeinschaft, which bites hardest for the four-person
household.

### Figure 6 — Budget curves for selected Gemeinden

**What is measured.** Disposable income against gross monthly earnings on a 25 € grid
for Single adult, age 35, drawn twice per Gemeinde — once under the local cap, once
under the Wohngeld-Höchstbetrag — for three Gemeinden at the P10, P50 and P90 of the
proxy-error distribution: P10 Kammerforst (K 324 €, W 397 €, Δy* -134 €); P50 Andervenne
(K 398 €, W 397 €, Δy* +2 €); P90 Achtrup (K 495 €, W 397 €, Δy* +186 €).

**The central quantitative finding.** The two curves are a vertical shift of one another
over the whole range in which the claim is positive, and they meet at the exit
threshold, which they reach at different earnings. Whether the shift exists at all
depends on where the actual Bruttokaltmiete sits, which the §12.2 rent grid puts a
number on: at 50 % of `max(K, W)` the two scenarios are indistinguishable in 100 % of
cells, at 90 % in 56.5 %, and only once rent reaches `max(K, W)` does the median claim
difference reach its full +1 € with 10.3 % of cells still unaffected.

**Why it matters for tax-transfer simulation.** This is the figure that makes the
mechanism legible without a microsimulation background, and it is also the one that
keeps the headline honest: the cap gap is an upper bound on the simulation error, not
the error itself. A modeller can read straight off the curves which households the
substitution touches and which it leaves alone.

**What may not be concluded.** The headline rent assumption `m = max(K, W)` is a
construction that makes both caps bind, not an estimate of what anyone pays, so the
curves are not a description of any real household's budget. The rent grid is
normalised, not a rent distribution, so nothing here says how many households sit at
each point. The three Gemeinden are quantile illustrations and are not representative of
their Bundesländer.

## Beitrag 5 — the local KdU is part of a regionalised needs level

**What is measured.** The administrative Bruttokaltbedarf before income offsetting of
§11.2: the nationally uniform Regelbedarfe and Mehrbedarfe of the Modellhaushalt plus
the local KdU-Obergrenze, before any income is offset. Regelbedarfsstufe 1 is 563 € for
2026 — a Nullrunde, confirmed against § 28a Abs. 5 SGB XII, since the arithmetic
Fortschreibung of 557 € is below the amount in force and may not reduce it (A14).

**The central quantitative finding.** For Single adult, age 35 the Regelbedarf is 563 €
everywhere in Germany, and the measure has a median of 992 €, a P10–P90 span of 906 € to
1,123 €, and a full regional range of 638 € across 9,442 Gemeinden, of which 9,323 carry
a Wohngeld benchmark to compare against. The housing component is a median 43.2 % of it.
For Couple (35, 35) with children aged 8 and 14 the median is 2,633 € with a regional
range of 1,121 € and a housing share of 27.0 %. Substituting the Wohngeld-Höchstbetrag
moves the measure by a median of +1 € and +0 € respectively, pooled — and by +9 € and +8
€ with the WoGG-linked Gemeinden set aside, where the difference is not zero by
construction.

**Why it matters for tax-transfer simulation.** Most parameters of the German minimum-
income system are set federally, which invites the assumption that the needs level is a
national constant. It is not: between 27 % and 43 % of it is a regional administrative
parameter, and a model without that parameter has no way to reproduce the regional
variation in simulated need.

**What may not be concluded.** The measure excludes heating, so it is not a complete
subsistence level and may not be described as one. It is built on caps, so it is the
maximum a Bedarfsgemeinschaft's Bruttokaltmiete could be recognised at, not an amount
paid. The regional range is not a ranking of local policy: it reflects housing markets,
Vergleichsraum definitions and document vintages at the same time.
`fig_needs_level_distribution.html` carries this Beitrag as a backup slide; §19 does not
list it among the eight main figures.

## The workshop deck — six figures (§19)

§19 admits at most 6 figures to the main talk. The selection is:

1. **Map of the log proxy error, household size 1** (`fig_proxy_error_log_map_h1.html`,
   Beitrag 1). Beitrag 1 in one picture: the substitution error is spatially structured,
   so it cannot be absorbed into a national constant.
2. **Map of the log proxy error, household size 4** (`fig_proxy_error_log_map_h4.html`,
   Beitrag 1). Shown beside figure 1 on the shared colour scale; the pair, not either
   map alone, is what shows the error moves with household size.
3. **Boxplots of K/W within the Wohngeld-Mietenstufen**
   (`fig_within_mietenstufe_ratio.html`, Beitrag 3). Beitrag 3, and the figure that
   speaks directly to model builders: it shows what the Mietenstufe, the only regional
   housing parameter such models carry, leaves unexplained.
4. **Familien-Tilt against the average relative KdU level**
   (`fig_household_profile_tilt_scatter.html`, Beitrag 2). Beitrag 2: the error changes
   with household size inside one and the same Gemeinde, so no fixed regional intercept
   can absorb it.
5. **Distribution of the simulated exit-threshold shift**
   (`fig_microsim_delta_exit_threshold.html`, Beitrag 4). The headline policy number:
   what the proxy error does to a simulated Transfer-Ausstiegsschwelle, in euro per
   month.
6. **Budget curves for selected Gemeinden** (`fig_microsim_budget_curves.html`, Beitrag
   4). Makes the mechanism legible without a microsimulation background, and shows why
   the cap gap is an upper bound on the simulation error rather than the error itself.

Everything else goes to backup or annex:

- **BA validation: recognition rate by decile of K/W**
  (`fig_ba_validation_recognition_by_decile.html`). Backup: the external validation
  answers a reviewer's question rather than carrying an argument of its own, and it may
  never be shown without the coefficient beside it, which a single slide makes hard
  (A20).
- **Administrative border jumps** (`fig_border_jumps_distribution.html`). Annex: the
  adjacency evidence of P1.1 is descriptive, with no identification strategy behind it
  (§20), so it documents the discontinuity rather than exploiting it.

Backup slides also carry the remaining built figures: the ECDF and the absolute
distribution of `D`, the Bundesland by household-size heatmap, the rent-point figure of
§8.4, the within-Mietenstufe cap boxplots and strata, the tilt map, the tilt
distribution, the decile transition matrix, the exit-threshold map, the hours-equivalent
figure, the proxy error against Δy*, and the needs-level distribution.
`bld/tables/workshop_figure_selection.csv` carries this table in machine-readable form.

## Limitations that travel with every number above

- **The Karenzzeit.** Under § 22 Abs. 1 S. 2–3 SGB II the cap is suspended for the first
  twelve months and actual Unterkunftskosten are recognised in full, so the proxy error
  is identically zero for a Bedarfsgemeinschaft inside it (D11). Every Δ reported here
  is conditional on the cap being in force. The BA product used for the external
  validation carries no Bezugsdauer, so the share of Bedarfsgemeinschaften inside the
  Karenzzeit is not scaled for.
- **9,323 against 9,442.** 119 main-sample Gemeinden have a local cap but no statutory
  Mietenstufe, so no Wohngeld benchmark exists for them at all and every `K − W`
  comparison runs on the smaller number (A2). §7's acceptance criterion of a complete
  Mietenstufe assignment is struck as unsatisfiable, with that reason recorded.
- **Two flagged groups, never one.** `exact_ratio` is the group with `K/W = 1.100` to
  five ten-thousandths, 12.9 % of Gemeinden at household size 1, and it is the group for
  which the proxy error is a definitional identity. `linked_union` is the union of the
  notes-regex and ratio detectors, 18.8 %, and it is the right group when asking which
  Kreise lean on the § 12 WoGG table at all. Every with-and-without pair above states
  which of the two it uses; the two are not interchangeable (A12).
- **ΔT_max and ΔT(0) are one outcome.** They coincide in every cell by construction, and
  the heating sensitivity cannot move ΔT(0) at all. Neither may be presented as
  independent confirmation of the other (A16).
- **The manual validation census was waived** on the data owner's judgement (A9). The
  90.1 % automated agreement rate is measured on the subset with a text layer and is not
  extrapolated. 666 rows remain flagged `not_found_in_text` and 19 source citations
  resolve to no corpus file.
- **The Zensus cross-tabulation of floor area by rent is unavailable** without a
  registered account, so a market-stress indicator can compare only against the overall
  mean Gemeinde Nettokaltmiete. That ignores that small dwellings cost more per square
  metre and biases a single-person indicator in a known direction (A11). Nothing was
  substituted for it.
- **Document vintages are mixed**, from 2019 to 2026, and the sample carries every rule
  in force at the Stichtag (D2). `publication_date` is empty throughout the source
  register and `retrieval_date` is a file mtime, so both are proxies rather than
  records.
- **The Bedarfsgemeinschaft weighting rests on an assumption.** Kreis
  Bedarfsgemeinschaft stock at this household size, spread over the Kreis's Gemeinden in
  proportion to population; BA publishes no Gemeinde-level stock.
- **Δy* is not computed across the rent grid.** Variante 2 delivers ΔT(0) at every rent
  factor but not the exit threshold, which would add a bisection at nine rent factors to
  every pytask build for a dimension whose shape is already clear (A17).

## §23 Definition of Done — the audit

All twelve criteria are met. The two that were open at the last audit are the external
validation, which P1.2 closed, and the manifest coverage of the tables and figures,
which P1.1 and P1.2 closed by registering their own outputs.

1. **Met — A cleaned Gemeinde-level KdU dataset for household sizes 1 to 5.**
   `kdu_municipality_household.parquet`, long and keyed `ags x household_size` over h =
   1…5 (D14); the h = 1…4 balanced main sample and the separate h = 1…5 subsample are
   both built (D3).
2. **Met — An unambiguous policy-region assignment.** `policy_region_id = ags_kreis` for
   all 400 Kreise (D1). Within-Kreis dispersion is reported descriptively rather than
   flagged, because 210 Kreise define Vergleichsräume internally.
3. **Met — A temporally and conceptually matching Wohngeld benchmark.**
   `wogg_benchmark.parquet`, the § 12 WoGG Höchstbetrag times the BSG
   Sicherheitszuschlag, keyed on the statutory `wogv_mietstufe` (D15), cross-validated
   against three independent sources (A1, A7).
4. **Met — The complete distribution of the euro and log proxy error.** Table 2 and
   `proxy_error_gemeinde_household.parquet`, every household size under four weightings,
   three benchmark variants and both linkage groups.
5. **Met — Quantification of the heterogeneity inside the Mietenstufen.** Table 3 with
   the variance decomposition, the dispersion tables and the boxplot figure of Beitrag
   3.
6. **Met — Analysis of the household-size profile.** The Familien-Tilt, the marginal
   amounts, the rank stability and the decile transition matrix of Beitrag 2.
7. **Met — A regionalised administrative needs level for the model households.**
   `table_needs_level.csv` and `needs_level_gemeinde.parquet` for all four §11.1
   Modellhaushalte (Beitrag 5).
8. **Met — A standard-case claim and exit-threshold analysis.** Table 4, the budget
   curves and the exit-threshold distribution, located by bisection to one euro on
   GETTSIM, whose own housing cap was replaced rather than reconfigured (D10, A6).
9. **Met — At least one external validation.** The BA “Wohn- und Kostensituation”
   validation above: `table5_external_validation.csv` and the §14.4 specifications, on
   data collected by a different institution for a different purpose.
10. **Met — A complete quality and methods appendix.** `quality_report.html`,
    `data_dictionary.csv`, `source_register.csv`, `exclusion_log.csv`,
    `validation_worklist.csv`, plus `docs/coverage_notes.md`, `docs/decision_log.md` and
    `docs/simulation_assumptions.md`.
11. **Met — Reproducible tables and figures.** One pytask graph rebuilds every table and
    figure this document reads, and all 8 §19 main figures are built.
    `bld/results_manifest.csv` registers 72 of the 72 files under `bld/tables` and
    `bld/figures`, each with the seven §5.2 fields.
12. **Met — A clear separation of descriptive findings, simulations and causal claims.**
    Every figure carries the §21 four-part reading whose fourth part states what may not
    be concluded; `forbidden_term_hits` fails this build on a §20 term used as a claim;
    the border-jump evidence is labelled an administrative and never a regression
    discontinuity.

Met is not the same as finished. The waived validation census (A9), the unavailable
Zensus cross-tabulation (A11) and the Karenzzeit conditionality (D11) are limitations of
results that exist, not criteria left open.

## Reproduction

```
pixi install
pixi run pytask      # rebuilds every artefact this document reads
pixi run pytest      # the test suite
```

`bld/results_manifest.csv` registers 72 outputs, each with the seven §5.2 fields:
filename, analysis module, underlying dataset, script, creation date, a one-line
interpretation and its key limitation. That is every file under `bld/tables/` and
`bld/figures/`, the supporting robustness tables included, so no output is presented
without a recorded reading and caveat.

Language follows D13: English throughout, German kept only for terms with no faithful
translation.
