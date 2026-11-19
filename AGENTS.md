# Public contributor and agent guidance

Read [README](README.md), [developer index](docs/README.md),
[component charter](docs/component-charter.md) and [requirements](requirements/catalog.json)
before edits. These public materials are sufficient for ordinary development.

- Keep the existing `meetup_integration` imports and `mathist-meetup-integration` distribution identity stable.
- Work on an issue-backed branch; submit a reviewed PR with exact validation.
- Preserve accepted IDs, revisions, safety criteria and tests. Record authority,
  reason and impact before material contract changes; do not infer approval.
- Keep caller authority, credential ownership, durable claims and interpretation
  outside the component. No ambient credentials or implicit provider access.
- Use synthetic fixtures and isolated installed consumers. Never use real mail,
  provider writes or registry publication for routine checks.
- Keep personal data, deployment identifiers, tokens, original messages,
  capability links and protected evidence out of public Git and logs.
- Follow [validation](docs/validation.md); report actual commands, revision,
  limitations and failures. Do not claim live compatibility from fixtures.
- Keep docs/examples aligned with source and review cross-component effects.
  Future functionality needs its own requirements and review.
- Preserve license/NOTICE. No private workflow dependency is required.
