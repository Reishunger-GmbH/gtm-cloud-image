#!/usr/bin/env bash
# Export /app from the upstream GTM image and strip arch-specific node_modules
# so the embedded Dockerfile can rebuild native addons (re2) for the target platform.
set -euo pipefail

UPSTREAM_IMAGE="${UPSTREAM_IMAGE:-gcr.io/cloud-tagging-10302018/gtm-cloud-image}"
UPSTREAM_REF="${UPSTREAM_REF:-stable}"
CONTEXT_DIR="${CONTEXT_DIR:-./context}"

if [[ "${UPSTREAM_REF}" == sha256:* ]]; then
  IMAGE_REF="${UPSTREAM_IMAGE}@${UPSTREAM_REF}"
else
  IMAGE_REF="${UPSTREAM_IMAGE}:${UPSTREAM_REF}"
fi

echo "Pulling ${IMAGE_REF}"
docker pull "${IMAGE_REF}"

rm -rf "${CONTEXT_DIR}"
mkdir -p "${CONTEXT_DIR}"

cid="$(docker create "${IMAGE_REF}")"
cleanup() { docker rm -f "${cid}" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker cp "${cid}:/app/." "${CONTEXT_DIR}/"
rm -rf "${CONTEXT_DIR}/node_modules"

if [[ ! -f "${CONTEXT_DIR}/Dockerfile" ]]; then
  echo "error: upstream image has no /app/Dockerfile" >&2
  exit 1
fi

echo "Prepared build context at ${CONTEXT_DIR}"
ls -la "${CONTEXT_DIR}"
