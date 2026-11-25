# MajorDom radio firmware

Firmware for the radios MajorDom drives (Silicon Labs EFR32 / ZGM230), published as GitHub Releases and a signed channel (`v1/stable.json`, `v1/dev.json`, `v1/boards.json`) on GitHub Pages. Binaries are release assets (mirrors: their upstream URL), never committed.

## Layout

- `boards/`: hardware manifests, consumed by the runtime / peripherals SDK. A `board.toml` has match rules and its radio slots. A slot describes only how the host is connected to it at hardware level (host pins `pins`: host UART device, GPIOs; flow-control wiring; reset GPIO; bootloader type and entry; flashers) plus the firmware it supports: `firmware = ["<package>", …]` and an optional `default = "<package>"`, the one pre-flashed (one of the list). Every board keeps explicit `[slots.<name>]` tables. Where one board has several slots, each may carry a free-text `label` telling them apart (`label = "EM357"` vs `label = "ZM5304"` on the HUSBZB-1), for display only; nothing depends on it. Single-slot boards get no label: their chip is noted in the comment at the top of the board.toml.
- `packages/`: firmware for a chip. A `package.toml` never names a board or slot (slots list packages, not the other way round). It names the chip it is built for, its `protocol`, baud/flow (`[serial]`), and where the binary comes from (`[source] type = "build"`, or a `url` mirror). Radio-chip pins (e.g. USART0 TX=PA04) are a build input under `[build.pins]`. Built packages are released as `<package>-v<version>` with `.gbl`, `.meta.json`, `.cdx.json`.
- `protocol` is the language the firmware speaks, in the integration SDK's `Need`/`Endpoint` protocol vocabulary: `ezsp` (Zigbee NCP), `spinel` (Thread RCP), `silabs-cpc` (multi-PAN RCP), `zwave-serial-api` (Z-Wave). The SDK picks the driver by it.
- CI checks every slot: each listed package exists, all target the same chip (the slot's chip is derived from them), `default` is in the list.
- `builder/<name>/`: a builder (see below).
- `tools/`: `release_plan`, `build`, `meta`, `board_json`, `manifest_gen`, `mirror`.

The runtime `board.json` (installed by the OS image at `/etc/majordom/board.json`) is generated from a board's slots and their default packages, never hand-written: `python3 -m tools.board_json majordom/proto-hub1-cm4-devkits/r1`. The site publishes it per public host-wired board at `v1/<board>/board.json`. Shape: `{"schema": 1, "board", "revision", "slots": [{"name", "path", "driver", "firmware"?, "params"}]}`. `driver` and `firmware` are the SDK's driver and firmware names for the default package's `protocol` (`tools/board_json.py` `DRIVERS`); the Hub passes them to the SDK's `FixedRadio` as they are. A slot without a default gets only `driver`, which identifies the running firmware; `params` carry baud/flow of the default package and the reset GPIO.

## Package naming

`<chip>-<app>[-<what makes it unique>]`, e.g. `mg26-multipan-pa04-pa05`: the chip without its family prefix (`EFR32MG26` → `mg26`), the app, then whatever distinguishes this build from others of the same chip and app. Here that is the radio-side UART pins; for another build it may be something else (a PA variant, a baud rate). Mirrors keep their upstream identity (`skyconnect-zigbee`, `skyconnect-thread`).

## Mirrors

A `url` package mirrors a third-party build without re-hosting it: its channel entry is generated from package.toml and points straight at the upstream URL with the pinned `sha256` and `size`; its version is the upstream version as is. Mirrors are never patch-bumped, built or released by CI; `[source] channel` (`dev` or `stable`) says where they are listed. CI never downloads them: verify a mirror once when adding or bumping it with `python3 -m tools.mirror packages/<name>`.

## Board naming

`boards/<vendor>/[proto-]<product><generation>-<platform>[-<wiring>]/r<N>`, e.g. `majordom/hub1-cm4/r1`, `majordom/hub1-cm3/r1`, `majordom/hub2-cm4/r1`, `majordom/proto-hub1-cm4-devkits/r1`.

- The generation is part of the product name; `r<N>` is the PCB revision. A new `r<N>` folder only when wiring or resets change; a `board.toml` may list the revisions it covers (`revisions = [1, 2]`).
- `proto-` marks dev-only setups. Proto boards stay off `boards.json`, and a package every listing board of which is `proto-` goes to the dev channel only.
- Third-party sticks keep their vendor id without `r<N>` (`nabucasa/skyconnect`, `sonoff/zbdongle-p`): their revisions are not ours to track; the USB match rules identify them.
- Only boards with shipped firmware or a manifest in use exist here; no placeholder folders.

## Builders

A `build` package declares `[build] builder = "<name>"` plus its inputs (project, config such as chip pins and CPC security, `[sdk] version`). `builder/<name>/` owns both the pinned toolchain image (`Dockerfile`) and the generic build steps (`build.py`); the package's SDK version parameterizes the image. CI builds the image with buildx and the Actions cache inside the release job and never pushes it. `silabs-sisdk` builds Simplicity SDK apps: `slc generate`, config edits, `make`, then a `.gbl` via pygbl.

## Releases

`boards.json` leaves out proto boards, and the packages only they list go to `dev.json` only, never `stable.json`. `index.html` lists everything; pre-releases, proto boards and the packages only they list are hidden until its "Show dev" checkbox is ticked (CSS only, no script).

Pushes to `develop` plan and build changed packages as a dry run (workflow artifacts). A dispatch of "Release packages" with `dry_run` unticked tags and publishes pre-releases (dev channel); `gh release edit <tag> --prerelease=false` promotes one to stable.

## Silicon Labs licensing

Silicon Labs firmware is under the Silicon Labs MSLA. The Simplicity SDK, its tools (slc-cli, Commander), Simplicity Studio and the builder image are never redistributed: CI only uses Silicon Labs' publicly downloadable tools to build. Compiled Silicon Labs firmware binaries are published as release assets for MajorDom and eligible hardware, as Nabu Casa does. See `NOTICE`.

Tests: `poetry install && poetry run pytest`.
