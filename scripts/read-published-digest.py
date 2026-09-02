#!/usr/bin/env python3
"""Read gtm.upstream.digest label from a GHCR (or other) image tag."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def request(
    url: str,
    *,
    token: str | None = None,
    basic: tuple[str, str] | None = None,
    accept: str | None = None,
    method: str = "GET",
) -> tuple[int, bytes, dict[str, str]]:
    headers: dict[str, str] = {}
    if accept:
        headers["Accept"] = accept
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif basic:
        user, password = basic
        raw = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {raw}"
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if exc.fp else b"", {k.lower(): v for k, v in exc.headers.items()}


def request_json(url: str, **kwargs) -> dict | list:
    status, body, _ = request(url, **kwargs)
    if status >= 400:
        raise urllib.error.HTTPError(url, status, body.decode("utf-8", "replace")[:300], hdrs=None, fp=None)
    return json.loads(body.decode())


def registry_bearer_token(host: str, path: str, github_token: str | None) -> str | None:
    """Exchange credentials for a registry bearer token (GHCR/GCR-compatible)."""
    if host == "ghcr.io":
        scope = f"repository:{path}:pull"
        url = f"https://ghcr.io/token?service=ghcr.io&scope={urllib.parse.quote(scope)}"
        if github_token:
            user = os.environ.get("GITHUB_ACTOR") or "x-access-token"
            status, body, _ = request(url, basic=(user, github_token), accept="application/json")
            if status < 400:
                token = json.loads(body.decode()).get("token")
                if token:
                    return token
            print(
                f"warning: authenticated GHCR token exchange failed ({status}); "
                "trying anonymous pull token",
                file=sys.stderr,
            )
        # Public packages can be pulled with an anonymous token.
        status, body, _ = request(url, accept="application/json")
        if status >= 400:
            raise SystemExit(
                f"GHCR token exchange failed ({status}): {body.decode('utf-8', 'replace')[:300]}"
            )
        token = json.loads(body.decode()).get("token")
        if not token:
            raise SystemExit("GHCR token exchange returned no token")
        return token

    return None


def fetch_config_labels(host: str, path: str, tag: str, token: str | None) -> dict[str, str]:
    manifest_url = f"https://{host}/v2/{path}/manifests/{tag}"
    status, body, _ = request(
        manifest_url,
        token=token,
        accept=(
            "application/vnd.oci.image.index.v1+json, "
            "application/vnd.docker.distribution.manifest.list.v2+json, "
            "application/vnd.oci.image.manifest.v1+json, "
            "application/vnd.docker.distribution.manifest.v2+json"
        ),
    )
    if status == 404:
        raise FileNotFoundError(f"tag not found: {host}/{path}:{tag}")
    if status >= 400:
        raise SystemExit(
            f"failed to read manifest {host}/{path}:{tag} ({status}): "
            f"{body.decode('utf-8', 'replace')[:300]}"
        )
    index = json.loads(body.decode())

    if index.get("manifests"):
        chosen = None
        for m in index["manifests"]:
            plat = m.get("platform") or {}
            if plat.get("os") == "linux" and plat.get("architecture") == "amd64":
                chosen = m["digest"]
                break
        if not chosen:
            chosen = index["manifests"][0]["digest"]
        status, body, _ = request(
            f"https://{host}/v2/{path}/manifests/{chosen}",
            token=token,
            accept=(
                "application/vnd.oci.image.manifest.v1+json, "
                "application/vnd.docker.distribution.manifest.v2+json"
            ),
        )
        if status >= 400:
            raise SystemExit(f"failed to read platform manifest {chosen} ({status})")
        manifest = json.loads(body.decode())
    else:
        manifest = index

    config_digest = manifest["config"]["digest"]
    # Use urllib opener that follows redirects; pass token only to registry host.
    status, body, _ = request(
        f"https://{host}/v2/{path}/blobs/{config_digest}",
        token=token,
        accept="application/vnd.docker.container.image.v1+json, application/vnd.oci.image.config.v1+json",
    )
    if status in (301, 302, 303, 307, 308):
        # Should be followed by urllib; if we get here as HTTPError path, fail clearly.
        raise SystemExit(f"blob redirect not followed for {config_digest} ({status})")
    if status >= 400:
        # Retry without Accept quirks via redirect-capable urlopen
        req = urllib.request.Request(
            f"https://{host}/v2/{path}/blobs/{config_digest}",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise SystemExit(
                f"failed to read config blob {config_digest} ({exc.code}): "
                f"{exc.read().decode('utf-8', 'replace')[:300]}"
            ) from exc
    config = json.loads(body.decode())
    return (config.get("config") or {}).get("Labels") or {}


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

    github_token = os.environ.get("REGISTRY_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if "/" not in args.image.replace("https://", ""):
        raise SystemExit("image must look like ghcr.io/owner/repo")
    host, path = args.image.split("/", 1)

    try:
        token = registry_bearer_token(host, path, github_token)
        labels = fetch_config_labels(host, path, args.tag, token)
    except FileNotFoundError as exc:
        print(f"{exc}; treating as unpublished", file=sys.stderr)
        digest = ""
        labels = {}
    else:
        digest = labels.get("gtm.upstream.digest", "")
        if not digest:
            print(
                f"warning: {args.image}:{args.tag} has no gtm.upstream.digest label",
                file=sys.stderr,
            )

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
