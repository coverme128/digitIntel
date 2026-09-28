# Architecture Delta

Sources
↓
Raw
↓
Canonical
↓
Deterministic Calculations
↓
Opportunity Engine
↓
Portfolio Risk
↓
CoreOutput
├── UI
├── Decision & Analysis Export
└── Optional AI Assist

AI adapter 只能写：
- ai_explanation
- ai_summary
- ai_notes
- candidate_extraction

AI adapter 不得调用：
- opportunity state mutation
- portfolio risk mutation
- order eligibility mutation
- broker order endpoint

AI outage 不得影响：
- ingest
- rule engine
- core UI
- export
- portfolio workflow
