# Gear 360 (SM-R210) USB Streamer & Virtual Webcam

A modular Python tool to stream live video from the Samsung Gear 360 (SM-R210) over USB, apply real-time cropping to a 16:9 aspect ratio matching the active profile's target resolution, and stream it to a virtual webcam (e.g. OBS Virtual Camera or pyvirtualcam) under Windows.

## Requirements & Installation

### 1. Drivers (Zadig)
You need to replace the default Samsung USB drivers with generic WinUSB drivers for the camera interfaces:
1. Connect the Gear 360 to your PC via USB and turn it on.
2. Download and run [Zadig](https://zadig.akeo.ie/).
3. In Zadig, click `Options` -> Check `List All Devices`.
4. From the dropdown list, find the interfaces corresponding to the Gear 360 (often shows up as `Samsung Mobile MTP Device` or `VR360` depending on state).
5. Install WinUSB on the VR360 interfaces:
   - Interface 0 (Video Endpoint)
   - Interface 1 (CCTRL Endpoint)

### 2. Standalone Virtual Camera Driver
To use the Gear 360 as a system-wide webcam, install the standalone OBS Virtual Camera driver:
- Download and run the lightweight driver installer from [GitHub OBS Virtual Camera Releases](https://github.com/miaulightouch/obs-virtual-cam/releases).

### 3. PyAV (FFmpeg bindings)
This project uses PyAV (`av`) to decode the camera's H.265 video stream and apply filters in-process. System-wide installation of FFmpeg is **not** required, as `av` comes with its own precompiled FFmpeg binaries.

### 4. Python Dependencies
Install the required python libraries using:
```bash
pip install -r requirements.txt
```

---

## How to Use

1. Configure Settings:
   Edit `config.json` to change the stream parameters:
   - `"preview"`: Set `true` to show a local preview window, or `false` to run headlessly in the background.
   - `"virtual_camera"`: Set `true` to feed the stream into the Windows virtual webcam.
   - `"stream_quality_profile"`: Choose the profile ID. For single lens modes, use hyphenated naming to specify which lens to stream (e.g., `"51-1"` for front lens, `"51-2"` for rear lens). See `gear360_profiles.md` for a full list.
   - `"ffmpeg_post_processing"`: Configuration for real-time video adjustment using FFmpeg filters.
     - `"enabled"`: Enable/disable all FFmpeg filters (`true` or `false`).
     - `"saturation"`: Color saturation multiplier. Range: `0.0` (grayscale) to `3.0`.
     - `"unsharp_msize"`: Size of the sharpening matrix (must be an odd integer). Range: `3` to `23`.
     - `"unsharp_amount"`: Strength of the sharpening/blurring effect. Range: `-2.0` (blur) to `5.0` (sharpen).
     - `"gamma"`: Mid-tone brightness correction. Range: `0.1` to `10.0`. Default: `1.0`.
     - `"hue"`: Hue rotation in degrees. Range: `-180.0` to `180.0`.
     - `"denoise"`: Enable or disable the `atadenoise` noise reduction filter (`true` or `false`).

2. Run the Streamer:
   Double-click `run_webcam.bat` or run:
   ```bash
   python gear360_webcam.py
   ```

3. Select the Virtual Camera:
   Open Zoom, MS Teams, Google Chrome, or the Windows Camera app, and select "OBS Virtual Camera" as your webcam device.

---

## File Structure

- `gear360_webcam.py`: Main entry point coordinating initialization, connection, and loop lifecycle.
- `run_webcam.bat`: Windows batch script to check/install dependencies and start the program.
- `config.json`: Unified configuration containing active parameters and the list of profiles.
- `utils/`:
  - `mtp_switch.py`: Triggers the MTP to VR360 USB bulk streaming state.
  - `cctrl.py`: Encapsulates packet definitions and camera configuration commands.
  - `video_stream.py`: Decodes HEVC frames via FFmpeg, crops/scales to 16:9, and pipes frames to OpenCV/pyvirtualcam.
- `cctrl_commands.md`: Command reference guide.
- `gear360_profiles.md`: Detailed list of supported camera quality profiles.

---

## Credits

- OBS Virtual Camera driver by miaulightouch (https://github.com/miaulightouch/obs-virtual-cam)
- pyvirtualcam library for virtual camera interfacing
- libusb and PyUSB projects for USB communication capabilities
