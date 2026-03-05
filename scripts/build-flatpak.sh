#!/usr/bin/env bash
# build-flatpak.sh — Build OrbitTrack as a .flatpak bundle for offline installation.
#
# Usage:
#   ./scripts/build-flatpak.sh
#
# Output:
#   orbittrack.flatpak   (in project root)
#
# On the target Fedora 43 machine, install with:
#   flatpak install --user orbittrack.flatpak

set -euo pipefail

APP_ID="io.github.jye16.OrbitTrack"
MANIFEST="io.github.jye16.OrbitTrack.yml"
BRANCH="stable"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${PROJECT_DIR}/.flatpak-build"
REPO_DIR="${PROJECT_DIR}/.flatpak-repo"
BUNDLE="${PROJECT_DIR}/orbittrack.flatpak"

cd "$PROJECT_DIR"

# ── 1. Ensure flatpak-builder is available ──────────────────────────────────
#    Prefer the Flatpak-packaged builder (org.flatpak.Builder) which avoids
#    needing system-level installs.
if flatpak info org.flatpak.Builder &>/dev/null; then
    BUILDER="flatpak run org.flatpak.Builder"
elif command -v flatpak-builder &>/dev/null; then
    BUILDER="flatpak-builder"
else
    echo ">> Installing org.flatpak.Builder from flathub …"
    flatpak install --user --noninteractive flathub org.flatpak.Builder
    BUILDER="flatpak run org.flatpak.Builder"
fi
echo ">> Using builder: ${BUILDER}"

# ── 2. Ensure GNOME 49 runtime & SDK are available ─────────────────────────
echo ">> Ensuring org.gnome.Platform//49 and org.gnome.Sdk//49 are installed …"
flatpak install --user --noninteractive flathub org.gnome.Platform//49 2>/dev/null || true
flatpak install --user --noninteractive flathub org.gnome.Sdk//49     2>/dev/null || true

# ── 3. Build ────────────────────────────────────────────────────────────────
echo ">> Building ${APP_ID} …"
${BUILDER} \
    --force-clean \
    --user \
    --install-deps-from=flathub \
    --repo="${REPO_DIR}" \
    --default-branch="${BRANCH}" \
    "${BUILD_DIR}" \
    "${MANIFEST}"

# ── 4. Export to a single-file bundle ───────────────────────────────────────
echo ">> Exporting bundle → ${BUNDLE}"
flatpak build-bundle \
    "${REPO_DIR}" \
    "${BUNDLE}" \
    "${APP_ID}" \
    "${BRANCH}"

BUNDLE_SIZE="$(du -h "${BUNDLE}" | cut -f1)"
echo ""
echo "========================================="
echo "  Bundle ready: orbittrack.flatpak (${BUNDLE_SIZE})"
echo "========================================="
echo ""
echo "Copy to target machine and install:"
echo "  # 1. Ensure the GNOME 49 runtime is available:"
echo "  flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo"
echo "  flatpak install --user flathub org.gnome.Platform//49"
echo ""
echo "  # 2. Install the bundle:"
echo "  flatpak install --user orbittrack.flatpak"
echo ""
echo "Then run:"
echo "  flatpak run ${APP_ID}"
