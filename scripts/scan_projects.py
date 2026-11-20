"""Scan all BYKC projects and produce the material-driven data assets.

Pipeline (see docs/PLAN-MATERIAL-DRIVEN.md, P1):
  1. discover firmware builds under E:/M_2026 and E:/history
  2. group by project number, choose the latest build per project
  3. scan source macros/polarity/params (source_scan.py)
  4. extract PcbDoc BOM models (pcbdoc_bom.py)
  5. write:
       omcfg/data/material_scan.json     - scanned material model -> raw contract (stats)
       docs/MATERIAL-STATS.md            - project-timeline statistics report
       omcfg/data/project_scan.json      - raw per-project records (debuggable)

Note: the curated selection contract omcfg/data/material_catalog.json (v2) is hand-tuned
       and consumed by omcfg/materials.py; the scanner never overwrites it.

Usage:
    python scripts/scan_projects.py                       # default roots
    python scripts/scan_projects.py --roots ROOT1 ROOT2   # custom
    python scripts/scan_projects.py --out-dir DIR         # override output dir
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pcbdoc_bom import extract_bom
from source_scan import choose_latest, find_builds, scan_build

__all__ = ["run"]

DEFAULT_ROOTS = ["E:/M_2026", "E:/history"]

# classify a model string into a material category
_CATEGORY_PATTERNS = [
    ("sensor", re.compile(
        r"\b(S203|S205|S201B|S202|KA8G2|KA8|KA5857|MX8650A|OM18|SG8912|3212|3075|3205|YS8008)\b",
        re.I,
    )),
    ("led_strip", re.compile(r"\b(WS2812|3528\s*ARGB|5050|2835|RGB\s*LED|ARGB)\b", re.I)),
    ("charger", re.compile(r"\b(4056H?|4057|DW4056|TP4056)\b", re.I)),
    ("ldo", re.compile(r"\b(6206|6205|1117|3V3|LDO)\b", re.I)),
    ("mcu", re.compile(r"\b(OM6239|OM6238|SE71M|STM32)\b", re.I)),
]

_KEY_PINS = ["P00", "P01", "P04", "P05", "P06", "P10", "P11", "P12", "P24", "P25", "P36"]


def _find_all(root: str) -> list[Path]:
    """Use find.exe via bash (portable across this Windows/git-bash env)."""
    out = subprocess.run(
        ["bash", "-c", f'find "{root}" -name user_config.h 2>/dev/null'],
        capture_output=True,
        text=True,
    ).stdout.strip()
    # user_config.h lives at <build>/projects/mouse_demo/periph/user_config.h -> 4 levels up
    return [Path(p).parent.parent.parent.parent for p in out.splitlines() if p]


def _pid_of(path: Path) -> str | None:
    text = str(path).replace("\\", "/")
    m = re.search(r"SE71M[_/]0*(\d{2,4})", text, re.I)
    if m:
        return m.group(1)
    # fall back to any 3-4 digit project number in a path component
    for part in text.split("/"):
        m = re.match(r"(\d{3,4})[-_]", part)
        if m:
            return m.group(1)
    return None


def _pcbdocs_for(root: str, pid: str) -> list[Path]:
    out = subprocess.run(
        ["bash", "-c", f'find "{root}" -iname "*.PcbDoc" 2>/dev/null'],
        capture_output=True,
        text=True,
    ).stdout.strip()
    docs = []
    for p in out.splitlines():
        if re.search(rf"(^|/|\\)0*{re.escape(pid)}[-_/]", p.replace("\\", "/")):
            docs.append(Path(p))
    return docs


def _classify_models(bom: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for desig, model in bom.items():
        for cat, pat in _CATEGORY_PATTERNS:
            if pat.search(model):
                out[cat].append(model)
                break
    return dict(out)


def _infer_material_params(records: list[dict]) -> dict:
    """Take mode (most common) values across projects as catalog defaults."""
    polarity = Counter()
    rgb_counts = Counter()
    ledc_on = 0
    wire = Counter()
    pair_present = 0
    encoders = Counter()
    for r in records:
        for v in r.get("polarity", {}).values():
            polarity[v] += 1
        n = r.get("ledc", {}).get("rgb_count")
        if n is not None:
            rgb_counts[n] += 1
        if r.get("ledc", {}).get("enabled"):
            ledc_on += 1
        if r.get("sensor", {}).get("wire"):
            wire[r["sensor"]["wire"]] += 1
        if r.get("mode", {}).get("pair_key"):
            pair_present += 1
        for pin in r.get("encoder", {}).values():
            encoders[pin] += 1

    return {
        "rgb_polarity_default": polarity.most_common(1)[0][0] if polarity else None,
        "rgb_polarity_distribution": dict(polarity),
        "rgb_count_default": rgb_counts.most_common(1)[0][0] if rgb_counts else None,
        "rgb_count_distribution": {str(k): v for k, v in rgb_counts.items()},
        "ledc_enabled_ratio": round(ledc_on / len(records), 3) if records else None,
        "sensor_wire_default": wire.most_common(1)[0][0] if wire else None,
        "sensor_wire_distribution": {str(k): v for k, v in wire.items()},
        "pair_key_present_ratio": round(pair_present / len(records), 3) if records else None,
        "encoder_pin_distribution": dict(encoders),
    }


def _build_catalog(records: list[dict], params: dict, generated: str) -> dict:
    """Build material_catalog.json - material model -> contract, same shape as plugins.json."""
    # sensor model -> wire count inferred from projects that support that model
    sensor_wire: dict[str, Counter] = defaultdict(Counter)
    sensor_din: dict[str, Counter] = defaultdict(Counter)
    strip_count: Counter = Counter()
    charger_count: Counter = Counter()
    for r in records:
        cats = r.get("bom_categories", {})
        w = r.get("sensor", {}).get("wire")
        for m in cats.get("sensor", []):
            if w:
                sensor_wire[m][w] += 1
        sdio = r.get("pins", {}).get("SENSOR_SDIO_PIN")
        if sdio:
            for m in cats.get("sensor", []):
                sensor_din[m][sdio] += 1
        for m in cats.get("led_strip", []):
            strip_count[m] += 1
        for m in cats.get("charger", []):
            charger_count[m] += 1

    def default(counter: Counter):
        return counter.most_common(1)[0][0] if counter else None

    catalog = {
        "schema": "om6239-material-catalog/v1",
        "generated_at": generated,
        "generated_from": "scripts/scan_projects.py over E:/M_2026 + E:/history",
        "note": (
            "物料型号 -> 角色/约束/板型默认。关键物料需选型号，普通物料用统计默认。"
            "此库供 P2 GUI 选料步骤驱动角色集合与插件开关。"
        ),
        "params_default": params,
        "materials": {},
    }
    for model, ctr in sorted(sensor_wire.items()):
        catalog["materials"][model] = {
            "category": "sensor",
            "wire": default(ctr),
            "wire_distribution": {str(k): v for k, v in ctr.items()},
            "din_pin_default": default(sensor_din.get(model, Counter())),
            "roles": ["SENSOR_SDIO_PIN"]
            + (["SENSOR_SCLK_PIN", "SENSOR_NCS_PIN", "SENSOR_MOSI_PIN", "SENSOR_MISO_PIN"]
               if default(ctr) == 4 else []),
            "note": "四线展开 SPI 四脚；两线只用 SDIO，影响 DPI 表与中断脚",
        }
    for model, cnt in sorted(strip_count.items(), key=lambda x: -x[1]):
        catalog["materials"][model] = {
            "category": "led_strip",
            "plugin": "ledc",
            "project_count": cnt,
            "roles": ["LEDC_PIN", "LEDC_CTRL_PIN"],
            "note": "选此型号等价于启用 LEDC 插件；不装灯带则无 LEDC 需求",
        }
    for model, cnt in sorted(charger_count.items(), key=lambda x: -x[1]):
        catalog["materials"][model] = {
            "category": "charger",
            "project_count": cnt,
            "roles": ["BAT_CHG_PIN"],
            "note": "充电管理型号决定充电检测脚与充电指示逻辑",
        }
    catalog["materials"]["__rgb__"] = {
        "category": "rgb",
        "count_default": params.get("rgb_count_default"),
        "polarity_default": params.get("rgb_polarity_default"),
        "note": "数量与极性（低电平点亮=另一端接 VCC）由原理图判断，选料后可覆盖默认值",
    }
    return catalog


def _render_stats(records: list[dict], params: dict, catalog: dict, generated: str) -> str:
    lines = [
        "# BYKC 项目物料统计报告",
        "",
        f"> 由 `scripts/scan_projects.py` 自动生成于 {generated}。",
        "> 数据源：`E:/M_2026` + `E:/history` firmware source + PcbDoc BOM。",
        "> 时间线主键：项目编号（同一项目多版本取最新 V/date）。",
        "",
        "## 1. 覆盖率",
        "",
        f"- 扫描到固件构建目录：{sum(1 for _ in find_builds('E:/M_2026')) + sum(1 for _ in find_builds('E:/history'))}",
        f"- 归一到项目号（每项目取最新构建）：**{len(records)}**",
        f"- 含 PcbDoc BOM 的项目：{sum(1 for r in records if r.get('bom'))}",
        "",
        "## 2. 关键参数分布（按项目）",
        "",
        "| 参数 | 取值分布 | 默认(众数) |",
        "|---|---|---|",
        f"| RGB 极性 | {params['rgb_polarity_distribution']} | {params['rgb_polarity_default']} |",
        f"| RGB 数量 | {params['rgb_count_distribution']} | {params['rgb_count_default']} |",
        f"| LEDC 启用率 | {params['ledc_enabled_ratio']} | - |",
        f"| 光电两线/四线 | {params['sensor_wire_distribution']} | {params['sensor_wire_default']} |",
        f"| pair/mode 键存在率 | {params['pair_key_present_ratio']} | - |",
        "",
        "## 3. 项目时间线（按编号）",
        "",
        "| 项目号 | 构建 | LEDC | RGB数 | 极性 | 光电线数 | 编码器 A/B | pair键 | BOM 关键物料 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        bom_brief = ", ".join(
            f"{m}" for m in sorted(set(
                x for v in r.get("bom_categories", {}).values() for x in v
            ))
        ) or "-"
        enc = r.get("encoder", {})
        enc_brief = "/".join(
            enc.get(k, "-") for k in ("WHEEL_A_PIN", "WHEEL_B_PIN")
        ) or "-"
        pol = "/".join(sorted(set(r.get("polarity", {}).values()))) or "-"
        lines.append(
            f"| {r['pid']} | {r['build_dir'].split('/')[-1]} | "
            f"{'是' if r['ledc']['enabled'] else '否'} | {r['ledc']['rgb_count'] or '-'} | "
            f"{pol} | {r['sensor']['wire'] or '-'} | {enc_brief} | "
            f"{r['mode']['pair_key'] or '-'} | {bom_brief} |"
        )
    lines += [
        "",
        "## 4. 物料型号频次（BOM 提取）",
        "",
        "| 类别 | 型号 | 项目数 | 推导默认 |",
        "|---|---|---|---|",
    ]
    for name, mat in sorted(catalog["materials"].items(), key=lambda x: (x[1]["category"], x[0])):
        if name.startswith("__"):
            continue
        pc = mat.get("project_count")
        if pc is None:
            ctr = mat.get("wire_distribution") or {}
            pc = sum(ctr.values())
        default_val = mat.get("wire") or mat.get("din_pin_default") or "-"
        lines.append(f"| {mat['category']} | {name} | {pc} | wire/pin={default_val} |")
    lines += [
        "",
        "## 5. 关键脚位占用（pins -> 出现项目数）",
        "",
        "| 脚 | 占用宏分布 |",
        "|---|---|",
    ]
    for p in _KEY_PINS:
        ctr: Counter = Counter()
        for r in records:
            for mac, pin in r.get("pins", {}).items():
                if pin == p:
                    ctr[mac] += 1
        lines.append(f"| {p} | {dict(ctr.most_common(5)) or '-'} |")
    lines += [
        "",
        "## 6. 已知偏差（需人工确认）",
        "",
        "- S205(512) 源码中 P00 定义为 `USB_5V`（`LED_CHG_PIN` 注释掉），用户口述“充电指示灯 P00”，"
        "待查原理图确认是否复用；源码极性为低电平点亮（接 VCC），与用户陈述一致。",
        "- 传感器型号是运行时按 PID 探测（sensor_type_check.c），源码枚举列出全部支持型号，"
        "并不代表该项目实际焊接型号；wire 线数由宏（NCS/SCLK 是否存在）判断更可靠。",
        "",
    ]
    return "\n".join(lines)


def run(roots: list[str], out_dir: Path) -> dict:
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    builds_by_pid: dict[str, list[Path]] = defaultdict(list)
    for root in roots:
        for b in _find_all(root):
            pid = _pid_of(b)
            if pid:
                builds_by_pid[pid].append(b)

    records: list[dict] = []
    for pid in sorted(builds_by_pid, key=lambda x: int(x)):
        latest = choose_latest(builds_by_pid[pid])
        if not latest:
            continue
        rec = scan_build(latest)
        rec["pid"] = pid

        bom: dict[str, str] = {}
        for root in roots:
            for doc in _pcbdocs_for(root, pid):
                bom.update(extract_bom(doc))
                rec.setdefault("pcbdocs", []).append(str(doc).replace("\\", "/"))
        rec["bom"] = bom
        rec["bom_categories"] = _classify_models(bom)
        records.append(rec)

    params = _infer_material_params(records)
    catalog = _build_catalog(records, params, stamp)

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "omcfg/data/project_scan.json"
    # 扫描产物（原始统计契约）单独存放，不覆盖经人工校准的选料契约 material_catalog.json/v2。
    scan_catalog_path = out_dir / "omcfg/data/material_scan.json"
    stats_path = out_dir / "docs/MATERIAL-STATS.md"

    for p in (raw_path, scan_catalog_path):
        p.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps({"generated_at": stamp, "projects": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    scan_catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(_render_stats(records, params, catalog, stamp), encoding="utf-8")

    return {
        "projects": len(records),
        "with_bom": sum(1 for r in records if r.get("bom")),
        "materials": len(catalog["materials"]),
        "outputs": [str(raw_path), str(scan_catalog_path), str(stats_path)],
        "params": params,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--roots", nargs="+", default=DEFAULT_ROOTS)
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args()
    result = run(args.roots, Path(args.out_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
