#!/usr/bin/env bash
# generate-flatpak-sources.sh
# Run this once to regenerate python3-deps.json (needed by the Flatpak manifest)
# Requires: pipx / pip  +  flatpak-pip-generator
#
# Usage:
#   ./generate-flatpak-sources.sh

set -euo pipefail

GENERATOR="flatpak-pip-generator"

if ! command -v "$GENERATOR" &>/dev/null; then
    echo "Installing flatpak-pip-generator…"
    pip install --user flatpak-pip-generator
    GENERATOR="$HOME/.local/bin/flatpak-pip-generator"
fi

echo "Generating python3-deps.json for GNOME 49 (Python 3.13 aarch64/x86_64)…"

"$GENERATOR" \
    --runtime org.gnome.Sdk//49 \
    --yaml \
    --output python3-deps \
    caldav \
    vobject \
    requests \
    lxml

echo "Done – python3-deps.yaml written."
echo "The Flatpak manifest will include it automatically."
