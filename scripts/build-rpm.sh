#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOPDIR_DEFAULT="${PROJECT_ROOT}/rpm-build"
TOPDIR="${TOPDIR_DEFAULT}"
SKIP_BUILD=0
SKIP_DEP_CHECK=0

usage() {
  cat <<'EOF'
Usage: scripts/build-rpm.sh [--topdir PATH] [--no-build] [--skip-dep-check]

Build a Fedora RPM for OrbitTrack from the current working tree.

Options:
  --topdir PATH  Set rpmbuild _topdir (default: ./rpm-build)
  --no-build     Only generate Source tarball and SPEC file
  --skip-dep-check  Skip local RPM package pre-check
  -h, --help     Show this help text
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --topdir)
      [[ $# -ge 2 ]] || { echo "Error: --topdir needs a value" >&2; exit 1; }
      TOPDIR="$2"
      shift 2
      ;;
    --no-build)
      SKIP_BUILD=1
      shift
      ;;
    --skip-dep-check)
      SKIP_DEP_CHECK=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument '$1'" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found in PATH." >&2
  exit 1
fi

if ! command -v rpmbuild >/dev/null 2>&1; then
  if [[ "$SKIP_BUILD" -eq 1 ]]; then
    echo "Warning: rpmbuild not found, but continuing because --no-build was set." >&2
  else
    echo "Error: rpmbuild not found. Install rpm-build first (sudo dnf install rpm-build)." >&2
    exit 1
  fi
fi

if [[ "$SKIP_BUILD" -eq 0 && "$SKIP_DEP_CHECK" -eq 0 ]]; then
  REQUIRED_RPMS=(
    rpm-build
    pyproject-rpm-macros
    python3-devel
    python3-wheel
    desktop-file-utils
    appstream
  )
  MISSING_RPMS=()

  for pkg in "${REQUIRED_RPMS[@]}"; do
    if ! rpm -q "$pkg" >/dev/null 2>&1; then
      MISSING_RPMS+=("$pkg")
    fi
  done

  if [[ ${#MISSING_RPMS[@]} -gt 0 ]]; then
    echo "Error: missing Fedora build dependencies: ${MISSING_RPMS[*]}" >&2
    echo "Install them with:" >&2
    echo "  sudo dnf install -y ${MISSING_RPMS[*]}" >&2
    exit 1
  fi
fi

readarray -t META < <(
  cd "$PROJECT_ROOT"
  python3 - <<'PY'
from pathlib import Path
import tomllib

with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)

project = data["project"]
name = project["name"].strip()
version = project["version"].strip()
summary = project.get("description", "OrbitTrack")
print(name)
print(version)
print(summary)
PY
)

NAME="${META[0]}"
VERSION="${META[1]}"
SUMMARY="${META[2]}"

APP_ID="io.github.jye16.OrbitTrack"
SOURCE_BASENAME="${NAME}-${VERSION}"
TARBALL="${SOURCE_BASENAME}.tar.gz"
SPEC_PATH="${TOPDIR}/SPECS/${NAME}.spec"

mkdir -p "${TOPDIR}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

STAGE_DIR="${TMPDIR}/${SOURCE_BASENAME}"
mkdir -p "$STAGE_DIR"

# Stage the source tree while excluding common build artifacts.
rsync -a \
  --exclude '.git' \
  --exclude '.flatpak-builder' \
  --exclude 'build-dir' \
  --exclude 'rpm-build' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.pyo' \
  --exclude 'dist' \
  --exclude '*.egg-info' \
  "$PROJECT_ROOT/" "$STAGE_DIR/"

# pyproject points to README.md. Ensure it exists to avoid wheel metadata failures.
if [[ ! -f "${STAGE_DIR}/README.md" ]]; then
  cat >"${STAGE_DIR}/README.md" <<EOF
# OrbitTrack

${SUMMARY}
EOF
fi

(
  cd "$TMPDIR"
  tar -czf "${TOPDIR}/SOURCES/${TARBALL}" "${SOURCE_BASENAME}"
)

cat >"$SPEC_PATH" <<EOF
Name:           ${NAME}
Version:        ${VERSION}
Release:        1%{?dist}
Summary:        ${SUMMARY}

License:        GPL-3.0-or-later
URL:            https://github.com/JYe16/OrbitTrack
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-wheel
BuildRequires:  desktop-file-utils
BuildRequires:  appstream
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita

%generate_buildrequires
%pyproject_buildrequires

%description
OrbitTrack is a GTK4/Libadwaita CalDAV task time tracker for GNOME.

%prep
%autosetup -n %{name}-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files orbittrack

install -Dpm0644 ${APP_ID}.desktop \
  %{buildroot}%{_datadir}/applications/${APP_ID}.desktop
install -Dpm0644 ${APP_ID}.metainfo.xml \
  %{buildroot}%{_metainfodir}/${APP_ID}.metainfo.xml
install -Dpm0644 data/${APP_ID}.svg \
  %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/${APP_ID}.svg

desktop-file-validate %{buildroot}%{_datadir}/applications/${APP_ID}.desktop
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/${APP_ID}.metainfo.xml

%files -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_datadir}/applications/${APP_ID}.desktop
%{_metainfodir}/${APP_ID}.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/${APP_ID}.svg

%changelog
* $(date '+%a %b %d %Y') OrbitTrack Packager <noreply@example.com> - ${VERSION}-1
- Build OrbitTrack as a Fedora RPM
EOF

echo "Generated source tarball: ${TOPDIR}/SOURCES/${TARBALL}"
echo "Generated spec file:      ${SPEC_PATH}"

if [[ "$SKIP_BUILD" -eq 1 ]]; then
  echo "Skipped rpmbuild because --no-build was set."
  exit 0
fi

set +e
rpmbuild --define "_topdir ${TOPDIR}" -ba "$SPEC_PATH"
RPMBUILD_EXIT=$?
set -e

if [[ "$RPMBUILD_EXIT" -ne 0 ]]; then
  BUILDREQ_NOSRC="$(ls -1t "${TOPDIR}/SRPMS/"*.buildreqs.nosrc.rpm 2>/dev/null | head -n1 || true)"
  if [[ -n "$BUILDREQ_NOSRC" ]]; then
    echo ""
    echo "rpmbuild failed, likely due to missing dependency RPMs." >&2
    echo "Install generated build dependencies with:" >&2
    echo "  sudo dnf builddep -y ${BUILDREQ_NOSRC}" >&2
  fi
  exit "$RPMBUILD_EXIT"
fi

echo "Build complete. RPM files are under: ${TOPDIR}/RPMS and ${TOPDIR}/SRPMS"
