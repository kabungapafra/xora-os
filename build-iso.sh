#!/usr/bin/env bash
# Turn the XORA OS image into a bootable installer ISO with bootc-image-builder.
# Needs root (sudo) because it builds disk images.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
IMAGE="${IMAGE:-localhost/xora-os:base}"   # the installer carries the base image; the toolkit downloads after installing
TYPE="${TYPE:-anaconda-iso}"      # anaconda-iso | qcow2 | raw
CONFIG="${CONFIG:-os/iso.toml}"   # os/iso-vm-test.toml = unattended install for a test VM
OUT="${OUT:-output}"
mkdir -p "$OUT" output-cache/store output-cache/rpmmd   # cache: a retry resumes downloads instead of starting over

# bootc-image-builder reads from root's container storage, so copy the image there
# (again whenever the rootless build is newer than root's copy).
SUDO="${SUDO:-sudo}"
MINE="$(podman image inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null || true)"
ROOTS="$($SUDO podman image inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null || true)"
if [ -z "$MINE" ] && [ -z "$ROOTS" ]; then
  echo "No $IMAGE found: build it first with ./build.sh" >&2; exit 1
fi
if [ -n "$MINE" ] && [ "$MINE" != "$ROOTS" ]; then
  echo "Copying $IMAGE into root's container storage…"
  podman save "$IMAGE" | $SUDO podman load
fi

# no interactive terminal flags: works from scripts and from prompts without a terminal
$SUDO podman run --rm --privileged --pull=newer \
  --security-opt label=type:unconfined_t \
  -v "./$OUT":/output \
  -v ./output-cache/store:/store -v ./output-cache/rpmmd:/rpmmd \
  -v "./$CONFIG":/config.toml:ro \
  -v /var/lib/containers/storage:/var/lib/containers/storage \
  quay.io/centos-bootc/bootc-image-builder:latest \
  --type "$TYPE" --rootfs btrfs --use-librepo=True \
  "$IMAGE"

$SUDO chown -R "$(id -u):$(id -g)" "$OUT"
echo
find "$OUT" -name '*.iso' -o -name '*.qcow2' -o -name '*.raw' | sed 's/^/Built: /'

# give the ISO XORA's own disc label and menu titles (the builder names it after the base system)
if [ "$TYPE" = anaconda-iso ] && [ -f "$OUT/bootiso/install.iso" ]; then
  name="$OUT/xora-os-${XORA_VERSION:-0.1}-$(uname -m).iso"
  if ./iso-relabel.sh "$OUT/bootiso/install.iso" "$name"; then
    rm -f "$OUT/bootiso/install.iso"
    (cd "$OUT" && sha256sum "$(basename "$name")" > "$(basename "$name").sha256")
  else
    echo "(relabel skipped: install xorriso, mtools and isomd5sum; the ISO still works with the base system's label)"
  fi
fi
