# Gear 360 (SM-R210) Stream Profiles

This is the complete list of available stream quality profiles, retrieved directly from the camera via `CCTRL GET STATUS STREAM QUALITY PROFILE AVAILABLE`.

## 1. Dual Lens Mode (Dual Camera - DUAL)
To be used when `lens_mode` is set to `0` (Dual CAM). Native aspect ratio is 2:1.

| Profile ID | Resolution | Framerate | Notes / Recommended Use |
| :---: | :---: | :---: | :--- |
| `0` | 2560x1280 | 15 fps | Maximum 360° resolution, ideal for static scenes. |
| `1` | 1920x960 | 30 fps | Great balance between resolution and smoothness for 360° video. |
| `2` | 1920x960 | 15 fps | Standard 360° resolution with reduced framerate (lower bitrate). |

## 2. Single Lens Mode (Single Camera - SINGLE)
To be used when `lens_mode` is set to `1` (Front) or `2` (Rear). Native aspect ratio is 16:9.

| Profile ID | Resolution | Framerate | Lens | Notes / Recommended Use |
| :---: | :---: | :---: | :---: | :--- |
| `50-1` | 1920x1080 | 60 fps | Front (1) | High-smoothness Full HD, front-facing. |
| `50-2` | 1920x1080 | 60 fps | Rear (2) | High-smoothness Full HD, rear-facing. |
| `51-1` | 1920x1080 | 30 fps | Front (1) | Standard Full HD, front-facing (recommended default). |
| `51-2` | 1920x1080 | 30 fps | Rear (2) | Standard Full HD, rear-facing. |
| `52-1` | 1280x720 | 30 fps | Front (1) | Standard HD, front-facing. |
| `52-2` | 1280x720 | 30 fps | Rear (2) | Standard HD, rear-facing. |

---

> [!NOTE]
> The parameters `"cam_width"`, `"cam_height"`, and `"fps"` are automatically set based on the active profile ID loaded from `config.json`.
