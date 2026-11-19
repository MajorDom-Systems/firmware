# Firmware builder: slc-cli + Simplicity Commander + Arm GCC + a pinned Simplicity SDK, Linux x86_64.
# Pushed to ghcr.io/majordom-systems/firmware-builder:sisdk-<SISDK_VERSION> by .github/workflows/builder.yml.
# Phase 2: not built or exercised yet. Silicon Labs serves slc-cli and Commander from unversioned URLs, so pin
# their sha256 (build args) once a known-good download is mirrored; until then the image is not reproducible.
FROM ubuntu:24.04

ARG SISDK_VERSION=v2025.6.3
ARG GCC_VERSION=12.2.rel1
ARG SLC_CLI_URL=https://www.silabs.com/documents/public/software/slc_cli_linux.zip
ARG SLC_CLI_SHA256=
ARG COMMANDER_URL=https://www.silabs.com/documents/public/software/SimplicityCommander-Linux.zip
ARG COMMANDER_SHA256=

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates curl git git-lfs make openjdk-21-jre-headless python3 unzip xz-utils libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

RUN curl -fsSL "https://developer.arm.com/-/media/Files/downloads/gnu/${GCC_VERSION}/binrel/arm-gnu-toolchain-${GCC_VERSION}-x86_64-arm-none-eabi.tar.xz" \
        | tar -xJ && mv "arm-gnu-toolchain-${GCC_VERSION}-x86_64-arm-none-eabi" gcc-arm

RUN curl -fsSLo slc.zip "$SLC_CLI_URL" \
    && { [ -z "$SLC_CLI_SHA256" ] || echo "$SLC_CLI_SHA256  slc.zip" | sha256sum -c; } \
    && unzip -q slc.zip && rm slc.zip

RUN curl -fsSLo commander.zip "$COMMANDER_URL" \
    && { [ -z "$COMMANDER_SHA256" ] || echo "$COMMANDER_SHA256  commander.zip" | sha256sum -c; } \
    && unzip -q commander.zip -d commander-dist && rm commander.zip \
    && tar -xjf commander-dist/*/Commander-cli_linux_x86_64_*.tar.bz2 && rm -rf commander-dist

RUN git clone --depth 1 --branch "$SISDK_VERSION" https://github.com/SiliconLabs/simplicity_sdk.git sisdk \
    && cd sisdk && git lfs pull

ENV PATH="/opt/gcc-arm/bin:/opt/slc_cli:/opt/commander-cli:${PATH}" \
    ARM_GCC_DIR=/opt/gcc-arm \
    SISDK=/opt/sisdk

RUN slc configuration --sdk "$SISDK" --gcc-toolchain "$ARM_GCC_DIR" && slc signature trust --sdk "$SISDK"

WORKDIR /work
