# AI Contract

## AI Roles

允许：
1. filing section classification
2. event extraction candidate generation
3. old-vs-new language comparison
4. management commentary summarization
5. Item 4 purpose summarization
6. user-facing explanation

## AI Prohibited

- invent canonical ids
- invent financial values
- overwrite SEC/XBRL facts
- predict target price
- return BUY/SELL as authoritative state
- change opportunity state directly
- submit orders
- infer missing dates/units without evidence

## Input Contract

AI receives:
- source text chunks
- canonical metadata
- allowed event taxonomy
- candidate metric registry
- prior comparable text when needed

## Output Contract

AI returns structured JSON:
- extracted_claims[]
- evidence_locator
- event_type_candidate
- confidence
- unresolved_fields[]
- contradiction_flags[]

## Validation

AI output only enters Canonical if:
- evidence locator resolves
- numeric strings reconcile
- allowed taxonomy match
- deterministic validator passes

Otherwise：
`REVIEW_REQUIRED`

## Presentation

AI explanation must distinguish:
- Fact
- Calculation
- Interpretation
