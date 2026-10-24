#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE_REF="${SOURCE_REF:-HEAD}"
WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT
SOURCE_COMMIT="$(git -C "$ROOT" rev-parse "$SOURCE_REF^{commit}")"
SOURCE_TREE="$WORK/source"
mkdir -p "$SOURCE_TREE"
git -C "$ROOT" archive "$SOURCE_COMMIT" -- launchpad packaging/rpm/aurora-launchpad.spec packaging/rpm/README.md LICENSE | tar -x -C "$SOURCE_TREE"
VERSION="$(awk '/^Version:/ {print $2; exit}' "$SOURCE_TREE/packaging/rpm/aurora-launchpad.spec")"
PKG="$WORK/aurora-launchpad-$VERSION"
mkdir -p "$PKG/launchpad" "$PKG/packaging/rpm" "$ROOT/dist"

for file in aurora-launchpad aurora_launchpad.py aurora_launchpad_core.py aurora-launchpad.desktop; do
  cp "$SOURCE_TREE/launchpad/$file" "$PKG/launchpad/"
done
cp -a "$SOURCE_TREE/launchpad/icons" "$PKG/launchpad/"
cp "$SOURCE_TREE/LICENSE" "$PKG/LICENSE"
cp "$SOURCE_TREE/packaging/rpm/README.md" "$PKG/packaging/rpm/README.md"

tar -C "$WORK" -czf "$WORK/aurora-launchpad-$VERSION.tar.gz" "aurora-launchpad-$VERSION"
TOPDIR="$WORK/rpmbuild"
mkdir -p "$TOPDIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
cp "$WORK/aurora-launchpad-$VERSION.tar.gz" "$TOPDIR/SOURCES/"
rpmbuild -bb --define "_topdir $TOPDIR" "$SOURCE_TREE/packaging/rpm/aurora-launchpad.spec"
RPM_FILES=("$TOPDIR"/RPMS/noarch/aurora-launchpad-"$VERSION"-*.noarch.rpm)
if [[ ${#RPM_FILES[@]} -ne 1 || ! -f "${RPM_FILES[0]}" ]]; then
  echo "Expected exactly one Launchpad RPM for version $VERSION." >&2
  exit 1
fi
RPM_NAME="$(basename "${RPM_FILES[0]}")"
cp "${RPM_FILES[0]}" "$ROOT/dist/$RPM_NAME"
(cd "$ROOT/dist" && sha256sum "$RPM_NAME" > SHA256SUMS)
ls -lh "$ROOT"/dist/aurora-launchpad-*.rpm "$ROOT/dist/SHA256SUMS"
