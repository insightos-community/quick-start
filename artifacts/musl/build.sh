#!/bin/sh
set -eu
mkdir -p /work/logs
exec > /work/logs/assemble.log 2>&1
mkdir -p /work/musl-loader
cp -L /lib/ld-musl-x86_64.so.1 /work/musl-loader/
apk add --no-cache bash git binutils patchelf tar zstd libgcc=15.2.0-r2 libstdc++=15.2.0-r2 libgomp=15.2.0-r2
python -m pip install pyyaml==6.0.3
# Bind the checkout read-only; all caches and source/wheel builds stay in /work.
git config --global --add safe.directory /src
python /src/artifacts/musl/assemble.py --cache /work/cache --work /work/build --output /work/dist --version "$MUSL_VERSION" --tag "$MUSL_TAG"
# Test the Python 3.13 source adaptation in its own environment, using the actual
# release wheelhouse and no dependency resolver substitution of MuJoCo.
python -m venv /work/test-venv
/work/test-venv/bin/pip install --no-index --no-deps /work/build/runtime-pack/wheelhouse/*.whl /work/build/runtime-pack/wheels/*.whl
/work/test-venv/bin/pip install pytest==8.3.5 pytest-cov==6.1.1 httpx==0.28.1
cd /work/build/mujoco-runtime
MUJOCO_GL=disable PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /work/test-venv/bin/python -m pytest -p pytest_cov -m 'not native' --cov=plugin_mujoco --cov-report=term > /work/logs/runtime-python313-tests.log 2>&1
