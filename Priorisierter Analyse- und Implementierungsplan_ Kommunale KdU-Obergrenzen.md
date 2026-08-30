# Priorisierter Analyse- und Implementierungsplan
## Kommunale KdU-Obergrenzen als fehlender regionaler Parameter deutscher Steuer-Transfer-Modelle

## 1. Arbeitsauftrag und Ziel des Projekts

Ziel des Projekts ist es, aus dem neu erhobenen Datensatz kommunaler beziehungsweise lokaler KdU-Obergrenzen einen eigenständigen empirischen Beitrag zu entwickeln. Die vorhandenen Karten sind dabei Ausgangspunkt, nicht Endprodukt.

Der Beitrag soll drei Elemente verbinden:

1. **Datenbeitrag:** Aufbau und Dokumentation eines bislang nicht zentral verfügbaren Datensatzes zu lokalen Obergrenzen der anerkennungsfähigen Unterkunftskosten.
2. **Messfehlerbeitrag:** Quantifizierung des Fehlers, der entsteht, wenn Steuer-Transfer-Modelle ersatzweise Wohngeld-Höchstbeträge verwenden.
3. **Simulationsbeitrag:** Quantifizierung der Auswirkungen dieses Fehlers auf standardisierte Leistungsansprüche, das regionale Bedarfsniveau und die simulierten Transfer-Ausstiegsschwellen.

Die zentrale Forschungsfrage lautet:

> **Wie groß ist der Fehler deutscher Steuer-Transfer-Simulationen, wenn lokale KdU-Obergrenzen durch die Wohngeld-Höchstbeträge approximiert werden?**

Die zentrale inhaltliche Aussage soll nicht sein, dass lokale KdU-Regelungen „großzügiger“ oder „restriktiver“ als das Wohngeld seien. KdU und Wohngeld sind unterschiedliche Institutionen. Der Wohngeld-Höchstbetrag dient hier ausschließlich als:

- häufig verfügbare Ersatzvariable,
- institutionell relevante Vergleichsgröße,
- Benchmark für die räumliche Auflösung eines bundesweiten Transferparameters.

Die lokalen KdU-Obergrenzen sind keine tatsächlichen Auszahlungen. Nach SGB II und SGB XII werden tatsächliche Unterkunfts- und Heizkosten grundsätzlich anerkannt, soweit sie angemessen sind. Die lokale Obergrenze bestimmt daher nur den maximal regulär anerkennungsfähigen Unterkunftsbedarf; die tatsächliche Leistung hängt zusätzlich von tatsächlicher Miete, Einkommen, Haushaltskonstellation, Karenz- und Ausnahmeregeln ab.

---

# 2. Erwartete Hauptbeiträge

Die empirische Arbeit soll auf die folgenden fünf Aussagen zulaufen:

### Beitrag 1: Der Wohngeld-Höchstbetrag ist kein präziser Proxy für die lokale KdU

Es soll gezeigt werden, wie häufig, in welcher Richtung und in welcher Größenordnung sich die lokale KdU-Obergrenze vom Wohngeld-Höchstbetrag unterscheidet.

### Beitrag 2: Die Abweichung ist haushaltsspezifisch

Die Differenz zwischen KdU und Wohngeld soll nicht nur für Einpersonenhaushalte, sondern für mehrere Haushaltsgrößen untersucht werden. Insbesondere ist zu prüfen, ob einzelne lokale KdU-Systeme relativ stärker auf Singles oder auf Familien ausgerichtet sind.

### Beitrag 3: Wohngeld-Mietenstufen komprimieren erhebliche lokale Heterogenität

Es soll quantifiziert werden, wie stark sich KdU-Obergrenzen innerhalb derselben Wohngeld-Mietenstufe unterscheiden. Für Gemeinden unter 10.000 Einwohnern wird das Wohngeld-Mietenniveau grundsätzlich kreisweise festgestellt, während größere Gemeinden gesondert eingestuft werden. Diese institutionelle Grobkörnigkeit ist für die Proxyfrage besonders relevant.

### Beitrag 4: Der Proxyfehler verändert simulierte Leistungsansprüche und Ausstiegsschwellen

Für ausgewählte Modellhaushalte soll berechnet werden, wie stark die Verwendung des Wohngeld-Höchstbetrags anstelle der lokalen KdU den simulierten Grundsicherungsanspruch und das Bruttoeinkommen beim Transferaustritt verändert.

### Beitrag 5: Die lokale KdU ist ein Baustein eines regionalisierten administrativen Bedarfsniveaus

Obwohl wesentliche Regelbedarfsparameter bundeseinheitlich sind, variiert der gesamte Bedarf eines standardisierten Haushalts aufgrund der lokalen Unterkunftskomponente. Diese regionale Variation soll explizit ausgewiesen werden.

---

# 3. Prioritäten und Reihenfolge

Die Arbeit ist strikt in der folgenden Reihenfolge durchzuführen. Mit Analysen der Priorität P1 oder P2 darf erst begonnen werden, wenn die Datenprüfung unter P0 abgeschlossen ist.

| Priorität | Modul | Funktion |
|---|---|---|
| P0 | Datenharmonisierung und Qualitätsprüfung | Unverzichtbare Grundlage |
| P0 | Aufbau des vergleichbaren Wohngeld-Benchmarks | Unverzichtbare Grundlage |
| P0 | Deskriptive Proxyfehleranalyse | Empirischer Kern |
| P0 | Heterogenität innerhalb der Mietenstufen | Empirischer Kern |
| P0 | Haushaltsgrößenprofil und regionalisiertes Bedarfsniveau | Empirischer Kern |
| P0 | Standardfall-Mikrosimulation | Zentraler Workshop-Beitrag |
| P1 | Analyse administrativer Grenzsprünge | Räumliche Vertiefung |
| P1 | Validierung mit BA-Wohnkostendaten | Externe Validierung |
| P1 | Marktvergleich mit Zensusmieten | Externe Plausibilisierung |
| P2 | Transparenz- und Aktualitätsanalyse | Institutioneller Zusatzbeitrag |
| P2 | Regelbasierte Counterfactuals | Politikszenarien |
| P2 | Weitere räumliche und regionale Heterogenität | Anhang oder spätere Fassung |

Das minimale Workshop-Paket besteht aus allen P0-Modulen sowie mindestens einem P1-Modul. Priorisiert ist bei P1 zunächst die BA-Validierung, danach die Grenzsprunganalyse und anschließend der Zensusvergleich.

---

# 4. Verbindliche Begriffe und Notation

## 4.1 Beobachtungseinheiten

Es sind drei räumliche Einheiten auseinanderzuhalten:

- \(g\): Gemeinde,
- \(r\): tatsächlicher KdU-Regelungs- oder Vergleichsraum,
- \(j\): Jobcenter beziehungsweise Kreis für externe Verwaltungsdaten.

Eine Gemeinde ist häufig nur die kartografische Darstellungseinheit. Mehrere Gemeinden können demselben KdU-Regime unterliegen. Deshalb muss jede Gemeinde zusätzlich einer `policy_region_id` zugeordnet werden.

Gemeinden mit identischer KdU-Regelung dürfen bei statistischen Auswertungen nicht automatisch als unabhängige politische Entscheidungen behandelt werden.

## 4.2 Haushaltsgröße

\(h\) bezeichnet die Zahl der Haushaltsmitglieder.

Die Hauptanalyse ist für folgende Größen durchzuführen:

\[
h\in\{1,2,3,4,5\}.
\]

Haushalte ab sechs Personen sind in den Anhang aufzunehmen, sofern die lokalen Zusatzbeträge hinreichend vollständig vorliegen.

## 4.3 KdU-Obergrenze

\[
K_{ght}
\]

bezeichnet die maximale regulär anerkennungsfähige **Bruttokaltmiete** für Gemeinde \(g\), Haushaltsgröße \(h\) und Rechtsstand \(t\).

Bruttokaltmiete bedeutet:

\[
\text{Nettokaltmiete}
+
\text{kalte Betriebskosten},
\]

ohne Heiz- und Warmwasserkosten.

## 4.4 Wohngeld-Benchmark

Der primäre Wohngeld-Benchmark lautet:

\[
W_{ght}
=
W^{\text{Basis}}_{ght}
+
W^{\text{Klima}}_{ht}.
\]

Der Basisbetrag hängt von Haushaltsgröße und Mietenstufe ab. Die Klimakomponente erhöht den Höchstbetrag der berücksichtigungsfähigen Miete. Die wohngeldrechtliche Miete schließt Heiz- und Warmwasserkosten aus. Die gesonderte Heizkostenentlastung geht nicht in den Bruttokaltmieten-Benchmark ein, sondern wird nur bei einer vollständigen Wohngeldsimulation verwendet.

Als Robustheitsvariante ist zusätzlich zu verwenden:

\[
W^{0}_{ght}=W^{\text{Basis}}_{ght}.
\]

In Tabellen und Code müssen die Begriffe wie folgt verwendet werden:

- `wogg_base_cap`: Basis-Höchstbetrag,
- `wogg_climate_component`: Klimakomponente,
- `wogg_bkc_cap`: Basis-Höchstbetrag plus Klimakomponente,
- `wogg_heating_relief`: gesonderte Heizkostenentlastung.

Die Heizkostenentlastung darf nicht zum Wert `wogg_bkc_cap` addiert werden.

## 4.5 Tatsächliche Miete und anerkannter Betrag

Für eine tatsächliche Bruttokaltmiete \(m\) lautet die anerkannte Unterkunftskomponente:

\[
A^{K}_{ght}(m)=\min(m,K_{ght})
\]

unter Verwendung der lokalen KdU und

\[
A^{W}_{ght}(m)=\min(m,W_{ght})
\]

unter Verwendung des Wohngeld-Proxys.

Der mechanische Proxyfehler ist:

\[
e_{ght}(m)
=
A^{K}_{ght}(m)-A^{W}_{ght}(m).
\]

Diese Funktion ist für die Interpretation zentral. Sie macht deutlich, dass die Differenz der Obergrenzen nur dann vollständig leistungsrelevant wird, wenn die tatsächliche Miete mindestens so hoch wie beide Obergrenzen ist.

---

# 5. Technische Projektstruktur

Der gesamte Workflow muss reproduzierbar sein. Rohdaten dürfen nicht manuell überschrieben werden.

## 5.1 Verzeichnisstruktur

Folgende Struktur verwenden:

- `data/raw/kdu/`
- `data/raw/wogg/`
- `data/raw/ba/`
- `data/raw/zensus/`
- `data/raw/geography/`
- `data/intermediate/`
- `data/processed/`
- `src/config/`
- `src/data/`
- `src/analysis/`
- `src/figures/`
- `src/tables/`
- `tests/`
- `output/figures/`
- `output/tables/`
- `docs/`
- `logs/`

## 5.2 Verbindliche Ausgabedateien

Am Ende müssen mindestens vorliegen:

- `kdu_municipality_household.parquet`
- `kdu_policy_region_household.parquet`
- `municipality_crosswalk.parquet`
- `analysis_sample_main.parquet`
- `analysis_sample_extended.parquet`
- `data_dictionary.csv`
- `source_register.csv`
- `exclusion_log.csv`
- `decision_log.md`
- `quality_report.html`
- `results_manifest.csv`

`results_manifest.csv` enthält für jede Tabelle und Abbildung:

- Dateiname,
- Analysemodul,
- zugrunde liegender Datensatz,
- Skript,
- Erstellungsdatum,
- Kurzinterpretation,
- zentrale Einschränkung.

## 5.3 Konfiguration

Alle rechtlichen und zeitlichen Parameter sind zentral in einer Konfigurationsdatei zu speichern:

- Analysestichtag,
- Gebietsstand,
- WoGG-Rechtsstand,
- SGB-Rechtsstand,
- Haushaltsgrößen,
- Modellhaushalte,
- Einkommensraster,
- Gewichte,
- Ausschlussregeln,
- Pfade.

Es dürfen keine Jahreszahlen oder Rechtsparameter verteilt in einzelnen Analyseskripten stehen.

---

# 6. P0.1 – Datenharmonisierung und Qualitätsprüfung

## Ziel

Aus den erhobenen lokalen Angaben ist ein kanonischer, gemeindescharfer Datensatz vergleichbarer Bruttokaltmieten-Obergrenzen zu erstellen.

## 6.1 Analysestichtag fixieren

Die Hauptanalyse muss einen eindeutigen Stichtag besitzen.

Vorgehen:

1. Verwende den Stichtag, der der bestehenden Karte zugrunde liegt.
2. Falls die bestehende Karte unterschiedliche Vintages mischt, definiere den Abschlussstichtag der Datenerhebung als Analysestichtag.
3. Verwende für jede Region nur die Regelung, die an diesem Stichtag wirksam war.
4. Eine alte Richtlinie darf nicht als aktuell behandelt werden, nur weil keine neuere öffentlich gefunden wurde.
5. Fälle ohne nachweisbar gültige Regelung erhalten einen Qualitätsflag und werden aus der Hauptstichprobe ausgeschlossen.
6. Der Wohngeld-Benchmark muss demselben Rechtsstand entsprechen.

Folgende Datumsvariablen getrennt führen:

- `valid_from`,
- `valid_to`,
- `publication_date`,
- `retrieval_date`,
- `analysis_date`.

## 6.2 Zielschema

Der harmonisierte Long-Datensatz muss mindestens folgende Variablen enthalten:

### Geografie

- `ags`,
- `municipality_name`,
- `district_ags`,
- `district_name`,
- `state_code`,
- `state_name`,
- `policy_region_id`,
- `policy_region_name`,
- `jobcenter_id`,
- `geometry_vintage`.

Der AGS ist als achtstelliger String einschließlich führender Nullen zu speichern. Verknüpfungen dürfen nicht ausschließlich über Gemeindenamen erfolgen.

### Zeit und Quellen

- `valid_from`,
- `valid_to`,
- `source_id`,
- `source_title`,
- `source_institution`,
- `source_type`,
- `source_location`,
- `retrieval_date`,
- `source_hash`,
- `quality_tier`.

### Inhalt der KdU-Regel

- `household_size`,
- `kdu_value_raw`,
- `kdu_unit_raw`,
- `cost_concept_raw`,
- `max_area_sqm`,
- `net_cold_cap_total`,
- `net_cold_cap_per_sqm`,
- `cold_opex_cap_total`,
- `cold_opex_cap_per_sqm`,
- `gross_cold_cap_total`,
- `heating_cap_total`,
- `gross_warm_cap_total`,
- `additional_person_amount`,
- `calculation_method`,
- `product_theory_flag`,
- `exception_text`,
- `derived_value_flag`.

### Finale Analysevariable

- `kdu_bkc_cap`.

## 6.3 Hierarchie zur Konstruktion von `kdu_bkc_cap`

Die Bruttokaltmieten-Obergrenze ist in folgender Reihenfolge zu bestimmen:

1. **Direkt veröffentlichter Gesamtbetrag der Bruttokaltmiete:** unverändert übernehmen.
2. **Direkt veröffentlichte Nettokaltmiete und kalte Betriebskosten:** beide Komponenten addieren.
3. **Veröffentlichte Quadratmeterwerte und Wohnflächenobergrenze:** nur entsprechend der in der Quelle beschriebenen Berechnungslogik multiplizieren.
4. **Gesamtangemessenheitsgrenze einschließlich Heizkosten:** nur verwenden, wenn der Heizkostenanteil explizit abtrennbar ist.
5. **Nur Bruttowarmgrenze ohne trennbare Komponenten:** aus der Hauptanalyse ausschließen.
6. **Unklare oder widersprüchliche Definition:** nicht eigenständig interpretieren; im `decision_log` dokumentieren und Qualitätsstufe C vergeben.

Es dürfen keine bundesweiten Durchschnittswerte für kalte Betriebskosten oder Heizkosten verwendet werden, um unklare lokale Angaben scheinpräzise umzurechnen.

## 6.4 Qualitätsstufen

### Qualitätsstufe A

- offizielle Primärquelle,
- Regelungsgebiet eindeutig,
- Wirksamkeitsdatum eindeutig,
- Bruttokaltmietengrenze direkt angegeben,
- Haushaltsgrößen vollständig.

### Qualitätsstufe B

- offizielle Primärquelle,
- Bruttokaltmietengrenze eindeutig aus dokumentierten Komponenten berechenbar,
- Berechnung vollständig reproduzierbar.

### Qualitätsstufe C

- Quelle veraltet, sekundär oder definitionsseitig unklar,
- Regelungsgebiet nicht eindeutig,
- Kostenkonzept nicht vollständig harmonisierbar,
- wesentliche Annahmen erforderlich.

Hauptanalyse: Qualitätsstufen A und B.
Erweiterte Analyse: A, B und separat gekennzeichnete C-Fälle.

## 6.5 Automatisierte Qualitätsprüfungen

Folgende Prüfungen programmieren:

1. Eindeutigkeit von `ags × household_size × analysis_date`.
2. Eindeutige Zuordnung jeder Gemeinde zu einer `policy_region_id`.
3. Positive und numerische KdU-Werte.
4. Monotonie der KdU nach Haushaltsgröße.
5. Identische Werte innerhalb einer Policy-Region, sofern keine dokumentierte Ausnahme besteht.
6. Fehlende Haushaltsgrößen.
7. Extrem hohe oder niedrige Werte anhand von Perzentilen und absoluten Warnschwellen.
8. Doppelte Quellen mit widersprüchlichen Werten.
9. Inkonsistenzen zwischen Gesamtbetrag und Einzelkomponenten.
10. Gebietsstands- und AGS-Konflikte.
11. Gemeinden ohne Geometrie.
12. Gemeinden mit mehreren konkurrierenden Regelungen am Stichtag.

Eine verletzte Plausibilitätsregel führt zunächst nur zu einem Warnflag, nicht automatisch zum Ausschluss.

## 6.6 Manuelle Validierung

Nach den automatisierten Tests sind mindestens folgende Fälle manuell mit der Originalquelle abzugleichen:

- eine geschichtete Zufallsstichprobe von mindestens 100 Gemeinde-Haushaltsgrößen-Beobachtungen,
- mindestens zwei Beobachtungen je Bundesland,
- alle Beobachtungen unter Qualitätsstufe C,
- die 20 größten positiven und negativen KdU-Wohngeld-Abweichungen,
- alle Fälle mit fallender KdU bei steigender Haushaltsgröße,
- alle Fälle mit ungewöhnlich großen Sprüngen zwischen benachbarten Gemeinden.

## Abnahmekriterien

Dieses Modul ist abgeschlossen, wenn:

- jede Beobachtung der Hauptstichprobe eine offizielle Quelle besitzt,
- Kostenkonzept und Wirksamkeitsdatum dokumentiert sind,
- alle automatisierten Prüfungen reproduzierbar laufen,
- sämtliche Ausschlüsse in `exclusion_log.csv` stehen,
- die Abdeckung nach Gemeinden, Bevölkerung, Policy-Regionen und Bundesländern berichtet wird,
- keine stillen Imputationen verbleiben.

---

# 7. P0.2 – Aufbau des Wohngeld-Benchmarks

## Ziel

Für jede Gemeinde, Haushaltsgröße und denselben Rechtsstand ist die maximal berücksichtigungsfähige wohngeldrechtliche Bruttokaltmiete zu berechnen.

## Arbeitsschritte

1. Lade die offizielle Zuordnung der Gemeinden zu den Wohngeld-Mietenstufen für den Analysestichtag.
2. Verknüpfe über den AGS, nicht über Gemeindenamen.
3. Verwende die offizielle Mietenstufenzuordnung; leite sie nicht selbst aus Kreiszugehörigkeit oder Einwohnerzahl ab.
4. Erstelle eine Parametertabelle der Basis-Höchstbeträge nach Haushaltsgröße und Mietenstufe.
5. Erstelle eine Parametertabelle der Klimakomponente nach Haushaltsgröße.
6. Berechne:

\[
W_{ght}
=
W^{\text{Basis}}_{ght}
+
W^{\text{Klima}}_{ht}.
\]

7. Halte die Heizkostenentlastung als separate Variable vor.
8. Prüfe stichprobenartig alle Mietenstufen und Haushaltsgrößen gegen die amtlichen Tabellen.

## Finale Variablen

- `wogg_rent_level`,
- `wogg_base_cap`,
- `wogg_climate_component`,
- `wogg_bkc_cap`,
- `wogg_heating_relief`,
- `wogg_parameter_vintage`.

## Abnahmekriterien

- vollständige Mietenstufenzuordnung für alle Gemeinden der Hauptstichprobe,
- keine manuell eingetragenen Gemeindewerte im Analyseskript,
- alle Parameter stammen aus einer zentralen Tabelle,
- automatisierte Tests für mindestens eine Gemeinde je Mietenstufe und jede Haushaltsgröße.

---

# 8. P0.3 – Deskriptive Proxyfehleranalyse

## Forschungsfrage

Wie stark weicht die tatsächliche lokale KdU-Obergrenze von dem Wert ab, der in einer Simulation durch den Wohngeld-Höchstbetrag approximiert würde?

## 8.1 Kennzahlen

Für jede Gemeinde und Haushaltsgröße berechnen:

### Eurodifferenz

\[
D_{gh}=K_{gh}-W_{gh}.
\]

### Relative Differenz

\[
P_{gh}
=
100\left(\frac{K_{gh}}{W_{gh}}-1\right).
\]

### Log-Differenz

\[
L_{gh}
=
100\left[\log(K_{gh})-\log(W_{gh})\right].
\]

### Absoluter Proxyfehler

\[
A_{gh}=|K_{gh}-W_{gh}|.
\]

Die Log-Differenz ist die bevorzugte Größe für Karten und Regressionen. Die Eurodifferenz ist die bevorzugte Größe für sozialpolitische Interpretation.

## 8.2 Berichtsgewichte

Alle zentralen Verteilungen sind mindestens vierfach auszuweisen:

1. ungewichtete Gemeinden,
2. bevölkerungsgewichtete Gemeinden,
3. ungewichtete Policy-Regionen,
4. soweit nach P1 verfügbar: nach SGB-II-Bedarfsgemeinschaften gewichtet.

Die Gewichte beantworten unterschiedliche Fragen:

- Gemeindegewichte: Wie sieht die administrative Landschaft aus?
- Bevölkerungsgewichte: Welcher Abweichung ist die Bevölkerung ausgesetzt?
- Policy-Region-Gewichte: Wie unterscheiden sich eigenständige Regelungsregime?
- Bedarfsgemeinschaftsgewichte: Welche Abweichung ist für potenziell betroffene Haushalte relevant?

## 8.3 Deskriptive Tabellen

Für jede Haushaltsgröße berichten:

- Anzahl Gemeinden,
- Anzahl Policy-Regionen,
- Bevölkerungsabdeckung,
- Mittelwert,
- Standardabweichung,
- P10, P25, Median, P75, P90,
- Minimum und Maximum,
- Anteil \(D>0\),
- Anteil \(D<0\),
- Anteil \(|D|>25\) Euro,
- Anteil \(|D|>50\) Euro,
- Anteil \(|D|>100\) Euro,
- mittlere absolute Differenz.

Zusätzlich dieselben Kennzahlen nach:

- Bundesland,
- Mietenstufe,
- Gemeindegrößenklasse,
- kreisfreier Stadt versus kreisangehöriger Gemeinde,
- Qualitätsstufe.

## 8.4 Mietabhängiger Proxyfehler

Für jede Beobachtung ist die Funktion

\[
e_{gh}(m)
=
\min(m,K_{gh})-\min(m,W_{gh})
\]

auf einem normierten Mietraster auszuwerten.

Verwende mindestens folgende Mietpunkte:

\[
m\in
\{
0{,}8\min(K,W),
\min(K,W),
0{,}5(K+W),
\max(K,W),
1{,}2\max(K,W)
\}.
\]

Erstelle eine Abbildung, die für positive und negative KdU-Wohngeld-Differenzen zeigt, wann der Proxyfehler tatsächlich leistungsrelevant wird.

## 8.5 Hauptabbildungen

1. Deutschlandkarte von \(L_{g1}\).
2. Deutschlandkarte von \(L_{g4}\) mit identischer Skalierung.
3. ECDF der Eurodifferenz nach Haushaltsgröße.
4. Verteilung der absoluten Eurodifferenz.
5. Bundesland-Haushaltsgrößen-Heatmap der Medianabweichung.

Die Farbskala der Karten muss um null zentriert und über Haushaltsgrößen hinweg identisch sein.

## Erwartete Kernaussage

> Der Wohngeld-Höchstbetrag erzeugt keinen einheitlichen, sondern einen regional und nach Haushaltsgröße heterogenen Messfehler bei der Approximation lokaler KdU-Obergrenzen.

---

# 9. P0.4 – Heterogenität innerhalb der Wohngeld-Mietenstufen

## Forschungsfrage

Wie viel lokale Variation der KdU bleibt bestehen, nachdem Gemeinden derselben Wohngeld-Mietenstufe zugeordnet wurden?

## 9.1 Deskriptive Analyse

Für jede Haushaltsgröße:

1. Boxplots von \(K_{gh}\) nach Mietenstufe.
2. Boxplots von \(K_{gh}/W_{gh}\) nach Mietenstufe.
3. P90-P10-Abstand innerhalb jeder Mietenstufe.
4. Standardabweichung der Log-KdU innerhalb jeder Mietenstufe.
5. Anteil der Gemeinden mit einer Abweichung von mehr als 50 beziehungsweise 100 Euro vom Median ihrer Mietenstufe.

Die Analyse zusätzlich getrennt durchführen für:

- Gemeinden unter 10.000 Einwohnern,
- Gemeinden ab 10.000 Einwohnern,
- kreisfreie Städte,
- kreisangehörige Gemeinden.

## 9.2 Regressionsbasierte Zusammenfassung

Schätze für jede Haushaltsgröße:

\[
\log K_{g}
=
\alpha
+
\mu_{\text{Mietenstufe}(g)}
+
\varepsilon_g.
\]

Zusätzlich gepoolt:

\[
\log K_{gh}
=
\alpha_h
+
\mu_{\text{Mietenstufe}(g)\times h}
+
\varepsilon_{gh}.
\]

Berichte:

- \(R^2\),
- Residualstandardabweichung,
- P10 und P90 der Residuen,
- mittleren absoluten Residualwert.

Schätze anschließend:

\[
\log K_{gh}
=
\alpha_h
+
\mu_{\text{Mietenstufe}(g)\times h}
+
\lambda_{\text{Bundesland}(g)}
+
\varepsilon_{gh}.
\]

Der Vergleich der Spezifikationen zeigt, wie viel zusätzliche Variation durch Bundeslandunterschiede absorbiert wird.

Es handelt sich um eine deskriptive Varianzzerlegung. P-Werte sind nicht als Hauptergebnis zu präsentieren.

## Hauptabbildung

Eine Abbildung mit Boxplots von \(K/W\) nach Mietenstufe und Haushaltsgröße. Ergänzend eine kleine Tabelle mit \(R^2\) und Residualstreuung.

## Erwartete Kernaussage

> Gemeinden mit derselben Wohngeld-Mietenstufe weisen teilweise deutlich unterschiedliche lokale KdU-Obergrenzen auf. Die Mietenstufe bildet daher die für SGB-Simulationen relevante lokale Heterogenität nur unvollständig ab.

---

# 10. P0.5 – Haushaltsgrößenprofil

## Forschungsfrage

Unterscheiden sich lokale KdU-Regime darin, wie stark die anerkannte Wohnkostenkomponente mit der Haushaltsgröße steigt?

## 10.1 Marginale Beträge

Berechne:

\[
\Delta K_{g,h}
=
K_{g,h}-K_{g,h-1}
\]

und

\[
\Delta W_{g,h}
=
W_{g,h}-W_{g,h-1}
\]

für \(h=2,\ldots,5\).

Zusätzliche Kennzahlen:

\[
Q_{g,h}
=
\frac{\Delta K_{g,h}}{\Delta W_{g,h}},
\]

\[
K^{pc}_{g,h}
=
\frac{K_{g,h}}{h},
\]

und

\[
W^{pc}_{g,h}
=
\frac{W_{g,h}}{h}.
\]

## 10.2 Familien-Tilt

Definiere:

\[
F_g
=
\log\left(\frac{K_{g4}}{W_{g4}}\right)
-
\log\left(\frac{K_{g1}}{W_{g1}}\right).
\]

Interpretation:

- \(F_g>0\): Die lokale KdU ist relativ zum Wohngeld für Vierpersonenhaushalte höher als für Singles.
- \(F_g<0\): Die lokale KdU ist relativ zum Wohngeld für Singles höher.

Zusätzlich analog für Drei- und Fünfpersonenhaushalte berechnen.

## 10.3 Rangstabilität

Berechne:

- Spearman-Rangkorrelation der Gemeinden zwischen \(K_{g1}\) und \(K_{g4}\),
- Spearman-Rangkorrelation der Proxyfehler zwischen Haushaltsgrößen,
- Anteil der Gemeinden, die zwischen Ein- und Vierpersonenhaushalt mindestens zwei Dezile wechseln,
- Übergangsmatrix der Dezilzugehörigkeit.

## Hauptabbildungen

1. Scatterplot der durchschnittlichen relativen KdU-Höhe gegen den Familien-Tilt.
2. Verteilung der marginalen KdU-Beträge nach zusätzlicher Person.
3. Karte des Familien-Tilts.
4. Dezil-Übergangsmatrix Einpersonenhaushalt versus Vierpersonenhaushalt.

## Erwartete Kernaussage

> Die Abweichung zwischen KdU und Wohngeld ist nicht lediglich ein gemeindespezifischer Niveauunterschied. Auch die implizite Haushaltsgrößenstruktur unterscheidet sich regional.

---

# 11. P0.6 – Regionalisiertes administratives Bedarfsniveau

## Ziel

Die KdU-Obergrenzen sollen in eine sozialpolitisch leichter interpretierbare Gesamtbedarfsgröße übersetzt werden.

## 11.1 Modellhaushalte

Verwende mindestens folgende Haushalte:

1. alleinstehende erwerbsfähige Person, 35 Jahre,
2. alleinerziehende Person mit einem achtjährigen Kind,
3. Paar mit zwei Kindern im Alter von acht und vierzehn Jahren,
4. alleinstehende Person im Rentenalter, 70 Jahre.

Alle Altersangaben und Haushaltsannahmen sind im Methodenanhang festzuhalten.

## 11.2 Bedarfsgröße

Für Modellhaushalt \(c\):

\[
B^{K}_{gc}
=
R_c
+
M_c
+
K_{g,h(c)},
\]

wobei:

- \(R_c\) die Summe der einschlägigen Regelbedarfe ist,
- \(M_c\) standardisierte Mehrbedarfe bezeichnet,
- \(h(c)\) die Haushaltsgröße ist.

Analog:

\[
B^{W}_{gc}
=
R_c
+
M_c
+
W_{g,h(c)}.
\]

Heizkosten sind in der Hauptkennzahl nicht enthalten. Die Kennzahl ist daher ausdrücklich zu bezeichnen als:

> **Administrativer Bruttokaltbedarf vor Einkommensanrechnung**

Nicht ohne Zusatz als vollständiges Existenzminimum bezeichnen.

Als Sensitivität kann eine einheitliche, haushaltsspezifische Heizkostenannahme ergänzt werden.

## 11.3 Kennzahlen

Berechne:

- P10, Median und P90 des Bedarfsniveaus,
- regionale Spannweite,
- KdU-Anteil am administrativen Bruttokaltbedarf:

\[
S^{K}_{gc}
=
\frac{K_{g,h(c)}}{B^{K}_{gc}},
\]

- Differenz zwischen KdU- und Wohngeld-basierter Bedarfsgröße,
- Variation nach Bundesland, Mietenstufe und Gemeindegrößenklasse.

## Hauptabbildung

Für jeden Modellhaushalt ein Punkt- oder Boxplot der regionalen Verteilung von \(B^{K}\) und \(B^{W}\).

## Erwartete Kernaussage

> Bundeseinheitliche Regelbedarfsparameter implizieren kein bundeseinheitliches administratives Bedarfsniveau, sobald die lokale Unterkunftskomponente berücksichtigt wird.

---

# 12. P0.7 – Standardfall-Mikrosimulation

## Ziel

Es ist zu quantifizieren, wie stark die Verwendung des Wohngeld-Höchstbetrags als KdU-Proxy simulierte Ansprüche und Transfer-Ausstiegsschwellen verändert.

## 12.1 Simulationsvarianten

Für jeden Modellhaushalt und jede Gemeinde sind mindestens zwei Szenarien zu berechnen:

### Szenario K: tatsächlicher lokaler Parameter

\[
\text{anerkannte Bruttokaltmiete}
=
\min(m,K_{gh}).
\]

### Szenario W: Wohngeld-Proxy

\[
\text{anerkannte Bruttokaltmiete}
=
\min(m,W_{gh}).
\]

Alle anderen rechtlichen und wirtschaftlichen Parameter müssen zwischen den beiden Szenarien identisch sein.

## 12.2 Mietannahmen

Verwende drei Varianten:

### Variante 1: Obergrenzenbindende Miete

\[
m_{gh}
=
\max(K_{gh},W_{gh}).
\]

Diese Variante isoliert den maximalen mechanischen Unterschied der beiden Parameter. Sie ist als Konstruktionsszenario und nicht als typische Marktmiete zu kennzeichnen.

### Variante 2: Mietraster

Simuliere tatsächliche Bruttokaltmieten zwischen 50 Prozent und 130 Prozent von \(\max(K,W)\), mindestens in Zehn-Prozent-Schritten.

### Variante 3: Lokale Marktmiete

Nach Abschluss des Zensusmoduls ist eine marktnähere Mietannahme zu ergänzen. Diese ist als Bestandsmietenszenario zu bezeichnen.

## 12.3 Heizkosten

Heizkosten sind zwischen K- und W-Szenario konstant zu halten.

Bevorzugtes Vorgehen:

- Verwende für jeden Haushaltstyp die bundesweit durchschnittlichen anerkannten Heizkosten aus den BA-Wohnkostendaten für einen möglichst zeitnahen Referenzmonat.
- Ergänze eine Sensitivität mit 75 und 125 Prozent dieses Werts.

Dadurch stammt jede Differenz zwischen Szenario K und W ausschließlich aus der Bruttokaltmieten-Obergrenze.

## 12.4 Einkommensraster

Für Erwerbshaushalte:

1. Starte bei null Euro monatlichem Bruttoerwerbseinkommen.
2. Erhöhe das Bruttoeinkommen in Schritten von höchstens 25 Euro.
3. Simuliere so lange, bis in beiden Szenarien für mindestens zwölf aufeinanderfolgende Rasterpunkte kein Grundsicherungsanspruch mehr besteht.
4. Setze eine technische Obergrenze von 8.000 Euro Monatsbrutto.

Für den Rentnerhaushalt:

- simuliere die monatliche Bruttorente auf einem entsprechend angepassten Raster.

## 12.5 Mindestumfang des Simulationsmodells

Das Modell muss für den gewählten Rechtsstand mindestens abbilden:

- einschlägige Regelbedarfe,
- Mehrbedarfe,
- Unterkunfts- und Heizkosten,
- Erwerbstätigenfreibeträge beziehungsweise Einkommensanrechnung,
- Kindergeld und sonstige zwingend anzurechnende Einkommen,
- Sozialversicherungsbeiträge,
- Lohn- beziehungsweise Einkommensteuer, soweit relevant,
- Haushaltszusammensetzung,
- Ausschluss wechselseitiger Transferansprüche.

Die lokalen KdU-Obergrenzen sind als austauschbares Modul zu implementieren. Der Simulationskern darf nicht für jede Gemeinde separat dupliziert werden.

Besteht bereits ein validiertes Steuer-Transfer-Modell, ist die KdU-Tabelle dort einzubinden. Falls kein solches Modell verfügbar ist, ist zunächst ein rechtlich präziser Standardfallrechner für die definierten Haushalte zu erstellen. Vereinfachungen sind in einer zentralen Annahmendatei zu dokumentieren.

## 12.6 Primäre Outcomes

### Anspruch bei keinem Erwerbseinkommen

\[
\Delta T_{gc}(0)
=
T^{K}_{gc}(0)-T^{W}_{gc}(0).
\]

### Maximale monatliche Anspruchsdifferenz

\[
\Delta T^{\max}_{gc}
=
\max_y
\left|
T^{K}_{gc}(y)-T^{W}_{gc}(y)
\right|.
\]

### Transfer-Ausstiegsschwelle

Definiere \(y^{*,K}_{gc}\) und \(y^{*,W}_{gc}\) als niedrigstes Bruttoeinkommen, ab dem im jeweiligen Szenario kein Anspruch mehr besteht.

\[
\Delta y^{*}_{gc}
=
y^{*,K}_{gc}
-
y^{*,W}_{gc}.
\]

### Wochenarbeitszeitäquivalent

Unter Verwendung des zum Rechtsstand passenden gesetzlichen Mindestlohns:

\[
\Delta H_{gc}
=
\frac{\Delta y^{*}_{gc}}
{4{,}33\times \text{Mindestlohn}}.
\]

### Verfügbares Einkommen nach Wohnkosten

\[
Y^{posthousing}
=
Y^{disposable}
-
\text{tatsächliche Bruttowarmmiete}.
\]

Berichte die Differenz zwischen beiden Parameterszenarien entlang der Einkommenskurve.

## 12.7 Vollständige Transferintegration

Nach Fertigstellung der SGB-Kernsimulation ist als nächste Stufe ein integriertes Modell mit Wohngeld und gegebenenfalls Kinderzuschlag zu erstellen beziehungsweise aus einem bestehenden Modell zu verwenden.

Ziel ist nicht, SGB II und Wohngeld gleichzeitig auszuzahlen. Das Modell muss die jeweiligen Anspruchsausschlüsse und Vorrangregeln des gewählten Rechtsstands anwenden.

Zusätzliche Outcomes:

- Einkommensbereich mit SGB-Bezug,
- Einkommensbereich mit Wohngeld beziehungsweise Wohngeld plus Kinderzuschlag,
- Regimewechsel,
- lokale Unterschiede in effektiven Grenzbelastungen,
- Differenz der Regimewechsel-Schwelle zwischen KdU- und Proxy-Simulation.

## 12.8 Tests

Mindestens folgende Tests implementieren:

1. Bei \(K=W\) müssen beide Simulationen identisch sein.
2. Bei \(m<\min(K,W)\) müssen beide anerkannten Unterkunftsbeträge identisch sein.
3. Bei \(m>\max(K,W)\) muss die Unterkunftsdifferenz gleich \(K-W\) sein.
4. Höhere KdU darf bei sonst identischem Fall den SGB-Anspruch nicht senken.
5. Für ausgewählte Einkommen sind die Ergebnisse manuell nachzurechnen.
6. Rechtsgrenzen der Einkommensanrechnung sind mit Werten unmittelbar unterhalb und oberhalb der Grenze zu testen.
7. Kinder- und Paarhaushalte sind getrennt zu prüfen.
8. Rundungsregeln sind zentral und konsistent anzuwenden.

## Hauptabbildungen

1. Verteilung von \(\Delta y^*\) nach Modellhaushalt.
2. Verteilung des Wochenarbeitszeitäquivalents.
3. Budgetkurven für Gemeinden am P10, Median und P90 des Proxyfehlers.
4. Karte der Veränderung der Ausstiegsschwelle für einen ausgewählten Haushalt.
5. Scatterplot \(K-W\) gegen \(\Delta y^*\).

## Erwartete Kernaussage

> Die Wahl des regionalen Wohnkostenparameters beeinflusst nicht nur kartografische Leistungsniveaus, sondern verschiebt modellierte Ansprüche, Bezugsbereiche und Transfer-Ausstiegsschwellen.

---

# 13. P1.1 – Administrative Grenzsprünge

## Forschungsfrage

Wie stark unterscheiden sich KdU-Obergrenzen zwischen unmittelbar benachbarten Gemeinden, insbesondere wenn sie unterschiedlichen Policy-Regionen angehören?

## 13.1 Geodaten

Verwende amtliche Gemeindegeometrien mit dokumentiertem Gebietsstand. Das BKG stellt Verwaltungsgebiete einschließlich Gemeinden, Schlüsselzahlen und Grenzen bereit.

Verwende für Entfernungs- und Grenzberechnungen ein projiziertes Koordinatensystem, vorzugsweise ETRS89/LAEA Europe.

## 13.2 Nachbarschaftsdefinition

Primär:

- Gemeinden gelten als Nachbarn, wenn sie eine gemeinsame Grenzlinie besitzen.
- Reine Punktberührungen sind auszuschließen.
- Sehr kurze gemeinsame Grenzen sind als mögliche Geometrieartefakte zu flaggen.
- Jedes Paar ist nur einmal zu speichern.

Für jedes Paar \((i,j)\) erfassen:

- gleiche oder unterschiedliche Policy-Region,
- gleicher oder unterschiedlicher Kreis,
- gleiches oder unterschiedliches Bundesland,
- gleiche oder unterschiedliche Mietenstufe,
- gemeinsame Grenzlänge,
- Entfernung der Gemeindezentroide.

## 13.3 Sprungmaß

Berechne:

\[
J_{ij,h}
=
\left|
\log K_{ih}-\log K_{jh}
\right|
\]

und

\[
J^{€}_{ij,h}
=
|K_{ih}-K_{jh}|.
\]

## 13.4 Analysen

1. Verteilung aller Nachbarschaftssprünge.
2. Vergleich von Paaren innerhalb und zwischen Policy-Regionen.
3. Vergleich bei gleicher und unterschiedlicher Mietenstufe.
4. Top-20-Grenzsprünge nach Haushaltsgröße.
5. Wiederholung nach Ausschluss möglicher Geometrieartefakte.
6. Engere Vergleichsgruppe mit:
   - gleicher Mietenstufe,
   - ähnlicher Zensusmiete,
   - ähnlicher Bevölkerungsdichte,
   - unterschiedlichen Policy-Regionen.

## Wichtige Interpretation

Die Analyse ist keine kausale Regression-Discontinuity-Analyse. Ein Sprung dokumentiert eine administrative Diskontinuität, beweist aber keinen kausalen Effekt der Grenze.

## Hauptabbildungen

- Histogramm beziehungsweise ECDF der Grenzsprünge,
- Boxplots nach Grenztyp,
- Detailkarten der zehn größten plausiblen Sprünge.

---

# 14. P1.2 – Validierung mit BA-Wohnkostendaten

## Ziel

Es ist zu prüfen, ob die neu erhobenen Obergrenzen systematisch mit realen Verwaltungskennzahlen zu tatsächlichen und anerkannten Wohnkosten zusammenhängen.

Die Bundesagentur für Arbeit veröffentlicht die „Wohn- und Kostensituation“ monatlich unter anderem für Länder, Kreise und Jobcenter. Die Tabellen enthalten tatsächliche und anerkannte Kosten, Wohnflächen und Differenzierungen nach Haushaltsgröße beziehungsweise Bedarfsgemeinschaftstyp.

## 14.1 Datenabgrenzung

1. Wähle einen Monat möglichst nahe am Analysestichtag.
2. Ergänze als Robustheit einen Jahresdurchschnitt aus zwölf Monaten.
3. Verwende nach Möglichkeit nur Mietunterkünfte.
4. Trenne:
   - Unterkunftskosten,
   - laufende Betriebskosten,
   - Heizkosten.
5. Konstruiere die tatsächliche und anerkannte Bruttokaltmiete als Unterkunftskosten plus kalte Betriebskosten.
6. Vermische nicht anerkannte Kosten mit tatsächlich ausgezahlten Leistungen. Die BA weist darauf hin, dass Leistungen wegen Einkommensanrechnung unter den anerkannten Wohnkosten liegen können.

## 14.2 Hauptoutcomes

### Eurodifferenz

\[
G^{BA}_{jh}
=
\overline{C^{actual}_{jh}}
-
\overline{C^{recognized}_{jh}}.
\]

### Anerkennungsquote

\[
R^{BA}_{jh}
=
\frac{\overline{C^{recognized}_{jh}}}
{\overline{C^{actual}_{jh}}}.
\]

### Nicht anerkannter Anteil

\[
N^{BA}_{jh}
=
1-R^{BA}_{jh}.
\]

## 14.3 Räumliche Verknüpfung

Erstelle eine dokumentierte Crosswalk-Tabelle zwischen:

- Gemeinden,
- Policy-Regionen,
- Kreisen,
- Jobcentern.

Hauptstichprobe für die Validierung:

- kreisfreie Städte,
- Jobcenter, die genau einer Policy-Region entsprechen,
- Jobcenter mit einer innerhalb des Gebiets einheitlichen KdU-Regel.

Erweiterte Stichprobe:

- Jobcenter mit mehreren Policy-Regionen.

Für diese sind mindestens zu berechnen:

- bevölkerungsgewichteter KdU-Mittelwert,
- Minimum,
- Maximum,
- Standardabweichung innerhalb des Jobcenters.

Die Ergebnisse der erweiterten Stichprobe sind als Robustheit zu behandeln.

## 14.4 Deskriptive Spezifikationen

Erste Spezifikation:

\[
N^{BA}_{jh}
=
\alpha_h
+
\beta
\log\left(\frac{K_{jh}}{W_{jh}}\right)
+
\lambda_{\text{Bundesland}}
+
\varepsilon_{jh}.
\]

Zweite Spezifikation nach Einbindung von Marktmieten:

\[
N^{BA}_{jh}
=
\alpha_h
+
\beta
\log\left(\frac{M^{market}_{jh}}{K_{jh}}\right)
+
\lambda_{\text{Bundesland}}
+
\varepsilon_{jh}.
\]

Dritte Spezifikation:

\[
G^{BA}_{jh}
=
\alpha_h
+
\beta_1 K_{jh}
+
\beta_2 M^{market}_{jh}
+
\lambda_{\text{Bundesland}}
+
\varepsilon_{jh}.
\]

Bei mehreren Haushaltstypen je Jobcenter sind Standardfehler auf Jobcenterebene zu clustern. Der Fokus liegt auf Effektgrößen, Binscattern und Robustheit, nicht auf kausaler Interpretation.

## 14.5 Gewichtete nationale Relevanz

Verwende die BA-Bestände nach Haushaltsgröße beziehungsweise Bedarfsgemeinschaftstyp, um die Proxyfehler zu gewichten.

Berechne:

\[
\overline{D}^{BG}_{h}
=
\frac{\sum_j BG_{jh}D_{jh}}
{\sum_j BG_{jh}}.
\]

Wenn ein Jobcenter mehrere KdU-Regime umfasst, ist diese Gewichtung nur in der klar dokumentierten erweiterten Variante zu verwenden.

## Hauptabbildungen

1. Binscatter von Markt-KdU-Druck gegen nicht anerkannten Kostenanteil.
2. Anerkennungsquote nach Dezilen von \(K/W\).
3. Vergleich von ungewichteter, bevölkerungsgewichteter und BG-gewichteter Proxyfehlerverteilung.

## Erwartete Kernaussage

> Die lokalen Obergrenzen sind nicht nur ein formaler Rechtsparameter, sondern weisen einen systematischen Zusammenhang mit tatsächlich beobachteten Unterschieden zwischen tatsächlichen und anerkannten Wohnkosten auf.

Diese Aussage ist ausdrücklich associational zu formulieren.

---

# 15. P1.3 – Marktvergleich mit Zensus 2022

## Ziel

Es ist zu prüfen, wie die lokalen KdU-Obergrenzen relativ zum lokalen Bestandsmietniveau einzuordnen sind.

Die Zensusdatenbank stellt Ergebnisse auf Gemeindeebene bereit und kann auch programmatisch angesprochen werden. Die veröffentlichten Mietgrößen sind Nettokaltmieten und bilden Bestandsmieten einschließlich länger bestehender Mietverhältnisse ab.

## 15.1 Vergleichbares Kostenkonzept

Der bevorzugte Vergleich verwendet lokale KdU-Nettokaltmietkomponenten:

\[
p^{K,NK}_{gh}
=
\frac{K^{NK}_{gh}}{A^{max}_{gh}},
\]

wobei:

- \(K^{NK}_{gh}\) die lokale Nettokaltmietengrenze ist,
- \(A^{max}_{gh}\) die lokale Wohnflächenobergrenze ist.

Vergleiche diesen Wert mit der Zensus-Nettokaltmiete je Quadratmeter für möglichst passende Wohnungsgrößen.

Falls nur die Bruttokaltmietengrenze vorliegt:

1. Nicht direkt mit der Zensus-Nettokaltmiete vergleichen.
2. Erstelle stattdessen Szenarien für kalte Betriebskosten.
3. Verwende mindestens eine niedrige, mittlere und hohe Betriebskostenannahme.
4. Weise die Ergebnisse getrennt aus.
5. Die Stichprobe mit expliziter lokaler Nettokaltmietengrenze ist die bevorzugte Hauptstichprobe.

## 15.2 Marktstressindikator

Für die bevorzugte Stichprobe:

\[
S^{market}_{gh}
=
\frac{p^{K,NK}_{gh}}
{p^{Zensus}_{g,s(h)}}.
\]

Dabei bezeichnet \(s(h)\) die zur zulässigen Wohnfläche passende Wohnungsgrößenklasse.

Interpretation:

- \(S^{market}>1\): Die implizite KdU-Nettokaltmiete liegt über der durchschnittlichen Zensus-Bestandsmiete.
- \(S^{market}<1\): Sie liegt darunter.

Diese Größe ist als Marktstress- oder Plausibilitätsindikator zu bezeichnen, nicht als Anteil verfügbarer Wohnungen.

## 15.3 Analysen

1. Verteilung des Marktstressindikators nach Haushaltsgröße.
2. Vergleich von Singles und Familien.
3. Unterschiede nach Mietenstufe, Bundesland und Stadt-/Landtyp.
4. Zusammenhang zwischen Marktstress und \(K/W\).
5. Zusammenhang zwischen Marktstress und BA-Anerkennungsquote.
6. Analyse der Grenzsprünge bei ähnlichem lokalem Zensus-Mietniveau.

## Einschränkungen

- Zensusmieten sind Bestandsmieten, keine Angebotsmieten.
- Der Durchschnitt sagt nichts unmittelbar über die Verfügbarkeit einfacher Wohnungen aus.
- Die Größe ist keine rechtliche Prüfung eines „schlüssigen Konzepts“.
- Abweichende Wohnungsqualitäten und Baualtersstrukturen bleiben zunächst unbeobachtet.

## Hauptabbildungen

1. Scatterplot KdU-impli­zierte Nettokaltmiete gegen Zensusmiete.
2. Karte des Marktstressindikators.
3. Binscatter Marktstress gegen BA-Nichtanerkennungsanteil.

---

# 16. P2.1 – Transparenz- und Aktualitätsanalyse

## Ziel

Die Schwierigkeit der Datenerhebung soll als eigenständiger institutioneller Befund dokumentiert werden.

## 16.1 Einzelindikatoren

Für jede Policy-Region erfassen:

- offizielle Richtlinie öffentlich verfügbar,
- Quelle ohne individuelle Anfrage zugänglich,
- maschinenlesbares Format,
- Wirksamkeitsdatum explizit,
- Regelungsgebiet eindeutig,
- Kostenkonzept eindeutig,
- Haushaltsgrößen vollständig,
- Nettokaltmiete und Betriebskosten getrennt,
- Wohnflächenobergrenzen dokumentiert,
- Heizkostenregelung dokumentiert,
- Vergleichsräume dokumentiert,
- methodische Grundlage beziehungsweise schlüssiges Konzept zugänglich.

## 16.2 Aktualität

Berechne:

\[
Age_r
=
\text{Analysestichtag}
-
\text{valid\_from}_r
\]

in Monaten.

Untersuche deskriptiv:

\[
L_{rh}
=
\alpha_h
+
\beta Age_r
+
\lambda_{\text{Bundesland}}
+
\varepsilon_{rh}.
\]

Die Interpretation lautet nicht automatisch, dass ältere Regelungen sachlich unangemessen sind. Geprüft wird nur, ob ältere Regelungen systematisch andere Abweichungen zum Wohngeld aufweisen.

## 16.3 Transparenzindex

Ein zusammengesetzter Index darf nur ergänzend erstellt werden. Im Haupttext sind die Einzelkomponenten zu berichten, damit die Gewichtung nicht willkürlich erscheint.

---

# 17. P2.2 – Regelbasierte Counterfactuals

Diese Analysen verändern ausschließlich Policy-Parameter. Sie sind ohne Mikrodaten keine fiskalischen Kostenschätzungen.

## Counterfactual 1: Wohngeld-Proxy

\[
K^{CF1}_{gh}=W_{gh}.
\]

Berichte:

- Veränderung des administrativen Bedarfs,
- Veränderung der simulierten Ausstiegsschwelle,
- Gewinner- und Verliererregionen,
- Verteilungswirkung nach Haushaltsgröße.

## Counterfactual 2: Median innerhalb der Mietenstufe

\[
K^{CF2}_{gh}
=
\operatorname{Median}
\left(
K_{ih}
\mid
Mietenstufe_i=Mietenstufe_g
\right).
\]

Berichte:

- Veränderung der regionalen Streuung,
- Zahl der Gemeinden mit positiver und negativer Änderung,
- Veränderungen nach Haushaltsgröße.

## Counterfactual 3: Bundeslandmedian

\[
K^{CF3}_{gh}
=
\operatorname{Median}
\left(
K_{ih}
\mid
Bundesland_i=Bundesland_g
\right).
\]

## Counterfactual 4: Einheitliches Haushaltsgrößenprofil

Halte das lokale Einpersonenniveau fest und ersetze die marginalen Aufschläge durch bundesweite Medianaufschläge:

\[
K^{CF4}_{g,h}
=
K_{g,1}
+
\sum_{s=2}^{h}
\operatorname{Median}_i(\Delta K_{i,s}).
\]

Damit wird getrennt, ob regionale Unterschiede primär aus dem allgemeinen Mietniveau oder aus dem Haushaltsgrößenprofil stammen.

## Optional: mechanisches fiskalisches Expositionsmaß

Mit BA-Beständen kann berechnet werden:

\[
Exposure
=
\sum_{jh}
BG_{jh}(K_{jh}-W_{jh}).
\]

Diese Größe ist ausdrücklich zu bezeichnen als:

> **Mechanische monatliche Parameterexposition bei vollständig bindenden Obergrenzen**

Sie ist keine tatsächliche Budgetwirkung, da tatsächliche Mieten, Einkommen, Ausnahmen und Nichtinanspruchnahme fehlen.

---

# 18. Robustheitsanalysen

Alle Hauptergebnisse sind mindestens unter folgenden Varianten zu prüfen:

## Wohngeld-Benchmark

- Basis-Höchstbetrag plus Klimakomponente,
- nur Basis-Höchstbetrag.

## Datenqualität

- nur Qualitätsstufe A,
- Qualitätsstufen A und B,
- erweiterte Stichprobe einschließlich C.

## Gewichtung

- Gemeinde ungewichtet,
- Bevölkerung,
- Policy-Region,
- Bedarfsgemeinschaften.

## Kostenkonzept

- direkt veröffentlichte Bruttokaltmiete,
- aus offiziellen Komponenten berechnete Bruttokaltmiete,
- Ausschluss sämtlicher berechneter Werte.

## Haushaltsgröße

- 1 Person,
- 2 Personen,
- 3 Personen,
- 4 Personen,
- 5 Personen.

## Regionstyp

- kreisfreie Städte,
- kreisangehörige Gemeinden,
- Gemeinden unter und über 10.000 Einwohnern,
- ost- und westdeutsche Bundesländer,
- Mietenstufen,
- Gemeindegrößenklassen.

## Räumliche Einheit

- Gemeindeebene,
- Policy-Region-Ebene,
- Kreis-/Jobcenter-Ebene.

## Ausreißer

- vollständige Stichprobe,
- Winsorisierung nur für grafische Skalierung,
- Ausschluss der manuell als Datenfehler bestätigten Beobachtungen.

Echte Extremwerte dürfen nicht allein wegen ihrer Größe entfernt werden.

---

# 19. Verbindliches Tabellen- und Abbildungsprogramm

## Haupttabellen

### Tabelle 1: Datenabdeckung und Qualität

Nach Bundesland:

- Gemeinden insgesamt,
- Gemeinden in Hauptstichprobe,
- Bevölkerungsabdeckung,
- Zahl Policy-Regionen,
- Anteil Qualität A/B/C,
- Anteil direkt veröffentlichter Bruttokaltmietengrenzen.

### Tabelle 2: Proxyfehler nach Haushaltsgröße

- Median und Mittelwert in Euro,
- Log-Differenz,
- mittlere absolute Differenz,
- P10/P90,
- Anteil über 50 und 100 Euro.

### Tabelle 3: Innerhalb-Mietenstufen-Heterogenität

- \(R^2\),
- Residualstandardabweichung,
- P90-P10-Abstand,
- Anzahl Gemeinden und Policy-Regionen.

### Tabelle 4: Standardfall-Mikrosimulation

Nach Modellhaushalt:

- Anspruchsdifferenz bei null Einkommen,
- maximale Anspruchsdifferenz,
- Median der Austrittsschwellenverschiebung,
- P10/P90,
- Wochenarbeitszeitäquivalent.

### Tabelle 5: Externe Validierung

- BA-Anerkennungsquote,
- Marktstress,
- deskriptive Regressionskoeffizienten,
- Stichprobenumfang,
- verwendete räumliche Einheit.

## Hauptabbildungen

1. Karte des Log-Proxyfehlers für Einpersonenhaushalte.
2. Karte des Log-Proxyfehlers für Vierpersonenhaushalte.
3. Boxplots \(K/W\) innerhalb der Mietenstufen.
4. Familien-Tilt und relatives KdU-Niveau.
5. Verteilung der simulierten Ausstiegsschwellenverschiebung.
6. Budgetkurven ausgewählter Gemeinden.
7. BA-Validierungsplot.
8. Administrative Grenzsprünge oder Zensus-Marktstress.

Für den Workshop sind maximal sechs Abbildungen in den Hauptvortrag aufzunehmen. Weitere Karten und Robustheiten gehören in Backup-Folien oder Anhang.

---

# 20. Framing und Formulierungsregeln

## Zu verwendende Begriffe

- lokale beziehungsweise kommunale KdU-Obergrenze,
- maximal anerkennungsfähige Bruttokaltmiete,
- regionaler Policy-Parameter,
- Wohngeld-Höchstbetrag als Benchmark oder Proxy,
- mechanischer Proxyfehler,
- standardfallbasierte Simulation,
- administrativer Bruttokaltbedarf,
- regionale Heterogenität,
- administrative Diskontinuität,
- Marktstressindikator.

## Zu vermeidende Begriffe

Nicht ohne zusätzliche Evidenz verwenden:

- „tatsächliche KdU-Zahlung“ für eine Obergrenze,
- „Großzügigkeit“ oder „Restriktivität“,
- „kausaler Effekt“,
- „Wohnungsverfügbarkeit“ auf Basis einer Durchschnittsmiete,
- „rechtswidrige KdU-Grenze“,
- „vollständiges Existenzminimum“ ohne Heizkosten,
- „unbekannte Regelbedarfe“.

## Zentrale Interpretation

Die lokale KdU-Obergrenze ist endogen zum lokalen Wohnungsmarkt, zu Verwaltungsverfahren und zur Definition von Vergleichsräumen. Eine hohe Obergrenze kann Ausdruck eines teuren Wohnungsmarkts sein und darf nicht automatisch als großzügigere Sozialpolitik interpretiert werden.

Der Wohngeld-Benchmark ist ebenfalls keine normative Zielgröße. Ein positiver oder negativer Abstand zeigt zunächst nur, dass zwei institutionelle Wohnkostenparameter unterschiedlich ausfallen.

Grenz- und Regressionsanalysen bleiben ohne zusätzliche Identifikationsstrategie deskriptiv.

---

# 21. Gewünschte Form der Ergebnisinterpretation

Für jede Hauptabbildung ist eine kurze Interpretation nach folgendem Muster zu verfassen:

1. **Was wird gemessen?**
2. **Was ist der zentrale quantitative Befund?**
3. **Warum ist dieser Befund für Steuer-Transfer-Simulationen relevant?**
4. **Welche Interpretation ist nicht zulässig?**

Beispielstruktur:

> Für einen Vierpersonenhaushalt liegt die lokale KdU-Obergrenze in der bevölkerungsgewichteten Median-Gemeinde um X Euro über beziehungsweise unter dem vergleichbaren Wohngeld-Höchstbetrag. In Y Prozent der Gemeinden beträgt die absolute Differenz mehr als 100 Euro monatlich. Ein Modell, das den Wohngeldwert als KdU-Proxy verwendet, kann daher den anerkannten Unterkunftsbedarf erheblich fehlmessen. Die Differenz ist nicht als kausales Maß kommunaler Großzügigkeit zu interpretieren.

Alle Platzhalter sind nach Abschluss der Analyse mit tatsächlichen Ergebnissen zu ersetzen.

---

# 22. Arbeits- und Abnahmeprozess

## Gate 1: Datenfreigabe

Vor Beginn der Ergebnisanalyse sind vorzulegen:

- Datenwörterbuch,
- Qualitätsbericht,
- Abdeckungstabelle,
- Liste aller Ausschlüsse,
- Liste der 20 größten positiven und negativen Abweichungen,
- Dokumentation des gemeinsamen Kostenkonzepts.

Erst danach beginnen die P0-Ergebnisanalysen.

## Gate 2: Kernbefunde

Nach Abschluss der P0-Deskriptivmodule sind vorzulegen:

- Tabellen 1 bis 3,
- Karten für Haushaltsgrößen 1 und 4,
- Within-Mietenstufen-Abbildung,
- Familien-Tilt-Abbildung,
- ein zweiseitiger Ergebnistext mit quantitativen Kernaussagen.

## Gate 3: Mikrosimulation

Vor Freigabe der Simulation:

- technische Dokumentation,
- Liste der Rechtsparameter,
- Testprotokoll,
- manuell validierte Standardfälle,
- Budgetkurven für mindestens drei Gemeinden.

## Gate 4: Externe Validierung

Vor Verwendung der BA- oder Zensusergebnisse:

- dokumentierter räumlicher Crosswalk,
- identische Kostenkonzepte,
- Stichprobendefinition,
- Vergleich Haupt- und erweiterte Stichprobe,
- explizite Einschränkungen.

---

# 23. Definition of Done

Das Projekt gilt als workshopfähig, wenn folgende Ergebnisse reproduzierbar vorliegen:

- ein bereinigter gemeindescharfer KdU-Datensatz für Haushaltsgrößen 1 bis 5,
- eindeutige Policy-Region-Zuordnung,
- ein zeitlich und konzeptionell passender Wohngeld-Benchmark,
- vollständige Verteilung des Euro- und Log-Proxyfehlers,
- Quantifizierung der Heterogenität innerhalb der Mietenstufen,
- Analyse des Haushaltsgrößenprofils,
- regionalisiertes administratives Bedarfsniveau für Modellhaushalte,
- standardfallbasierte Anspruchs- und Ausstiegsschwellenanalyse,
- mindestens eine externe Validierung,
- vollständiger Qualitäts- und Methodenanhang,
- reproduzierbare Tabellen und Abbildungen,
- klare Trennung zwischen deskriptiven Befunden, Simulationen und kausalen Aussagen.

---

# 24. Offizielle Datenanker

Die rechtliche Definition der lokalen Unterkunftsbedarfe ist für den gewählten Stichtag anhand von § 22 SGB II und § 35 SGB XII zu dokumentieren.

Die Wohngeld-Mietenstufen, Höchstbeträge, Klimakomponente und Heizkostenentlastung sind aus dem Wohngeldgesetz und der Wohngeldverordnung desselben Rechtsstands zu übernehmen.

Für tatsächliche und anerkannte Unterkunftskosten sind die Veröffentlichungen der Statistik der Bundesagentur für Arbeit zu verwenden.

Für lokale Bestandsmieten und Wohnungsmerkmale ist die Zensusdatenbank 2022 zu verwenden. Die Datenbank erlaubt Gemeindeauswertungen und programmatische Abrufe.

Für regionale Kontrollvariablen können ergänzend INKAR-Indikatoren des BBSR verwendet werden.

Für AGS, Gebietsstände und Gemeindestrukturen sind das amtliche Gemeindeverzeichnis und für räumliche Nachbarschaften die Verwaltungsgebiete des BKG zu verwenden.
