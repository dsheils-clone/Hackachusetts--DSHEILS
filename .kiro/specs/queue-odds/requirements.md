# Requirements Document

## Introduction

Queue Odds predicts whether a proposed US power project will make it through the grid interconnection queue, and explains why in plain English. It is a solo hackathon build for the Hackachusetts energy/climate track, demoed on ISO New England projects.

Core scope is Requirements 1–6. Requirement 7 (bylaw reader) is a secondary proof of concept: start it only after the core demo works end to end.

## Glossary

- **Queue:** the list of proposed power projects waiting for permission to connect to the grid.
- **ISO-NE:** ISO New England, the grid operator for the six New England states.
- **Resolved project:** a project that either reached operation or withdrew from the queue.
- **SHAP values:** per-project numbers showing how much each feature pushed the prediction up or down.
- **AUC:** a score for how well the model ranks successes above failures; 0.5 is a coin flip, 1.0 is perfect.

## Requirements

### Requirement 1: Model

**User Story:** As the developer, I want a model trained on past queue outcomes, so that the app can score active projects.

#### Acceptance Criteria

1. WHEN the training script runs, THE SYSTEM SHALL train a HistGradientBoostingClassifier on resolved projects, using older queue entry years for training and the most recent years with outcomes for testing.
2. THE SYSTEM SHALL use only features known when a project entered the queue, as listed in design.md.
3. WHEN training finishes, THE SYSTEM SHALL report the test-set AUC and save the trained model to models/.

### Requirement 2: Prediction

**User Story:** As a developer or planner, I want a project's probability of reaching operation, so that I can judge its chances.

#### Acceptance Criteria

1. WHEN a user selects a project or submits a set of features, THE SYSTEM SHALL return the probability that the project reaches operation.

### Requirement 3: Explanation

**User Story:** As a non-expert, I want a plain-English reason for each prediction, so that I understand what drives it.

#### Acceptance Criteria

1. WHEN a prediction is returned, THE SYSTEM SHALL compute SHAP values and pass the top 3 factors (name, value, direction) to an LLM.
2. THE SYSTEM SHALL instruct the LLM to explain the prediction in 2–3 sentences using only those factors.
3. THE SYSTEM SHALL show a note that the dataset does not record why projects withdrew.
4. IF the LLM call fails, THE SYSTEM SHALL show the top 3 factors as a plain list instead.

### Requirement 4: What-if

**User Story:** As a developer, I want to change a project's features and see the effect, so that I can find what would improve its odds.

#### Acceptance Criteria

1. WHEN a user changes size, technology or storage pairing, THE SYSTEM SHALL update the probability and explanation without a full page reload.

### Requirement 5: Similar projects

**User Story:** As a user, I want to see similar past projects and how they ended, so that each prediction is grounded in real cases.

#### Acceptance Criteria

1. WHEN a project is selected, THE SYSTEM SHALL list the 5 most similar resolved projects (same region and technology, nearest size and queue entry year) with their outcomes.

### Requirement 6: Map

**User Story:** As a user, I want to browse active ISO-NE projects on a map, so that I can pick projects to inspect.

#### Acceptance Criteria

1. WHEN the app loads, THE SYSTEM SHALL show active ISO-NE projects colored by predicted odds.
2. WHEN a user clicks a project, THE SYSTEM SHALL open a panel with its probability, explanation, what-if controls and similar projects.
3. THE SYSTEM SHALL credit the data in the app footer: "Data: Lawrence Berkeley National Laboratory and GridTracker, Queued Up 2026 Edition (CC BY 4.0)."

### Requirement 7: Bylaw reader (secondary)

**User Story:** As a planner or developer, I want the local zoning rules for a project's town, so that I can see local barriers the model can't capture.

#### Acceptance Criteria

1. WHEN a town's bylaw text is loaded, THE SYSTEM SHALL extract these fields for solar and battery storage: allowed by right, by special permit or prohibited (per zone); setbacks; size caps; any moratorium; decommissioning bond.
2. THE SYSTEM SHALL store a quoted passage and section number for every extracted field, and mark a field "not found" rather than guess.
3. WHEN a project in a covered town is selected, THE SYSTEM SHALL show the extracted rules and their quotes in the detail panel.
4. WHEN a project's town is not covered, THE SYSTEM SHALL say so.
