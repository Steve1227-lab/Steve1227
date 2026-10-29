#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反霸屏卫士 v10.0
基于 v9.0，增量修复：
- 空标题窗口误判保护
- PyInstaller 单文件打包子进程兼容
- ActivityFaker stop() 竞态修复
模式1：普通模式 — 日常使用，反侦察（可选：防最小化 + 键盘释放 + 活动伪造）
模式2：进阶模式 — 挂起霸屏进程的全部线程（彻底冻结）
"""

import ctypes
import ctypes.wintypes
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
import os
import sys
import traceback
import json
import subprocess
import random
import logging
from logging.handlers import RotatingFileHandler
from ctypes import wintypes

# ========== 全局崩溃捕获 ==========
_crash_log = os.path.join(os.environ.get("TEMP", "."), "anti_baping_v10_crash.log")

def _write_crash(exc_type, exc_value, exc_tb):
    with open(_crash_log, "w", encoding="utf-8") as f:
        f.write(f"Crash time: {datetime.now()}\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"Platform: {sys.platform}\n")
        f.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

sys.excepthook = _write_crash

# ========== Win32 API 常量 ==========
HWND_TOPMOST = ctypes.wintypes.HWND(-1)
HWND_NOTOPMOST = ctypes.wintypes.HWND(-2)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SWP_FLAGS = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

VK_MENU = 0x12
KEYEVENTF_KEYUP = 2

# 键盘钩子常量
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_LWIN = 0x5B
VK_RWIN = 0x5C

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulong),
    ]

# WinEvent 常量
EVENT_SYSTEM_MINIMIZESTART = 0x0016
WINEVENT_OUTOFCONTEXT = 0x0000
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9
PM_REMOVE = 1

# SendInput 常量（活动伪造）
INPUT_KEYBOARD = 1

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("union", ctypes.c_ubyte * (ctypes.sizeof(ctypes.c_void_p) * 3)),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulong),
    ]

# ========== Win32 API 声明 ==========
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.FindWindowW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
user32.FindWindowW.restype = ctypes.wintypes.HWND

user32.SetWindowPos.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint
]
user32.SetWindowPos.restype = ctypes.wintypes.BOOL

user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
user32.IsWindowVisible.restype = ctypes.wintypes.BOOL

user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
user32.SetForegroundWindow.restype = ctypes.wintypes.BOOL

user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD

kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD
kernel32.GetCurrentProcessId.restype = ctypes.wintypes.DWORD

user32.AttachThreadInput.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.BOOL]
user32.AttachThreadInput.restype = ctypes.wintypes.BOOL

user32.keybd_event.argtypes = [ctypes.c_byte, ctypes.c_byte, ctypes.c_ulong, ctypes.c_ulong]
user32.keybd_event.restype = None

user32.SwitchToThisWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.BOOL]
user32.SwitchToThisWindow.restype = None

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = ctypes.wintypes.BOOL

user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetClassNameW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long

user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.wintypes.BOOL

# 线程挂起相关 API
kernel32.OpenThread.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
kernel32.OpenThread.restype = ctypes.wintypes.HANDLE

kernel32.SuspendThread.argtypes = [ctypes.wintypes.HANDLE]
kernel32.SuspendThread.restype = ctypes.c_ulong

kernel32.ResumeThread.argtypes = [ctypes.wintypes.HANDLE]
kernel32.ResumeThread.restype = ctypes.c_ulong

kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
kernel32.CloseHandle.restype = ctypes.c_bool

THREAD_SUSPEND_RESUME = 0x0002

# 窗口最小化相关 API
user32.IsIconic.argtypes = [ctypes.wintypes.HWND]
user32.IsIconic.restype = ctypes.wintypes.BOOL

user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = ctypes.wintypes.BOOL

# SetWinEventHook
WinEventProcType = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.HWND,
                                       ctypes.wintypes.LONG, ctypes.wintypes.LONG, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD)

user32.SetWinEventHook.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.HMODULE,
                                    WinEventProcType, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
user32.SetWinEventHook.restype = ctypes.c_void_p

user32.UnhookWinEvent.argtypes = [ctypes.c_void_p]
user32.UnhookWinEvent.restype = ctypes.wintypes.BOOL

# 键盘钩子相关 API
KeyboardProcType = ctypes.WINFUNCTYPE(ctypes.wintypes.LPARAM, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, KeyboardProcType, ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p

user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.wintypes.LPARAM

user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE

# SendInput
user32.SendInput.argtypes = [ctypes.wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.wintypes.UINT

# 消息循环
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", POINT),
    ]

user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.UINT, ctypes.wintypes.UINT]
user32.PeekMessageW.restype = ctypes.wintypes.BOOL

user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.UINT]
user32.GetMessageW.restype = ctypes.wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = ctypes.wintypes.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = ctypes.wintypes.LPARAM

user32.PostThreadMessageW.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL

# ========== 进程线程枚举（Toolhelp32） ==========
TH32CS_SNAPTHREAD = 0x00000004

class THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD)
    ]

kernel32.CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

kernel32.Thread32First = kernel32.Thread32First
kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
kernel32.Thread32First.restype = wintypes.BOOL

kernel32.Thread32Next = kernel32.Thread32Next
kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
kernel32.Thread32Next.restype = wintypes.BOOL

# ========== 系统窗口类名白名单 ==========
SYSTEM_CLASSES = {
    "Shell_TrayWnd", "Progman", "WorkerW",
    "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow",
    "#32768", "#32769", "SysShadow",
    "NotifyIconOverflowWindow", "Shell_SecondaryTrayWnd",
    "TopLevelWindowForOverflowXamlIsland",
    "Windows.Internal.Shell.TabProxyWindow",
    "Windows.UI.Composition.DesktopWindowContentBridge",
    "NVIDIA_GeForce_Overlay", "NVIDIA_Overlay",
    "GDI+ Hook Window Class", "RTSSWndClass",
    "MAINGUIWndClass", "EVGA Precision", "HWiNFOFPS",
    "OleMainThreadWndClass", "IME", "MSCTFIME UI",
    "CiceroUIWndFrame", "TaskManagerWindow", "MultitaskingViewFrame",
}

# ========== 配置中心化 ==========
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anti_baping_v10_config.json")

DEFAULT_CONFIG = {
    "schema_version": 1,
    "skip_advanced_warning": False,
    "guards": {
        "focus": True,
        "topmost": True,
        "minimize": False,
        "keyboard": False,
        "activity_faker": False,
    },
    "heuristic": {
        "min_area_ratio": 0.85,
        "known_titles": [
            "极域电子教室", "红蜘蛛", "NetSupport", "NetControl", "LanSchool",
            "Veyon", "italc", "Mythware", "Lanstar", "DawnStones",
            "云课堂", "电子教室", "Student", "Classroom",
        ],
    },
    "logging": {
        "level": "INFO",
        "max_bytes": 1048576,
        "backup_count": 3,
        "log_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), "anti_baping_v10.log"),
    },
}

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 合并默认值，确保新增字段存在
            merged = _deep_merge(DEFAULT_CONFIG, cfg)
            return merged
    except Exception:
        pass
    return DEFAULT_CONFIG.copy()

def _deep_merge(base, override):
    """递归合并配置，override 覆盖 base"""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ========== 文件日志（轮转） ==========
def setup_file_logger():
    cfg = load_config()
    log_cfg = cfg.get("logging", {})
    log_path = log_cfg.get("log_path", os.path.join(os.path.dirname(os.path.abspath(__file__)), "anti_baping_v10.log"))
    level = getattr(logging, log_cfg.get("level", "INFO"), logging.INFO)
    max_bytes = log_cfg.get("max_bytes", 1048576)
    backup_count = log_cfg.get("backup_count", 3)

    logger = logging.getLogger("anti_baping_v10")
    logger.setLevel(level)
    # 避免重复添加 handler
    if logger.handlers:
        return logger

    handler = RotatingFileHandler(log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return logger

_file_logger = None

def _get_file_logger():
    global _file_logger
    if _file_logger is None:
        _file_logger = setup_file_logger()
    return _file_logger

# ========== 电路熔断器（仅日志，不禁用守卫） ==========
class CircuitBreaker:
    """记录连续错误，仅日志告警，不禁用任何守卫"""
    def __init__(self, name, threshold=5, cooldown=30):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown
        self._failures = 0
        self._last_fail_time = 0
        self._warned = False

    def record_success(self):
        self._failures = 0
        self._warned = False

    def record_failure(self):
        self._failures += 1
        self._last_fail_time = time.time()

    def should_warn(self):
        if self._failures >= self.threshold and not self._warned:
            self._warned = True
            return True
        return False

    @property
    def status(self):
        if self._failures >= self.threshold:
            return f"⚠ {self._failures}次连续失败"
        return "正常"

# ========== 启发式窗口分析器 ==========
class HeuristicAnalyzer:
    """基于行为特征判断霸屏软件，不依赖单一类名"""
    def __init__(self):
        cfg = load_config().get("heuristic", {})
        self._min_area_ratio = cfg.get("min_area_ratio", 0.85)
        self._known_titles = [t.lower() for t in cfg.get("known_titles", [])]

    def analyze(self, hwnd, class_name, title, rect, pid, my_pid, screen_area, ex_style):
        """返回 (is_baping, score, is_system)"""
        if pid == my_pid:
            return False, 0, True

        # 系统窗口直接排除，不做评分（避免 NVIDIA 等叠加面积+置顶后过线）
        is_system = _is_system_window(class_name, title, ex_style)
        if is_system:
            return False, 0, True

        # 自身窗口排除（标题含 anti_baping 等自身关键词）
        title_lower = (title or "").lower()
        if "anti_baping" in title_lower or "反霸屏" in title_lower:
            return False, 0, True

        # 【v10 修复】空标题 + 空类名 → 直接排除（如游戏启动画面、无标题全屏窗口）
        if not title and not class_name:
            return False, 0, True

        w = max(0, rect.right - rect.left)
        h = max(0, rect.bottom - rect.top)
        area = w * h
        if area <= 0:
            return False, 0, True

        area_ratio = area / max(1, screen_area)
        score = 0.0

        # 全屏/大窗口
        if area_ratio >= self._min_area_ratio:
            score += 0.35

        # 强制置顶
        if ex_style & WS_EX_TOPMOST:
            score += 0.20

        # 已知标题关键词
        for kw in self._known_titles:
            if kw in title_lower:
                score += 0.25
                break

        # 已知类名关键词
        class_lower = (class_name or "").lower()
        for kw in self._known_titles:
            if kw in class_lower:
                score += 0.15
                break

        return score >= 0.35, score, False

def _is_system_window(class_name, title, ex_style):
    if not class_name:
        return True
    if class_name in SYSTEM_CLASSES:
        return True
    if class_name.startswith(("Windows", "NVIDIA", "AMD", "Intel")):
        return True
    if "Overlay" in class_name or "overlay" in class_name:
        return True
    if "RTSS" in class_name or "FPS" in class_name:
        return True
    if (ex_style & WS_EX_TOOLWINDOW) != 0:
        return True
    if (ex_style & WS_EX_NOACTIVATE) != 0:
        return True
    if (ex_style & WS_EX_TRANSPARENT) != 0 and (ex_style & WS_EX_LAYERED) != 0:
        return True
    return False

# ========== 活动伪造器 ==========
class ActivityFaker:
    """模拟键盘活动，防止教师端检测到学生不活跃"""
    def __init__(self):
        self._active = False
        self._thread = None
        self._log_cb = None

    def set_log_callback(self, cb):
        self._log_cb = cb

    def _log(self, msg):
        if self._log_cb:
            self._log_cb(msg)

    def start(self):
        if self._active:
            return
        self._active = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._log("活动伪造已启动")

    def stop(self):
        # 【v10 修复】先读状态再置 False，避免竞态导致重复打印
        was_active = self._active
        self._active = False
        if was_active:
            self._log("活动伪造已停止")

    @property
    def running(self):
        return self._active

    def _loop(self):
        while self._active:
            try:
                delay = 2 + random.uniform(-1, 1)
                time.sleep(max(0.5, delay))
                if not self._active:
                    break
                self._inject()
            except Exception:
                time.sleep(1)

    def _inject(self):
        """发送无害的 KEYUP 事件（VK=0xFF），不触发任何实际按键"""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        ki = KEYBDINPUT.from_buffer(inp.union)
        ki.wVk = 0xFF
        ki.wScan = 0
        ki.dwFlags = KEYEVENTF_KEYUP
        ki.time = 0
        ki.dwExtraInfo = 0
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def get_window_pid(hwnd):
    try:
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return 0


def get_window_tid(hwnd):
    try:
        return user32.GetWindowThreadProcessId(hwnd, None)
    except Exception:
        return 0


def steal_focus(target_hwnd):
    try:
        ok = user32.SetForegroundWindow(target_hwnd)
        if ok:
            return True, "direct"

        user32.keybd_event(VK_MENU, 0x38, 0, 0)
        ok = user32.SetForegroundWindow(target_hwnd)
        user32.keybd_event(VK_MENU, 0x38, KEYEVENTF_KEYUP, 0)
        if ok:
            return True, "alt_key"

        fg = user32.GetForegroundWindow()
        if fg:
            fg_pid = ctypes.wintypes.DWORD()
            fg_tid = user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))
            my_tid = kernel32.GetCurrentThreadId()
            if fg_tid and fg_tid != my_tid:
                user32.AttachThreadInput(fg_tid, my_tid, True)
                user32.keybd_event(VK_MENU, 0x38, 0, 0)
                ok = user32.SetForegroundWindow(target_hwnd)
                user32.keybd_event(VK_MENU, 0x38, KEYEVENTF_KEYUP, 0)
                user32.AttachThreadInput(fg_tid, my_tid, False)
                if ok:
                    return True, "attach+alt"

        user32.SwitchToThisWindow(target_hwnd, True)
        if user32.GetForegroundWindow() == target_hwnd:
            return True, "switch"

        return False, "failed"
    except Exception as e:
        return False, f"exc:{e}"


class AntiBapingGuard:
    def __init__(self, threshold=0.5, interval_ms=300, mode="normal",
                 prevent_minimize=False, keep_keyboard=False, activity_faker=False):
        self.threshold = threshold
        self.interval_ms = interval_ms
        self.mode = mode
        self.prevent_minimize = prevent_minimize
        self.keep_keyboard = keep_keyboard
        self.activity_faker_enabled = activity_faker
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.scan_count = 0
        self.focus_steals = 0
        self.focus_skips = 0
        self.focus_fails = 0
        self.topmost_cancels = 0
        self.suspended_threads = 0
        self.resumed_threads = 0
        self.minimize_restores = 0
        self.last_log_baping = []
        self.callback = None
        self.my_pid = os.getpid()
        self.suspended_tids = set()
        self.last_suspended_set = set()
        self.first_scan_done = False

        # 钩子相关
        self._win_event_hook = None
        self._win_event_callback = None
        self._kb_worker = None
        self._kb_worker_pid = 0          # 子进程 PID，用于扫描时排除自身
        self._kb_worker_running = False
        self._kb_reader_thread = None
        self._last_kb_hook_reinstall = 0
        self._kb_hook_first_install = True
        self._last_win_key_log = 0

        # 启发式分析器
        self.heuristic = HeuristicAnalyzer()

        # 活动伪造器
        self.activity_faker = ActivityFaker()
        self.activity_faker.set_log_callback(lambda msg: self.log(msg, "info"))

        # 电路熔断器
        self._scan_cb = CircuitBreaker("scan", threshold=5, cooldown=30)
        self._focus_cb = CircuitBreaker("focus", threshold=3, cooldown=30)

        self.screen_w = user32.GetSystemMetrics(0)
        self.screen_h = user32.GetSystemMetrics(1)
        self.screen_area = max(1, self.screen_w * self.screen_h)
        self.taskbar_hwnd = user32.FindWindowW("Shell_TrayWnd", None)

    def set_callback(self, cb):
        self.callback = cb

    def log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        if self.callback:
            self.callback(line, level)
        # 同步写入文件日志
        try:
            fl = _get_file_logger()
            if level == "error":
                fl.error(msg)
            elif level == "warn":
                fl.warning(msg)
            elif level == "debug":
                fl.debug(msg)
            else:
                fl.info(msg)
        except Exception:
            pass

    def pin_taskbar(self):
        if self.taskbar_hwnd:
            return bool(user32.SetWindowPos(self.taskbar_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS))
        return False

    def focus_guard(self):
        try:
            fg = user32.GetForegroundWindow()
            if not fg:
                return False, "no_fg", True
            if fg == self.taskbar_hwnd:
                return False, "already_taskbar", True
            if get_window_pid(fg) == self.my_pid:
                return False, "self_pid", True

            rect = RECT()
            if not user32.GetWindowRect(fg, ctypes.byref(rect)):
                return False, "no_rect", True

            w = max(0, rect.right - rect.left)
            h = max(0, rect.bottom - rect.top)
            area = w * h
            percent = area / self.screen_area

            if percent <= self.threshold:
                return False, "too_small", True

            buf_cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(fg, buf_cls, 256)
            class_name = buf_cls.value

            buf_title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(fg, buf_title, 256)
            title = buf_title.value or ""

            ex_style = user32.GetWindowLongW(fg, GWL_EXSTYLE)

            # 使用启发式分析器
            is_baping, score, is_system = self.heuristic.analyze(
                fg, class_name, title, rect, get_window_pid(fg), self.my_pid, self.screen_area, ex_style
            )
            if is_system:
                return False, "system", True

            ok, method = steal_focus(self.taskbar_hwnd)
            self._focus_cb.record_success()
            return ok, method, False
        except Exception as e:
            self._focus_cb.record_failure()
            if self._focus_cb.should_warn():
                self.log(f"焦点守护连续失败: {e}", "error")
            return False, f"exc:{e}", False

    def get_process_threads(self, pid):
        tids = []
        hSnapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if hSnapshot == wintypes.HANDLE(-1).value:
            return tids
        try:
            te = THREADENTRY32()
            te.dwSize = ctypes.sizeof(THREADENTRY32)
            if kernel32.Thread32First(hSnapshot, ctypes.byref(te)):
                while True:
                    if te.th32OwnerProcessID == pid:
                        tids.append(te.th32ThreadID)
                    if not kernel32.Thread32Next(hSnapshot, ctypes.byref(te)):
                        break
        finally:
            kernel32.CloseHandle(hSnapshot)
        return tids

    def suspend_threads(self, tids_to_suspend):
        if not self.running:
            return 0
        count = 0
        my_tid = kernel32.GetCurrentThreadId()
        for tid in tids_to_suspend:
            if tid == my_tid:
                continue
            hThread = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, tid)
            if hThread:
                try:
                    result = kernel32.SuspendThread(hThread)
                    if result != ctypes.c_ulong(-1).value:
                        with self.lock:
                            self.suspended_tids.add(tid)
                        count += 1
                finally:
                    kernel32.CloseHandle(hThread)
        return count

    def resume_threads(self, tids_to_resume):
        count = 0
        for tid in tids_to_resume:
            hThread = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, tid)
            if hThread:
                try:
                    result = kernel32.ResumeThread(hThread)
                    if result != ctypes.c_ulong(-1).value:
                        with self.lock:
                            self.suspended_tids.discard(tid)
                        count += 1
                finally:
                    kernel32.CloseHandle(hThread)
        return count

    def resume_all_suspended(self):
        with self.lock:
            tids = list(self.suspended_tids)
            self.suspended_tids.clear()
        count = 0
        for tid in tids:
            hThread = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, tid)
            if hThread:
                try:
                    result = kernel32.ResumeThread(hThread)
                    if result != ctypes.c_ulong(-1).value:
                        count += 1
                finally:
                    kernel32.CloseHandle(hThread)
        if count > 0:
            self.log(f"恢复线程 {count} 个（强制）", "info")
        return count

    # ========== 防最小化钩子 ==========
    def _setup_win_event_hook(self):
        guard = self

        @WinEventProcType
        def callback(hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
            if event != EVENT_SYSTEM_MINIMIZESTART or idObject != 0 or idChild != 0:
                return
            if not user32.IsWindowVisible(hwnd):
                return
            try:
                rect = RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return
                w = max(0, rect.right - rect.left)
                h = max(0, rect.bottom - rect.top)
                area = w * h
                if area <= 0:
                    return
                percent = area / guard.screen_area
                if percent <= guard.threshold:
                    return
                buf_cls = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buf_cls, 256)
                class_name = buf_cls.value
                if _is_system_window(class_name, "", 0):
                    return
                user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                with guard.lock:
                    guard.minimize_restores += 1
            except Exception:
                pass

        self._win_event_callback = callback
        self._win_event_hook = user32.SetWinEventHook(
            EVENT_SYSTEM_MINIMIZESTART, EVENT_SYSTEM_MINIMIZESTART,
            0, callback, 0, 0, WINEVENT_OUTOFCONTEXT
        )
        if self._win_event_hook:
            self.log("防最小化钩子已安装", "info")
        else:
            self.log("防最小化钩子安装失败", "error")

    def _teardown_win_event_hook(self):
        if self._win_event_hook:
            user32.UnhookWinEvent(self._win_event_hook)
            self._win_event_hook = None
            self._win_event_callback = None

    # ========== 键盘钩子子进程 ==========
    def _start_kb_worker(self):
        if self._kb_worker:
            self._stop_kb_worker()
        try:
            # 【v10 修复】PyInstaller 单文件打包兼容：frozen 环境下直接启动自身 exe，
            # 不传 script_path（因为脚本已内嵌在 exe 中）
            if getattr(sys, 'frozen', False):
                self._kb_worker = subprocess.Popen(
                    [sys.executable, '--worker'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                )
            else:
                script_path = os.path.abspath(__file__)
                self._kb_worker = subprocess.Popen(
                    [sys.executable, script_path, '--worker'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                )
            self._kb_worker_pid = self._kb_worker.pid
            self._kb_worker_running = True
            self._last_kb_hook_reinstall = time.time()
            if self._kb_hook_first_install:
                self.log("键盘钩子已安装（Win键已释放）", "info")
                self._kb_hook_first_install = False
            self._kb_reader_thread = threading.Thread(target=self._read_kb_worker, daemon=True)
            self._kb_reader_thread.start()
        except Exception as e:
            self.log(f"键盘钩子子进程启动失败: {e}", "error")
            self._kb_worker = None
            self._kb_worker_running = False

    def _stop_kb_worker(self):
        self._kb_worker_running = False
        if self._kb_worker:
            try:
                self._kb_worker.terminate()
                self._kb_worker.wait(timeout=1)
            except Exception:
                try:
                    self._kb_worker.kill()
                except Exception:
                    pass
            self._kb_worker = None
        self._kb_reader_thread = None
        self._kb_worker_pid = 0

    def _read_kb_worker(self):
        try:
            for line in self._kb_worker.stdout:
                if not self._kb_worker_running:
                    break
                line = line.strip()
                if line == "WIN":
                    now = time.time()
                    if now - self._last_win_key_log > 1.0:
                        self._last_win_key_log = now
                        self.log("win键释放成功", "info")
                elif line == "READY":
                    pass
        except (IOError, OSError):
            pass
        finally:
            self._kb_worker_running = False

    def _manage_keyboard_hook(self, has_baping):
        if not self.keep_keyboard:
            return
        if self._kb_worker and self._kb_worker.poll() is not None:
            self._kb_worker = None
            self._kb_worker_running = False
        if has_baping:
            if not self._kb_worker:
                self._start_kb_worker()
                self.log("检测到霸屏，键盘钩子已安装", "info")
            elif time.time() - self._last_kb_hook_reinstall > 5.0:
                self._start_kb_worker()
        else:
            if self._kb_worker:
                self._stop_kb_worker()
                self.log("无霸屏，键盘钩子已卸载", "info")

    # ========== 活动伪造管理 ==========
    def _manage_activity_faker(self, has_baping):
        if not self.activity_faker_enabled:
            return
        if has_baping:
            if not self.activity_faker.running:
                self.activity_faker.start()
        else:
            if self.activity_faker.running:
                self.activity_faker.stop()

    # ========== 扫描 ==========
    def scan_once(self):
        if not self.running:
            return [], 0, False, "", True, False, 0, 0

        baping_list = []
        topmost_count = 0
        window_count = 0
        taskbar_ok = self.pin_taskbar()

        def enum_callback(hwnd, lparam):
            nonlocal topmost_count, window_count
            window_count += 1
            if window_count % 10 == 0:
                time.sleep(0)
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                pid = get_window_pid(hwnd)
                if pid == self.my_pid or pid == self._kb_worker_pid:
                    return True

                rect = RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return True

                w = max(0, rect.right - rect.left)
                h = max(0, rect.bottom - rect.top)
                area = w * h
                if area <= 0:
                    return True

                buf_cls = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buf_cls, 256)
                class_name = buf_cls.value

                buf_title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf_title, 256)
                title = buf_title.value or ""

                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

                # 使用启发式分析器
                is_baping, score, _ = self.heuristic.analyze(
                    hwnd, class_name, title, rect, pid, self.my_pid, self.screen_area, ex_style
                )

                if not is_baping:
                    return True

                baping_list.append({
                    "hwnd": hwnd,
                    "title": title,
                    "class": class_name,
                    "percent": round(area / self.screen_area * 100, 1),
                    "score": round(score, 2),
                })

                if (ex_style & WS_EX_TOPMOST) != 0:
                    ok = user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
                    if ok:
                        topmost_count += 1

            except Exception:
                pass
            return True

        cb = EnumWindowsProc(enum_callback)
        try:
            user32.EnumWindows(cb, 0)
            self._scan_cb.record_success()
        except Exception as e:
            self._scan_cb.record_failure()
            if self._scan_cb.should_warn():
                self.log(f"窗口扫描连续失败: {e}", "error")

        stolen, method, skip = self.focus_guard()

        # ===== 进阶模式：差异挂起/恢复 =====
        suspended_count = 0
        resumed_count = 0
        if self.mode == "advanced":
            current_pids = {get_window_pid(b["hwnd"]) for b in baping_list if get_window_pid(b["hwnd"]) != 0}
            current_tids = set()
            for pid in current_pids:
                if pid != self.my_pid:
                    current_tids.update(self.get_process_threads(pid))
            with self.lock:
                to_resume = self.suspended_tids - current_tids
            if to_resume:
                resumed_count = self.resume_threads(to_resume)
            to_suspend = current_tids - self.suspended_tids
            if to_suspend and self.running:
                suspended_count = self.suspend_threads(to_suspend)

        with self.lock:
            self.scan_count += 1
            if topmost_count > 0:
                self.topmost_cancels += topmost_count
            if stolen:
                self.focus_steals += 1
            elif skip:
                self.focus_skips += 1
            else:
                self.focus_fails += 1
            self.suspended_threads += suspended_count
            self.resumed_threads += resumed_count

        return baping_list, topmost_count, stolen, method, skip, taskbar_ok, suspended_count, resumed_count

    def loop(self):
        mode_str = "普通模式" if self.mode == "normal" else "进阶模式"
        self.log(f"守护启动 [{mode_str}] | 屏幕:{self.screen_w}x{self.screen_h} | 阈值:{self.threshold*100:.0f}% | 间隔:{self.interval_ms}ms")
        self.log("原则：不最小化、不压底、不改外观")
        if self.mode == "advanced":
            self.log("进阶模式：挂起霸屏进程的所有线程（彻底冻结）")
        if self.prevent_minimize:
            self._setup_win_event_hook()
        if self.activity_faker_enabled:
            self.log("活动伪造：待机（检测到霸屏后自动启动）", "info")

        while self.running:
            try:
                baping_list, topmost_count, stolen, method, skip, taskbar_ok, suspended_count, resumed_count = self.scan_once()

                has_baping = len(baping_list) > 0

                # 动态管理键盘钩子
                self._manage_keyboard_hook(has_baping)

                # 动态管理活动伪造
                self._manage_activity_faker(has_baping)

                time.sleep(0)

                with self.lock:
                    current_suspended_set = set(self.suspended_tids)
                suspended_changed = (current_suspended_set != self.last_suspended_set)
                self.last_suspended_set = current_suspended_set.copy()

                # ---- 日志处理 ----
                if not self.first_scan_done:
                    self.first_scan_done = True
                    if baping_list:
                        titles = ", ".join([b["title"][:15] for b in baping_list])
                        self.log(f"检测 | 霸屏:{len(baping_list)}个 [{titles}]", "info")

                result_parts = []
                if topmost_count > 0:
                    result_parts.append(f"取消置顶:{topmost_count}")
                if stolen:
                    result_parts.append(f"抢焦点:成功({method})")
                elif not skip and method not in ("no_fg", "already_taskbar", "self_pid", "too_small", "system"):
                    result_parts.append(f"抢焦点:失败({method})")
                if self.mode == "advanced" and suspended_changed:
                    if suspended_count > 0:
                        result_parts.append(f"挂起线程:{suspended_count}")
                    if resumed_count > 0:
                        result_parts.append(f"恢复线程:{resumed_count}")
                if not taskbar_ok:
                    result_parts.append("任务栏置顶失败")

                if result_parts:
                    titles = ", ".join([b["title"][:15] for b in baping_list]) if baping_list else "无"
                    self.log(f"动作 | 霸屏:{len(baping_list)}个 [{titles}] | {' | '.join(result_parts)}", "warn")

                # 心跳日志
                if self.scan_count % 60 == 0:
                    extra = ""
                    if self.mode == "advanced":
                        extra = f" | 挂起总数:{self.suspended_threads} | 恢复总数:{self.resumed_threads}"
                    if self.prevent_minimize:
                        extra += f" | 防最小化:{self.minimize_restores}"
                    if self.activity_faker_enabled:
                        extra += f" | 活动伪造:{'运行中' if self.activity_faker.running else '待机'}"
                    self.log(f"心跳 #{self.scan_count} | 取消置顶:{self.topmost_cancels} | 抢成功:{self.focus_steals} | 跳过:{self.focus_skips} | 失败:{self.focus_fails}{extra}", "debug")

            except Exception as e:
                self.log(f"异常: {e}", "error")
                # 电路熔断：仅记录，不禁用守卫
                self._scan_cb.record_failure()
                if self._scan_cb.should_warn():
                    self.log(f"扫描循环异常频繁: {e}", "error")

            if self.running:
                remaining = self.interval_ms / 1000.0
                while remaining > 0 and self.running:
                    sleep_chunk = min(0.1, remaining)
                    time.sleep(sleep_chunk)
                    remaining -= sleep_chunk

        self.resume_all_suspended()
        if self.activity_faker.running:
            self.activity_faker.stop()
        self.log("守护已停止")

    def start(self):
        if self.running:
            return
        self.running = True
        self.first_scan_done = False
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.resume_all_suspended()
        self._teardown_win_event_hook()
        self._stop_kb_worker()
        if self.activity_faker.running:
            self.activity_faker.stop()
        if self.thread:
            self.thread.join(timeout=0.3)

    def update_params(self, threshold, interval_ms, mode, prevent_minimize=False, keep_keyboard=False, activity_faker=False):
        with self.lock:
            self.threshold = threshold
            self.interval_ms = interval_ms
            self.mode = mode
            self.prevent_minimize = prevent_minimize
            self.keep_keyboard = keep_keyboard
            self.activity_faker_enabled = activity_faker


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("反霸屏卫士 v10.0")
        self.root.geometry("750x700")
        self.root.minsize(600, 550)

        self.is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        self.config = load_config()
        self.guard = AntiBapingGuard(threshold=0.85, interval_ms=300, mode="normal")
        self.guard.set_callback(self.on_log)

        self._build_ui()

    def _build_ui(self):
        info_frame = ttk.Frame(self.root, padding=10)
        info_frame.pack(fill=tk.X)

        ttk.Label(info_frame, text="反霸屏卫士 v10.0", font=("Microsoft YaHei", 14, "bold")).pack(side=tk.LEFT)

        self.status_label = ttk.Label(info_frame, text="● 已停止", foreground="gray", font=("Microsoft YaHei", 10))
        self.status_label.pack(side=tk.RIGHT)

        admin_text = "管理员" if self.is_admin else "普通权限"
        admin_color = "green" if self.is_admin else "orange"
        ttk.Label(info_frame, text=admin_text, foreground=admin_color, font=("Microsoft YaHei", 9)).pack(side=tk.RIGHT, padx=10)

        # 模式选择
        mode_frame = ttk.LabelFrame(self.root, text="模式选择", padding=10)
        mode_frame.pack(fill=tk.X, padx=10, pady=5)

        self.mode_var = tk.StringVar(value="normal")

        self.rb_normal = ttk.Radiobutton(
            mode_frame, text="普通模式", variable=self.mode_var, value="normal",
            command=self._on_mode_change
        )
        self.rb_normal.pack(anchor=tk.W)
        ttk.Label(mode_frame, text="  备注：日常使用，反侦察", foreground="gray", font=("Microsoft YaHei", 9)).pack(anchor=tk.W, padx=20)

        # 普通模式附加选项
        guards_cfg = self.config.get("guards", {})

        self.prevent_minimize_var = tk.BooleanVar(value=guards_cfg.get("minimize", False))
        self.cb_prevent_minimize = ttk.Checkbutton(
            mode_frame, text="防止程序最小化（阻止霸屏软件检测到遮挡后自动最小化）",
            variable=self.prevent_minimize_var
        )
        self.cb_prevent_minimize.pack(anchor=tk.W, padx=20, pady=(5, 0))

        self.keep_keyboard_var = tk.BooleanVar(value=guards_cfg.get("keyboard", False))
        self.cb_keep_keyboard = ttk.Checkbutton(
            mode_frame, text="保持键盘可用（释放被霸屏软件锁定的 Win 键等快捷键）",
            variable=self.keep_keyboard_var
        )
        self.cb_keep_keyboard.pack(anchor=tk.W, padx=20, pady=(2, 0))

        self.activity_faker_var = tk.BooleanVar(value=guards_cfg.get("activity_faker", False))
        self.cb_activity_faker = ttk.Checkbutton(
            mode_frame, text="活动伪造（模拟键盘活动，防止教师端检测到不活跃）",
            variable=self.activity_faker_var
        )
        self.cb_activity_faker.pack(anchor=tk.W, padx=20, pady=(2, 0))

        self.rb_advanced = ttk.Radiobutton(
            mode_frame, text="进阶模式", variable=self.mode_var, value="advanced",
            command=self._on_mode_change
        )
        self.rb_advanced.pack(anchor=tk.W, pady=(5, 0))
        ttk.Label(mode_frame, text="  备注：进阶拦截，挂起霸屏进程所有线程（彻底冻结）", foreground="#E67E22", font=("Microsoft YaHei", 9)).pack(anchor=tk.W, padx=20)

        # 设置
        ctrl_frame = ttk.LabelFrame(self.root, text="设置", padding=10)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(ctrl_frame, text="检测阈值:").grid(row=0, column=0, sticky=tk.W)
        self.threshold_var = tk.DoubleVar(value=85)
        self.threshold_scale = ttk.Scale(ctrl_frame, from_=30, to=100, orient=tk.HORIZONTAL,
                                          variable=self.threshold_var, command=self._on_threshold_change)
        self.threshold_scale.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.threshold_label = ttk.Label(ctrl_frame, text="85%")
        self.threshold_label.grid(row=0, column=2, sticky=tk.W)

        ttk.Label(ctrl_frame, text="扫描间隔:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.interval_var = tk.IntVar(value=300)
        ttk.Spinbox(ctrl_frame, from_=100, to=1000, increment=50, textvariable=self.interval_var,
                    width=8).grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Label(ctrl_frame, text="毫秒").grid(row=1, column=2, sticky=tk.W)

        ctrl_frame.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(ctrl_frame)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=10)

        self.start_btn = ttk.Button(btn_frame, text="▶ 开始", command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="⏹ 停止", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=5)

        tip_frame = ttk.Frame(self.root, padding=5)
        tip_frame.pack(fill=tk.X, padx=10)
        ttk.Label(tip_frame, text="普通模式：保持任务栏置顶 + 焦点守护 + 可选防最小化 + 可选键盘释放 + 可选活动伪造",
                  foreground="gray", font=("Microsoft YaHei", 9)).pack(anchor=tk.W)
        ttk.Label(tip_frame, text="进阶模式：挂起霸屏进程的全部线程，彻底冻结（停止后自动恢复）",
                  foreground="#E67E22", font=("Microsoft YaHei", 9)).pack(anchor=tk.W)

        log_frame = ttk.LabelFrame(self.root, text="日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_box = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 10), height=12)
        self.log_box.pack(fill=tk.BOTH, expand=True)
        self.log_box.tag_config("warn", foreground="#E67E22")
        self.log_box.tag_config("error", foreground="#E74C3C")
        self.log_box.tag_config("debug", foreground="#7F8C8D")
        self.log_box.tag_config("info", foreground="#2C3E50")

        self._schedule_refresh()

    def _on_mode_change(self):
        mode = self.mode_var.get()
        if mode == "advanced":
            self.cb_prevent_minimize.config(state=tk.DISABLED)
            self.cb_keep_keyboard.config(state=tk.DISABLED)
            self.cb_activity_faker.config(state=tk.DISABLED)
        else:
            self.cb_prevent_minimize.config(state=tk.NORMAL)
            self.cb_keep_keyboard.config(state=tk.NORMAL)
            self.cb_activity_faker.config(state=tk.NORMAL)

    def _on_threshold_change(self, val):
        pct = int(float(val))
        self.threshold_label.config(text=f"{pct}%")

    def on_log(self, msg, level="info"):
        def _insert():
            self.log_box.insert(tk.END, msg + "\n", level)
            self.log_box.see(tk.END)
        self.root.after(0, _insert)

    def _show_advanced_warning(self):
        if self.config.get("skip_advanced_warning", False):
            return True

        dialog = tk.Toplevel(self.root)
        dialog.title("⚠ 警告")
        dialog.geometry("420x200")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        ttk.Label(dialog, text="注意：本功能将挂起霸屏进程的所有线程，\n可能导致该进程完全冻结。\n如有问题，作者概不负责。",
                  font=("Microsoft YaHei", 11), foreground="#C0392B", justify=tk.CENTER).pack(pady=15)

        skip_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="下次启动不再提示", variable=skip_var).pack(pady=5)

        result = {"ok": False}

        def on_confirm():
            result["ok"] = True
            if skip_var.get():
                self.config["skip_advanced_warning"] = True
                save_config(self.config)
            dialog.destroy()

        def on_cancel():
            result["ok"] = False
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="确认启用", command=on_confirm).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=10)

        self.root.wait_window(dialog)
        return result["ok"]

    def _force_focus_self(self):
        hwnd = ctypes.wintypes.HWND(self.root.winfo_id())
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        for _ in range(3):
            if user32.SetForegroundWindow(hwnd):
                break
            user32.SwitchToThisWindow(hwnd, True)
            time.sleep(0.02)
        self.root.after(200, lambda: user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE))

    def _start(self):
        mode = self.mode_var.get()
        if mode == "advanced":
            if not self._show_advanced_warning():
                self.on_log("用户取消了进阶模式启用", "info")
                return
            self.on_log("=== 进阶模式警告已确认 ===", "warn")

        # 保存配置
        self.config["guards"]["minimize"] = self.prevent_minimize_var.get()
        self.config["guards"]["keyboard"] = self.keep_keyboard_var.get()
        self.config["guards"]["activity_faker"] = self.activity_faker_var.get()
        save_config(self.config)

        self.guard.update_params(
            self.threshold_var.get() / 100.0,
            self.interval_var.get(),
            mode,
            self.prevent_minimize_var.get(),
            self.keep_keyboard_var.get(),
            self.activity_faker_var.get(),
        )
        self.guard.start()
        self.status_label.config(text="● 运行中", foreground="green")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.rb_normal.config(state=tk.DISABLED)
        self.rb_advanced.config(state=tk.DISABLED)
        self.cb_prevent_minimize.config(state=tk.DISABLED)
        self.cb_keep_keyboard.config(state=tk.DISABLED)
        self.cb_activity_faker.config(state=tk.DISABLED)
        self.on_log("=== 开始 ===", "info")

    def _stop(self):
        self._force_focus_self()
        self.guard.stop()
        self._force_focus_self()

        self.status_label.config(text="● 已停止", foreground="gray")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.rb_normal.config(state=tk.NORMAL)
        self.rb_advanced.config(state=tk.NORMAL)
        self._on_mode_change()
        self.on_log("=== 停止 ===", "info")

    def _clear_log(self):
        self.log_box.delete(1.0, tk.END)

    def _schedule_refresh(self):
        self.root.after(500, self._schedule_refresh)

    def on_close(self):
        self._stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


# ========== 键盘钩子子进程 ==========
def run_kb_worker():
    """键盘钩子子进程 — 极简，无UI、无扫描、无日志，独立 GIL 不阻塞主进程"""
    @KeyboardProcType
    def callback(nCode, wParam, lParam):
        if nCode < 0:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)
        vkCode = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_uint))[0]
        if vkCode == VK_LWIN or vkCode == VK_RWIN:
            if wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN:
                os.write(1, b"WIN\n")
            return 0
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    hmod = kernel32.GetModuleHandleW(None)
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, hmod, 0)
    if not hook:
        sys.exit(1)
    os.write(1, b"READY\n")

    msg = MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    user32.UnhookWindowsHookEx(hook)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        run_kb_worker()
        sys.exit(0)
    try:
        main()
    except Exception:
        _write_crash(*sys.exc_info())
        raise