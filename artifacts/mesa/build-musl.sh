#!/bin/sh
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
set -eu

# Run inside the musl toolchain container documented in README.md.
: "${MESA_SOURCE:?Path to verified Mesa 25.2.7 source is required}"
: "${MESA_OUTPUT:?An unused absolute output directory is required}"
test "$(cat "$MESA_SOURCE/VERSION")" = '25.2.7'
case "$MESA_OUTPUT" in /*) ;; *) echo 'MESA_OUTPUT must be absolute' >&2; exit 2;; esac
test ! -e "$MESA_OUTPUT"
mkdir -p "$MESA_OUTPUT/logs"
drivers=${MESA_DRIVERS:-llvmpipe,iris,crocus,radeonsi,nouveau}
jobs=${MESA_JOBS:-3}
meson setup "$MESA_OUTPUT/build" "$MESA_SOURCE" \
  --prefix="$MESA_OUTPUT/prefix" --libdir=lib --buildtype=release \
  -Dplatforms=[] -Dgallium-drivers="$drivers" -Dvulkan-drivers=[] \
  -Dllvm=enabled -Dshared-llvm=enabled -Dglx=disabled -Degl=enabled \
  -Dgbm=enabled -Dgles1=disabled -Dgles2=enabled -Dbuild-tests=true \
  > "$MESA_OUTPUT/logs/configure.log" 2>&1
meson compile -C "$MESA_OUTPUT/build" -j "$jobs" > "$MESA_OUTPUT/logs/build.log" 2>&1
meson test -C "$MESA_OUTPUT/build" --print-errorlogs --num-processes "$jobs" \
  --timeout-multiplier 3 > "$MESA_OUTPUT/logs/test.log" 2>&1
meson install -C "$MESA_OUTPUT/build" > "$MESA_OUTPUT/logs/install.log" 2>&1
printf '%s\n' "$drivers" > "$MESA_OUTPUT/prefix/drivers.txt"
apk info -v > "$MESA_OUTPUT/logs/apk-packages.txt"
python -m pip freeze > "$MESA_OUTPUT/logs/python-packages.txt"
echo 'Mesa build, tests and install completed'
