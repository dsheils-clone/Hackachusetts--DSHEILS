# Decision log

Decisions made before and during the build, oldest first. New entries follow the format in .kiro/steering/workflow.md and continue numbering from the last entry.

### D-001 · pre-event · Build an explainable interconnection-queue predictor
- Decided by: human
- Context: Picking a project for the Hackachusetts energy/climate track.
- Decision: Predict whether a queued power project reaches operation, and explain why in plain English.
- Why: A large, well-understood problem with a free labeled dataset. Rejected: carbon-aware LLM routing (already demonstrated in published research), a utility bill decoder, and other consumer ideas.
- Affects: whole project

### D-002 · pre-event · Use Berkeley Lab Queued Up 2026 data
- Decided by: human
- Context: Need labeled project outcomes.
- Decision: Train on Berkeley Lab's Queued Up 2026 Edition, project-level data through 2025.
- Why: Free under CC BY 4.0, and covers grid operators representing about 98% of US generating capacity. Rejected: paid commercial datasets.
- Affects: src/prepare_data.py, README.md, app footer

### D-003 · pre-event · Gradient boosting plus SHAP, no survival model
- Decided by: human
- Context: Minimal ML experience and one day to build.
- Decision: Use scikit-learn's HistGradientBoostingClassifier, with SHAP for per-project explanations.
- Why: A few lines of code, handles mixed data types, works well without tuning. Rejected: survival analysis (harder to build and explain).
- Affects: src/train.py, src/explain.py

### D-004 · pre-event · Label, features and split chosen to avoid leakage
- Decided by: human
- Context: Many fields in the data reveal the outcome.
- Decision: Operational = 1, withdrawn = 0; drop active and suspended projects; use only features known at queue entry; split by queue entry year; report AUC.
- Why: Predictions must reflect what was knowable when a project entered the queue. Most projects fail, so accuracy would mislead.
- Affects: src/prepare_data.py, src/train.py

### D-005 · pre-event · LLM explains only the SHAP factors
- Decided by: human
- Context: LLM explanations can invent reasons.
- Decision: Pass the top 3 SHAP factors to the LLM and instruct it to use nothing else.
- Why: Keeps explanations tied to what the model actually used.
- Affects: src/explain.py

### D-006 · pre-event · Position as free and transparent, focused on ISO-NE
- Decided by: human
- Context: Enverus and Pearl Street sell queue-success scores; Paces sells AI siting and permitting tools.
- Decision: Pitch a free, explainable tool for the public, demoed on ISO New England and Massachusetts.
- Why: The commercial tools are paywalled and aimed at developers and investors.
- Affects: pitch, docs/WRITEUP.md

### D-007 · pre-event · Bylaw reader as a secondary proof of concept
- Decided by: human
- Context: The queue data doesn't record whether projects failed over local permitting.
- Decision: Add an LLM bylaw reader for 3 Massachusetts towns, with quoted sections checked by the human. Not used as model features. If the model isn't working by the halfway point, the bylaw reader becomes the lead feature.
- Why: Covers the model's blind spot and is timely given Massachusetts' new consolidated local permits. Kept secondary because it covers only hand-picked towns.
- Affects: src/bylaws.py, app.py

### D-008 · pre-event · Solo build as one Streamlit app
- Decided by: human
- Context: Working alone.
- Decision: One Streamlit app instead of a separate API and web frontend. Cut order if behind: bylaw reader, similar projects, what-if controls.
- Why: Saves roughly 3–4 hours; the cost is a plainer look.
- Affects: app.py, project structure

### D-009 · pre-event · Log decisions, write changelog entries and commit after every task
- Decided by: human
- Context: Want a traceable build and material for the Devpost writeup.
- Decision: A Kiro steering file plus hooks enforce the decision log, changelog, writeup updates and a commit after each task.
- Why: Keeps a record of why things changed and shows the work happened during the event.
- Affects: .kiro/steering/workflow.md, .kiro/hooks/, docs/

### D-010 · pre-event · Details added while writing the Kiro spec
- Decided by: agent (Claude, while converting the plan into spec files)
- Context: Turning the planning doc into Kiro spec files exposed a few gaps.
- Decision: Show the SHAP factors as a plain list if the LLM call fails; make the data credit a requirement; use Census county centroids when projects lack coordinates; fall back to shap.Explainer if TreeExplainer rejects the model; save processed tables as CSV.
- Why: Keeps the demo working when one piece fails, and meets the data license.
- Affects: requirements.md (3.4, 6.3), design.md
