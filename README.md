# Meetup Integration

Caller-configured Python and JavaScript clients for Meetup operations. Applications supply authorization and transport.

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
