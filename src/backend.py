#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Root backend for the Framely plugin ``dhies23.frame-fan-panel``.

This backend does not reimplement fan control.  It installs, enables, disables
and removes the *standalone* Steam Frame fan panel that ships in
``dhies23/steam-frame-fan-panel``, and it reports whether that panel is
installed / enabled / running together with a live fan + temperature snapshot.

The payload carries a vendored copy of the panel (``sf_fan_qamd.py``,
``sf_fan_qam.js``, ``sf-fan-qamd.service``, ``VERSION``) so the plugin works
fully offline, and it uses exactly the same paths as the standalone installer::

    /home/<steam user>/sf-fan-qam        # program + docs
    /etc/systemd/system/sf-fan-qamd.service

Because the paths and unit name match, a device that already ran the standalone
``install.sh`` is reported as installed, and either installer can clean up after
the other.

Why root: the panel writes ``/sys/class/hwmon/<slg4ax46073v>/pwm1`` and must be
able to stop and start ``deckard-fan-control.service``.  The plugin page itself
needs no elevated permissions.

Safety rule followed everywhere below: no failure path may leave the device
without thermal control, so anything that could strand a manual fan speed ends
by starting ``deckard-fan-control.service`` again.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from framely import emit, serve  # noqa: E402

PAYLOAD = pathlib.Path(__file__).resolve().parent
SERVICE = "sf-fan-qamd.service"
STOCK = "deckard-fan-control.service"
FAN_HWMON_NAME = "slg4ax46073v"
HW = pathlib.Path("/sys/class/hwmon")
IIO = pathlib.Path("/sys/bus/iio/devices/iio:device0")

# payload name -> (installed name, mode)
PAYLOAD_FILES = {
    "sf_fan_qamd.py": ("sf_fan_qamd.py", 0o755),
    "sf_fan_qam.js": ("sf_fan_qam.js", 0o644),
    "sf-fan-qamd.service": ("sf-fan-qamd.service", 0o644),
    "VERSION": ("VERSION", 0o644),
    "README.md": ("README.md", 0o644),
}

CPU_SENSORS = ["cpu%d_thermal" % i for i in range(8)] + ["cpuss%d_thermal" % i for i in range(4)]
GPU_SENSORS = ["gpuss_%d_thermal" % i for i in range(5)]
SOC_EXTRA = ["aoss0_thermal", "aoss1_thermal", "aoss2_thermal", "video_thermal",
             "nsphvx0_thermal", "nsphvx1_thermal", "nsphmx0_thermal",
             "nsphmx1_thermal", "nsphmx2_thermal", "nsphmx3_thermal", "modem3_thermal"]


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def run(args, timeout=25, check=False):
    """Run a fixed argv (never a shell string) and return the completed process."""
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise RuntimeError((result.stdout or "").strip()[-800:]
                           or ("命令失败：" + " ".join(args)))
    return result


def read_int(path):
    try:
        return int(pathlib.Path(path).read_text().strip())
    except Exception:
        return None


def hwmon_dirs():
    if not HW.is_dir():
        return []
    return sorted(HW.glob("hwmon*"))


def hwmon_named(name):
    for entry in hwmon_dirs():
        try:
            if (entry / "name").read_text().strip() == name:
                return entry
        except OSError:
            continue
    return None


def fan_dir():
    return hwmon_named(FAN_HWMON_NAME)


def active(unit):
    return run(["systemctl", "is-active", unit], timeout=10).stdout.strip() == "active"


def enabled(unit):
    return run(["systemctl", "is-enabled", unit], timeout=10).stdout.strip() == "enabled"


def unit_known():
    return UNIT.is_file() or run(["systemctl", "cat", SERVICE], timeout=10).returncode == 0


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(262144), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# steam user / install layout
# --------------------------------------------------------------------------

def steam_user():
    """The account that actually runs Steam, exactly like the standalone installer."""
    try:
        listing = run(["ps", "-eo", "user:32,args"], timeout=10).stdout
    except Exception:
        listing = ""
    for line in listing.splitlines()[1:]:
        parts = line.split(None, 1)
        if len(parts) == 2 and "steamwebhelper" in parts[1] and "awk" not in parts[1]:
            return parts[0]
    return "steamos"


def install_dir():
    return pathlib.Path("/home") / steam_user() / "sf-fan-qam"


UNIT = pathlib.Path("/etc/systemd/system") / SERVICE


# --------------------------------------------------------------------------
# live state
# --------------------------------------------------------------------------

def fan_read():
    d = fan_dir()
    if d is None:
        return None, None
    raw = read_int(d / "fan1_input")
    pwm = read_int(d / "pwm1")
    # Delta fan on this board: two tach periods per revolution.
    return (None if raw is None else raw / 2.0), pwm


def hwmon_temp(name):
    entry = hwmon_named(name)
    if entry is None:
        return None
    value = read_int(entry / "temp1_input")
    return None if value is None else value / 1000.0


def iio_temp(node):
    value = read_int(IIO / node)
    return None if value is None else value / 1000.0


def read_temps():
    def mx(names):
        values = [hwmon_temp(n) for n in names]
        values = [v for v in values if v is not None]
        return max(values) if values else None

    return {
        "cpu": mx(CPU_SENSORS),
        "gpu": mx(GPU_SENSORS),
        "soc": mx(CPU_SENSORS + GPU_SENSORS + SOC_EXTRA),
        "ddr": hwmon_temp("ddr_thermal"),
        "heatsink": iio_temp("in_temp_pcba_at_heat_sink_fins_input"),
        "exhaust": iio_temp("in_temp_pcba_at_fan_exhaust_input"),
    }


def daemon_state():
    directory = install_dir()
    state = {"installed": False, "enabled": False, "active": False,
             "pid": None, "since": None, "version": None, "path": str(directory)}
    state["installed"] = (directory / "sf_fan_qamd.py").is_file() and unit_known()
    if not state["installed"]:
        return state
    state["enabled"] = enabled(SERVICE)
    state["active"] = active(SERVICE)
    version = directory / "VERSION"
    try:
        state["version"] = version.read_text().strip()[:32]
    except OSError:
        pass
    if state["active"]:
        props = run(["systemctl", "show", SERVICE, "-p", "MainPID",
                     "-p", "ActiveEnterTimestamp"], timeout=10).stdout
        for line in props.splitlines():
            if line.startswith("MainPID="):
                value = line.split("=", 1)[1].strip()
                state["pid"] = int(value) if value.isdigit() and value != "0" else None
            elif line.startswith("ActiveEnterTimestamp="):
                state["since"] = line.split("=", 1)[1].strip() or None
    return state


def snapshot():
    rpm, pwm = fan_read()
    return {
        "rpm": None if rpm is None else int(round(rpm)),
        "pwm": pwm,
        # The panel daemon stops the stock controller while it holds a manual
        # speed, so "who is active" is also "which mode the fan is in".
        "mode": "auto" if active(STOCK) else "manual",
        "temps": read_temps(),
        "stockActive": active(STOCK),
    }


def full_status():
    d = fan_dir()
    return {
        "hardware": {
            "supported": d is not None,
            "fanPath": None if d is None else str(d),
            "message": None if d is not None else
                       "没有找到 Steam Frame 的风扇控制器（hwmon " + FAN_HWMON_NAME + "）",
        },
        "daemon": daemon_state(),
        "snapshot": snapshot(),
        "bundled": bundled_version(),
        "unit": {"name": SERVICE, "path": str(UNIT)},
        "stock": {"name": STOCK, "active": active(STOCK)},
    }


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def bundled_version():
    version = PAYLOAD / "VERSION"
    try:
        return version.read_text().strip()[:32]
    except OSError:
        return None


def require_hardware():
    if fan_dir() is None:
        raise RuntimeError("这台设备上没有 Steam Frame 的风扇控制器，插件不会改动任何东西")


def stage(force=False):
    """Copy the bundled panel into the install directory and write the unit."""
    require_hardware()
    for source in PAYLOAD_FILES:
        if not (PAYLOAD / source).is_file():
            raise RuntimeError("插件包不完整：缺少 " + source)

    directory = install_dir()
    directory.mkdir(parents=True, exist_ok=True)
    owner = steam_user()
    for source, (target, mode) in PAYLOAD_FILES.items():
        destination = directory / target
        if not force and destination.is_file() and sha256(destination) == sha256(PAYLOAD / source):
            continue
        shutil.copyfile(PAYLOAD / source, destination)
        os.chmod(destination, mode)
    if owner != "root":
        run(["chown", "-R", owner + ":" + owner, str(directory)])

    unit_text = (PAYLOAD / "sf-fan-qamd.service").read_text()
    unit_text = unit_text.replace("@INSTALL_DIR@", str(directory))
    if "@INSTALL_DIR@" in unit_text:
        raise RuntimeError("systemd 单元里的安装路径没有被替换")
    UNIT.write_text(unit_text)
    os.chmod(UNIT, 0o644)
    run(["systemctl", "daemon-reload"], check=True)
    return {"directory": str(directory), "version": bundled_version()}


def start_panel():
    run(["systemctl", "enable", SERVICE], check=True)
    run(["systemctl", "start", SERVICE], check=True)
    for _ in range(12):
        time.sleep(0.5)
        if active(SERVICE):
            return True
    return False


def restore_stock():
    run(["systemctl", "start", STOCK])
    for _ in range(8):
        time.sleep(0.4)
        if active(STOCK):
            return True
    return False


def rollback(reason):
    run(["systemctl", "stop", SERVICE])
    ok = restore_stock()
    log = run(["journalctl", "-u", SERVICE, "-n", "12", "--no-pager", "-o", "cat"],
              timeout=15).stdout.strip()
    raise RuntimeError(reason + "，已回滚。" + ("" if ok else
                       " 注意：系统温控没有起来，请手动执行：sudo systemctl start " + STOCK)
                       + ("\n最近日志：\n" + log[-700:] if log else ""))


def cmd_status(params):
    return full_status()


def cmd_install(params):
    result = stage()
    if not start_panel():
        rollback("风扇面板启动失败")
    emit("progress", {"percent": 100})
    return {"ok": True, "staged": result, "status": full_status(),
            "message": "已安装并启用风扇面板（" + (result["version"] or "未知版本") + "）"}


def cmd_enable(params):
    if not (install_dir() / "sf_fan_qamd.py").is_file():
        # Nothing on disk yet: install it the same way.
        return cmd_install(params)
    if not start_panel():
        rollback("启用风扇面板失败")
    return {"ok": True, "status": full_status(), "message": "风扇面板已启用"}


def cmd_disable(params):
    if unit_known():
        run(["systemctl", "stop", SERVICE])
        run(["systemctl", "disable", SERVICE])
    if not restore_stock():
        raise RuntimeError("系统温控没有起来，请手动执行：sudo systemctl start " + STOCK)
    return {"ok": True, "status": full_status(),
            "message": "已停用，风扇交回系统温控（下次开机不会自动启动）"}


def cmd_uninstall(params):
    run(["systemctl", "stop", SERVICE])
    run(["systemctl", "disable", SERVICE])
    if UNIT.is_file():
        UNIT.unlink()
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "reset-failed", SERVICE])

    directory = install_dir()
    if directory.is_dir():
        # Guard the path before deleting anything, and only delete a directory
        # that really is the panel (it must contain our own files).
        guarded = str(directory).startswith("/home/") and str(directory).endswith("/sf-fan-qam")
        panel_like = (directory / "sf_fan_qamd.py").is_file() or (directory / "sf_fan_qam.js").is_file()
        if guarded and panel_like:
            shutil.rmtree(directory, ignore_errors=True)
        else:
            raise RuntimeError("安装目录 " + str(directory) + " 看起来不是本插件创建的，已保留不动")

    if not restore_stock():
        raise RuntimeError("系统温控没有起来，请手动执行：sudo systemctl start " + STOCK)
    return {"ok": True, "status": full_status(),
            "message": "已卸载，风扇交回系统温控。界面上的风扇标签会在 QAM 重新渲染后消失"}


def cmd_set_auto(params):
    run(["systemctl", "stop", SERVICE])
    if not restore_stock():
        raise RuntimeError("系统温控没有起来，请手动执行：sudo systemctl start " + STOCK)
    return {"ok": True, "status": full_status(), "message": "已交回系统温控"}


def dispatch(method, params):
    handlers = {
        "status": cmd_status,
        "install": cmd_install,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "uninstall": cmd_uninstall,
        "setAuto": cmd_set_auto,
    }
    handler = handlers.get(method)
    if handler is None:
        raise ValueError("Unknown method: " + str(method))
    return handler(params or {})


# --------------------------------------------------------------------------
# lifecycle (standalone hooks run with FRAMELY_LIFECYCLE set, then exit)
# --------------------------------------------------------------------------

def on_install(context):
    """First install: verify the device and make sure the fan is the stock one.

    The panel itself is only written to disk when the user presses 安装, so that
    installing the plugin never silently changes how the fan is driven.
    """
    return {
        "supported": fan_dir() is not None,
        "stockActive": active(STOCK),
        "bundled": bundled_version(),
        "version": context.get("version"),
    }


def on_update(context):
    return on_install(context)


def on_start(context):
    return {"daemon": daemon_state()}


def on_stop(context):
    return {"ok": True}


def on_uninstall(context):
    """Remove the panel and always hand the fan back to the stock controller."""
    try:
        run(["systemctl", "stop", SERVICE])
        run(["systemctl", "disable", SERVICE])
    except Exception:
        pass
    try:
        if UNIT.is_file():
            UNIT.unlink()
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "reset-failed", SERVICE])
    except Exception:
        pass
    directory = install_dir()
    try:
        if (directory.is_dir() and str(directory).startswith("/home/")
                and str(directory).endswith("/sf-fan-qam")
                and ((directory / "sf_fan_qamd.py").is_file() or (directory / "sf_fan_qam.js").is_file())):
            shutil.rmtree(directory, ignore_errors=True)
    except Exception:
        pass
    try:
        restore_stock()
    except Exception:
        pass
    return {"ok": True}


def on_crash_cleanup(context):
    # A crashed backend may have left a manual fan speed behind; give it back.
    try:
        if not active(SERVICE):
            restore_stock()
    except Exception:
        pass
    return {"ok": True}


if __name__ == "__main__":
    serve(dispatch, {
        "onInstall": on_install,
        "onUpdate": on_update,
        "onStart": on_start,
        "onStop": on_stop,
        "onUninstall": on_uninstall,
        "onCrashCleanup": on_crash_cleanup,
    })
