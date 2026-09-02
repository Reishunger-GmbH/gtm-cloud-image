#!/usr/bin/env python3
"""Read gtm.upstream.digest label from a GHCR (or other) image tag."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def request_json(url: str, token: str | None, accept: str) -> dict | list:
    headers = {"Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        required=True,
        help="Image without tag, e.g. ghcr.io/owner/repo",
    )
    parser.add_argument("--tag", default="stable")
    parser.add_argument(
        "--output-key",
        default="published_digest",
        help="GitHub Actions output name (default: published_digest)",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Write the digest to $GITHUB_OUTPUT under --output-key",
    )
    args = parser.parse_args()

    token = os.environ.get("REGISTRY_TOKEN") or os.environ.get("GITHUB_TOKEN")
    # ghcr.io/owner/name -> host=ghcr.io, path=owner/name
    if "/" not in args.image.replace("https://", ""):
        raise SystemExit("image must look like ghcr.io/owner/repo")
    parts = args.image.split("/", 1)
    host, path = parts[0], parts[1]
    manifest_url = f"https://{host}/v2/{path}/manifests/{args.tag}"

    try:
        index = request_json(
            manifest_url,
            token,
            "application/vnd.oci.image.index.v1+json, "
            "application/vnd.docker.distribution.manifest.list.v2+json, "
            "application/vnd.oci.image.manifest.v1+json, "
            "application/vnd.docker.distribution.manifest.v2+json",
        )
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 401, 403):
            digest = ""
            print(f"manifest not readable ({exc.code}); treating as unpublished", file=sys.stderr)
            _emit(args, digest)
            return
        raise

    # Resolve a platform manifest to read config Labels
    if index.get("manifests"):
        # Prefer linux/amd64 config for labels
        chosen = None
        for m in index["manifests"]:
            plat = m.get("platform") or {}
            if plat.get("os") == "linux" and plat.get("architecture") == "amd64":
                chosen = m["digest"]
                break
        if not chosen:
            chosen = index["manifests"][0]["digest"]
        manifest = request_json(
            f"https://{host}/v2/{path}/manifests/{chosen}",
            token,
            "application/vnd.oci.image.manifest.v1+json, "
            "application/vnd.docker.distribution.manifest.v2+json",
        )
    else:
        manifest = index

    config_digest = manifest["config"]["digest"]
    config_url = f"https://{host}/v2/{path}/blobs/{config_digest}"
    config = request_json(config_url, token, "application/vnd.docker.container.image.v1+json")
    labels = (config.get("config") or {}).get("Labels") or {}
    digest = labels.get("gtm.upstream.digest", "")
    print(json.dumps({"published_digest": digest, "labels": labels}, indent=2))
    _emit(args, digest)


def _emit(args: argparse.Namespace, digest: str) -> None:
    if not args.github_output:
        return
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        raise SystemExit("GITHUB_OUTPUT is not set")
    key = args.output_key
    if not key.replace("_", "").isalnum():
        raise SystemExit(f"invalid output key: {key}")
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(f"{key}={digest}\n")


if __name__ == "__main__":
    main()
