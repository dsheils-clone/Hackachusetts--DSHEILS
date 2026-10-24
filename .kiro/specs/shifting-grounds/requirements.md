# Requirements Document

## Introduction

Shifting Grounds projects where commercially important fish can live as the ocean warms, and shows how that changes their overlap with offshore wind lease areas. Wind farms run for decades, but fishing conflict is judged today from past catch data. This tool adds a forward-looking signal for each lease area: rising, falling, stable or uncertain overlap.

It is a solo hackathon build for the Hackachusetts climate track (sustainable blue economy), focused on Massachusetts-area leases. The tool shows change in fishing overlap, not harm to fish, and it gives planning signals, not build-or-don't-build verdicts.

## Glossary

- **Trawl survey:** NOAA's fall bottom trawl survey, which records catch by species, location, depth and bottom temperature for each tow.
- **Tow:** one survey haul at one location.
- **Habitat suitability:** the model's predicted probability that a species is present at a location.
- **Lease area:** an active BOEM offshore wind lease.
- **Overlap signal:** a label for how a species' habitat inside a lease area changes under warming: Rising, Falling, Stable or Uncertain.
- **Hindcast:** testing the model by training on older years and checking its predictions against what happened in later years.
- **SHAP values:** numbers showing how much each feature pushed a prediction up or down.
- **AUC:** a score for how well the model ranks presences above absences; 0.5 is a coin flip, 1.0 is perfect.

## Requirements

### Requirement 1: Survey data preparation

**User Story:** As the developer, I want a clean table of survey tows with presence or absence for each target species, so that the models train on complete data.

#### Acceptance Criteria

1. WHEN the preparation script runs, THE SYSTEM SHALL load fall trawl survey tows from 2009 onward and join each tow's station data to its catch data.
2. THE SYSTEM SHALL record a species as absent (0) for every tow in which it was not caught, and present (1) otherwise.
3. THE SYSTEM SHALL drop tows missing bottom temperature, depth or location, and report how many were dropped.
4. WHEN preparation finishes, THE SYSTEM SHALL report tows per year and the presence rate for each species.

### Requirement 2: Habitat models

**User Story:** As the developer, I want one habitat model per species based on bottom temperature and depth, so that habitat can be re-predicted under warming.

#### Acceptance Criteria

1. WHEN the training script runs, THE SYSTEM SHALL train one HistGradientBoostingClassifier per target species, using bottom temperature and depth as features.
2. THE SYSTEM SHALL NOT use latitude, longitude or year as model features.
3. THE SYSTEM SHALL train on survey years up to 2018 and test on 2019 onward, and save each species' test AUC and class balance.
4. WHEN training finishes, THE SYSTEM SHALL save each trained model to models/.

### Requirement 3: Hindcast check

**User Story:** As a judge or user, I want to see whether the model could have predicted shifts that already happened, so that I can trust its projections.

#### Acceptance Criteria

1. WHEN the hindcast runs, THE SYSTEM SHALL train each species' model on 2009–2015 tows only.
2. THE SYSTEM SHALL compute the predicted shift in each species' habitat center (north-south, in km) between 2009–2015 and 2019 onward, using each period's observed temperatures.
3. THE SYSTEM SHALL compute the observed shift in the center of tows where the species was present over the same periods.
4. THE SYSTEM SHALL save predicted and observed shifts per species for display in the app.

### Requirement 4: Warming scenarios

**User Story:** As a user, I want to see how habitat changes if bottom water warms by 1°C or 2°C, so that I can compare today with plausible futures.

#### Acceptance Criteria

1. THE SYSTEM SHALL build a grid of recent conditions (mean bottom temperature and depth per cell) from 2016-onward tows.
2. THE SYSTEM SHALL predict habitat suitability for every grid cell, species and scenario (+0°C, +1°C, +2°C).
3. THE SYSTEM SHALL state in the app that the scenarios add the same warming everywhere, which is a simplification.

### Requirement 5: Lease overlap signals

**User Story:** As a planner or fisherman, I want a signal for each lease area and species, so that I can see where future overlap is likely to rise or fall.

#### Acceptance Criteria

1. THE SYSTEM SHALL compute the area-weighted mean habitat suitability inside each active lease area, for each species and scenario.
2. THE SYSTEM SHALL compute the percent change from +0°C to the selected scenario.
3. THE SYSTEM SHALL label the change Rising, Falling or Stable using the thresholds in design.md.
4. IF the species' test AUC or the survey coverage near the lease area is below the thresholds in design.md, THE SYSTEM SHALL label the result Uncertain instead.
5. THE SYSTEM SHALL pair each label with its fixed suggestion text from design.md.

### Requirement 6: Revenue context

**User Story:** As a user, I want to see current fishing revenue from each lease area for each species, so that the signal is tied to what's at stake today.

#### Acceptance Criteria

1. THE SYSTEM SHALL load NOAA's landings and value data for wind lease areas and compute each species' average annual value per lease area over the most recent 5 years available.
2. WHEN a lease area and species are selected, THE SYSTEM SHALL show that value next to the overlap signal.
3. IF no revenue data matches the species and lease area, THE SYSTEM SHALL show "no data" rather than zero.

### Requirement 7: Explanations

**User Story:** As a non-expert, I want plain-English explanations, so that I understand what the model found.

#### Acceptance Criteria

1. THE SYSTEM SHALL show each species' modeled response to bottom temperature, based on SHAP values.
2. WHEN a lease area and species are selected, THE SYSTEM SHALL send the computed numbers, label and suggestion text to the DeepSeek API and show a 2–3 sentence brief.
3. THE SYSTEM SHALL instruct the LLM to use only the numbers and suggestion provided.
4. IF the DeepSeek call fails, THE SYSTEM SHALL show a template sentence built from the same numbers instead.

### Requirement 8: Map and app

**User Story:** As a user, I want an interactive map, so that I can explore species, scenarios and lease areas.

#### Acceptance Criteria

1. WHEN the app loads, THE SYSTEM SHALL show a map with active lease area outlines and the grid colored by change in habitat suitability for the selected species and scenario.
2. THE SYSTEM SHALL provide a species selector and a warming scenario selector.
3. WHEN a user selects a lease area, THE SYSTEM SHALL show its signal, numbers, revenue, brief and suggestion.
4. THE SYSTEM SHALL show the hindcast results for the selected species.
5. THE SYSTEM SHALL show the note "Shows change in fishing overlap, not harm to fish" and the data credits in the footer.
