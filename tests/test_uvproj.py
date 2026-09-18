import xml.etree.ElementTree as ET
from pathlib import Path

from port_apply import UVPROJ_LEDC_FILES, ensure_uvproj_ledc


def _project_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<Project>
  <Targets>
    <Target>
      <Groups>
        <Group><GroupName>periph</GroupName><Files /></Group>
        <Group><GroupName>driver</GroupName><Files /></Group>
      </Groups>
    </Target>
  </Targets>
</Project>
"""


def _files_by_group(path: Path) -> dict[str, list[tuple[str, str]]]:
    root = ET.parse(path).getroot()
    result = {}
    for group in root.findall(".//Group"):
        name = group.findtext("GroupName")
        result[name] = [
            (item.findtext("FileName"), item.findtext("FilePath"))
            for item in group.findall("./Files/File")
        ]
    return result


def test_uvproj_ledc_xml_update_is_idempotent(tmp_path: Path):
    project = tmp_path / "SE71M.uvprojx"
    project.write_text(_project_xml(), encoding="utf-8")

    result = ensure_uvproj_ledc(str(project))

    assert result["ok"]
    assert result["added"] == [spec["name"] for spec in UVPROJ_LEDC_FILES]
    files = _files_by_group(project)
    assert ("ledc.c", r"..\periph\ledc.c") in files["periph"]
    assert ("ledc_mode.c", r"..\periph\ledc_mode.c") in files["periph"]
    assert ("drv_ledc.c", r"..\..\..\hal\driver\om6239\drv_ledc.c") in files["driver"]

    repeat = ensure_uvproj_ledc(str(project))

    assert repeat == {"ok": True, "message": "uvproj 已含 ledc 文件", "added": []}


def test_uvproj_rejects_same_filename_in_wrong_path(tmp_path: Path):
    project = tmp_path / "SE71M.uvprojx"
    project.write_text(
        _project_xml().replace("<Files />", "<Files><File><FileName>ledc.c</FileName><FileType>1</FileType><FilePath>bad.c</FilePath></File></Files>", 1),
        encoding="utf-8",
    )

    result = ensure_uvproj_ledc(str(project))

    assert not result["ok"]
    assert "路径不匹配" in result["message"]
