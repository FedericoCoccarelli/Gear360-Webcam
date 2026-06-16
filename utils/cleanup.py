"""
utils/cleanup.py — Emergency USB cleanup and Windows console signal handling.

Registers handlers that send CCTRL STREAM STOP and release USB resources
in every termination scenario:
  - Normal exit / sys.exit()        → atexit
  - Ctrl+C                          → KeyboardInterrupt (handled in main)
  - Forced window close / Ctrl+Break
  - User logoff / system shutdown   → SetConsoleCtrlHandler (Windows only)
"""

import sys
import atexit
import threading
import usb.util

from utils.cctrl import cctrl_send

# ---------------------------------------------------------------------------
# Shared USB state — populated by register_usb_state() after open_interfaces()
# ---------------------------------------------------------------------------

_usb_state: dict = {"ep_out": None, "ep_in_cctrl": None, "dev": None}
_cleanup_lock = threading.Lock()
_cleanup_done = False


# ---------------------------------------------------------------------------
# Core cleanup function
# ---------------------------------------------------------------------------

def emergency_stop(reason: str = "signal") -> None:
    """Send STREAM STOP and release USB resources.

    Idempotent and thread-safe: subsequent calls after the first are no-ops.
    Designed to be called from atexit, signal handlers, and finally blocks.
    """
    global _cleanup_done
    with _cleanup_lock:
        if _cleanup_done:
            return
        _cleanup_done = True

    ep_out      = _usb_state.get("ep_out")
    ep_in_cctrl = _usb_state.get("ep_in_cctrl")
    dev         = _usb_state.get("dev")

    if ep_out is not None and ep_in_cctrl is not None:
        try:
            print(f"\n[CLEANUP] {reason} — sending STREAM STOP...")
            resp = cctrl_send(ep_out, ep_in_cctrl, "CCTRL STREAM STOP")
            print(f"[CLEANUP] STREAM STOP -> {resp}")
        except Exception as exc:
            print(f"[CLEANUP] STREAM STOP error: {exc}")

    if dev is not None:
        try:
            usb.util.dispose_resources(dev)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_usb_state(ep_out, ep_in_cctrl, dev) -> None:
    """Store USB handles so emergency_stop() can reach them from any context.

    Call this immediately after open_interfaces() succeeds in main().
    """
    _usb_state["ep_out"]      = ep_out
    _usb_state["ep_in_cctrl"] = ep_in_cctrl
    _usb_state["dev"]         = dev


def register_cleanup_handlers() -> None:
    """Register emergency_stop() with atexit and (on Windows) with the
    console control handler so it fires on forced window close, Ctrl+Break,
    user logoff, and system shutdown.

    Call once at program startup, before any USB activity.
    """
    # atexit: covers normal sys.exit() and end-of-script
    atexit.register(emergency_stop, "program exit")

    # Windows console control handler
    if sys.platform != "win32":
        return

    import ctypes

    CTRL_C_EVENT        = 0
    CTRL_BREAK_EVENT    = 1
    CTRL_CLOSE_EVENT    = 2
    CTRL_LOGOFF_EVENT   = 5
    CTRL_SHUTDOWN_EVENT = 6

    _CTRL_REASONS = {
        CTRL_C_EVENT:        "Ctrl+C",
        CTRL_BREAK_EVENT:    "Ctrl+Break",
        CTRL_CLOSE_EVENT:    "console window closed",
        CTRL_LOGOFF_EVENT:   "user logoff",
        CTRL_SHUTDOWN_EVENT: "system shutdown",
    }

    HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

    @HandlerRoutine
    def _console_ctrl_handler(ctrl_type: int) -> bool:
        reason = _CTRL_REASONS.get(ctrl_type, f"ctrl event {ctrl_type}")
        emergency_stop(reason)
        return False  # let the default handler proceed (terminates the process)

    # Keep a module-level reference so the GC does not collect the callback
    register_cleanup_handlers._win_handler = _console_ctrl_handler
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_ctrl_handler, True)
