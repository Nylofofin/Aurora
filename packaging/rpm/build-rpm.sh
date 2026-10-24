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
git -C "$ROOT" archive "$SOURCE_COMMIT" -- launchpad packaging/rpm/aurora-launchpad.spec | tar -x -C "$SOURCE_TREE"
VERSION="$(awk '/^Version:/ {print $2; exit}' "$SOURCE_TREE/packaging/rpm/aurora-launchpad.spec")"
PKG="$WORK/aurora-launchpad-$VERSION"
mkdir -p "$PKG/launchpad" "$PKG/payload" "$ROOT/dist"

for file in aurora-launchpad aurora_launchpad.py aurora_launchpad_core.py aurora-launchpad.desktop; do
  cp "$SOURCE_TREE/launchpad/$file" "$PKG/launchpad/"
done
cp -a "$SOURCE_TREE/launchpad/icons" "$PKG/launchpad/"

git -C "$ROOT" archive "$SOURCE_COMMIT" -- \
  aurora.py aurora_core aurora_fx.py aurora_integrations.py aurora-settings.json \
  orb.qml requirements.txt requirements-voice.txt run.sh start-alpha.sh \
  install-service.sh install-desktop.sh setup-voice.sh uninstall-service.sh \
  aurora.desktop README.md LICENSE assets/audio | tar -x -C "$PKG/payload"
printf 'source_ref=%s\nsource_commit=%s\nbuild_utc=%s\n' \
  "$SOURCE_REF" "$SOURCE_COMMIT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  > "$PKG/payload/BUILDINFO.txt"

tar -C "$WORK" -czf "$WORK/aurora-launchpad-$VERSION.tar.gz" "aurora-launchpad-$VERSION"
TOPDIR="$WORK/rpmbuild"
mkdir -p "$TOPDIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
cp "$WORK/aurora-launchpad-$VERSION.tar.gz" "$TOPDIR/SOURCES/"
rpmbuild -bb --define "_topdir $TOPDIR" "$SOURCE_TREE/packaging/rpm/aurora-launchpad.spec"
cp "$TOPDIR/RPMS/noarch/aurora-launchpad-$VERSION-"*.noarch.rpm "$ROOT/dist/"
(cd "$ROOT/dist" && sha256sum aurora-launchpad-*.rpm > SHA256SUMS)
ls -lh "$ROOT"/dist/aurora-launchpad-*.rpm "$ROOT/dist/SHA256SUMS"
