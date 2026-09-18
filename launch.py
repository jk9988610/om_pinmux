#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OM6239 PinMux — 独立无边框窗口（WebView2）

最大化贴工作区（不盖任务栏）；可拉伸；记住位置/大小。
支持：选择工程目录并写入 user_config.h / .c（标记块合并）。
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import sys
import threading
import traceback
from ctypes import wintypes
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
LOG = os.path.join(HERE, "launch.log")
STATE_PATH = os.path.join(HERE, "pinmux_state.json")

sys.path.insert(0, HERE)
try:
    import biz_sync
except ImportError:
    biz_sync = None  # type: ignore

try:
    import golden_diff
except ImportError:
    golden_diff = None  # type: ignore

try:
    import board_pack
except ImportError:
    board_pack = None  # type: ignore

try:
    import validation
except ImportError:
    validation = None  # type: ignore

BEGIN_H = "/* >>> OM_PINMUX_GENERATED begin */"
END_H = "/* <<< OM_PINMUX_GENERATED end */"
BEGIN_C = "/* >>> OM_PINMUX_GPIO_TABLE begin */"
END_C = "/* <<< OM_PINMUX_GPIO_TABLE end */"

DEFAULT_WIDTH = 1440
DEFAULT_HEIGHT = 900
MIN_WIDTH = 960
MIN_HEIGHT = 640

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
MONITOR_DEFAULTTONEAREST = 2
DWMWA_NCRENDERING_POLICY = 2
DWMNCRP_DISABLED = 1


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def load_session_state() -> dict:
    """上次选中的工程 / 板描述 / 窗口几何（本机会话，不进 git）。"""
    if not os.path.isfile(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_session_state(
    root: str = "",
    periph: str = "",
    board: str = "",
    window: dict | None = None,
    golden_root: str | None = None,
    compare_root: str | None = None,
    donor_root: str | None = None,
) -> None:
    prev = load_session_state()
    data = {
        "project_root": root if root else (prev.get("project_root") or ""),
        "periph": periph if periph else (prev.get("periph") or ""),
        "board": board if board else (prev.get("board") or ""),
        "golden_root": (
            golden_root if golden_root is not None else (prev.get("golden_root") or "")
        ),
        "compare_root": (
            compare_root if compare_root is not None else (prev.get("compare_root") or "")
        ),
        "donor_root": (
            donor_root if donor_root is not None else (prev.get("donor_root") or "")
        ),
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    if window is not None:
        data["window"] = window
    elif isinstance(prev.get("window"), dict):
        data["window"] = prev["window"]
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log(f"保存 pinmux_state.json 失败: {e}")


def try_restore_project(root_hint: str = "") -> tuple[str, str]:
    """返回 (project_root, periph)；路径失效则空。"""
    root = (root_hint or "").strip()
    if not root:
        st = load_session_state()
        root = (st.get("project_root") or "").strip()
    if not root or not os.path.isdir(root):
        return "", ""
    periph = find_periph_dir(root)
    if not periph:
        return "", ""
    return os.path.abspath(root), periph


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _user32():
    return ctypes.windll.user32


def get_hwnd(window) -> int | None:
    native = getattr(window, "native", None) if window else None
    if native is None:
        return None
    try:
        return int(native.Handle.ToInt32())
    except Exception:
        return None


def get_monitor_work_area(hwnd: int) -> tuple[int, int, int, int]:
    """返回工作区 (x, y, w, h)，不含任务栏。"""
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    hmon = _user32().MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not _user32().GetMonitorInfoW(hmon, ctypes.byref(mi)):
        # 回退：主屏工作区
        rc = RECT()
        _user32().SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0)  # SPI_GETWORKAREA
        return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top
    w = mi.rcWork.right - mi.rcWork.left
    h = mi.rcWork.bottom - mi.rcWork.top
    return mi.rcWork.left, mi.rcWork.top, w, h


def set_hwnd_bounds(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    _user32().SetWindowPos(
        hwnd,
        None,
        int(x),
        int(y),
        int(w),
        int(h),
        SWP_NOZORDER | SWP_SHOWWINDOW,
    )


def set_thick_frame(hwnd: int, enabled: bool) -> None:
    """最大化时关掉粗边框以免空隙；还原后再打开以便拖边。"""
    style = _user32().GetWindowLongW(hwnd, GWL_STYLE)
    if enabled:
        style |= WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX
    else:
        style &= ~WS_THICKFRAME
        style |= WS_MAXIMIZEBOX | WS_MINIMIZEBOX
    _user32().SetWindowLongW(hwnd, GWL_STYLE, style)
    _user32().SetWindowPos(
        hwnd,
        None,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
    )


def disable_dwm_nc_frame(hwnd: int) -> None:
    """关掉 DWM 非客户区渲染，避免顶栏白条/玻璃边。"""
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_NCRENDERING_POLICY,
            ctypes.byref(ctypes.c_int(DWMNCRP_DISABLED)),
            ctypes.sizeof(ctypes.c_int),
        )
        # 取消延伸到客户区的 1px 边框
        class _MARGINS(ctypes.Structure):
            _fields_ = [
                ("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int),
            ]

        m = _MARGINS(0, 0, 0, 0)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))
    except Exception as e:
        log(f"disable DWM frame: {e}")


def enable_frameless_resize(hwnd: int) -> None:
    """无边框可拉伸；并去掉 DWM 白边。"""
    disable_dwm_nc_frame(hwnd)
    set_thick_frame(hwnd, True)


def maximize_to_work_area(hwnd: int) -> None:
    """
    像普通窗口最大化一样铺满工作区（不盖任务栏）。
    有 WS_THICKFRAME 时外框需略超出工作区，客户区才贴齐。
    """
    set_thick_frame(hwnd, False)
    disable_dwm_nc_frame(hwnd)
    x, y, w, h = get_monitor_work_area(hwnd)
    # 无粗边框时直接贴齐工作区即可
    set_hwnd_bounds(hwnd, x, y, w, h)


def clamp_window_geom(x, y, w, h) -> tuple[int | None, int | None, int, int]:
    """保证窗口至少一部分落在某显示器工作区内；坐标无效则 x/y 为 None（由系统居中）。"""
    w = max(MIN_WIDTH, int(w or DEFAULT_WIDTH))
    h = max(MIN_HEIGHT, int(h or DEFAULT_HEIGHT))
    try:
        x = int(x)
        y = int(y)
    except (TypeError, ValueError):
        return None, None, w, h

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    for px, py in ((x + 40, y + 40), (x + w // 2, y + h // 2), (x, y)):
        pt = POINT(px, py)
        hmon = _user32().MonitorFromPoint(pt, 0)  # MONITOR_DEFAULTTONULL
        if hmon:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if _user32().GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return x, y, w, h

    rc = RECT()
    _user32().SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0)
    aw, ah = rc.right - rc.left, rc.bottom - rc.top
    nx = rc.left + max(0, (aw - w) // 2)
    ny = rc.top + max(0, (ah - h) // 2)
    return nx, ny, w, h


def load_window_geom(cli_w: int | None, cli_h: int | None) -> dict:
    st = load_session_state().get("window") or {}
    w = cli_w if cli_w and cli_w > 0 else int(st.get("width") or DEFAULT_WIDTH)
    h = cli_h if cli_h and cli_h > 0 else int(st.get("height") or DEFAULT_HEIGHT)
    x = st.get("x")
    y = st.get("y")
    maximized = bool(st.get("maximized"))
    cx, cy, cw, ch = clamp_window_geom(x, y, w, h)
    return {
        "x": cx,
        "y": cy,
        "width": cw,
        "height": ch,
        "maximized": maximized,
        "restore_x": st.get("restore_x", cx),
        "restore_y": st.get("restore_y", cy),
        "restore_width": st.get("restore_width", cw),
        "restore_height": st.get("restore_height", ch),
    }


def ensure_webview():
    """Verify the desktop dependency; installation is explicit and reproducible."""
    try:
        import webview  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "缺少 pywebview。请先执行: python -m pip install -r requirements.txt "
            "（或 python -m pip install -e .）"
        ) from exc


def find_periph_dir(root: str) -> str | None:
    """接受 SDK 根、mouse_demo、或 periph 目录。"""
    if not root or not os.path.isdir(root):
        return None
    root = os.path.abspath(root)
    candidates = [
        root,
        os.path.join(root, "periph"),
        os.path.join(root, "projects", "mouse_demo", "periph"),
        os.path.join(root, "mouse_demo", "periph"),
    ]
    for c in candidates:
        h = os.path.join(c, "user_config.h")
        if os.path.isfile(h):
            return c
    # 浅搜
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "out", "Objects", "Listings", "node_modules")]
        if "user_config.h" in filenames and os.path.basename(dirpath) == "periph":
            return dirpath
        if len(dirpath) - len(root) > 80:
            dirnames.clear()
    return None


def replace_marked_or_insert(text: str, begin: str, end: str, payload: str, fallback_anchor: str | None) -> str:
    block = f"{begin}\n{payload.rstrip()}\n{end}\n"
    if begin in text and end in text:
        return re.sub(
            re.escape(begin) + r"[\s\S]*?" + re.escape(end) + r"\n?",
            block,
            text,
            count=1,
        )
    if fallback_anchor and fallback_anchor in text:
        # 插在锚点之前
        return text.replace(fallback_anchor, block + "\n" + fallback_anchor, 1)
    return text.rstrip() + "\n\n" + block


def patch_project_id(text: str, meta: dict) -> str:
    def sub_def(src, name, value, quoted=False):
        if value is None or value == "":
            return src
        val = f'"{value}"' if quoted else str(value)
        pat = rf"(#define\s+{name}\s+)([^\n]+)"
        if re.search(pat, src):
            return re.sub(pat, rf"\g<1>{val}", src, count=1)
        return src

    text = sub_def(text, "iPROJECT_ID_H", meta.get("projIdH"))
    text = sub_def(text, "iPROJECT_ID_L", meta.get("projIdL"))
    text = sub_def(text, "iREAL_VERSION_ID", meta.get("verId"))
    text = sub_def(text, "iCONSUMER_NAME", meta.get("consumerName"), quoted=True)
    text = sub_def(text, "iPROJECT_NAME", meta.get("projName"), quoted=True)
    return text


class WindowApi:
    def __init__(self, start_maximized=False, geom: dict | None = None):
        self._win = None
        self._maximized = bool(start_maximized)
        self._project_root = ""
        self._periph = ""
        st0 = load_session_state()
        self._board = (st0.get("board") or "").strip()
        self._golden_root = (st0.get("golden_root") or "").strip()
        self._compare_root = (st0.get("compare_root") or "").strip()
        self._donor_root = (st0.get("donor_root") or "").strip()
        if golden_diff is not None and not self._compare_root:
            self._compare_root = golden_diff.find_compare_tool() or ""
        g = geom or {}
        self._restore = {
            "x": g.get("restore_x", g.get("x")),
            "y": g.get("restore_y", g.get("y")),
            "width": int(g.get("restore_width") or g.get("width") or DEFAULT_WIDTH),
            "height": int(g.get("restore_height") or g.get("height") or DEFAULT_HEIGHT),
        }
        self._save_timer: threading.Timer | None = None
        self._ignore_geom_events = False

    def bind(self, window):
        self._win = window

    def _persist(self, board: str | None = None, window: dict | None = None):
        if board is not None and board != "":
            self._board = board
        save_session_state(
            self._project_root,
            self._periph,
            self._board,
            window=window,
            golden_root=self._golden_root,
            compare_root=self._compare_root,
            donor_root=self._donor_root,
        )

    def _snapshot_window(self) -> dict:
        w = self._win
        if not w:
            return {}
        try:
            cur = {
                "x": int(w.x) if w.x is not None else self._restore.get("x"),
                "y": int(w.y) if w.y is not None else self._restore.get("y"),
                "width": int(w.width or self._restore["width"]),
                "height": int(w.height or self._restore["height"]),
                "maximized": bool(self._maximized),
                "restore_x": self._restore.get("x"),
                "restore_y": self._restore.get("y"),
                "restore_width": self._restore["width"],
                "restore_height": self._restore["height"],
            }
        except Exception:
            return {"maximized": bool(self._maximized)}
        if not self._maximized:
            self._restore = {
                "x": cur["x"],
                "y": cur["y"],
                "width": cur["width"],
                "height": cur["height"],
            }
            cur["restore_x"] = cur["x"]
            cur["restore_y"] = cur["y"]
            cur["restore_width"] = cur["width"]
            cur["restore_height"] = cur["height"]
        return cur

    def persist_window_now(self):
        self._persist(window=self._snapshot_window())

    def schedule_persist_window(self, delay=0.35):
        if self._ignore_geom_events:
            return

        def _flush():
            self._save_timer = None
            if not self._maximized:
                self.persist_window_now()

        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(delay, _flush)
        self._save_timer.daemon = True
        self._save_timer.start()

    def save_session(self, payload_json: str = ""):
        """前端记住当前板描述名等：{ board?: str }。"""
        try:
            data = json.loads(payload_json) if payload_json else {}
        except json.JSONDecodeError:
            data = {}
        board = (data.get("board") or "").strip()
        self._persist(board if board else None)
        return {
            "ok": True,
            "root": self._project_root,
            "periph": self._periph,
            "board": self._board,
        }

    def get_session(self):
        return {
            "ok": True,
            "root": self._project_root or "",
            "periph": self._periph or "",
            "board": self._board or "",
            "h": os.path.join(self._periph, "user_config.h") if self._periph else "",
            "c": os.path.join(self._periph, "user_config.c") if self._periph else "",
        }

    def _apply_workarea_maximize(self) -> bool:
        """贴当前显示器工作区最大化（不盖任务栏、无白边空隙）。"""
        hwnd = get_hwnd(self._win)
        form = getattr(self._win, "native", None)
        try:
            self._restore = {
                "x": int(self._win.x) if self._win.x is not None else 100,
                "y": int(self._win.y) if self._win.y is not None else 80,
                "width": int(self._win.width or DEFAULT_WIDTH),
                "height": int(self._win.height or DEFAULT_HEIGHT),
            }
            # 保持 Normal，仅把外框精确设为工作区（避免系统 Maximized 的边框/白条）
            if form is not None:
                try:
                    from System.Windows.Forms import FormWindowState

                    if form.WindowState != FormWindowState.Normal:
                        form.WindowState = FormWindowState.Normal
                except Exception:
                    pass
            if not hwnd:
                self._win.maximize()
                return True
            maximize_to_work_area(hwnd)
            return True
        except Exception as e:
            log(f"workarea maximize: {e}")
            return False

    def _apply_restore(self) -> bool:
        rx = self._restore.get("x")
        ry = self._restore.get("y")
        rw = int(self._restore.get("width") or DEFAULT_WIDTH)
        rh = int(self._restore.get("height") or DEFAULT_HEIGHT)
        cx, cy, cw, ch = clamp_window_geom(rx, ry, rw, rh)
        hwnd = get_hwnd(self._win)
        form = getattr(self._win, "native", None)
        try:
            if form is not None:
                try:
                    from System.Windows.Forms import FormWindowState

                    form.WindowState = FormWindowState.Normal
                except Exception:
                    pass
            else:
                try:
                    self._win.restore()
                except Exception:
                    pass
            if hwnd:
                set_thick_frame(hwnd, True)
                disable_dwm_nc_frame(hwnd)
            if cx is not None and cy is not None:
                self._win.move(cx, cy)
            self._win.resize(cw, ch)
            return True
        except Exception as e:
            log(f"restore: {e}")
            return False

    def toggle_maximize(self):
        """最大化（工作区）↔ 还原。"""
        if not self._win:
            return {"ok": False, "maximized": False}
        try:
            self._ignore_geom_events = True
            if self._maximized:
                ok = self._apply_restore()
                self._maximized = False
            else:
                ok = self._apply_workarea_maximize()
                self._maximized = True
            self.persist_window_now()
            return {"ok": ok, "maximized": self._maximized}
        except Exception as e:
            log(f"toggle_maximize: {e}")
            return {"ok": False, "maximized": self._maximized, "message": str(e)}
        finally:
            self._ignore_geom_events = False

    def get_maximize_state(self):
        return {"ok": True, "maximized": bool(self._maximized)}

    def minimize(self):
        if self._win:
            self._win.minimize()
            return True
        return False

    def close(self):
        if self._win:
            try:
                self.persist_window_now()
            except Exception:
                pass
            self._win.destroy()
            return True
        return False

    def get_project_info(self):
        return {
            "root": self._project_root or "",
            "periph": self._periph or "",
            "board": self._board or "",
            "golden_root": self._golden_root or "",
            "compare_root": self._compare_root or "",
            "donor_root": self._donor_root or "",
            "h": os.path.join(self._periph, "user_config.h") if self._periph else "",
            "c": os.path.join(self._periph, "user_config.c") if self._periph else "",
        }

    def pick_project_dir(self):
        """弹出目录选择；返回 {ok, root, periph, message}。成功则写入 pinmux_state.json。"""
        import webview

        if not self._win:
            return {"ok": False, "message": "窗口未就绪"}
        try:
            result = self._win.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception as e:
            log(f"FOLDER_DIALOG 失败: {e}")
            return {"ok": False, "message": str(e)}
        if not result:
            return {"ok": False, "message": "已取消"}
        root = result[0] if isinstance(result, (list, tuple)) else result
        periph = find_periph_dir(root)
        if not periph:
            return {
                "ok": False,
                "root": root,
                "message": "未找到 projects/mouse_demo/periph/user_config.h，请选 SDK 根目录或 mouse_demo / periph",
            }
        self._project_root = os.path.abspath(root)
        self._periph = periph
        self._persist()
        info = self.get_project_info()
        info["ok"] = True
        info["message"] = f"已绑定: {periph}"
        log(info["message"] + "（已记住，下次启动自动恢复）")
        return info

    def scan_biz_refs(self):
        """扫描 periph + main 中对脚位宏的引用。"""
        if not self._periph:
            return {"ok": False, "message": "请先选择工程目录"}
        if biz_sync is None:
            return {"ok": False, "message": "biz_sync 模块不可用"}
        try:
            result = biz_sync.scan_project_refs(self._periph)
            log(f"scan_biz_refs: {result.get('ref_count')} refs, issues={result.get('issues')}")
            return result
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    def scan_port_checklist(self, feat_json: str | dict | None = None):
        """换板体检：C/D/E 阶段常见缺口（LEDC/轮询/RTE/SEL≠滚轮等）。"""
        if not self._periph:
            return {"ok": False, "message": "请先选择工程目录"}
        if biz_sync is None:
            return {"ok": False, "message": "biz_sync 模块不可用"}
        try:
            feat = feat_json
            if isinstance(feat_json, str):
                feat = json.loads(feat_json) if feat_json.strip() else {}
            feat = feat or {}
            result = biz_sync.scan_port_checklist(self._periph, feat)
            log(f"scan_port_checklist: {result.get('summary')}")
            return result
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    def _resolve_target_sdk(self) -> str | None:
        if golden_diff is None:
            return None
        hint = self._project_root or self._periph
        if not hint:
            return None
        return golden_diff.find_sdk_root(hint)

    def pick_golden_dir(self):
        """选择金机/参照工程目录（如 CH04 SDK 根）。"""
        import webview

        if not self._win:
            return {"ok": False, "message": "窗口未就绪"}
        if golden_diff is None:
            return {"ok": False, "message": "golden_diff 模块不可用"}
        try:
            result = self._win.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception as e:
            log(f"FOLDER_DIALOG(golden) 失败: {e}")
            return {"ok": False, "message": str(e)}
        if not result:
            return {"ok": False, "message": "已取消"}
        path = result[0] if isinstance(result, (list, tuple)) else result
        sdk = golden_diff.find_sdk_root(path) or os.path.abspath(path)
        self._golden_root = sdk
        self._persist()
        log(f"金机目录: {sdk}")
        return {
            "ok": True,
            "golden_root": sdk,
            "message": f"金机(参照) = {sdk}",
        }

    def set_compare_root(self, path: str = ""):
        """手动指定 E:\\tools\\compare 根目录；空则自动探测。"""
        if golden_diff is None:
            return {"ok": False, "message": "golden_diff 模块不可用"}
        path = (path or "").strip()
        if path:
            if not os.path.isfile(os.path.join(path, "compare.py")):
                return {"ok": False, "message": f"目录无 compare.py: {path}"}
            self._compare_root = os.path.abspath(path)
        else:
            self._compare_root = golden_diff.find_compare_tool() or ""
        self._persist()
        return {
            "ok": bool(self._compare_root),
            "compare_root": self._compare_root,
            "message": (
                f"compare = {self._compare_root}"
                if self._compare_root
                else "未找到 compare 工具"
            ),
        }

    def inventory_golden(self):
        """关注文件清单：金机 vs 当前工程（不依赖 compare GUI）。"""
        if golden_diff is None:
            return {"ok": False, "message": "golden_diff 模块不可用"}
        if not self._golden_root:
            return {"ok": False, "message": "请先选金机目录"}
        target = self._resolve_target_sdk()
        if not target:
            return {"ok": False, "message": "请先选目标工程目录"}
        try:
            inv = golden_diff.inventory_focus(self._golden_root, target)
            inv["text"] = golden_diff.format_inventory_text(inv)
            log(inv.get("message", ""))
            return inv
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    def open_golden_compare(self):
        """打开 E:\\tools\\compare GUI：左=金机，右=目标。"""
        if golden_diff is None:
            return {"ok": False, "message": "golden_diff 模块不可用"}
        if not self._golden_root:
            return {"ok": False, "message": "请先选金机目录"}
        target = self._resolve_target_sdk()
        if not target:
            return {"ok": False, "message": "请先选目标工程目录"}
        try:
            r = golden_diff.open_compare_gui(
                self._golden_root, target, self._compare_root
            )
            if r.get("compare_root"):
                self._compare_root = r["compare_root"]
                self._persist()
            log(r.get("message", ""))
            return r
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    def export_golden_diff(self, out_path: str = ""):
        """导出全文 unified .diff（调用 compare.engine）；附带关注文件摘要。"""
        if golden_diff is None:
            return {"ok": False, "message": "golden_diff 模块不可用"}
        if not self._golden_root:
            return {"ok": False, "message": "请先选金机目录"}
        target = self._resolve_target_sdk()
        if not target:
            return {"ok": False, "message": "请先选目标工程目录"}
        out = (out_path or "").strip() or golden_diff.default_export_path(target)
        try:
            r = golden_diff.export_unified_diff(
                self._golden_root, target, out, self._compare_root
            )
            if r.get("ok") and r.get("inventory"):
                r["text"] = golden_diff.format_inventory_text(r["inventory"])
            log(r.get("message", ""))
            return r
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    def sync_biz_contracts(self, feat_json: str | dict | None = None):
        """按板型同步 key_io / sleep 契约（可单独调用）。"""
        if not self._periph:
            return {"ok": False, "message": "请先选择工程目录"}
        if biz_sync is None:
            return {"ok": False, "message": "biz_sync 模块不可用"}
        try:
            feat = feat_json
            if isinstance(feat_json, str):
                feat = json.loads(feat_json) if feat_json.strip() else {}
            feat = feat or {}
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak_dir = os.path.join(self._periph, f"_pinmux_bak_{stamp}")
            result = biz_sync.sync_board_contracts(self._periph, feat, bak_dir)
            result["backup"] = bak_dir if result.get("written") else ""
            log(f"sync_biz_contracts: {result}")
            return result
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    def write_user_config(self, payload_json: str):
        """
        payload: {
          pins_h: str,   # 脚位区（不含项目ID也可）
          gpio_c: str,   # gpio_config_table 整表
          meta: {projName, consumerName, projIdL, projIdH, verId},
          write_features: bool,
          features_h: str,
          write_sleep: bool,
          sleep_c: str,
          sync_biz: bool,          # 写入后同步 key_io / sleep 契约
          biz_features: dict       # has_key_pair / mode_dual / …
        }
        """
        try:
            data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
        except json.JSONDecodeError as e:
            return {"ok": False, "message": f"JSON 无效: {e}"}

        if not self._periph:
            return {"ok": False, "message": "请先选择工程目录"}

        h_path = os.path.join(self._periph, "user_config.h")
        c_path = os.path.join(self._periph, "user_config.c")
        if not os.path.isfile(h_path) or not os.path.isfile(c_path):
            return {"ok": False, "message": f"缺少 user_config.h/.c: {self._periph}"}

        pins_h = (data.get("pins_h") or "").strip()
        gpio_c = (data.get("gpio_c") or "").strip()
        meta = data.get("meta") or {}
        written = []
        biz_actions = []
        scan_preview = None

        try:
            # backup
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak_dir = os.path.join(self._periph, f"_pinmux_bak_{stamp}")
            os.makedirs(bak_dir, exist_ok=True)
            shutil.copy2(h_path, os.path.join(bak_dir, "user_config.h"))
            shutil.copy2(c_path, os.path.join(bak_dir, "user_config.c"))

            h_text = open(h_path, encoding="utf-8", errors="replace").read()
            # 去掉生成块里的项目 ID 行，改用 patch_project_id 改原文件宏
            pins_only = re.sub(r"^#define\s+i(PROJECT_ID_[HL]|REAL_VERSION_ID|CONSUMER_NAME|PROJECT_NAME).*$", "", pins_h, flags=re.M)
            pins_only = re.sub(r"\n{3,}", "\n\n", pins_only).strip()
            h_text = replace_marked_or_insert(
                h_text, BEGIN_H, END_H, pins_only,
                fallback_anchor="//* 按键配置 */",
            )
            # 若仍有旧的「//* 按键配置 */」在标记外重复，保留标记块即可；首次插入会在锚点前放块，旧锚点还在——需删旧脚位区到 USB/FLASH 一段较难。
            # 策略：若插入后存在两份按键配置，删除标记外从 //* 按键配置 */ 到 #define FLASH_MISO 的旧块（不在标记内）
            h_text = _dedupe_pin_section(h_text)
            h_text = patch_project_id(h_text, meta)
            open(h_path, "w", encoding="utf-8", newline="\n").write(h_text)
            written.append(h_path)

            c_text = open(c_path, encoding="utf-8", errors="replace").read()
            # gpio 表只要 table 内容
            table = gpio_c
            if "gpio_config_table" not in table:
                table = "const user_gpio_config_t gpio_config_table[] = {\n" + table + "\n};"
            c_text = replace_marked_or_insert(
                c_text, BEGIN_C, END_C, table,
                fallback_anchor="const user_gpio_config_t gpio_config_table[]",
            )
            c_text = _dedupe_gpio_table(c_text)
            open(c_path, "w", encoding="utf-8", newline="\n").write(c_text)
            written.append(c_path)

            if data.get("write_features") and data.get("features_h"):
                feat = os.path.join(self._periph, "board_features.h")
                open(feat, "w", encoding="utf-8", newline="\n").write(data["features_h"])
                written.append(feat)

            if data.get("write_sleep") and data.get("sleep_c"):
                sleep_path = os.path.join(self._periph, "periph_gpio_sleep_set.pinmux.c")
                open(sleep_path, "w", encoding="utf-8", newline="\n").write(data["sleep_c"])
                written.append(sleep_path)

            # 核心价值：扫描引用 + 按板型同步 key_io / sleep
            if biz_sync is not None:
                try:
                    scan_preview = biz_sync.scan_project_refs(self._periph)
                except Exception as e:
                    log(f"scan after write: {e}")
                    scan_preview = {"ok": False, "message": str(e)}

            if data.get("sync_biz", True) and biz_sync is not None:
                feat_biz = data.get("biz_features") or {}
                sync_r = biz_sync.sync_board_contracts(self._periph, feat_biz, bak_dir)
                biz_actions = sync_r.get("actions") or []
                for p in sync_r.get("written") or []:
                    if p not in written:
                        written.append(p)

            self._persist()
            msg = "已写入:\n" + "\n".join(written) + f"\n备份: {bak_dir}"
            applied = [a for a in biz_actions if a.get("applied")]
            if applied:
                msg += "\n\n业务契约同步:\n" + "\n".join(
                    f"- {a.get('file')}: {a.get('detail')}" for a in applied
                )
            elif data.get("sync_biz", True):
                msg += "\n\n业务契约：未匹配到需改写处（或已是目标形态）"
            if scan_preview and scan_preview.get("issues"):
                msg += "\n\n引用提示:\n" + "\n".join(f"- {x}" for x in scan_preview["issues"][:8])
            log(msg)
            return {
                "ok": True,
                "message": msg,
                "backup": bak_dir,
                "written": written,
                "biz_actions": biz_actions,
                "scan": scan_preview,
            }
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    # ----- 板级包 / 宏观金机 -----

    def save_board_json(self, board_name: str, desc_json: str):
        """把 UI 板描述写回 boards/<name>.json。"""
        try:
            name = (board_name or self._board or "").strip()
            if not name or name in ("blank",):
                return {"ok": False, "message": "请先在下拉框选择板名（如 BD319）"}
            data = json.loads(desc_json) if isinstance(desc_json, str) else desc_json
            if validation is not None:
                validation_result = validation.validate_board(data)
                if not validation_result.get("ok"):
                    return {
                        "ok": False,
                        "message": "板描述校验失败，未保存",
                        "validation": validation_result,
                    }
            path = os.path.join(HERE, "boards", f"{name}.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w", encoding="utf-8", newline="\n").write(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )
            self._persist(board=name)
            log(f"已保存板描述: {path}")
            return {"ok": True, "path": path, "message": f"已保存 {path}"}
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    def get_policy_catalog(self, logo_ledc: bool = False):
        if board_pack is None:
            return {"ok": False, "message": "board_pack 模块不可用"}
        # overlay synth policy if present
        name = (self._board or "").strip() or "BD319"
        catalog = board_pack.policy_catalog(bool(logo_ledc))
        synth_pol = os.path.join(HERE, "synth", name, "policy.json")
        enabled = {c["id"]: c["enabled"] for c in catalog}
        if os.path.isfile(synth_pol):
            try:
                raw = json.load(open(synth_pol, encoding="utf-8"))
                en = raw.get("enabled") if isinstance(raw, dict) else None
                if isinstance(en, dict):
                    enabled.update({k: bool(v) for k, v in en.items()})
            except (OSError, json.JSONDecodeError):
                pass
        for c in catalog:
            c["enabled"] = bool(enabled.get(c["id"], c["enabled"]))
        return {
            "ok": True,
            "board": name,
            "catalog": catalog,
            "donor_root": self._donor_root or "",
            "synth_dir": os.path.join(HERE, "synth", name),
        }

    def pick_donor_dir(self):
        if not self._win:
            return {"ok": False, "message": "窗口未就绪"}
        try:
            import webview
            paths = self._win.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception as e:
            log(f"FOLDER_DIALOG(donor) 失败: {e}")
            return {"ok": False, "message": str(e)}
        if not paths:
            return {"ok": False, "message": "已取消"}
        path = paths[0] if isinstance(paths, (list, tuple)) else paths
        sdk = path
        if golden_diff is not None:
            sdk = golden_diff.find_sdk_root(path) or os.path.abspath(path)
        self._donor_root = sdk
        self._persist()
        return {"ok": True, "donor_root": sdk, "message": f"供体: {sdk}"}

    def synth_golden_board(self, board_name: str = "", pictures: str = ""):
        if synth_golden is None:
            return {"ok": False, "message": "synth_golden 模块不可用"}
        name = (board_name or self._board or "").strip()
        if not name:
            return {"ok": False, "message": "请先选择板名"}
        pics = (pictures or "").strip()
        if not pics:
            cand = os.path.join(r"E:\pictures", name)
            if os.path.isdir(cand):
                pics = cand
        try:
            r = synth_golden.synth_board(name, pictures_dir=pics)
            self._persist(board=name)
            log(r.get("message") or "")
            return r
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    def inventory_synth(self, board_name: str = ""):
        if synth_golden is None:
            return {"ok": False, "message": "synth_golden 模块不可用"}
        if not self._periph:
            return {"ok": False, "message": "请先选择工程目录"}
        name = (board_name or self._board or "").strip()
        if not name:
            return {"ok": False, "message": "请先选择板名"}
        try:
            r = synth_golden.inventory_synth_vs_target(name, self._project_root or self._periph)
            return r
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}

    def apply_board_pack(self, payload_json: str = ""):
        """
        payload: {
          board?: str,
          policy?: {id: bool},
          donor?: str,
          dry_run?: bool,
          write_pins_first?: bool,  # 若 true，调用方应已先 write_user_config
          features_h?: str
        }
        """
        if board_pack is None:
            return {"ok": False, "message": "board_pack 模块不可用"}
        if not self._periph:
            return {"ok": False, "message": "请先选择工程目录"}
        try:
            data = {}
            if payload_json:
                data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
            name = (data.get("board") or self._board or "").strip()
            if not name:
                return {"ok": False, "message": "请先选择板名"}
            donor = (data.get("donor") or self._donor_root or "").strip()
            r = board_pack.apply_board_pack(
                self._project_root or self._periph,
                name,
                policy=data.get("policy"),
                donor_hint=donor,
                features_h=data.get("features_h") or "",
                dry_run=bool(data.get("dry_run")),
            )
            log(r.get("message") or "")
            return r
        except Exception as e:
            log(traceback.format_exc())
            return {"ok": False, "message": str(e)}


def _dedupe_pin_section(text: str) -> str:
    """若标记块已存在，删除标记外的旧 //* 按键配置 */ … FLASH_MISO 一段（粗粒度）。"""
    if BEGIN_H not in text or END_H not in text:
        return text
    # 只处理 END 之后的重复脚位区
    pre, rest = text.split(END_H, 1)
    # 删 rest 里从 //* 按键配置 */ 到 #define FLASH_MISO_PIN ... 行
    rest2 = re.sub(
        r"\n//\*\s*按键配置\s*\*/[\s\S]*?(?=\n//----------------------------------------------------------------------------;\n// RF模式配置|\n//----------------------------------------------------------------------------;\n// 项目ID|\n#endif|\Z)",
        "\n",
        rest,
        count=1,
    )
    # 英文/乱码锚点兼容：从 KEY_R0 到 FLASH_MISO
    if rest2 == rest:
        rest2 = re.sub(
            r"\n//\*[\s\S]{0,40}\*/\s*\n#define\s+KEY_R0_PIN[\s\S]*?#define\s+FLASH_MISO_PIN[^\n]*\n?",
            "\n",
            rest,
            count=1,
        )
    return pre + END_H + rest2


def _dedupe_gpio_table(text: str) -> str:
    if BEGIN_C not in text or END_C not in text:
        return text
    pre, rest = text.split(END_C, 1)
    # 删标记后残留的旧 gpio_config_table
    rest2 = re.sub(
        r"\nconst user_gpio_config_t gpio_config_table\[]\s*=\s*\{[\s\S]*?\};\s*",
        "\n",
        rest,
        count=1,
    )
    return pre + END_C + rest2


def main():
    parser = argparse.ArgumentParser(description="OM6239 PinMux")
    parser.add_argument("--maximize", action="store_true", help="启动时最大化（贴工作区）")
    parser.add_argument("--fullscreen", action="store_true", help="兼容旧参数：等同 --maximize")
    parser.add_argument("--windowed", action="store_true", help="兼容旧参数（默认已是窗口）")
    parser.add_argument("--width", type=int, default=0, help="窗口宽度（默认用上次记忆）")
    parser.add_argument("--height", type=int, default=0, help="窗口高度（默认用上次记忆）")
    parser.add_argument("--project", type=str, default="", help="预绑定工程目录")
    args = parser.parse_args()

    if not os.path.isfile(INDEX):
        log(f"找不到 {INDEX}")
        sys.exit(1)

    try:
        ensure_webview()
        import webview
    except Exception:
        log(traceback.format_exc())
        sys.exit(2)

    geom = load_window_geom(args.width or None, args.height or None)
    start_max = bool(args.maximize or args.fullscreen or geom.get("maximized"))
    if args.windowed and not (args.maximize or args.fullscreen):
        start_max = False

    api = WindowApi(start_maximized=start_max, geom=geom)
    restore_root = args.project.strip() if args.project else ""
    root, periph = try_restore_project(restore_root)
    if periph:
        api._project_root = root
        api._periph = periph
        api._persist()
        log(f"恢复工程 periph={periph}" + (" (--project)" if args.project else " (pinmux_state.json)"))
    elif args.project:
        log(f"--project 无效或找不到 user_config.h: {args.project}")

    create_kwargs = dict(
        title="OM6239 PinMux",
        url=INDEX,
        js_api=api,
        width=geom["width"],
        height=geom["height"],
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        resizable=True,
        frameless=True,
        easy_drag=False,
        shadow=False,  # DWM 阴影在无边框最大化时易出顶栏白条
        fullscreen=False,
        maximized=False,  # 自管工作区最大化，避免盖任务栏
        background_color="#1a1d23",
    )
    if geom["x"] is not None and geom["y"] is not None:
        create_kwargs["x"] = geom["x"]
        create_kwargs["y"] = geom["y"]

    try:
        window = webview.create_window(**create_kwargs)
        api.bind(window)

        def on_shown():
            hwnd = get_hwnd(window)
            if hwnd:
                try:
                    enable_frameless_resize(hwnd)
                except Exception as e:
                    log(f"enable resize: {e}")
            if start_max:
                try:
                    api._ignore_geom_events = True
                    api._apply_workarea_maximize()
                    api._maximized = True
                    api.persist_window_now()
                except Exception as e:
                    log(f"start maximize: {e}")
                finally:
                    api._ignore_geom_events = False

        def on_loaded():
            mx = "true" if api._maximized else "false"
            info = json.dumps(api.get_project_info(), ensure_ascii=False)
            board = json.dumps(api._board or "", ensure_ascii=False)
            window.evaluate_js(
                "window.__PINMUX_HOST__={ok:true,mode:'frameless',alwaysFrameless:true,canWriteProject:true};"
                "document.documentElement.classList.add('pinmux-host','pinmux-frameless');"
                f"window.__PINMUX_MAX__={mx};"
                f"window.__PINMUX_PROJECT__={info};"
                f"window.__PINMUX_BOARD__={board};"
                "if(window.pinmuxHostReady) window.pinmuxHostReady();"
            )

        def on_moved(*_a):
            if api._maximized:
                return
            api.schedule_persist_window()

        def on_resized(*_a):
            if api._maximized:
                hwnd = get_hwnd(window)
                if hwnd:
                    try:
                        rc = RECT()
                        _user32().GetWindowRect(hwnd, ctypes.byref(rc))
                        wx, wy, ww, wh = get_monitor_work_area(hwnd)
                        cur_w = rc.right - rc.left
                        cur_h = rc.bottom - rc.top
                        if (
                            abs(rc.left - wx) > 12
                            or abs(rc.top - wy) > 12
                            or abs(cur_w - ww) > 12
                            or abs(cur_h - wh) > 12
                        ):
                            api._maximized = False
                            window.evaluate_js(
                                "window.__PINMUX_MAX__=false;"
                                "if(window.syncMaxButton) window.syncMaxButton(false);"
                            )
                    except Exception:
                        pass
            if not api._maximized:
                api.schedule_persist_window()

        def on_closing():
            try:
                api.persist_window_now()
            except Exception:
                pass

        window.events.shown += on_shown
        window.events.loaded += on_loaded
        window.events.moved += on_moved
        window.events.resized += on_resized
        window.events.closing += on_closing

        log("启动 webview (edgechromium) …")
        webview.start(gui="edgechromium", debug=False)
    except Exception:
        log(traceback.format_exc())
        try:
            log("回退: frameless=False")
            api2 = WindowApi(start_maximized=False, geom=geom)
            if api._periph:
                api2._project_root = api._project_root
                api2._periph = api._periph
                api2._board = api._board
            window = webview.create_window(
                title="OM6239 PinMux",
                url=INDEX,
                js_api=api2,
                width=geom["width"],
                height=geom["height"],
                **({"x": geom["x"], "y": geom["y"]} if geom["x"] is not None and geom["y"] is not None else {}),
                resizable=True,
                frameless=False,
            )
            api2.bind(window)

            def on_loaded2():
                info = json.dumps(api2.get_project_info(), ensure_ascii=False)
                board = json.dumps(api2._board or "", ensure_ascii=False)
                window.evaluate_js(
                    "window.__PINMUX_HOST__={ok:true,mode:'framed',canWriteProject:true};"
                    f"window.__PINMUX_PROJECT__={info};"
                    f"window.__PINMUX_BOARD__={board};"
                    "if(window.pinmuxHostReady) window.pinmuxHostReady();"
                )

            window.events.loaded += on_loaded2
            window.events.closing += lambda: api2.persist_window_now()
            webview.start()
        except Exception:
            log(traceback.format_exc())
            sys.exit(3)


if __name__ == "__main__":
    main()
