#!/usr/bin/env bash
# Build the XORA OS image (rootless podman is fine).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
FEDORA_VERSION="${FEDORA_VERSION:-44}"
IMAGE="${IMAGE:-localhost/xora-os:latest}"
# where installed machines take updates from (the GitHub build sets ghcr.io/<owner>/xora-os:latest)
XORA_IMAGE="${XORA_IMAGE:-$IMAGE}"
podman build \
  --build-arg FEDORA_VERSION="$FEDORA_VERSION" \
  --build-arg XORA_IMAGE="$XORA_IMAGE" \
  -f os/Containerfile \
  -t "$IMAGE" \
  --build-context cli=cli \
  os/
echo
echo "Built $IMAGE"
echo "Next: ./build-iso.sh   (makes a bootable installer ISO)"
