#!/usr/bin/env bash
# Build the XORA OS image (rootless podman is fine).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
FEDORA_VERSION="${FEDORA_VERSION:-44}"
IMAGE="${IMAGE:-localhost/xora-os:latest}"
# where installed machines take updates from: the public image GitHub builds for this repository
# (ghcr.io/<owner>/xora-os:latest). A machine installed from an ISO made here switches to it on first
# boot, so it gets every update pushed to GitHub. Override with XORA_IMAGE=... for a private registry.
if [ -z "${XORA_IMAGE:-}" ]; then
  owner="$(git remote get-url origin 2>/dev/null | sed -nE 's#.*github\.com[:/]([^/]+)/.*#\1#p' | tr '[:upper:]' '[:lower:]')"
  XORA_IMAGE="${owner:+ghcr.io/$owner/xora-os:latest}"
  XORA_IMAGE="${XORA_IMAGE:-$IMAGE}"
fi
echo "Installed machines will take updates from: $XORA_IMAGE"
# two images from one build: base (what the installer USB carries: a fast install) and full = base + the
# toolkit (what installed machines run and update to). The second build reuses every base layer.
for target in base full; do
  tag="$IMAGE"; [ "$target" = base ] && tag="${IMAGE%:*}:base"
  podman build \
    --build-arg FEDORA_VERSION="$FEDORA_VERSION" \
    --build-arg XORA_IMAGE="$XORA_IMAGE" \
    --target "$target" \
    -f os/Containerfile \
    -t "$tag" \
    --build-context cli=cli \
    os/
  echo "Built $tag ($target)"
done
echo
echo "Next: ./build-iso.sh   (makes a bootable installer ISO)"
