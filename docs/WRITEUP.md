# Queue Odds

Running Devpost draft. Kiro updates it after each finished feature; edit freely. Check the figures against Berkeley Lab's Queued Up report before submitting.

## Inspiration

Most proposed power projects never get built. The median US project that came online in 2025 spent 61 months in the interconnection queue, and only about 10% of queued projects are expected to come online within three years. Commercial tools score projects' odds, but they're paywalled and don't explain themselves. I wanted a free tool that shows anyone which projects are likely to make it, and why.

## What it does

Queue Odds maps active ISO New England projects, colored by their predicted chance of reaching operation. Clicking a project shows its probability, a plain-English explanation of the main factors, what-if controls for size, technology and storage, and similar past projects with how they ended.

_If built: a bylaw panel shows the town's zoning rules for solar and battery storage, with quoted sections._

## How we built it

- Data: Berkeley Lab's Queued Up 2026 Edition, project-level queue data through 2025
- Model: scikit-learn gradient boosting trained on resolved projects, split by queue entry year
- Explanations: SHAP values give each project's top factors; an LLM turns them into plain English and may use only those factors
- App: Streamlit with a Folium map
- Workflow: Kiro specs, steering and hooks, with a decision log and a commit after every task

## Challenges we ran into

_To fill in during the event._

## Accomplishments

_To fill in. Include the test AUC._

## What we learned

_To fill in._

## What's next

- Cover the other grid operators
- Predict time to outcome, not just the outcome
- Add local permitting data, such as county restrictions on renewables, as model features
- Extend the bylaw reader to more towns, cross-checked against NREL's ordinance database

## Sources

- [Berkeley Lab, Queued Up](https://emp.lbl.gov/queues)
- [Axis Intelligence, grid interconnection queue statistics](https://axis-intelligence.com/grid-interconnection-queue-statistics/)
- [POWER Magazine, Enverus 2025 Interconnection Queue Outlook](https://www.powermag.com/enverus-releases-2025-interconnection-queue-outlook)
