# Integrating and extending

Start with an authorized read-only importer: construct the client with a token
supplier and bounded transport, request a date window, then map `MeetupEvent.id`
and returned fields into your application's own records. Persist sync state in
your application and distinguish an incomplete read from an empty result. The
[read example](../examples/read_events.py) demonstrates this seam and safe failure.
For writes, add application permissions, a persistent atomic claim and exact
remote reconciliation before using the existing mutation methods. See
[recovery](recovery.md); the package is not an organizer policy engine.

For JS, compose the group resolver and topic provider/catalog with the same
existing refresh owner. Keep topic recommendations and audience ranking in your
application. Schema capability flags do not implement create/readback/edit.

A new provider, operation or transport default needs separate scope and accepted
requirements. Prefer a focused independently testable component within the
repository over moving the working packages. Do not retrofit another provider's
identities into Meetup records. Define its contracts, effects, auth ownership,
limits and uncertainty, then add synthetic positive/adverse installed-consumer
cases without weakening the existing suite. This guide adds no new provider.

For provider drift, compare supplied schemas with
`python -m meetup_integration.contract_check --help` and the
[offline checker](../scripts/check-contracts.py). The command consumes local
snapshots and does not establish current live support. Root repository relocation
must be coordinated: update clone/source links, charter identity, cross-repository
references and any owner-managed monitor target after a rename. Package names,
imports and existing distributions remain stable unless separately authorized.
