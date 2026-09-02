# Local/dev rebuild of Google's GTM cloud image for the current platform.
# CI prefers exporting /app from upstream and building that embedded Dockerfile
# directly (see scripts/prepare-context.sh) so Node/distroless majors track upstream.
#
# Usage:
#   docker build -t gtm-cloud-image:local .
#   docker buildx build --platform linux/amd64,linux/arm64 -t gtm-cloud-image:local .

ARG UPSTREAM_TAG=stable
FROM gcr.io/cloud-tagging-10302018/gtm-cloud-image:${UPSTREAM_TAG} AS upstream

FROM node:26 AS build-env
COPY --from=upstream /app/package.json /app/package-lock.json /app/
COPY --from=upstream /app/server_bin.js /app/health_checker_bin.js /app/
COPY --from=upstream /app/public_suffix_list.json /app/LICENSE /app/
WORKDIR /app/
RUN npm --unsafe-perm install

# Mirror upstream license redistribution of glibc sources into /third_party.
RUN mkdir /third_party && \
    TEMP_FILE=$(mktemp) && \
    curl http://ftp.gnu.org/gnu/glibc/glibc-2.41.tar.gz --output "$TEMP_FILE" && \
    echo "c7be6e25eeaf4b956f5d4d56a04d23e4db453fc07760f872903bb61a49519b80 ${TEMP_FILE}" \
        | sha256sum --check --status && \
    tar -xz -C /third_party -f "${TEMP_FILE}" && \
    rm -f "${TEMP_FILE}"

FROM gcr.io/distroless/nodejs24-debian13:latest
COPY --from=build-env /app/ /app/
COPY --from=build-env /third_party/ /third_party/
HEALTHCHECK CMD ["/nodejs/bin/node", "/app/health_checker_bin.js"]
WORKDIR /app/
CMD ["server_bin.js"]
