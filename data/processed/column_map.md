# Column and species-code map (task 2.1)

Maps the real headers in the NOAA NEFSC bottom trawl survey CSVs to the canonical
field names used in `.kiro/specs/shifting-grounds/design.md`, and resolves the
target-species common names to their numeric `SVSPP` codes.

Inspected files:
- Stations: `data/raw/survey/22560_NEFSCFallFisheriesIndependentBottomTrawlData/22560_UNION_FSCS_SVSTA.csv`
- Catch: `data/raw/survey/22560_NEFSCFallFisheriesIndependentBottomTrawlData/22560_UNION_FSCS_SVCAT.csv`
- Cruises: `data/raw/survey/22560_NEFSCFallFisheriesIndependentBottomTrawlData/22560_SVDBS_CRUISES.csv`
- Species lookup: `data/raw/survey/SVDBS_SupportTables/SVDBS_SVSPECIES_LIST.csv`

All real headers confirmed by reading the header row and sample rows (including a
2019 fall tow). Values are quoted CSV (`"..."`).

## SVSTA (stations) → design field

| design.md field          | real SVSTA column   | notes |
| ------------------------ | ------------------- | ----- |
| tow / station id         | `ID`                | 18-digit key, e.g. `201904031100020035`. Confirmed **unique** across all 22,432 rows, so it is a clean per-tow key. Equivalent to `CRUISE6`+`STRATUM`+`TOW`+`STATION` concatenated. |
| year                     | `EST_YEAR`          | e.g. `2019`. (A matching `GMT_YEAR` also exists; design specifies `EST_YEAR`.) |
| latitude                 | `DECDEG_BEGLAT`     | decimal degrees, tow start, e.g. `40.549787`. |
| longitude                | `DECDEG_BEGLON`     | decimal degrees, tow start, e.g. `-73.251245`. |
| depth                    | `AVGDEPTH`          | metres, e.g. `23`. (`SETDEPTH`/`ENDDEPTH`/`MIN`/`MAX` also present; design specifies `AVGDEPTH`.) |
| bottom temperature       | `BOTTEMP`           | °C, e.g. `20.12`. (`BOTSALIN`, `SURFTEMP` also present.) |
| season / fall indicator  | **not in SVSTA**    | See FLAG 1 — season comes from `CRUISES.SEASON` joined on `CRUISE6`. |

All design-expected SVSTA names (`ID`, `EST_YEAR`, `DECDEG_BEGLAT`,
`DECDEG_BEGLON`, `AVGDEPTH`, `BOTTEMP`) exist exactly as written. No ambiguity.

## SVCAT (catch) → design field

| design.md field     | real SVCAT column | notes |
| ------------------- | ----------------- | ----- |
| tow / station id    | `ID`              | same key as SVSTA; this is the join column. |
| species code        | `SVSPP`           | zero-padded 3-char string, e.g. `"503"`. |
| catch count         | `EXPCATCHNUM`     | e.g. `10`. |
| catch weight        | `EXPCATCHWT`      | kg, e.g. `19.5`. |
| (helper, not design)| `SCIENTIFIC_NAME` | free text incl. common name, e.g. `Loligo pealeii (longfin squid)`. Useful cross-check only. |
| (helper)            | `CATCHSEX`        | sex split; design counts presence per tow, so sum/ignore sex. |

All design-expected SVCAT names (`ID`, `SVSPP`, `EXPCATCHNUM`, `EXPCATCHWT`) exist
exactly as written. No ambiguity.

**Join:** SVSTA and SVCAT join on `ID` (one SVSTA row per tow; zero or more SVCAT
rows per tow). A species is *present* in a tow if an SVCAT row exists for that `ID`
with the matching `SVSPP`; *absent* (zero-fill) otherwise.

## Target species → SVSPP code

Lookup source: `data/raw/survey/SVDBS_SupportTables/SVDBS_SVSPECIES_LIST.csv`
(columns `SCINAME,COMNAME,SVSPP`). Every code below was also confirmed to appear in
SVCAT with a matching `SCIENTIFIC_NAME`.

| species (design)  | COMNAME in list  | SCINAME                | SVSPP | design expected | match | present in SVCAT |
| ----------------- | ---------------- | ---------------------- | ----- | --------------- | ----- | ---------------- |
| Longfin squid     | LONGFIN SQUID    | LOLIGO PEALEII         | 503   | 503             | ✓     | ✓ (Loligo pealeii (longfin squid)) |
| Summer flounder   | SUMMER FLOUNDER  | PARALICHTHYS DENTATUS  | 103   | 103             | ✓     | ✓ |
| Black sea bass    | BLACK SEA BASS   | CENTROPRISTIS STRIATA  | 141   | 141             | ✓     | ✓ |
| Scup              | SCUP             | STENOTOMUS CHRYSOPS    | 143   | 143             | ✓     | ✓ |
| Silver hake       | SILVER HAKE      | MERLUCCIUS BILINEARIS  | 072   | 072             | ✓     | ✓ |
| Atlantic cod      | ATLANTIC COD     | GADUS MORHUA           | 073   | 073             | ✓     | ✓ |

All six target species resolve, and every resolved code matches the code
design.md expected. No code had to be guessed.

## Flags for the human (confirm at the 2.2 checkpoint)

These are documented, not resolved by guessing. None blocks the design's codes, but
please confirm.

**FLAG 1 — Season is not in SVSTA; it must be joined from CRUISES.**
SVSTA has no `SEASON` column. Season lives in `22560_SVDBS_CRUISES.csv`
(`CRUISE6,...,SEASON,YEAR`), joined on `CRUISE6`. This download is the *fall* survey
package, but the SVSTA table it contains spans all years/seasons (earliest rows are
1963). So task 2.3's "fall tows from 2009 onward" needs a `SEASON = 'FALL'` filter
via the CRUISES join, not just a year filter. Confirm that approach.

**FLAG 2 — "SCUP" common name is duplicated in the species list.**
Two rows carry COMNAME `SCUP`: `STENOTOMUS CHRYSOPS = 143` (true Atlantic scup, the
target) and `STENOTOMUS CAPRINUS = 642` (longspine porgy, mislabeled). Design's 143
is the correct one. Code 642 does **not** appear in SVCAT at all, so there is no real
data collision — but flagging because a name-based lookup alone would be ambiguous.
Using SVSPP 143 (not 642).

**FLAG 3 — Longfin squid has a separate "egg mop" code.**
`LOLIGO PEALEII = 503` (the animal, target) vs `LOLIGO PEALEII EGG MOPS = 520`
(egg masses). Code 520 **does** appear in SVCAT ("longfin squid egg mop"). Presence
for longfin squid must count SVSPP **503 only** and must NOT include 520, or presence
would be inflated. Using 503 only.

**FLAG 4 — Code storage format.**
`SVSPP` is a zero-padded 3-character string in both the lookup (`072`, `073`) and
SVCAT (`"503"`). When filtering, compare as zero-padded strings (or cast both sides
to int consistently) so `72`/`072` don't mismatch.

## Resolved species-code constants (for prepare_data.py in task 2.3/2.4)

```python
TARGET_SPECIES = {
    "longfin_squid":   "503",
    "summer_flounder": "103",
    "black_sea_bass":  "141",
    "scup":            "143",
    "silver_hake":     "072",
    "atlantic_cod":    "073",
}
```
