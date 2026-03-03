#!/usr/bin/env bash
# generate-flatpak-sources.sh
# Run this once to regenerate python3-deps.json (needed by the Flatpak manifest)
# Requires: pipx / pip  +  flatpak-pip-generator
#
# Usage:
#   ./generate-flatpak-sources.sh

set -euo pipefail

GENERATOR="flatpak-pip-generator"
GEN_CMD=("$GENERATOR")

if ! command -v "$GENERATOR" &>/dev/null; then
    echo "Installing flatpak-pip-generator…"
    python3 -m pip install --user flatpak-pip-generator
    if command -v "$GENERATOR" &>/dev/null; then
        GEN_CMD=("$GENERATOR")
    else
        GEN_CMD=(python3 -m flatpak_pip_generator)
    fi
else
    GEN_CMD=("$GENERATOR")
fi

echo "Generating python3-deps.json for GNOME 49 (Python 3.13 aarch64/x86_64)…"

"${GEN_CMD[@]}" \
    --runtime org.gnome.Sdk//49 \
    --yaml \
    --output python3-deps \
    "caldav<2" \
    vobject \
    requests \
    lxml

echo "Done – python3-deps.yaml written."
echo "The Flatpak manifest will include it automatically."
