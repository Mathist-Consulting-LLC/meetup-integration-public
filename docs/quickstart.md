# Fresh consumer quickstart

Use Python 3.11+ with pip/venv and Git plus Node.js 20+ and npm.
The provisioning interpreter needs pip 22.3+ (`--python` support); it installs
into isolated venvs even on systems without ensurepip.
Commands below use a POSIX shell; on Windows use the venv's Scripts/python.exe
and equivalent copy/path commands.
The recorded validation platform is described in [validation](validation.md).

Run in a new work directory. Resolve main once, record its full Git SHA, and use
that exact revision again to reproduce the source. The commands deliberately
build artifacts locally, without registry publication. The first build downloads
only the pinned build dependency; subsequent consumer installation is offline.

```sh
git clone https://github.com/Mathist-Consulting-LLC/meetup-integration-public.git
cd meetup-integration-public
REVISION=$(git rev-parse HEAD)
printf '%s\n' "$REVISION" > ../source-revision.txt
git checkout --detach "$REVISION"
SOURCE=$(pwd)
PIP_PYTHON=$(command -v python3)
"$PIP_PYTHON" -m pip --version
"$PIP_PYTHON" -m venv --without-pip ../build-env
BUILD_PYTHON="$(cd ../build-env && pwd)/bin/python"
"$PIP_PYTHON" -m pip --python "$BUILD_PYTHON" install --require-hashes -r requirements-build.txt
mkdir -p ../wheels
WHEELS="$(cd ../wheels && pwd)"
"$PIP_PYTHON" -m pip --python "$BUILD_PYTHON" wheel --no-build-isolation --no-deps . --wheel-dir "$WHEELS"
cd ..
mkdir consumer
cd consumer
"$PIP_PYTHON" -m venv --without-pip .venv
PYTHON="$(pwd)/.venv/bin/python"
"$PIP_PYTHON" -m pip --python "$PYTHON" install --no-index --find-links "$WHEELS" 'mathist-meetup-integration==0.0.0.dev3'
"$PYTHON" -I -c 'import pathlib,sys,meetup_integration as p; assert pathlib.Path(p.__file__).is_relative_to(sys.prefix); print("installed package")'
cp "$SOURCE/examples/read_events.py" .
cp "$SOURCE/examples/uncertain_write.py" .
"$PYTHON" -I read_events.py
"$PYTHON" -I uncertain_write.py
```

Expected output (after installation messages):

```text
installed package
imported=event-one,event-two; pages=2
read failure=permission_denied; no retry
mutation_uncertain: outcome_unknown=True; attempts=1; no retry
```

The first script models a bounded read importer and permission failure. The
second models a lost response after one synthetic mutation; it never opens a
connection and deliberately does not authorize recovery/replay.

## JavaScript consumer

Continue in the separate consumer directory with SOURCE still set. The Python
and npm names differ; do not install a same-named registry package by accident.

```sh
(cd "$SOURCE/javascript" && npm pack --ignore-scripts --pack-destination "$WHEELS")
printf '{"private":true,"type":"module"}\n' > package.json
npm install --offline --ignore-scripts --no-audit --no-fund "$WHEELS/mathist-meetup-integration-0.0.0-dev.3.tgz"
cp "$SOURCE/examples/read_group.mjs" .
node read_group.mjs
```

Expected output:

```text
group=group-one; calls=1
read failure=invalid_request; calls=1
```

This installs the packed public package rather than importing from source.
For broader coverage follow [validation](validation.md). npm pack remains local;
the package's private flag prevents ordinary registry publication.

Keep `source-revision.txt`, built artifact SHA256 and your consumer lockfile in
your own reproducibility record. A future same-version source build can differ;
Git SHA plus artifact hash is the pin. Read [setup](setup.md) before replacing
fixtures, [API](api.md) for returned shapes, and [recovery](recovery.md) for errors.
These commands create only local environments/artifacts. To clean up, remove
those directories after retaining any records you need.
