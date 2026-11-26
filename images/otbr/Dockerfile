# OpenThread Border Router on a plain Thread RCP, with thread-source as an s6 service (see ../thread-source/run).
# Pinned: a moved :latest once shipped a broken RCP serial init (no wpan0). Bump on purpose.
#   docker buildx build --build-context thread-source=../thread-source --platform linux/arm64 .
FROM openthread/border-router@sha256:acc612303d3bd5aea28621ec8f3d2cc154cdc94c370398285dc828d08c5a5cf9
COPY --from=thread-source --chmod=755 run /etc/services.d/thread-source/run
