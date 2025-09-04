#!/usr/bin/env bash
set -e

BUILDDIR=build-auto
rm -rf "$BUILDDIR"
meson setup "$BUILDDIR" --buildtype=release --strip -Db_lto=true
cd "$BUILDDIR"
ninja
