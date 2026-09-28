# Pipelines

## Pipeline A — SEC Event

1. Poll / receive filings
2. Deduplicate by accession
3. Save raw
4. Parse filing index
5. Fetch relevant exhibits
6. Normalize form / item
7. Extract deterministic facts
8. AI assists classification/extraction
9. Evidence validator
10. Create Event
11. Materiality evaluation

## Pipeline B — Fundamental

1. Pull companyfacts
2. Normalize taxonomy
3. Align periods
4. reconcile filing/exhibit
5. compute deltas
6. save Calculation

## Pipeline C — Reaction

1. map accepted_at to market session
2. fetch market windows
3. fetch SPY/sector benchmark
4. calculate raw/excess reaction
5. calculate volume context
6. classify reaction bucket

## Pipeline D — Opportunity

1. evidence gate
2. freshness gate
3. materiality gate
4. data quality gate
5. reaction gate
6. pattern gate
7. portfolio gate
8. create/update state

## Pipeline E — Portfolio

1. authenticate broker
2. read account
3. read positions
4. reconcile local
5. create snapshot
6. evaluate concentration
7. update Opportunity warnings

## Pipeline F — Order

1. user opens READY
2. deterministic sizing worksheet
3. user creates intent
4. preview
5. explicit confirmation
6. submit broker order
7. reconcile execution
8. create thesis snapshot
