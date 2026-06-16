import os
import sys
import time
import json
import usb.core
import usb.util
import libusb_package

from utils.mtp_switch import switch_to_vr360
from utils.cctrl import cctrl_sequence, cctrl_send
from utils.video_stream import pipe_to_opencv

# VID/PID of the camera after switch (from pcap: 04e8:a50c)
VID_VR360 = 0x04e8
PID_VR360 = 0xa50c

def wait_for_vr360(timeout=15):
    print(f"[USB] Waiting for VR360 device {VID_VR360:04x}:{PID_VR360:04x}...")
    t0 = time.time()
    backend = libusb_package.get_libusb1_backend()
    while time.time() - t0 < timeout:
        dev = usb.core.find(idVendor=VID_VR360, idProduct=PID_VR360, backend=backend)
        if dev:
            print("[USB] Device found!")
            return dev
        time.sleep(0.5)
    raise RuntimeError("Timeout: VR360 camera not found via USB")

def open_interfaces(dev):
    try:
        dev.set_configuration()
    except Exception as e:
        print(f"[USB] Info: set_configuration failed (normal on Windows): {e}")

    # VR360 device has only one interface (Interface 0) with all endpoints
    intf = dev[0].interfaces()[0]
    usb.util.claim_interface(dev, intf.bInterfaceNumber)
    
    ep_out = usb.util.find_descriptor(intf,
        custom_match=lambda e: e.bEndpointAddress == 0x02)
    ep_in_cctrl = usb.util.find_descriptor(intf,
        custom_match=lambda e: e.bEndpointAddress == 0x82)
    ep_in_video = usb.util.find_descriptor(intf,
        custom_match=lambda e: e.bEndpointAddress == 0x81)

    return ep_out, ep_in_cctrl, ep_in_video


def load_config():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    config_path = os.path.join(base_dir, "config.json")
    
    defaults = {
        "preview": True,
        "virtual_camera": True,
        "stream_quality_profile": 51,
        "brightness": 0,
        "contrast": 1.0,
        "post_processing": {
            "enabled": True,
            "saturation": 1.2,
            "unsharp_msize": 3,
            "unsharp_amount": 0.5,
            "gamma": 1.0,
            "hue": 0.0,
            "denoise": False
        }
    }
    
    user_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
        except Exception as e:
            print(f"[CONFIG] Error reading {config_path}: {e}.")

    active_profile = str(user_config.get("stream_quality_profile", defaults["stream_quality_profile"]))

    profile_defaults = {}
    # Read profiles from the 'profiles' key in config.json
    profiles = user_config.get("profiles", {})
    if active_profile in profiles:
        profile_defaults = profiles[active_profile]
    elif active_profile + "-1" in profiles:
        active_profile = active_profile + "-1"
        profile_defaults = profiles[active_profile]

    if profile_defaults:
        print(f"[CONFIG] Profile {active_profile} applied: "
              f"{profile_defaults.get('cam_width')}x{profile_defaults.get('cam_height')} "
              f"@ {profile_defaults.get('fps')}fps, lens_mode: {profile_defaults.get('lens_mode')}")

    # Fallback profile details if profile is missing in config.json
    if not profile_defaults:
        profile_defaults = {
            "cam_width": 1920,
            "cam_height": 1080,
            "fps": 30,
            "lens_mode": 1
        }

    config = defaults.copy()
    config.update(profile_defaults)
    config.update(user_config)
    
    if not os.path.exists(config_path):
        try:
            with open(config_path, 'w') as f:
                default_profiles = {
                    "0": {"cam_width": 2560, "cam_height": 1280, "fps": 15, "lens_mode": 0},
                    "1": {"cam_width": 1920, "cam_height": 960, "fps": 30, "lens_mode": 0},
                    "2": {"cam_width": 1920, "cam_height": 960, "fps": 15, "lens_mode": 0},
                    "50-1": {"cam_width": 1920, "cam_height": 1080, "fps": 60, "lens_mode": 1},
                    "50-2": {"cam_width": 1920, "cam_height": 1080, "fps": 60, "lens_mode": 2},
                    "51-1": {"cam_width": 1920, "cam_height": 1080, "fps": 30, "lens_mode": 1},
                    "51-2": {"cam_width": 1920, "cam_height": 1080, "fps": 30, "lens_mode": 2},
                    "52-1": {"cam_width": 1280, "cam_height": 720, "fps": 30, "lens_mode": 1},
                    "52-2": {"cam_width": 1280, "cam_height": 720, "fps": 30, "lens_mode": 2}
                }

                user_defaults = {
                    "preview": True,
                    "virtual_camera": True,
                    "stream_quality_profile": 51,
                    "brightness": 0,
                    "contrast": 1.0,
                    "post_processing": {
                        "enabled": True,
                        "saturation": 1.2,
                        "unsharp_msize": 3,
                        "unsharp_amount": 0.5,
                        "gamma": 1.0,
                        "hue": 0.0,
                        "denoise": False
                    },
                    "profiles": default_profiles
                }

                json.dump(user_defaults, f, indent=4)
            print(f"[CONFIG] Created default configuration file: {config_path}")
        except Exception as e:
            print(f"[CONFIG] Could not write {config_path}: {e}")

    return config

def main():
    config = load_config()

    # Step 1: switch mode via MTP (always triggered)
    switch_to_vr360()

    # Step 2: wait for re-enumerate
    dev = wait_for_vr360(timeout=15)

    # Step 3: open interfaces
    print("[USB] Opening interfaces...")
    try:
        ep_out, ep_in_cctrl, ep_in_video = open_interfaces(dev)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[USB] ERROR opening interfaces: {e}")
        print("      Make sure you have installed WinUSB on both interfaces with Zadig")
        sys.exit(1)

    print(f"[USB] ep_out=0x{ep_out.bEndpointAddress:02X} "
          f"ep_in_cctrl=0x{ep_in_cctrl.bEndpointAddress:02X} "
          f"ep_in_video=0x{ep_in_video.bEndpointAddress:02X}")

    # Extract the base profile integer for the camera (e.g., "51-2" -> 51)
    raw_profile = config.get("stream_quality_profile", 51)
    try:
        if isinstance(raw_profile, str) and '-' in raw_profile:
            cctrl_profile = int(raw_profile.split('-')[0])
        else:
            cctrl_profile = int(raw_profile)
    except Exception:
        cctrl_profile = 51

    # Step 4: CCTRL sequence
    print("[CCTRL] Sending initialization sequence...")
    cctrl_sequence(
        ep_out, 
        ep_in_cctrl, 
        lens_mode=config.get("lens_mode", 1), 
        stream_quality_profile=cctrl_profile
    )

    # Step 5: STREAM START
    print("[CCTRL] STREAM START...")
    resp = cctrl_send(ep_out, ep_in_cctrl, "CCTRL STREAM START")
    print(f"  -> {resp}")
    if "SUCCESS" not in resp:
        print("[CCTRL] STREAM START failed!")
        sys.exit(1)

    # Step 6: read video
    actual_width = config.get("cam_width", 1920)
    actual_height = config.get("cam_height", 1080)
    try:
        res_resp = cctrl_send(ep_out, ep_in_cctrl, "CCTRL GET STATUS RESOLUTION")
        print(f"[CCTRL] Camera active resolution: {res_resp}")
        if res_resp:
            res_str = res_resp.split()[-1]
            if "x" in res_str:
                parts = res_str.split("x")
                actual_width = int(parts[0])
                actual_height = int(parts[1])
                print(f"[CCTRL] Dynamic resolution detection: {actual_width}x{actual_height}")
    except Exception as e:
        print(f"[CCTRL] Warning: could not query active resolution, using config defaults: {e}")

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
            post_processing=config.get("post_processing", {})
        )
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    finally:
        # STREAM STOP
        try:
            resp = cctrl_send(ep_out, ep_in_cctrl, "CCTRL STREAM STOP")
            print(f"[CCTRL] STREAM STOP -> {resp}")
        except Exception:
            pass
        usb.util.dispose_resources(dev)

if __name__ == "__main__":
    main()