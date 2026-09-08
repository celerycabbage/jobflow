"""Fail CI when JobFlow component versions drift apart."""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_versions() -> dict[str, str]:
    backend = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    extension = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    desktop = ET.parse(ROOT / "desktop" / "JobFlow.Desktop" / "JobFlow.Desktop.csproj")
    desktop_version = desktop.findtext(".//Version")
    main_source = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    api_match = re.search(r'FastAPI\([^\n]*version="([^"]+)"', main_source)
    if desktop_version is None or api_match is None:
        raise RuntimeError("Could not read every component version")
    return {
        "backend package": backend["project"]["version"],
        "backend API": api_match.group(1),
        "frontend": frontend["version"],
        "extension": extension["version"],
        "desktop": desktop_version,
    }


versions = read_versions()
if len(set(versions.values())) != 1:
    details = ", ".join(f"{name}={version}" for name, version in versions.items())
    raise SystemExit(f"JobFlow versions do not match: {details}")
print(f"JobFlow version {next(iter(versions.values()))} is consistent across all components")
