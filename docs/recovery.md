# Failures, pagination and recovery

Python `MeetupApiError` exposes a fixed `code` and `outcome_unknown`.
Messages contain no caller/provider text or chained source exception.

| Codes | Caller action |
| --- | --- |
| `invalid_request` | Fix inputs/bounds; do not blindly retry |
| `authentication_unavailable`, `authentication_failed` | Inspect the single credential owner and account authorization privately |
| `permission_denied` | Verify requested group/network permission; refreshing is not authorization |
| `rate_limited` | Delay bounded read retries under caller policy; inspect write uncertainty first |
| `transport_unavailable` | Check transport/deadline; retry reads only under explicit policy |
| `response_invalid`, `schema_unsupported`, `topic_unverified` | Retain safe context, compare the contract, require review; no silent empty success |
| `mutation_uncertain` | Preserve claim and exact attempted identity; reconcile before any replay |
| `image_unsafe`, `image_invalid`, `image_support_unavailable` | Correct source/transport/optional dependency; account for possible placeholder/upload effects |

JS provider errors use the shared categories through `response_invalid`, plus
`deadline_exceeded` and `cancelled`; image/topic-unverified/mutation errors are
Python-specific. JS read helpers have no mutation-outcome flag. Partial GraphQL
data plus errors is failure. HTTP 401/403/429 map to authentication/permission/
rate categories, not generic empty results. See the [fault fixtures](../contracts/provider-faults.json).

An auth/permission/rate response to a Python mutation can still carry
`outcome_unknown=True`. Inspect the flag as well as the code. No package method
automatically retries a mutation. Persist the original request, authorized
principal, durable atomic claim and correlation context before write I/O. After
uncertainty, retain that claim and check the exact remote event, group, interval
and intended fields. Do not infer identity from newest title matches or create a
second event because the first response was lost. Recovery/claim release requires
caller-owned evidence and authority; the library supplies no database or scheduler.
The [offline mutation example](../examples/uncertain_write.py) leaves this state
explicitly unresolved and asserts one transport attempt.

`list_group_events` and group-venue search follow cursors and reject missing,
repeated/cyclic cursors or `max_pages` exhaustion (default 1000, allowed 1..10000).
A later failure never returns a successful partial list. Network events and
groups each read one bounded page; nearby venue search and topic suggestions
also return bounded prefixes. No completeness guarantee or extra cursor API is
invented for them. JS group resolution has no pagination; topic search is a
single bounded prefix. Do not use absence from a prefix as deletion evidence.

Troubleshoot imports with the quickstart's isolated wheel consumer; a source
checkout or PYTHONPATH can hide packaging defects. For JS use Node >=20 and the
installed tarball with ES modules. For schema failures run the offline snapshot
checker before any separately authorized live inspection. Log only safe codes,
caller correlation IDs and your own redacted operation metadata. Tokens, image
URLs, raw responses and callback exceptions remain private.
