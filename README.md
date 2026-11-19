# MajorDom radio firmware

Firmware for the radios MajorDom drives (Silicon Labs EFR32 / ZGM230), published as GitHub Releases and a signed channel (`v1/stable.json`, `v1/dev.json`) on GitHub Pages. Binaries are release assets, never committed.

- `targets/<vendor>/<target>/target.toml`: a board's radio slots; host-wired boards also carry `board.json` (the host side the OS image installs).
- `packages/<family>-<kind>/package.toml`: one firmware per family and kind, released as `<package>-v<version>` with `.gbl`, `.meta.json`, `.cdx.json` (and `_full.s37` for source builds).
- `tools/`: `release_plan`, `build`, `meta`, `manifest_gen`, `publish_local`. `builder/`: the SiSDK build image (phase 2).

Releases start as pre-releases (dev channel); `gh release edit <tag> --prerelease=false` promotes one to stable.

Tests: `poetry install && poetry run pytest`.
