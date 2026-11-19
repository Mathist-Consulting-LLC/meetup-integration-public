# Event Integrations

The existing Meetup integration is the current component. Python clients and JavaScript helpers keep their existing package names.

Start with the [developer guide](docs/README.md) for installation, runnable offline examples and API contracts. See the [component map](docs/component-charter.md) and [requirements](requirements/README.md).

Connect Meetup to your own application so event information and event management can be part of a larger workflow. This library provides reusable Python clients and JavaScript helpers around selected Meetup operations.

An event organizer could use the Python client to bring group events into a calendar, look up a venue, or create and update events from an application they already use. A developer could use the JavaScript helpers to resolve a group or search and validate event topics.

## Why use it?

Meetup provides the event platform and API. This library supplies reusable request handling, response models, topic validation, and error handling for the supported operations. It also reports an uncertain write when a request may have succeeded but its response was lost. Your application can then check the original event before deciding whether to retry.

Using the Meetup website works well for managing events manually. This library is useful when you want your own software to work with those events, such as a calendar, organizer dashboard, or event import tool.

## What access does it provide?

| Package | Supported areas |
| --- | --- |
| Python | Read group and network events, retrieve an event, search venues, create and update events, cancel events, and work with event topics and images through the implemented client methods. |
| JavaScript | Group resolution, topic search and validation, token-response normalization, and an injectable GraphQL transport boundary. |

The packages expose different capabilities. Provider permissions and current API support determine which operations an authorized account can use. Your application supplies the access token and HTTP transport, manages credential refresh and storage, and decides when an operation is allowed.

For example, a calendar application can read a group's events for a date window and use the returned identities to reconcile its calendar entries. When creating an event, it retains its local attempt and checks the remote result if the response is lost. The [offline uncertain-write example](examples/uncertain_write.py) demonstrates that failure case with a synthetic transport.

## Install from source

Requires Python 3.11 or newer. From the repository root, run `python -m pip install .`.

For JavaScript, use Node.js 20 or newer and run `npm pack --ignore-scripts` in `javascript/`. Install the resulting tarball in your application.

## Provider operations

The caller supplies authorization and transport. Keep credentials, token storage, and application scheduling in the consuming application. The [provider contract](contracts/provider-operations.json) records operation cases and the [fault contract](contracts/provider-faults.json) records error cases.

For live requests, configure a token supplier that returns a Meetup access token authorized for the requested operation, and a transport that sends the request with that token. Access depends on the authenticated account and the target group or network. The example below uses a synthetic token and a local transport.

In Python, `list_group_events` follows cursors within the requested date window. Its `first` argument controls page size. `search_venues` follows group venue cursors, then can query nearby events. Cursor loops and page-limit exhaustion raise `response_invalid`. `list_network_events` requests a single bounded page of up to 100 events, so its results may be incomplete for a larger network.

When a write returns an uncertain outcome, retain the local attempt and reconcile it against the exact remote event before deciding whether to retry. The [offline example](examples/uncertain_write.py) simulates a lost response after submission and checks that only one write is attempted. Run it with `python examples/uncertain_write.py` after installing the Python package.

## License

[PolyForm Small Business 1.0.0](LICENSE.md). Preserve the [required notice](NOTICE) when redistributing.

## Test the installed packages

In a Python virtual environment, install the build requirements with `python -m pip install --require-hashes -r requirements-build.txt`. Download those same wheels into a local directory with `python -m pip download --require-hashes -r requirements-build.txt -d wheelhouse`. Run `MEETUP_BUILD_WHEELHOUSE=wheelhouse python scripts/check.py` from the repository root. The checks use synthetic requests.
