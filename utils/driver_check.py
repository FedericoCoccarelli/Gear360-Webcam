"""
driver_check.py — Pre-flight WinUSB driver verification for Samsung Gear 360.

Checks that both PID_6860 (Webcam/Streaming mode) and PID_A50C (MTP/Tizen mode)
have the WinUSB driver installed and are accessible via libusb/pyusb.
Must be called at startup, before any USB communication is attempted.
"""

import sys
import subprocess

# Samsung Gear 360 USB identifiers
GEAR360_VID   = 0x04E8
PID_MTP       = 0x6860   # Initial MTP/Tizen mode (camera powers on in this state)
PID_VR360     = 0xA50C   # VR360/Streaming mode (after switch_to_vr360)

ZADIG_URL = "https://zadig.akeo.ie"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _query_winusb_service(instance_id: str) -> str | None:
    """
    Returns the Service string for a PnP device via PowerShell.
    Returns None if the property cannot be read or the device is absent.
    """
    ps_cmd = (
        f"(Get-PnpDeviceProperty -InstanceId '{instance_id}' "
        f"-KeyName DEVPKEY_Device_Service -ErrorAction SilentlyContinue).Data"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=8
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _find_devices_by_pid(pid: int) -> list[dict]:
    """
    Returns a list of PnP device dicts matching VID 04E8 and the given PID,
    reading InstanceId, FriendlyName, Status, and Service from PowerShell.
    """
    ps_cmd = (
        f"Get-PnpDevice | Where-Object {{ $_.InstanceId -like '*PID_{pid:04X}*' }} | "
        f"Select-Object InstanceId, FriendlyName, Status | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10
        )
        import json
        raw = result.stdout.strip()
        if not raw:
            return []
        data = json.loads(raw)
        # PowerShell returns a single object (not array) when only one match
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception:
        return []


def _check_pid(pid: int, label: str) -> bool:
    """
    Verifies that at least one PnP entry for the given PID has Service == WinUSB.
    Prints a detailed status line.  Returns True if the check passes.
    """
    devices = _find_devices_by_pid(pid)

    if not devices:
        # Device not present in device manager at all → driver never installed
        print(f"  [DRIVER] PID_{pid:04X} ({label}): not found in Device Manager")
        print(f"           --> Install WinUSB via Zadig: {ZADIG_URL}")
        return False

    # Subdevice suffixes that appear alongside the main USB entry but are
    # not the WinUSB interface we care about (MTP composite, COM port, modem…)
    SKIP_MARKERS = ("MS_COMP_", "MODEM", "&MODEM", "COM")

    winusb_ok   = False
    main_checked = False  # track whether we found at least one top-level entry

    for dev in devices:
        iid  = dev.get("InstanceId", "")
        name = dev.get("FriendlyName", "?")

        # Skip sub-device entries that share the PID but are different functions
        if any(marker in iid for marker in SKIP_MARKERS):
            continue
        # Also skip COM-port sub-devices identified by their friendly name suffix
        if name.strip().endswith(")") and "(COM" in name:
            continue

        status  = dev.get("Status", "?")
        service = _query_winusb_service(iid) or "(unknown)"

        is_winusb    = service.lower() == "winusb"
        tag          = "[OK]" if is_winusb else "[!!]"
        main_checked = True

        print(f"  {tag} PID_{pid:04X} ({label})")
        print(f"       Name:    {name}")
        print(f"       Status:  {status}")
        print(f"       Service: {service}")

        if is_winusb:
            winusb_ok = True

    if not main_checked:
        # All entries were sub-devices; treat as missing
        print(f"  [!!] PID_{pid:04X} ({label}): no top-level USB device entry found")
        return False

    if not winusb_ok:
        print(f"       --> No WinUSB service found for PID_{pid:04X}.")
        print(f"           Open Zadig, select 'SAMSUNG_Tizen (PID_{pid:04X})', install WinUSB.")
        print(f"           Download: {ZADIG_URL}")

    return winusb_ok


def _check_libusb_backend() -> bool:
    """
    Verifies that libusb_package can expose a working libusb1 backend.
    """
    try:
        import libusb_package
        import usb.backend.libusb1
        backend = libusb_package.get_libusb1_backend()
        if backend is None:
            print("  [!!] libusb backend: could not initialize (libusb-1.0.dll missing?)")
            return False
        print(f"  [OK] libusb backend: {backend}")
        return True
    except ImportError as e:
        print(f"  [!!] Missing Python package: {e}")
        print("       Run: pip install pyusb libusb-package")
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_drivers(abort_on_failure: bool = True) -> bool:
    """
    Runs a complete pre-flight check:
      1. libusb backend reachable
      2. PID_6860 (MTP mode)  → WinUSB installed
      3. PID_A50C (VR360 mode) → WinUSB installed

    If abort_on_failure is True (default) and any check fails, prints
    instructions and calls sys.exit(1).

    Returns True if all checks pass, False otherwise.
    """
    print("[DRIVER CHECK] Verifying WinUSB drivers for Samsung Gear 360...")

    all_ok = True

    # 1. libusb backend
    print("\n  --- libusb backend ---")
    if not _check_libusb_backend():
        all_ok = False

    # 2. PID_6860 — initial MTP/Tizen mode
    print("\n  --- PID_6860 (MTP/Tizen — initial power-on mode) ---")
    if not _check_pid(PID_MTP, "MTP/Tizen initial mode"):
        all_ok = False

    # 3. PID_A50C — VR360 streaming mode
    print("\n  --- PID_A50C (VR360 — streaming mode after switch) ---")
    if not _check_pid(PID_VR360, "VR360 streaming mode"):
        all_ok = False

    # Result
    print()
    if all_ok:
        print("[DRIVER CHECK] All drivers OK — continuing.\n")
    else:
        print("[DRIVER CHECK] One or more driver checks FAILED.")
        print("  Both PID_6860 and PID_A50C must have WinUSB installed via Zadig.")
        print(f"  Download Zadig: {ZADIG_URL}\n")
        if abort_on_failure:
            sys.exit(1)

    return all_ok
