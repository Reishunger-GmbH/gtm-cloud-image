# Multi-arch GTM cloud image

Unofficial multi-architecture rebuild of Google’s [server-side Tag Manager](https://developers.google.com/tag-platform/tag-manager/server-side/manual-setup-guide) image:

`gcr.io/cloud-tagging-10302018/gtm-cloud-image`

Google publishes **linux/amd64** only. This project rebuilds the same application for **linux/amd64** and **linux/arm64** (Apple Silicon, AWS Graviton, and other ARM hosts) and publishes it to GitHub Container Registry.

> **Not affiliated with Google.** Prefer the [official image](https://developers.google.com/tag-platform/tag-manager/server-side/manual-setup-guide) when you only need amd64. Review [upstream release notes](https://developers.google.com/tag-platform/tag-manager/server-side/release-notes) before upgrading major versions.

## Image

```bash
docker pull ghcr.io/reishunger-gmbh/gtm-cloud-image:stable
```

Package: [ghcr.io/reishunger-gmbh/gtm-cloud-image](https://github.com/Reishunger-GmbH/gtm-cloud-image/pkgs/container/gtm-cloud-image)

| Tag | Meaning |
| --- | --- |
| `stable` | Tracks upstream `:stable` |
| `latest` | Tracks upstream `:latest` |
| `4.4.0` (etc.) | Exact upstream version for that digest |

Sync watches **both** upstream `:stable` and `:latest`. When they share a digest (common today), one multi-arch rebuild inherits all tags on that digest. If they diverge, each changed digest is rebuilt separately and only the tags that point at that digest are updated — so a new major on `:latest` does not move `:stable`.

Semver tags stay available after floating tags move on. Images include a `gtm.upstream.digest` label pointing at the Google image they were built from.

Confirm platforms:

```bash
docker buildx imagetools inspect ghcr.io/reishunger-gmbh/gtm-cloud-image:stable
```

## Run

Same environment variables and behavior as Google’s image. Preview server:

```bash
docker run --rm -p 8080:8080 \
  -e CONTAINER_CONFIG='<config string>' \
  -e RUN_AS_PREVIEW_SERVER=true \
  ghcr.io/reishunger-gmbh/gtm-cloud-image:stable
```

Tagging server:

```bash
docker run --rm -p 8080:8080 \
  -e CONTAINER_CONFIG='<config string>' \
  -e PREVIEW_SERVER_URL='https://your-preview.example' \
  ghcr.io/reishunger-gmbh/gtm-cloud-image:stable
```

Get `<config string>` from Tag Manager → Server container → Admin → Container settings. Full options: [manual setup guide](https://developers.google.com/tag-platform/tag-manager/server-side/manual-setup-guide).

Smoke-test the binary:

```bash
docker run --rm ghcr.io/reishunger-gmbh/gtm-cloud-image:stable server_bin.js --help
```

## How the rebuild works

1. Export `/app` from the upstream image (including Google’s embedded Dockerfile).
2. Drop the prebuilt `node_modules` (amd64 natives such as `re2`).
3. Rebuild on native amd64 and arm64 runners so dependencies match each architecture.
4. Publish a multi-arch manifest with the upstream tags for that digest.

A GitHub Action checks upstream `:stable` and `:latest` daily and rebuilds only when either digest changes.

## Build locally

Quick check on your machine (repo `Dockerfile`; may lag upstream Node/distroless majors):

```bash
docker compose build
docker compose run --rm gtm
```

CI-parity build (uses the Dockerfile exported from upstream):

```bash
./scripts/prepare-context.sh
docker build -f context/Dockerfile -t gtm-cloud-image:local context
docker run --rm gtm-cloud-image:local server_bin.js --help
```

## License

Application code and dependencies come from Google’s published image and their respective licenses (see `LICENSE` inside the image). This repository’s automation and docs are provided as-is for rebuilding and distributing a multi-arch variant.
