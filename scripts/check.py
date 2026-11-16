"""Offline acceptance; run with the pinned isolated build interpreter."""
import email
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

PIP_PYTHON = os.environ.get('MEETUP_PIP_PYTHON', sys.executable)
ROOT = Path(__file__).resolve().parents[1]
ENV = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME', 'NODE_PATH')}
ENV.update(SOURCE_DATE_EPOCH='1700000000', PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1', npm_config_offline='true', npm_config_audit='false', npm_config_fund='false')

def run(*args, cwd, capture=False):
    return subprocess.run(args, cwd=cwd, env=ENV, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout

def consume(wheel, directory):
    venv = directory / 'venv'
    run(sys.executable, '-m', 'venv', '--without-pip', str(venv), cwd=directory)
    python = venv / 'bin/python'
    run(PIP_PYTHON, '-m', 'pip', '--python', str(python), 'install', '--no-index', '--no-deps', str(wheel), cwd=directory)
    run(str(python), '-I', '-c', "import importlib.util, pathlib, sys, meetup_integration; assert importlib.util.find_spec('meetup_management') is None; assert pathlib.Path(meetup_integration.__file__).is_relative_to(sys.prefix)", cwd=directory)
    shutil.copy(ROOT/'examples/uncertain_write.py', directory/'uncertain_write.py')
    run(str(python), '-I', str(directory/'uncertain_write.py'), cwd=directory)
    shutil.copy(ROOT/'tests/consumer.py', directory/'consumer.py')
    run(str(python), '-I', str(directory/'consumer.py'), str(ROOT/'contracts/topics.json'), cwd=directory)
    shutil.copytree(ROOT/'tests', directory/'provider-tests')
    shutil.copy(ROOT/'contracts/provider-faults.json', directory/'provider-tests/provider-faults.json')
    shutil.copy(ROOT/'contracts/provider-schema.json', directory/'provider-tests/provider-schema.json')
    shutil.copy(ROOT/'contracts/provider-operations.json', directory/'provider-tests/provider-operations.json')
    run(str(python), '-I', '-B', '-m', 'unittest', 'discover', '-s',
        str(directory/'provider-tests'), '-p', 'test_*.py', cwd=directory)
    if os.environ.get('MEETUP_IMAGE_WHEELHOUSE'):
        image_venv = directory/'venv-images'
        run(sys.executable, '-m', 'venv', '--without-pip', str(image_venv), cwd=directory)
        image_python = image_venv/'bin/python'
        run(PIP_PYTHON, '-m', 'pip', '--python', str(image_python), 'install',
            '--no-index', '--no-deps', str(wheel), cwd=directory)
        run(PIP_PYTHON, '-m', 'pip', '--python', str(image_python), 'install',
            '--no-index', '--find-links', os.environ['MEETUP_IMAGE_WHEELHOUSE'],
            '--require-hashes', '-r', str(ROOT/'requirements-images-test.txt'), cwd=directory)
        run(str(image_python), '-I', '-B', '-m', 'unittest', 'discover', '-s',
            str(directory/'provider-tests'), '-p', 'test_*.py', cwd=directory)

def inspect_wheel(path):
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        assert all(n.startswith(('meetup_integration/', 'mathist_meetup_integration-')) for n in names)
        metadata = email.message_from_bytes(wheel.read(next(n for n in names if n.endswith('/METADATA'))))
        assert metadata['Name'] == 'mathist-meetup-integration'
        assert metadata['Version'] == '0.0.0.dev3'
        assert metadata['Requires-Python'] == '>=3.11'
        assert metadata.get_all('Requires-Dist') == ['Pillow==13.0.0; extra == "images"']

assert importlib.metadata.version('setuptools') == '84.2.1'
# Modern setuptools includes its wheel command; no separate wheel dependency.
print(sys.version, 'setuptools', importlib.metadata.version('setuptools'), flush=True)
for binary in ('node', 'npm'): print(run(binary, '--version', cwd=ROOT, capture=True).strip(), flush=True)
for path in [*ROOT.glob('python/src/**/*.py'), *ROOT.glob('javascript/src/**/*.js')]:
    for forbidden in ('gmail', 'database'):
        assert forbidden not in path.read_text(), (path, forbidden)

with tempfile.TemporaryDirectory(prefix='meetup-offline-') as temp:
    tmp = Path(temp)
    ENV['npm_config_cache'] = str(tmp/'npm-cache')
    source = tmp/'source'
    shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns('.git', '.private', '.agents', '.aws', '.codex', '__pycache__', '*.egg-info', 'build', 'dist', 'node_modules'))
    output = tmp/'artifacts'
    output.mkdir()
    run(sys.executable, '-c', "from setuptools.build_meta import build_wheel, build_sdist; import sys; out=sys.argv[1]; build_wheel(out); build_sdist(out)", str(output), cwd=source)
    wheel = next(output.glob('*.whl'))
    inspect_wheel(wheel)
    consume(wheel, tmp)
    # Build from the actual sdist in a distinct clean build venv, provisioned offline.
    sdist = next(output.glob('*.tar.gz'))
    unpacked = tmp/'sdist'
    with tarfile.open(sdist) as archive:
        names = archive.getnames()
        assert any(n.endswith('/pyproject.toml') for n in names)
        assert any(n.endswith('/meetup_integration/__init__.py') for n in names)
        archive.extractall(unpacked, filter='data')
    build = tmp/'sdist-build'
    run(sys.executable, '-m', 'venv', '--without-pip', str(build), cwd=tmp)
    build_python = build/'bin/python'
    wheelhouse = Path(os.environ['MEETUP_BUILD_WHEELHOUSE']).resolve()
    run(PIP_PYTHON, '-m', 'pip', '--python', str(build_python), 'install', '--no-index', '--find-links', str(wheelhouse), '--require-hashes', '-r', str(ROOT/'requirements-build.txt'), cwd=tmp)
    rebuilt = tmp/'rebuilt'
    rebuilt.mkdir()
    run(str(build_python), '-c', "from setuptools.build_meta import build_wheel; import sys; build_wheel(sys.argv[1])", str(rebuilt), cwd=next(unpacked.iterdir()))
    rebuilt_wheel = next(rebuilt.glob('*.whl'))
    inspect_wheel(rebuilt_wheel)
    consumer = tmp/'sdist-consumer'
    consumer.mkdir()
    consume(rebuilt_wheel, consumer)
    print('Artifact SHA256:', json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}), flush=True)
    npm = tmp/'npm'
    npm.mkdir()
    (npm/'package.json').write_text('{"private":true,"type":"module"}')
    packed = json.loads(run('npm', 'pack', '--json', '--ignore-scripts', '--pack-destination', str(npm), cwd=source/'javascript', capture=True))
    assert {x['path'] for x in packed[0]['files']} == {'package.json', 'README.md', 'LICENSE.md', 'NOTICE'} | {
        str(p.relative_to(ROOT/'javascript')) for p in (ROOT/'javascript/src').glob('*.js')}
    run('npm', 'install', '--offline', '--ignore-scripts', '--no-audit', '--no-fund', str(npm/packed[0]['filename']), cwd=npm)
    shutil.copy(ROOT/'tests/consumer.mjs', npm/'consumer.mjs')
    # Direct invocation reports real subtests on hosts where --test only reports a file.
    run('node', 'consumer.mjs', str(ROOT/'contracts/topics.json'), cwd=npm)
    shutil.copy(ROOT/'tests/javascript-provider.mjs', npm/'javascript-provider.mjs')
    run('node', 'javascript-provider.mjs', cwd=npm)
    shutil.copy(ROOT/'tests/provider-contracts.mjs', npm/'provider-contracts.mjs')
    run('node', 'provider-contracts.mjs', str(ROOT/'contracts/provider-faults.json'),
        str(ROOT/'contracts/provider-schema.json'), cwd=npm)
print('Offline wheel, sdist and npm consumption passed.', flush=True)
