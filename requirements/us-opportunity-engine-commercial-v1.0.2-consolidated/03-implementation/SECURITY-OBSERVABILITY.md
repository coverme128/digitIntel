# Security & Observability

## Security

- secrets never stored in repo
- broker credentials/token encrypted
- order endpoints require re-auth / confirmation policy
- no account numbers in logs
- least privilege
- immutable audit trail
- CSP and standard web hardening
- dependency scanning

## Observability

Required metrics:
- SEC ingest lag
- source error rate
- filing parse success
- evidence validation failure
- market-data gap rate
- opportunity creation count
- state transition count
- stale opportunity count
- broker reconciliation mismatch
- AI validation rejection rate
- order submission / execution reconciliation

## Alerts

P0:
- wrong security mapping
- broker account mismatch
- duplicated live order
- market data timestamp corruption
- evidence points to wrong issuer

P1:
- SEC lag
- Massive stream degraded
- IR adapter failures
- AI extraction spike failures

## Replay

任一 Opportunity 必须能通过：
- raw source
- versioned rules
- market snapshot
重新构建。
