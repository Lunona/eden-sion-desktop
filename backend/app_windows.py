"""Launch installed applications and operate on revalidated native windows."""
import json
import os
import sys
import time
import unicodedata
from pathlib import Path

import psutil
import pythoncom
import pywintypes
import win32con
import win32gui
import win32process
from win32com.shell import shell, shellcon


SYSTEM_IMAGES = {
    "applicationframehost.exe", "consent.exe", "credentialuibroker.exe",
    "lockapp.exe", "logonui.exe", "searchhost.exe", "securityhealthsystray.exe",
    "shellexperiencehost.exe", "startmenuexperiencehost.exe", "systemsettings.exe",
    "taskmgr.exe", "textinputhost.exe", "winlogon.exe",
}
COMMAND_IMAGES = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "wt.exe", "windowsterminal.exe",
    "wscript.exe", "cscript.exe", "mshta.exe", "rundll32.exe", "regsvr32.exe",
    "bash.exe", "wsl.exe",
}


def packaged_window_process(hwnd):
    if win32gui.GetClassName(hwnd) != "ApplicationFrameWindow":
        return None
    pids = set()

    def inspect(child, _):
        if win32gui.GetClassName(child) == "Windows.UI.Core.CoreWindow":
            pids.add(win32process.GetWindowThreadProcessId(child)[1])
        return True

    win32gui.EnumChildWindows(hwnd, inspect, None)
    return psutil.Process(pids.pop()) if len(pids) == 1 else None


def window_identity(hwnd, include_packaged=False):
    try:
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return None
        title = win32gui.GetWindowText(hwnd)[:256]
        if not title or win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        image = process.exe()
        executable = os.path.basename(image).casefold()
        if include_packaged and executable == "applicationframehost.exe":
            # Use the app's process for receipts, leaving close-window targets unchanged.
            process = packaged_window_process(hwnd)
            if process is None:
                return None
            image = process.exe()
            executable = os.path.basename(image).casefold()
        if executable in SYSTEM_IMAGES:
            return None
        if executable == "explorer.exe" and win32gui.GetClassName(hwnd) != "CabinetWClass":
            return None
        return {"hwnd": hwnd, "pid": process.pid, "image": image, "created": process.create_time(), "title": title}
    except (psutil.Error, pywintypes.error):
        return None


def find_windows(include_packaged=False):
    windows = []

    def inspect(hwnd, _):
        identity = window_identity(hwnd, include_packaged)
        if identity:
            windows.append(identity)
        return True

    win32gui.EnumWindows(inspect, None)
    return windows


def app_name(value):
    return unicodedata.normalize("NFKC", value).casefold().strip()


def start_menu_targets(name):
    targets = {}
    for folder in (shellcon.CSIDL_PROGRAMS, shellcon.CSIDL_COMMON_PROGRAMS):
        root = Path(shell.SHGetFolderPath(0, folder, None, 0))
        for shortcut in root.rglob("*.lnk"):
            if app_name(shortcut.stem) != name:
                continue
            try:
                link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                                  pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
                link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(shortcut))
                executable = Path(os.path.expandvars(link.GetPath(shell.SLGP_RAWPATH)[0]))
                if not executable.is_absolute() or executable.suffix.casefold() != ".exe" or not executable.is_file():
                    continue
                executable = executable.resolve()
                arguments = link.GetArguments()
                working_dir = os.path.expandvars(link.GetWorkingDirectory())
                key = (os.path.normcase(executable), arguments)
                targets.setdefault(key, (executable, arguments, working_dir, link.GetShowCmd()))
            except (OSError, pywintypes.com_error):
                continue
    return list(targets.values())


def launch_installed_app(name):
    targets = start_menu_targets(app_name(name))
    if not targets:
        return {"status": "not-found"}
    if len(targets) != 1:
        return {"status": "ambiguous"}
    executable, arguments, working_dir, show_cmd = targets[0]
    if executable.name.casefold() in COMMAND_IMAGES:
        return {"status": "blocked"}

    image = os.path.normcase(executable)

    def app_windows():
        return [window for window in find_windows(include_packaged=True)
                if os.path.normcase(window["image"]) == image and not win32gui.IsIconic(window["hwnd"])]

    def identity(window):
        return window["hwnd"], window["pid"], window["created"]

    before = {identity(window) for window in app_windows()}
    if any(hwnd == win32gui.GetForegroundWindow() for hwnd, _, _ in before):
        return {"status": "already-open"}
    try:
        os.startfile(str(executable), "open", arguments, working_dir or None, show_cmd)
    except OSError:
        return {"status": "failed"}

    deadline = time.monotonic() + (1 if before else 5)
    while True:
        windows = app_windows()
        foreground = win32gui.GetForegroundWindow()
        if any(identity(window) not in before or window["hwnd"] == foreground for window in windows):
            return {"status": "confirmed"}
        if time.monotonic() >= deadline:
            return {"status": "already-open" if windows else "submitted"}
        time.sleep(0.15)


def close_window(target):
    hwnd = target["hwnd"]
    if window_identity(hwnd) != target:
        return {"status": "changed"}
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    for _ in range(20):
        time.sleep(0.1)
        if not win32gui.IsWindowVisible(hwnd):
            return {"status": "hidden"}
    return {"status": "requested"}


def qq_processes():
    psutil.process_iter.cache_clear()
    owner = psutil.Process().username().casefold()
    matches = []
    for process in psutil.process_iter(["name"]):
        if (process.info["name"] or "").casefold() != "qq.exe":
            continue
        try:
            data = process.as_dict(attrs=["exe", "username", "create_time", "ppid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if not data["exe"] or (data["username"] or "").casefold() != owner:
            continue
        matches.append((process, {"pid": process.pid, "created": data["create_time"],
                                  "image": os.path.normcase(data["exe"]), "parent": data["ppid"]}))
    return matches


def quit_qq(targets):
    matches = qq_processes()
    current = [identity for _, identity in matches]
    if not targets or len({target["image"] for target in targets}) != 1:
        return {"status": "changed"}
    approved = {target["pid"]: target for target in targets}
    if not current:
        return {"status": "gone"}
    if any(approved.get(identity["pid"]) != identity for identity in current):
        return {"status": "changed"}
    pids = {identity["pid"] for identity in current}
    for process, identity in sorted(matches, key=lambda item: item[1]["parent"] in pids):
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    psutil.wait_procs([process for process, _ in matches], timeout=2)
    remaining = len(qq_processes())
    return {"status": "remaining", "count": remaining} if remaining else {"status": "gone"}


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "find":
        result = find_windows()
    elif mode == "find-launch":
        result = find_windows(include_packaged=True)
    elif mode == "launch":
        result = launch_installed_app(json.loads(sys.argv[2]))
    elif mode == "close":
        result = close_window(json.loads(sys.argv[2]))
    elif mode == "find-qq":
        result = [identity for _, identity in qq_processes()]
    elif mode == "quit-qq":
        result = quit_qq(json.loads(sys.argv[2]))
    else:
        raise ValueError("Unknown operation")
    print(json.dumps(result, ensure_ascii=True))
