# Event Integrations component charter

Owner: Mathist Consulting LLC maintainers. Repository: `meetup-integration-public`.
The current repository name and URLs remain in use pending coordinated mapping.
Package names and imports stay unchanged. Retaining the current directory layout
avoids a migration with no functional benefit.

| Area | Responsibility | Boundary |
| --- | --- | --- |
| `python/src/meetup_integration` | Existing Python component | Public API reference and synthetic contracts |
| `javascript/src` | Existing JavaScript component | Narrower capabilities; see JavaScript guide |
| `requirements` | Source-backed acceptance and explanations | JSON is authoritative; protected originals retain provenance |
| `docs`, `examples`, `tests` | Consumer instructions and offline evidence | Fixtures do not prove provider compatibility |

The Meetup component owns selected GraphQL mappings, topic identity checks,
image safeguards and redacted uncertainty. Python supports event mutations;
JavaScript supports group/topic reads and pure token normalization. Callers own
HTTP/TLS, token refresh/brokers, credentials, event policy, persistent claims,
scheduling and reconciliation. Upstream inputs are provider GraphQL and image
contracts; optional Pillow decodes images. Consumers can be organizer dashboards,
calendar importers or scripts; their workers, storage and UI are indirect owners
whose acceptance is separate. Trace `MI4-*`, `MI5-*`, `MI6-*` through transport
contracts, installed-package tests and caller reconciliation. No monitoring is
activated here; offline schema checking uses only supplied snapshots.

Expansion point: add a separately scoped provider component with its own accepted
requirements and tests if later authorized. Keep provider identity and effects
explicit; no other event provider is implemented by this organization change.

Read [API](api.md), [setup and transport](setup.md), [recovery](recovery.md) and
[validation](validation.md). Acceptance and authorization are separate from
capability detection. Review changes against the original accepted baseline and
actual final diff; preserve all negative tests and state evidence limits.
