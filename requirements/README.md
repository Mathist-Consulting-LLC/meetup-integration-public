# Requirements

[The JSON catalog](catalog.json) owns statements, plain-language explanations,
positive examples and acceptance criteria. Examples explain requirements; they do
not establish acceptance. [Developer contracts](../docs/README.md) describe the
current implementation. [Validation](../docs/validation.md) explains local proof
and its limits.

This is one cohesive component, so one catalog keeps its boundaries together.
Historical IDs and revisions are preserved. The [public provenance map](provenance.json)
identifies protected original catalog digests and publication qualifications. Public issue [#7](https://github.com/Mathist-Consulting-LLC/meetup-integration-public/issues/7)
routes restoration of the sanitized records; it does not retroactively approve
them. Maintainers retain original catalogs, original sources, approval records,
revision digests and task evidence in protected storage. Historical source
pointers and named deployment references are redacted, including in change
records. No test or historical acceptance criterion is waived by publication.
Live compatibility, composed application adoption and independent review require
separate evidence. New organization and documentation obligations come from
[#7](https://github.com/Mathist-Consulting-LLC/meetup-integration-public/issues/7) and [#6](https://github.com/Mathist-Consulting-LLC/meetup-integration-public/issues/6), with separately authorized implementation.

For a proposed change, identify affected IDs and stable acceptance IDs, compare
the accepted baseline, record authority/reason/impact and advance a revision for
normative changes. Preserve tombstones and earlier history. Never change a test
expectation merely to make a regression pass. Public consumers need no access
to protected evidence to install, use or contribute to the package.
