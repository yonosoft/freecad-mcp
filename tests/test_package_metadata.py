from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = REPOSITORY_ROOT / "src" / "FreeCADMCP"


def test_package_metadata_references_existing_files() -> None:
    root = ET.parse(ADDON_ROOT / "package.xml").getroot()
    namespace = {"pkg": "https://wiki.freecad.org/Package_Metadata"}

    icon = root.findtext("pkg:icon", namespaces=namespace)
    license_element = root.find("pkg:license", namespace)

    assert icon
    assert (ADDON_ROOT / icon).is_file()
    assert license_element is not None
    assert license_element.attrib["file"] == "LICENSE"
    assert (ADDON_ROOT / license_element.attrib["file"]).is_file()


def test_addon_and_repository_licenses_match() -> None:
    assert (ADDON_ROOT / "LICENSE").read_bytes() == (REPOSITORY_ROOT / "LICENSE").read_bytes()
