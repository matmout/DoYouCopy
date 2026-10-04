"""Start with Windows: a value under the HKCU Run key, no admin rights needed.

From the Microsoft Store package, HKCU writes are virtualized and the Run value would
never be seen: the package declares a StartupTask instead (TASK_ID, in
packaging/msix/AppxManifest.template.xml), switched on and off through WinRT.
"""

from __future__ import annotations

import logging
import sys

from doyoucopy.desktop import packaging
from doyoucopy.desktop.shortcuts import launch_target

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DoYouCopy"
TASK_ID = "DoYouCopyStartup"


def command() -> str:
    """DoYouCopy.exe --minimized, or pythonw.exe (no console) -m doyoucopy from a checkout:
    the same program as the shortcuts, started in the notification area."""
    return launch_target().command_line("--minimized")


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    if packaging.is_packaged():
        return _task_enabled()
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Returns False if the registry (or the StartupTask) could not be changed."""
    if sys.platform != "win32":
        return False
    if packaging.is_packaged():
        return _set_task(enabled)
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("Could not update the Run registry key")
        return False


def launched_at_logon() -> bool:
    """Started by the StartupTask: the package cannot pass --minimized to it, so the
    activation kind tells that DoYouCopy should start in the notification area."""
    if not packaging.is_packaged():
        return False
    try:
        from winrt.windows.applicationmodel import AppInstance
        from winrt.windows.applicationmodel.activation import ActivationKind

        activation = AppInstance.get_activated_event_args()
        return activation is not None and activation.kind == ActivationKind.STARTUP_TASK
    except Exception:
        log.exception("Could not read the activation kind")
        return False


# ---- StartupTask (Microsoft Store package) -----------------------------------------


def _run(operation):
    """Waits for a WinRT IAsyncOperation (they are awaitable)."""
    import asyncio

    async def wait():
        return await operation

    return asyncio.run(wait())


def _task():
    from winrt.windows.applicationmodel import StartupTask

    return _run(StartupTask.get_async(TASK_ID))


def _task_enabled() -> bool:
    from winrt.windows.applicationmodel import StartupTaskState

    try:
        return _task().state in (StartupTaskState.ENABLED, StartupTaskState.ENABLED_BY_POLICY)
    except Exception:
        log.exception("Could not read the StartupTask")
        return False


def _set_task(enabled: bool) -> bool:
    """Turned off by the user in Windows settings (or by a policy), the task cannot be
    turned back on from here: False, and the user is told where to do it."""
    from winrt.windows.applicationmodel import StartupTaskState

    try:
        task = _task()
        if not enabled:
            task.disable()
            return True
        state = _run(task.request_enable_async())
    except Exception:
        log.exception("Could not update the StartupTask")
        return False
    if state in (StartupTaskState.ENABLED, StartupTaskState.ENABLED_BY_POLICY):
        return True
    log.warning("StartupTask not enabled: %s", state)
    return False
