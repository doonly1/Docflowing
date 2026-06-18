#!/usr/bin/env python3
"""
WordKeepAlive - 保持 Word 进程常驻（事件驱动版，无托盘）
功能：
  - 通过 WMI 事件监听 WINWORD.EXE 进程退出，即时重启隐藏实例
  - 无 UI，后台静默运行
  - 单实例互斥
  - 退出：taskkill /IM WordKeepAlive.exe 或 --stop 参数
用法：
  WordKeepAlive.exe          # 启动
  WordKeepAlive.exe --stop   # 停止已运行的实例
"""

import os
import sys
import signal
import threading
import ctypes
import tempfile
import pythoncom
import win32com.client

# ── 配置 ────────────────────────────────────────────────────────────────────
MUTEX_FILE = os.path.join(tempfile.gettempdir(), "WordKeepAlive_Mutex.txt")
STOP_FILE  = os.path.join(tempfile.gettempdir(), "WordKeepAlive_Stop.txt")

# 全局退出事件
_quit_event = threading.Event()
_is_starting = False
_owned_word = None


# ── 进程检测 ────────────────────────────────────────────────────────────────

def is_winword_running():
    try:
        wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\cimv2")
        col = wmi.ExecQuery(
            "SELECT Name FROM Win32_Process WHERE Name = 'WINWORD.EXE'"
        )
        for _ in col:
            return True
        return False
    except Exception:
        return False


def _is_process_alive(pid):
    try:
        pid = int(pid)
    except (ValueError, TypeError):
        return False
    PROCESS_QUERY_INFORMATION = 0x0400
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION, False, pid
    )
    if handle == 0:
        return False
    exit_code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return exit_code.value == 259  # STILL_ACTIVE


# ── 注册表优化 ──────────────────────────────────────────────────────────────

def apply_registry_optimizations():
    import winreg
    for version in range(12, 17):
        reg_path = rf"Software\Microsoft\Office\{version}.0\Word\Options"
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
            for name, val in [
                ("NoReReg", 1), ("NoRereg", 1),
                ("DisableBootCheck", 1), ("StartupVerifySSL", 0),
            ]:
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, val)
            winreg.CloseKey(key)
        except Exception:
            pass


# ── Word 启动 / 关闭 ───────────────────────────────────────────────────────

def start_hidden_word():
    global _is_starting, _owned_word
    if _is_starting:
        return
    _is_starting = True

    if is_winword_running():
        _is_starting = False
        return

    word_app = None
    for prog_id in ("Word.Application", "KWPS.Application"):
        try:
            pythoncom.CoInitialize()
            word_app = win32com.client.Dispatch(prog_id)
            if word_app is not None:
                break
        except Exception:
            continue

    if word_app is not None:
        try:
            word_app.Visible = False
            word_app.DisplayAlerts = False
            word_app.Documents.Add()
        except Exception:
            pass
        _owned_word = word_app

    _is_starting = False


def quit_word():
    global _owned_word
    if _owned_word is not None:
        try:
            _owned_word.Quit(SaveChanges=False)
        except Exception:
            pass
        _owned_word = None


# ── 单实例互斥 ──────────────────────────────────────────────────────────────

def check_single_instance():
    if os.path.exists(MUTEX_FILE):
        try:
            with open(MUTEX_FILE, "r") as f:
                pid = f.read().strip()
            if _is_process_alive(pid):
                return False
        except Exception:
            pass
        try:
            os.remove(MUTEX_FILE)
        except Exception:
            return False
    try:
        with open(MUTEX_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False


def cleanup():
    quit_word()
    try:
        if os.path.exists(MUTEX_FILE):
            os.remove(MUTEX_FILE)
    except Exception:
        pass
    try:
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)
    except Exception:
        pass


# ── 停止已有实例 ────────────────────────────────────────────────────────────

def stop_running_instance():
    """通过写入停止文件通知已有实例退出"""
    if not os.path.exists(MUTEX_FILE):
        print("WordKeepAlive 未在运行。")
        return True

    try:
        with open(MUTEX_FILE, "r") as f:
            pid = f.read().strip()
    except Exception:
        print("无法读取互斥文件。")
        return False

    # 写入停止文件，通知主进程退出
    try:
        with open(STOP_FILE, "w") as f:
            f.write("stop")
        print(f"已发送停止信号给 PID {pid}，等待退出...")
    except Exception:
        print("无法写入停止文件。")
        return False

    # 等待进程退出（最多 5 秒）
    import time
    for _ in range(50):
        if not _is_process_alive(pid):
            print("WordKeepAlive 已停止。")
            return True
        time.sleep(0.1)

    print("进程未响应，尝试强制终止...")
    os.system(f"taskkill /PID {pid} /F 2>nul")
    return True


# ── WMI 事件监听线程 ────────────────────────────────────────────────────────

def wmi_watch_thread():
    pythoncom.CoInitialize()
    try:
        wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\cimv2")
        watcher = wmi.ExecNotificationQuery(
            "SELECT * FROM __InstanceDeletionEvent"
            " WITHIN 0.1"
            " WHERE TargetInstance ISA 'Win32_Process'"
            " AND TargetInstance.Name = 'WINWORD.EXE'"
        )
    except Exception:
        _quit_event.set()
        return

    while not _quit_event.is_set():
        try:
            # 检查停止文件
            if os.path.exists(STOP_FILE):
                _quit_event.set()
                break
            event = watcher.NextEvent(10000)
            if event is not None and not _quit_event.is_set():
                if not os.path.exists(STOP_FILE):
                    start_hidden_word()
        except pythoncom.com_error:
            pass
        except Exception:
            pass


# ── 主入口 ──────────────────────────────────────────────────────────────────

def main():
    # 支持 --stop 参数
    if "--stop" in sys.argv or "/stop" in sys.argv:
        stop_running_instance()
        sys.exit(0)

    silent = "--silent" in sys.argv

    if not check_single_instance():
        pid = "未知"
        try:
            with open(MUTEX_FILE, "r") as f:
                pid = f.read().strip()
        except Exception:
            pass
        if not silent:
            ctypes.windll.user32.MessageBoxW(
                0, f"WordKeepAlive 已经在运行中（PID: {pid}）。", "提示", 0x40
            )
        sys.exit(0)

    apply_registry_optimizations()
    pythoncom.CoInitialize()
    start_hidden_word()

    # 启动成功提示（仅非静默模式弹窗）
    if not silent:
        ctypes.windll.user32.MessageBoxW(
            0,
            "WordKeepAlive 已启动。\n按 Ctrl+C 或运行 WordKeepAlive.exe --stop 停止。",
            "WordKeepAlive",
            0x40,
        )

    # 启动 WMI 监听线程
    t_wmi = threading.Thread(target=wmi_watch_thread, daemon=True)
    t_wmi.start()

    # 主线程：轮询等待退出信号，支持 Ctrl+C
    if not silent:
        print("WordKeepAlive 运行中，按 Ctrl+C 退出...")
    try:
        while not _quit_event.wait(timeout=0.5):
            pass
    except KeyboardInterrupt:
        _quit_event.set()
    cleanup()
    if not silent:
        print("WordKeepAlive 已退出。")


if __name__ == "__main__":
    main()
