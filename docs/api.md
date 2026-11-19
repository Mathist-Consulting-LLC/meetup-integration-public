# Meetup API and operation contracts

[Python signatures and records](python-api.md) enumerate all current public
classes/functions, including inherited image methods. Import client models from
`meetup_integration`; lower-level topic helpers are in `.topics`. See also the
[operation fixtures](../contracts/provider-operations.json),
[fault cases](../contracts/provider-faults.json) and [schema](../contracts/provider-schema.json).
These are offline contracts, not a snapshot of today's live provider.

| Python operation | Return / limit |
| --- | --- |
| `verify_auth()` | `True` only for a returned self identity |
| `list_group_events(slug, after_date_time=..., before_date_time=..., first=50)` | `list[MeetupEvent]`, date-bounded cursors, size clamped 1..100 |
| `list_network_events(slug, first=100)` | `list[MeetupEvent]`, one page, size 1..100 |
| `list_network_groups(slug, network_id='')` | `list[dict]` with `id`, `name`, `urlname`, `parentNetworkId`; one page of 100; optional exact network check |
| `search_venues(slug, query, first=25)` | `list[MeetupVenue]`; group cursors then one nearby-events page; deduplicates IDs |
| `get_event(id)` | `MeetupEvent` or `None` for explicit provider null |
| `create_event(EventCreateRequest(...))` | `MeetupEvent`; nonblank returned identity required |
| `update_event(id, changes)` | `MeetupEvent`; exact returned event ID required |
| `cancel_event(id, reason)` | `None`; `reason` is retained in signature but not sent; no series removal |
| `inspect_network_creation_contract()` | `{supported: bool, checks: dict[str, bool]}` from schema probes |
| `inspect_event_topic_contract()` | `{supported: bool, provenance: 'authenticated_graphql_introspection'}` |
| `search_event_topics(text)` | `list[{id, name}]`; bounded search, not a complete catalog |
| `validate_event_topics(selections)` | tuple of canonical IDs, exact fresh name/ID checks, max five |
| `get_event_topic_ids(event_id)` | tuple of IDs, exact event binding |
| `supports_event_images()` | local dependency/callback readiness, not provider authorization |
| `upload_event_image_from_url(slug, image_url)` | uploaded photo ID after validation/placeholder/PUT and up to five one-byte readbacks; may mutate |
| `event_image_is_readable(event_id, photo_id)` | bool, checks exact event photo and image readback |

Image upload polls immediately, then after injected sleeps of 1/2/4/8 seconds;
failed readback after placeholder/upload is `mutation_uncertain`. Include polls
and sleeps in the caller time/request budget; see [image lifecycle](setup.md#images-python-only).

`MeetupEvent` and `MeetupVenue` are frozen provider projections, not application
models. The [record fields](python-api.md) preserve names, defaults and optional
values. Missing optional provider values can become empty strings, `None` or
zero; do not interpret them as verified facts. Nonblank event identity and connection structures are validated; title/time
values are projected without a completeness guarantee. No local persistence occurs.

`EventCreateRequest` requires group slug, title, description, provider start time,
ISO duration, venue ID, find-us text and publish status. Optional fields include
RSVP settings, image and network inputs and topic selections. Topic IDs require
matching canonical selections and fresh validation; bare arbitrary IDs are not
accepted. Provider/account permissions remain the caller's prerequisite.
`update_event` recognizes `title`, `description`, `start_date_time`, `duration`,
`how_to_find_us`, `venue_id`, `rsvp_open_time`, `rsvp_limit`, `rsvp_question`,
`featured_photo_id`, `topic_ids` and `topic_selections`. Most empty strings are
omitted; `rsvp_limit` presence propagates its value; an empty `rsvp_question`
explicitly clears the question and disables the survey. Unrecognized keys do not
add provider fields. There is no general arbitrary GraphQL mutation API.

## JavaScript exports

Import from `@mathist/meetup-integration`. No event create/edit/cancel or image
implementation is exported in JavaScript. All provider functions are asynchronous.

| Export | Arguments and return |
| --- | --- |
| `createMeetupGroupResolver(options)` | returns `(urlName, controls={}) => Promise<group|null>`; group `{id,name,urlName,url}` |
| `normalizeMeetupUrlName(value)` | canonical lowercase slug or `''`; rejects unsupported host/path/reserved slug |
| `normalizeMeetupGroupResult(group)` | normalizes identity aliases, returns canonical group or `null` |
| `createMeetupTopicProvider(options)` | returns `{probe(controls={}), search(term, controls={})}` |
| `createMeetupTopicCatalog({probe,search,ttlMs=300000,clock=Date.now})` | returns `{search(query,options={}), validate(topics,{signal}={})}` |
| `normalizeMeetupTokenResponse(result, now=Date.now())` | `{accessToken,refreshToken,expiresAt}`; no exchange, storage or refresh |
| `createBoundary({tokenSupplier,transport}={})` | opaque async `exchange({body:Uint8Array})`, returns `{status,body:Uint8Array}` |
| `validateTopic({id,name})` | copied exact trimmed nonempty identity; ID <=128/name <=160 code points |

`probe` performs eight sequential introspection reads and returns capability flags
`searchSupported`, `readbackSupported`, `createSupported`, `editSupported`,
`provenance:'authenticated_introspection'`, and ISO `expiresAt` (240 seconds).
Flags describe schema shape, not additional implemented methods. `search` uses
`suggestTopics(first:20, excludeMemberTopics:false)` and returns ID/name records.
Catalog `search` returns `{supported,manualReviewRequired,reason,state,topics,
provenance,expiresAt,maxTopics}`; unsupported results also include empty
`recommendations`. State is `ok` on success and `unsupported` on failure,
including stale capability. Optional `errorCode` is safe.
`options` accepts `groupId`, `signal`, `fresh`; groupId is not an authorization
filter. Validation refreshes schema, checks at most five unique exact selections
by bounded name search, and returns the canonical `[{id,name}]` array on success;
absence from a prefix is unverified, not proof of nonexistence.

Token normalization requires own `access_token`, `refresh_token`, `expires_in`
properties; expiry must be finite >60 seconds, and optional token type must be
Bearer. `expiresAt` is integer milliseconds. The successful result contains
secrets: never log it. There is no rotating owner in this package.

`IntegrationError` is the opaque boundary error (`invalid_contract`,
`authentication_unavailable`, `transport_unavailable`). Provider helpers throw
`MeetupProviderError`; Python uses `MeetupApiError` and `TopicReviewRequired`.
See [recovery](recovery.md) before using any failure as a retry signal.
