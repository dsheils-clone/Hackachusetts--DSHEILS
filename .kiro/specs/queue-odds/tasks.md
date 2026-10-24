# Implementation Plan

Work through the tasks in order. After each task, follow .kiro/steering/workflow.md: decision log, changelog, commit. Get tasks 1–9 working end to end before starting task 10. If the build falls behind, skip in this order: task 10, task 8, task 7.

The human does these steps outside Kiro:

- Before task 2: download the Queued Up Excel file into data/raw/ and the Census county Gazetteer file into data/geo/.
- Before task 6: add an LLM API key to .env.
- Before task 10: put 3 towns' zoning bylaw PDFs in data/bylaws/.

- [ ] 1. Set up the project (20 min)
  - Create the folder structure in design.md
  - Create requirements.txt: pandas, openpyxl, scikit-learn, shap, joblib, streamlit, streamlit-folium, folium, python-dotenv and the LLM provider's SDK
  - Create .gitignore covering data/raw/, .env and Python caches
  - Write README.md with the data download steps and the data credit
  - _Requirements: 6.3_

- [ ] 2. Prepare the training data (1.5 h)
  - [ ] 2.1 Load the Excel file, read its codebook tab, and map the real column names to the features, label and status fields in design.md
    - _Requirements: 1.2_
  - [ ] 2.2 Stop and show the human the column mapping and the excluded columns; continue only after they confirm
    - _Requirements: 1.2_
  - [ ] 2.3 Build the training table of resolved projects with the label; drop active and suspended projects and every excluded column; save to data/processed/training.csv
    - _Requirements: 1.1, 1.2_
  - [ ] 2.4 Build the table of active ISO-NE projects with coordinates or county centroids; save to data/processed/active_isone.csv
    - _Requirements: 6.1_

- [ ] 3. Train and evaluate the model (1 h)
  - Encode categorical features and split by queue entry year as in design.md
  - Train a HistGradientBoostingClassifier; print the class balance and test AUC
  - Save models/model.joblib and models/metrics.json
  - Add an assert that no excluded column is in the feature list
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 4. Add prediction and SHAP factors (1 h)
  - Implement predict() and top_factors() in src/explain.py
  - If TreeExplainer rejects the model, use the fallback in design.md
  - _Requirements: 2.1, 3.1_

- [ ] 5. Build the app: map and detail panel (2 h)
  - Map of active ISO-NE projects colored by predicted probability, using streamlit-folium, with a project dropdown as fallback
  - Clicking or selecting a project opens a detail panel showing its probability
  - Data credit in the footer
  - _Requirements: 2.1, 6.1, 6.2, 6.3_

- [ ] 6. Add the LLM explanation (1 h)
  - Implement explain_text() with the prompt in design.md; read the API key from .env
  - Show the explanation and the note that the data doesn't record why projects withdrew
  - Fall back to a plain list of factors if the call fails
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 7. Add what-if controls (30 min)
  - Add controls for size, technology and storage pairing to the detail panel
  - Recompute the probability and explanation when a control changes
  - _Requirements: 4.1_

- [ ] 8. Add similar past projects (30 min)
  - Implement similar_projects() and show the 5 matches with their outcomes in the detail panel
  - _Requirements: 5.1_

- [ ] 9. Checkpoint: demo readiness (1.5 h)
  - Ask the human to click through the app and pick 2–3 showcase projects; fix anything broken
  - Write docs/DEMO.md with the demo flow from design.md and the chosen projects
  - Update docs/WRITEUP.md from DECISIONS.md and CHANGELOG.md
  - The human makes 3 slides
  - _Requirements: 2.1, 3.1, 4.1, 5.1, 6.2_

- [ ] 10. Bylaw reader (secondary; start only after task 9)
  - [ ] 10.1 Implement extract_rules() with the prompt and schema in design.md; run it on the PDFs in data/bylaws/ (1 h)
    - _Requirements: 7.1, 7.2_
  - [ ] 10.2 Checkpoint: stop and ask the human to check every extracted field against its quote; apply their corrections (45 min)
    - _Requirements: 7.2_
  - [ ] 10.3 Add the bylaw section to the detail panel, with the "not available for this town" message (30 min)
    - _Requirements: 7.3, 7.4_
