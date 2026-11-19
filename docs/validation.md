# Validation and evidence limits

Run the [quickstart](quickstart.md) from a fresh checkout into a separate
consumer. Execute every copied example using the installed wheel/tarball, with
no source-path injection. Expected output is in that guide. Record Git SHA,
artifact hash, runtime versions, actual command results and any skips privately.
All included responses are synthetic; no live provider write or mail access is
required or implied. An offline pass does not establish deployed workflows,
current provider schemas, credential validity or live follow-up delivery.

## Existing installed-artifact suite

From the repository root in the pinned build environment:

```sh
"$PIP_PYTHON" -m pip download --require-hashes -r requirements-build.txt -d "$WHEELS"
MEETUP_PIP_PYTHON="$PIP_PYTHON" MEETUP_BUILD_WHEELHOUSE="$WHEELS" "$BUILD_PYTHON" scripts/check.py
```

Use absolute paths for WHEELS and BUILD_PYTHON as in the quickstart. The suite
builds a wheel and sdist, rebuilds the sdist in another environment, installs
both into isolated consumers, and packs/installs npm separately. It checks
metadata, imports, capability/time/transport contracts, adverse cases and safety
regressions. It runs source fixtures against actual installed packages, not
ambient private application imports.

To include image decoder regressions on a compatible host, download the
hash-pinned `requirements-images-test.txt` wheels into a separate absolute
image wheelhouse and run the same suite with
`MEETUP_IMAGE_WHEELHOUSE=/absolute/path/to/image-wheels`. The core suite also
exercises operation without Pillow. Do not report image-enabled passes when
that optional environment was skipped. `python scripts/check-whitespace.py`
checks source formatting; `git diff --check` checks your branch diff.
`python scripts/check-contracts.py --help` documents offline snapshot inputs.

## Documentation and requirement review

Check all relative Markdown links, JSON parsing, source-derived signatures,
examples' exact output and public-data hygiene. Compare the final diff with
accepted requirements and preserve existing tests. Independent parent review
owns final approval; an implementer's pass is not that approval. Private source,
original approval and full test logs remain protected. Public contributors can
run package validation using only this repository and the optional public Gmail
component. Requirement statements/explanations live in JSON, not copied policy.

Validated documentation examples on Linux x86_64, CPython 3.12 and Node.js 24.
The declared runtime floors remain Python 3.11 / Node.js 20 where applicable;
this task does not claim testing every supported OS/runtime combination.
