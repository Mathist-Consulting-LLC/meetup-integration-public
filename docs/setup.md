# Setup, authorization and transports

The [quickstart](quickstart.md) works without an account. To connect your own
application, obtain access through the provider's supported authorization process
and verify the account is permitted to use each target group/network operation.
This library registers no OAuth application, grants no scopes/roles and reads no
environment credentials. Maintain a single caller-owned refresh store or broker;
use its access-token supplier rather than creating competing refresh owners.
Keep token rotation, locking, encryption and uncertain-refresh recovery there.

## Python GraphQL transport

Construct `MeetupClient(token_supplier=..., transport=..., max_pages=1000)`.
The supplier is called for each exchange and returns a nonempty printable ASCII
token with no whitespace. It may raise; diagnostics are redacted.
`transport(request: Request, token: str) -> Result` is synchronous. `request.body`
is UTF-8 JSON bytes with `query` and optional `variables`. The transport sends
those bytes as JSON POST to `https://api.meetup.com/gql-ext`, with
`Authorization: Bearer <token>`, and returns `Result(status=int, body=bytes)`.
It must return HTTP error bodies as Results if classification is wanted;
raising loses the HTTP category. There is no default HTTP implementation.

A replacement transport should: validate TLS/hostname, route only to that host,
disable redirects and retries, preserve HTTP status, bound time/body/decompression
and sockets, and release resources in a finally block. Python has no built-in
network deadline/cancellation mechanism: implement those in the callback. The
client checks a 16 MiB JSON body ceiling after allocation, which cannot protect
against an unbounded transport allocation. Never log body/token/exception data.
The [offline read example](../examples/read_events.py) provides the complete
call/response seam; replace only its synthetic dispatcher with your authorized
HTTP session after implementing these controls. Handle safe errors in caller code.

## JavaScript fetch boundary

Group and topic factory `options` require `fetchImpl` and `tokenSupplier`.
`tokenSupplier({signal})` may resolve a token; a zero-argument broker supplier also
works. `fetchImpl(url, options)` must implement fetch's Response stream contract,
including status, redirected and `body.getReader()` yielding Uint8Array chunks.
A `{json()}`-only mock is insufficient. The fixed GraphQL endpoint, JSON POST and
bearer header are constructed by the package; no endpoint override or global
fetch fallback exists. A caller may supply a hardened wrapper around platform
fetch after validating its network policy and disabling hidden retries.

Options: `clock` returns milliseconds; `timeoutMs` integer 1..15000 (groups
5000, topics 15000); `maxResponseBytes` integer 1..16777216 (default 1048576).
Per-call `controls` supports `signal` and absolute millisecond `deadline`.
The total probe deadline spans eight sequential exchanges. A strict overall
catalog-validation budget needs a caller abort signal, since validation can
perform a probe plus five sequential searches. Supplier/fetch abort is cooperative:
a timed-out refresh may still have completed externally. Late supplier completion
cannot start a fetch; late response bodies are cancelled. The caller must ensure
underlying sockets, decompression and stream chunks remain bounded and obey abort.

## Images (Python only)

Install the optional `images` extra (`Pillow==13.0.0`) from a trusted wheel source.
`image_transport(ImageRequest)->ImageResult` and `resolver(host,443)->addresses`
are separate injected callbacks. The resolver must return the actual connectable
addresses. Transport MUST pin `ImageRequest.addresses` while still checking TLS
against the original hostname; resolving again permits DNS rebinding. Deny
redirects before following them. Enforce `max_bytes`, timeout, MIME and streaming
limits before allocation. The package rejects unsafe URL forms and non-global,
mapped-private/reserved addresses, validates up to 10 MiB/40 million pixels,
and validates JPEG or normalizes supported PNG/WebP/GIF to JPEG.
Image requests never carry the provider bearer token. Placeholder creation and
PUT/readback are effects; failed upload/readback can be uncertain. Readiness via
`supports_event_images` alone proves no live capability or authorization.
