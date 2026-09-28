# Data Model

## Core Entities

### Security
- security_id
- ticker
- cik
- issuer_name
- exchange
- sector
- industry
- active

### Source
- source_id
- source_type
- canonical_url
- rights_status
- access_method

### RawDocument
- raw_document_id
- source_id
- external_id
- received_at
- published_at
- sha256
- object_path

### Filing
- filing_id
- accession_number
- security_id
- form_type
- accepted_at
- filing_date
- primary_document_id

### EvidenceSpan
- evidence_id
- raw_document_id
- locator
- text_hash
- evidence_level

### Fact
- fact_id
- security_id
- metric_id
- period_start
- period_end
- value
- unit
- evidence_id
- fact_version

### Event
- event_id
- security_id
- event_family
- event_type
- event_at
- materiality_bucket
- evidence_quality
- parent_event_id

### Calculation
- calculation_id
- type
- rule_version
- inputs_json
- output_json
- calculated_at

### Opportunity
- opportunity_id
- security_id
- event_id
- state
- created_at
- current_rule_version
- reaction_bucket
- trigger_status
- invalidation_status

### OpportunityTransition
- transition_id
- opportunity_id
- from_state
- to_state
- reason_code
- actor_type
- created_at

### PortfolioSnapshot
- snapshot_id
- account_ref
- captured_at
- equity
- cash
- buying_power

### Position
- position_id
- security_id
- quantity
- avg_price
- broker_ref

### Thesis
- thesis_id
- opportunity_id
- position_id
- catalyst
- invalidation_json
- entry_plan_json
- created_at

### OrderIntent
- intent_id
- opportunity_id
- side
- quantity
- order_type
- limit_price
- status
- user_confirmed_at

## Audit

所有 derived entity 必须保存：
- source versions
- rule version
- calculation version
