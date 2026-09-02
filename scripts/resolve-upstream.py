#!/usr/bin/env python3
"""Resolve upstream stable/latest digests and emit rebuild targets for CI."""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

UPSTREAM_REPO = "cloud-tagging-10302018/gtm-cloud-image"
TAGS_URL = f"https://gcr.io/v2/{UPSTREAM_REPO}/tags/list"
WATCH_TAGS = ("stable", "latest")

PLATFORMS = (
    {"platform": "linux/amd64", "runner": "ubuntu-24.04", "suffix": "amd64"},
    {"platform": "linux/arm64", "runner": "ubuntu-24.04-arm", "suffix": "arm64"},
)


def fetch_tags() -> dict:
    with urllib.request.urlopen(TAGS_URL, timeout=60) as resp:
        return json.load(resp)


def digest_for_tag(payload: dict, tag: str) -> str:
    for digest, meta in payload.get("manifest", {}).items():
        if tag in meta.get("tag", []):
            return digest
    raise SystemExit(f"tag not found in upstream registry: {tag}")


def tags_for_digest(payload: dict, digest: str) -> list[str]:
    meta = payload.get("manifest", {}).get(digest)
    if not meta:
        raise SystemExit(f"digest not found in upstream registry: {digest}")
    tags = sorted(set(meta.get("tag", [])))
    if not tags:
        raise SystemExit(f"no tags point at digest {digest}")
    return tags


def slug_for_digest(digest: str) -> str:
    raw = digest.removeprefix("sha256:")
    return raw[:12]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Include all watched digests even if already published",
    )
    parser.add_argument(
        "--published-stable",
        default="",
        help="gtm.upstream.digest label currently on GHCR :stable",
    )
    parser.add_argument(
        "--published-latest",
        default="",
        help="gtm.upstream.digest label currently on GHCR :latest",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Write key=value lines to $GITHUB_OUTPUT",
    )
    args = parser.parse_args()

    payload = fetch_tags()
    watch_digests = {tag: digest_for_tag(payload, tag) for tag in WATCH_TAGS}

    needed: set[str] = set()
    if args.force:
        needed.update(watch_digests.values())
    else:
        published = {
            "stable": args.published_stable.strip(),
            "latest": args.published_latest.strip(),
        }
        for tag, digest in watch_digests.items():
            if published[tag] != digest:
                needed.add(digest)

    targets: list[dict] = []
    for digest in sorted(needed):
        tags = tags_for_digest(payload, digest)
        targets.append(
            {
                "digest": digest,
                "slug": slug_for_digest(digest),
                "tags_csv": ",".join(tags),
                "ref": f"gcr.io/{UPSTREAM_REPO}@{digest}",
            }
        )

    build_matrix: list[dict] = []
    for target in targets:
        for platform in PLATFORMS:
            build_matrix.append({**target, **platform})

    result = {
        "should_build": bool(targets),
        "watch": watch_digests,
        "targets": targets,
        "build_matrix": build_matrix,
        "image": f"gcr.io/{UPSTREAM_REPO}",
    }
    print(json.dumps(result, indent=2))

    if args.github_output:
        out = os.environ.get("GITHUB_OUTPUT")
        if not out:
            raise SystemExit("GITHUB_OUTPUT is not set")
        # Empty matrix is invalid in GHA; use a placeholder when skipping.
        targets_json = json.dumps(targets)
        build_json = json.dumps(build_matrix)
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"should_build={'true' if targets else 'false'}\n")
            fh.write(f"stable_digest={watch_digests['stable']}\n")
            fh.write(f"latest_digest={watch_digests['latest']}\n")
            fh.write("targets<<EOF\n")
            fh.write(targets_json + "\n")
            fh.write("EOF\n")
            fh.write("build_matrix<<EOF\n")
            fh.write(build_json + "\n")
            fh.write("EOF\n")


if __name__ == "__main__":
    main()
