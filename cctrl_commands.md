# Gear 360 (SM-R210) CCTRL Command Reference

This document keeps track of the known commands sent to the camera via the CCTRL protocol, their values, and their meanings.

## 1. Stream Control Commands
Commands to start or stop the video stream.

- `CCTRL STREAM START`
  - Description: Starts the HEVC video stream over the bulk endpoint.
  - Response: `RET SUCCESS STREAM START` (or error if not initialized)
- `CCTRL STREAM STOP`
  - Description: Stops the video stream.
  - Response: `RET SUCCESS STREAM STOP`

---

## 2. Configuration Commands (SET)
Commands to change the camera state.

- `CCTRL SET STATUS LENS MODE <value>`
  - Description: Selects active camera lenses.
  - Values:
    - `0`: Dual CAM (Both lenses active, outputs spherical/360 projection)
    - `1`: Single CAM - Front (Front lens active)
    - `2`: Single CAM - Rear (Rear lens active)
- `CCTRL SET STATUS STREAM QUALITY PROFILE <value>`
  - Description: Selects the streaming quality profile (resolution, fps, and bitrate combination).
  - Values: (See `profiles.json` for details)
    - `0`, `1`, `2` (Used for Dual CAM mode)
    - `50`, `51`, `52` (Used for Single CAM mode)

---

## 3. Query Commands (GET)
Commands to query camera status and details.

- `CCTRL GET STATUS LENS MODE AVAILABLE`
  - Description: Returns the list of supported lens modes.
- `CCTRL GET STATUS STREAM QUALITY PROFILE AVAILABLE`
  - Description: Returns all supported stream profiles (resolutions and frame rates).
- `CCTRL GET STATUS STREAM QUALITY PROFILE CURRENT`
  - Description: Returns the active stream quality profile.
- `CCTRL GET STATUS BATTERY LEVEL`
  - Description: Returns current battery percentage (0-100).
- `CCTRL GET STATUS TEMPERATURE WARNING LEVEL`
  - Description: Returns the internal heat warning level status.
- `CCTRL GET STATUS FRAME RATE`
  - Description: Returns the current stream framerate.
- `CCTRL GET STATUS BITRATE`
  - Description: Returns the active stream bitrate in bits per second (e.g. `15000000` = 15 Mbps).
- `CCTRL GET STATUS RESOLUTION`
  - Description: Returns the stream resolution (e.g. `1920x960` or `1920x1080`).
- `CCTRL GET STATUS OPTICAL METADATA OPAI` / `OPAX`
  - Description: Retrieves lens calibration / optical metadata parameters.
