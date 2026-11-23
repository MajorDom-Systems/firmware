# Builder `silabs-sisdk`: the pinned environment for Simplicity SDK firmware; build.py (the steps) runs inside it.
# Built in CI only (.github/workflows/release.yml), never pushed: it bundles Silicon Labs tools, which are not ours to
# redistribute. Every download is Silicon Labs' or Arm's own public, versioned URL, pinned by sha256.
# The package's `[sdk] version` selects the SDK (build arg SISDK_VERSION, commit pinned in sdk-commits).
FROM ubuntu:24.04

ARG SISDK_VERSION
ARG GCC_VERSION=12.2.rel1
ARG GCC_SHA256=84be93d0f9e96a15addd490b6e237f588c641c8afdf90e7610a628007fc96867
ARG SILABS=https://updates.silabs.com/studio/v6/updates/update_site/archives

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates curl git git-lfs libarchive-tools libglib2.0-0 make python3 python3-pip xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --break-system-packages pygbl==1.2.0 pyelftools==0.32

# Arm GNU toolchain (the version the SDK release notes name).
RUN mkdir -p /opt/gcc-arm \
    && curl -fsSLo gcc.tar.xz "https://developer.arm.com/-/media/Files/downloads/gnu/${GCC_VERSION}/binrel/arm-gnu-toolchain-${GCC_VERSION}-x86_64-arm-none-eabi.tar.xz" \
    && echo "${GCC_SHA256}  gcc.tar.xz" | sha256sum -c \
    && bsdtar -xf gcc.tar.xz --strip-components=1 -C /opt/gcc-arm && rm gcc.tar.xz

# slc-cli, ZAP, a JRE and the Python slc runs the SDK's generators with (found as adapter packs, not on PATH).
RUN set -eux; mkdir -p /opt/silabs/slc-cli /opt/silabs/zap /opt/silabs/java21 /opt/silabs/python; \
    fetch() { curl -fsSLo "$1" "$SILABS/$3" && echo "$2  $1" | sha256sum -c; }; \
    fetch python.zip 26f56b1cfa05b2b3b7dafb2c2a5e3c19498389c34dfe68be800f71f476c86363 python/3.10.3/python.3.10.3.gtk.linux.x86_64.zip; \
    fetch slc.zip f05e078b369d7e7dbfa31bdd2ad8edf61f04a9291393deab4702137639ba7d19 slc-cli/6.0.22/slc-cli.linux.gtk.x86_64.zip; \
    fetch zap.zip 45537226973fb892894f7110288dd4a7db627728af8cd9fc7c27b658530e2b88 zap/2026.06.17/zap-linux-x64.zip; \
    fetch jre.zip 5382fa98bcc66fc3aef48792a3e84328eca16afa9bf97517527e92812516ee50 java21/21.0.6/linux.x86_64_21.0.6.zip; \
    bsdtar -xf python.zip --strip-components=1 -C /opt/silabs/python; \
    bsdtar -xf slc.zip --strip-components=1 -C /opt/silabs/slc-cli; \
    bsdtar -xf zap.zip -C /opt/silabs/zap; \
    bsdtar -xf jre.zip --strip-components=1 -C /opt/silabs/java21; \
    rm python.zip slc.zip zap.zip jre.zip; \
    mkdir -p /opt/silabs/bin; \
    ln -s /opt/silabs/java21/jre/bin/java /opt/silabs/bin/java; \
    ln -s /opt/silabs/zap/zap /opt/silabs/bin/zap; \
    printf '#!/bin/sh\nexec /opt/silabs/slc-cli/slc "$@"\n' > /opt/silabs/bin/slc && chmod +x /opt/silabs/bin/slc

# Simplicity SDK at the pinned commit; its prebuilt stack libraries are Git LFS objects.
COPY sdk-commits /opt/sdk-commits
RUN set -eux; commit=$(awk -v v="$SISDK_VERSION" '$1 == v {print $2}' /opt/sdk-commits); test -n "$commit"; \
    git clone -q --depth 1 --branch "v${SISDK_VERSION}" https://github.com/SiliconLabs/simplicity_sdk /opt/sisdk; \
    cd /opt/sisdk; test "$(git rev-parse HEAD)" = "$commit"; \
    git lfs install --local; git lfs pull -I "**/*.a"; rm -rf .git

ENV PATH="/opt/gcc-arm/bin:/opt/silabs/bin:${PATH}" \
    ARM_GCC_DIR=/opt/gcc-arm \
    ARM_GCC_DIR_LINUX=/opt/gcc-arm \
    SISDK=/opt/sisdk \
    SISDK_VERSION=${SISDK_VERSION}

RUN slc signature trust --sdk "$SISDK"

COPY build.py /opt/builder/build.py
WORKDIR /repo
ENTRYPOINT ["python3", "/opt/builder/build.py"]
