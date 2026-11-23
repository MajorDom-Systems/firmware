"""Verify a mirror package once, when adding or bumping it: download its upstream `.gbl`, check the sha256 and size pinned
in package.toml, and parse it. CI never downloads mirrors; the channel lists the upstream URL as is."""

import argparse
import hashlib
import urllib.request
from pathlib import Path

from tools.common import load_package
from tools.meta import parse_gbl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    package = load_package(parser.parse_args().package_dir)
    source = package.source
    with urllib.request.urlopen(source["url"], timeout=60) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if (digest, len(data)) != (source["sha256"], source["size"]):
        raise SystemExit(f"{package.name}: upstream has sha256 {digest}, {len(data)} bytes; package.toml pins "
                         f"{source['sha256']}, {source['size']} bytes")
    gbl = parse_gbl(data)
    print(f"{package.name} {package.version}: sha256 and size match, GBL app types {gbl.app_types}")


if __name__ == "__main__":
    main()
