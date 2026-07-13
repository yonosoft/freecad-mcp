from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = REPOSITORY_ROOT / "src"


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


def test_package_metadata_uses_visible_workbench_name() -> None:
    root = ET.parse(ADDON_ROOT / "package.xml").getroot()
    namespace = {"pkg": "https://wiki.freecad.org/Package_Metadata"}

    assert root.findtext("pkg:name", namespaces=namespace) == "MCP"
    assert root.findtext("pkg:content/pkg:workbench/pkg:name", namespaces=namespace) == "MCP"


def test_package_metadata_declares_the_supported_mcp_sdk() -> None:
    root = ET.parse(ADDON_ROOT / "package.xml").getroot()
    namespace = {"pkg": "https://wiki.freecad.org/Package_Metadata"}

    dependencies = root.findall("pkg:depend", namespace)
    mcp_dependency = next(dependency for dependency in dependencies if dependency.text == "mcp")

    assert mcp_dependency.attrib == {
        "type": "python",
        "version_gte": "1.27.2",
        "version_lt": "2",
    }


def test_command_icons_are_valid_svg_files() -> None:
    for filename in (
        "mcp-start-server.svg",
        "mcp-stop-server.svg",
        "report-status.svg",
    ):
        icon = ADDON_ROOT / "Resources" / "icons" / filename
        root = ET.parse(icon).getroot()

        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert root.attrib["viewBox"] == "0 0 64 64"

    assert not (ADDON_ROOT / "Resources" / "icons" / "mcp-create-document.svg").exists()
