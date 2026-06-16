"""
utils/config.py — Configuration loading for the Gear 360 webcam.

Reads config.json from the project directory, merges the active stream
profile into a flat dict, and creates a default config file on first run.
"""

import os
import sys
import json

# ---------------------------------------------------------------------------
# Default values (used when config.json is absent or a key is missing)
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE = {
    "cam_width":  1920,
    "cam_height": 1080,
    "fps":        30,
    "lens_mode":  1,
}

_DEFAULT_CONFIG = {
    "preview":               True,
    "virtual_camera":        True,
    "stream_quality_profile": 51,
    "brightness":            0,
    "contrast":              1.0,
    "post_processing": {
        "enabled":        True,
        "saturation":     1.2,
        "unsharp_msize":  3,
        "unsharp_amount": 0.5,
        "gamma":          1.0,
        "hue":            0.0,
        "denoise":        False,
    },
}

_DEFAULT_PROFILES = {
    "0":    {"cam_width": 2560, "cam_height": 1280, "fps": 15, "lens_mode": 0},
    "1":    {"cam_width": 1920, "cam_height":  960, "fps": 30, "lens_mode": 0},
    "2":    {"cam_width": 1920, "cam_height":  960, "fps": 15, "lens_mode": 0},
    "50-1": {"cam_width": 1920, "cam_height": 1080, "fps": 60, "lens_mode": 1},
    "50-2": {"cam_width": 1920, "cam_height": 1080, "fps": 60, "lens_mode": 2},
    "51-1": {"cam_width": 1920, "cam_height": 1080, "fps": 30, "lens_mode": 1},
    "51-2": {"cam_width": 1920, "cam_height": 1080, "fps": 30, "lens_mode": 2},
    "52-1": {"cam_width": 1280, "cam_height":  720, "fps": 30, "lens_mode": 1},
    "52-2": {"cam_width": 1280, "cam_height":  720, "fps": 30, "lens_mode": 2},
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _config_path() -> str:
    """Return the absolute path to config.json next to the main script."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        # Resolve relative to this file's parent directory (project root)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "config.json")


def _resolve_profile(user_config: dict) -> tuple[str, dict]:
    """Return (active_profile_key, profile_dict) from user_config.

    Tries the exact profile key first, then appends "-1" as a fallback
    (e.g. "51" → "51-1").
    """
    raw_key = str(user_config.get(
        "stream_quality_profile",
        _DEFAULT_CONFIG["stream_quality_profile"]
    ))
    profiles = user_config.get("profiles", {})

    if raw_key in profiles:
        return raw_key, profiles[raw_key]

    fallback_key = raw_key + "-1"
    if fallback_key in profiles:
        return fallback_key, profiles[fallback_key]

    return raw_key, {}


def _write_default_config(path: str) -> None:
    """Write a full default config.json to disk (only on first run)."""
    try:
        payload = dict(_DEFAULT_CONFIG)
        payload["profiles"] = _DEFAULT_PROFILES
        with open(path, 'w') as f:
            json.dump(payload, f, indent=2)
        print(f"[CONFIG] Created default configuration file: {path}")
    except Exception as e:
        print(f"[CONFIG] Could not write {path}: {e}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load, merge, and return the active configuration.

    Priority (high → low):
      1. Top-level keys in config.json
      2. Active stream profile (cam_width, cam_height, fps, lens_mode)
      3. Built-in defaults
    """
    path = _config_path()

    # Read user config from disk
    user_config: dict = {}
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                user_config = json.load(f)
        except Exception as e:
            print(f"[CONFIG] Error reading {path}: {e}")
    else:
        _write_default_config(path)

    # Resolve the active stream profile
    profile_key, profile_vals = _resolve_profile(user_config)
    if profile_vals:
        print(
            f"[CONFIG] Profile {profile_key} applied: "
            f"{profile_vals.get('cam_width')}x{profile_vals.get('cam_height')} "
            f"@ {profile_vals.get('fps')}fps, "
            f"lens_mode: {profile_vals.get('lens_mode')}"
        )
    else:
        profile_vals = _DEFAULT_PROFILE
        print(f"[CONFIG] Profile '{profile_key}' not found — using default "
              f"{profile_vals['cam_width']}x{profile_vals['cam_height']} "
              f"@ {profile_vals['fps']}fps")

    # Merge: defaults ← profile ← user top-level keys
    config = dict(_DEFAULT_CONFIG)
    config.update(profile_vals)
    config.update(user_config)
    return config


def parse_cctrl_profile(raw_profile) -> int:
    """Extract the integer CCTRL profile number from a profile key.

    Examples:
        "51-2" -> 51
        "52-1" -> 52
        52     -> 52
    """
    try:
        if isinstance(raw_profile, str) and '-' in raw_profile:
            return int(raw_profile.split('-')[0])
        return int(raw_profile)
    except (ValueError, TypeError):
        return 51
