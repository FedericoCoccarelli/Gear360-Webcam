"""
gear360_webcam.py — Entry point for the Samsung Gear 360 virtual webcam.

Startup sequence:
  0. Verify WinUSB drivers          (utils/driver_check.py)
  1. Switch camera to VR360 mode    (utils/mtp_switch.py)
  2. Wait for USB re-enumerate
  3. Open USB interfaces
  4. Send CCTRL init sequence       (utils/cctrl.py)
  5. Start STREAM and pipe video    (utils/video_stream.py)
  6. On exit: send STREAM STOP      (utils/cleanup.py)
"""

import os
import sys
import time

# Force UTF-8 stdout so binary framing bytes from the camera don't produce
# garbled characters in cmd.exe / Windows Terminal (default cp1252/cp437).
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import usb.core
import usb.util
import libusb_package

from utils.driver_check import verify_drivers
from utils.mtp_switch   import switch_to_vr360
from utils.cctrl        import cctrl_sequence, cctrl_send
from utils.video_stream import pipe_to_opencv
from utils.config       import load_config, parse_cctrl_profile
from utils.cleanup      import register_cleanup_handlers, register_usb_state, emergency_stop

# VID/PID of the camera in VR360 streaming mode (from pcap: 04e8:a50c)
VID_VR360 = 0x04e8
PID_VR360 = 0xa50c


# ---------------------------------------------------------------------------
# USB helpers
# ---------------------------------------------------------------------------

def wait_for_vr360(timeout: int = 15):
    """Poll USB until the Gear 360 re-enumerates as a VR360 device."""
    print(f"[USB] Waiting for VR360 device {VID_VR360:04x}:{PID_VR360:04x}...")
    t0      = time.time()
    backend = libusb_package.get_libusb1_backend()
    while time.time() - t0 < timeout:
        dev = usb.core.find(idVendor=VID_VR360, idProduct=PID_VR360, backend=backend)
        if dev:
            print("[USB] Device found!")
            return dev
        time.sleep(0.5)
    raise RuntimeError("Timeout: VR360 camera not found via USB")


def open_interfaces(dev):
    """Claim Interface 0 and return (ep_out, ep_in_cctrl, ep_in_video)."""
    try:
        dev.set_configuration()
    except Exception as e:
        print(f"[USB] Info: set_configuration failed (normal on Windows): {e}")

    intf = dev[0].interfaces()[0]
    usb.util.claim_interface(dev, intf.bInterfaceNumber)

    ep_out      = usb.util.find_descriptor(intf, custom_match=lambda e: e.bEndpointAddress == 0x02)
    ep_in_cctrl = usb.util.find_descriptor(intf, custom_match=lambda e: e.bEndpointAddress == 0x82)
    ep_in_video = usb.util.find_descriptor(intf, custom_match=lambda e: e.bEndpointAddress == 0x81)

    return ep_out, ep_in_cctrl, ep_in_video


def query_active_resolution(ep_out, ep_in_cctrl,
                             fallback_w: int, fallback_h: int) -> tuple[int, int]:
    """Ask the camera for its current resolution; return fallback on failure."""
    try:
        resp = cctrl_send(ep_out, ep_in_cctrl, "CCTRL GET STATUS RESOLUTION")
        print(f"[CCTRL] Camera active resolution: {resp}")
        if resp:
            res_str = resp.split()[-1]
            if "x" in res_str:
                w, h = res_str.split("x")
                width, height = int(w), int(h)
                print(f"[CCTRL] Dynamic resolution: {width}x{height}")
                return width, height
    except Exception as e:
        print(f"[CCTRL] Warning: could not query resolution, using config defaults: {e}")
    return fallback_w, fallback_h


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Step 0: register emergency cleanup handlers (window close, logoff, etc.)
    register_cleanup_handlers()

    # Step 1: verify WinUSB drivers for both Gear 360 USB modes
    verify_drivers(abort_on_failure=True)

    # Step 2: load configuration
    config = load_config()

    # Step 3: switch camera from MTP to VR360 mode
    switch_to_vr360()

    # Step 4: wait for re-enumerate
    dev = wait_for_vr360(timeout=15)

    # Step 5: open USB interfaces
    print("[USB] Opening interfaces...")
    try:
        ep_out, ep_in_cctrl, ep_in_video = open_interfaces(dev)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[USB] ERROR opening interfaces: {e}")
        print("      Make sure you have installed WinUSB on both interfaces with Zadig")
        sys.exit(1)

    # Expose handles so emergency_stop() can reach them from any context
    register_usb_state(ep_out, ep_in_cctrl, dev)

    print(
        f"[USB] ep_out=0x{ep_out.bEndpointAddress:02X}  "
        f"ep_in_cctrl=0x{ep_in_cctrl.bEndpointAddress:02X}  "
        f"ep_in_video=0x{ep_in_video.bEndpointAddress:02X}"
    )

    # Step 6: CCTRL init sequence
    cctrl_profile = parse_cctrl_profile(config.get("stream_quality_profile", 51))
    print("[CCTRL] Sending initialization sequence...")
    cctrl_sequence(
        ep_out, ep_in_cctrl,
        lens_mode=config.get("lens_mode", 1),
        stream_quality_profile=cctrl_profile,
    )

    # Step 7: STREAM START
    print("[CCTRL] STREAM START...")
    resp = cctrl_send(ep_out, ep_in_cctrl, "CCTRL STREAM START")
    print(f"  -> {resp}")
    if "SUCCESS" not in resp:
        print("[CCTRL] STREAM START failed!")
        sys.exit(1)

    # Step 8: query actual resolution, then start video pipeline
    actual_width, actual_height = query_active_resolution(
        ep_out, ep_in_cctrl,
        fallback_w=config.get("cam_width",  1920),
        fallback_h=config.get("cam_height", 1080),
    )

    try:
        pipe_to_opencv(
            ep_in_video,
            fps=config.get("fps", 30),
            cam_width=actual_width,
            cam_height=actual_height,
            brightness=config.get("brightness", 0),
            contrast=config.get("contrast", 1.0),
            show_preview=config.get("preview", True),
            use_virtual_cam=config.get("virtual_camera", True),
            post_processing=config.get("post_processing", {}),
        )
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    finally:
        # emergency_stop() is idempotent — safe even if the console handler
        # already triggered it on a forced close.
        emergency_stop("normal shutdown")


if __name__ == "__main__":
    main()