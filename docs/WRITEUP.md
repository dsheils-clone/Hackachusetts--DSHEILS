# Shifting Grounds

Running Devpost draft. Kiro updates it when asked; edit freely.

## Inspiration

Offshore wind farms are planned to run for decades, but fishing conflict is judged from past catch data. Meanwhile fish are moving as the ocean warms. An area that looks quiet for fishing today could matter much more by the time a wind farm is halfway through its life, or much less. Researchers have flagged this overlap between shifting fisheries and wind areas as an open problem, but I couldn't find a public tool that looks forward. I wanted one that fishermen and planners can actually use.

## What it does

Shifting Grounds projects where six commercially important species can live under +1°C and +2°C of bottom-water warming, and shows how their habitat inside each offshore wind lease area changes. Each lease and species gets a planning signal (rising, falling, stable or uncertain overlap) with the numbers behind it, NOAA's figure for current fishing value from that area, and a plain-English brief. A hindcast shows whether the model, trained on older years, predicted the shifts that actually happened.

It shows change in fishing overlap, not harm to fish, and it gives planning signals rather than build-or-don't-build verdicts.

## How we built it

- Data: NOAA's fall bottom trawl survey (2009 onward), BOEM lease areas, and NOAA's landings and value data for wind areas
- Model: one gradient boosting classifier per species, using only bottom temperature and depth so it can be re-run under warming
- Validation: test AUC on recent years, plus a hindcast of predicted versus observed habitat shifts
- Explanations: SHAP temperature-response curves, and short briefs from DeepSeek that may use only the computed numbers
- App: Streamlit with a Folium map
- Workflow: Kiro specs and steering, a Claude Haiku subagent for data cleaning, and a decision log with a commit after every task

## Challenges we ran into

_To fill in during the event._

## Accomplishments

_To fill in. Include test AUCs and the hindcast result._

## What we learned

_To fill in._

## What's next

- Use regional climate projections instead of uniform warming
- Add the spring survey and more species
- Add habitat and food-web features
- Weight the map by each species' share of fishing revenue
- Work with fishermen to check the signals against what they see on the water

## Sources

- [NOAA, NEFSC Fall Bottom Trawl Survey](https://www.fisheries.noaa.gov/inport/item/22560)
- [BOEM, Renewable Energy GIS Data](https://www.boem.gov/Renewable-Energy-GIS-Data/)
- [NOAA GARFO, Socioeconomic Impacts of Atlantic Offshore Wind Development](https://apps-garfo.fisheries.noaa.gov/offshore-energy/wind-reports/ALL_WEA_BY_AREA_DATA.html)
- [Friedland et al. 2021, Frontiers in Marine Science](https://frontiersin.org/articles/10.3389/fmars.2021.629230/full)
- [Munroe and Hofmann 2026, Fisheries Oceanography (Tethys summary)](https://tethys.pnnl.gov/publications/fisheries-climate-change-offshore-wind-energy-development-us-continental-shelf-regions)
