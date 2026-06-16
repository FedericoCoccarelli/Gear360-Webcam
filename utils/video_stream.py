import struct
import threading
import usb.core
import time
import queue
import av

def unwrap_stream(ep_in_video):
    """Generator that reads from the USB endpoint, parses it, and
       yields only the HEVC payloads of '00VD' chunks on the fly.
    """
    buffer = bytearray()
    while True:
        try:
            chunk = ep_in_video.read(65536, timeout=5000)
            if not chunk:
                break
            buffer.extend(chunk)

            while True:
                pos_vd = buffer.find(b'00VD')
                pos_au = buffer.find(b'00AU')
                positions = [p for p in (pos_vd, pos_au) if p != -1]

                if not positions:
                    if len(buffer) > 7:
                        del buffer[:-7]
                    break

                first_pos = min(positions)
                if first_pos > 0:
                    del buffer[:first_pos]
                    continue

                if len(buffer) < 8:
                    break

                size = struct.unpack_from('>I', buffer, 4)[0]
                if len(buffer) < 8 + size:
                    break

                is_video = buffer.startswith(b'00VD')
                payload = buffer[8:8+size]

                if is_video:
                    yield bytes(payload[8:])

                del buffer[:8+size]
        except usb.core.USBTimeoutError:
            print("\n[VIDEO] Info: USB read timeout (end of stream or no data)")
            break
        except Exception as e:
            print(f"\n[VIDEO] Unwrap error: {e}")
            break


def _build_pp_pipeline(pp, cv2, np):
    """
    Pre-compute all OpenCV post-processing steps from config.
    Returns a list of callables (frame: ndarray) -> ndarray.
    Each op is independent so only enabled ones run.
    """
    ops = []
    if not pp.get("enabled", False):
        return ops

    # --- Saturation / Hue (HSV space) ---
    saturation = pp.get("saturation", 1.0)
    hue_shift  = pp.get("hue", 0.0)
    if saturation != 1.0 or hue_shift != 0.0:
        sat_scale = float(saturation)
        hue_deg   = float(hue_shift)
        def apply_hsv(img, _sat=sat_scale, _hue=hue_deg):
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
            if _hue != 0.0:
                hsv[:, :, 0] = (hsv[:, :, 0] + _hue) % 180.0
            if _sat != 1.0:
                hsv[:, :, 1] = np.clip(hsv[:, :, 1] * _sat, 0, 255)
            return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        ops.append(apply_hsv)

    # --- Gamma (LUT, precomputed — O(1) per frame) ---
    gamma = pp.get("gamma", 1.0)
    if gamma is not None and gamma != 1.0:
        lut = np.array([
            int(((i / 255.0) ** (1.0 / float(gamma))) * 255)
            for i in range(256)
        ], dtype=np.uint8)
        def apply_gamma(img, _lut=lut):
            return cv2.LUT(img, _lut)
        ops.append(apply_gamma)

    # --- Unsharp mask (Gaussian blur + weighted blend) ---
    unsharp_amount = pp.get("unsharp_amount", 0.0)
    if unsharp_amount is not None and unsharp_amount != 0.0:
        msize = pp.get("unsharp_msize", 3)
        ksize = int(msize) | 1  # must be odd
        strength = float(unsharp_amount)
        def apply_unsharp(img, _k=ksize, _s=strength):
            blurred = cv2.GaussianBlur(img, (_k, _k), 0)
            return cv2.addWeighted(img, 1.0 + _s, blurred, -_s, 0)
        ops.append(apply_unsharp)

    # --- Denoise (bilateral: edge-preserving, much faster than atadenoise) ---
    if pp.get("denoise", False):
        def apply_denoise(img):
            # d=5 keeps it real-time; sigmaColor/sigmaSpace tunable
            return cv2.bilateralFilter(img, d=5, sigmaColor=50, sigmaSpace=50)
        ops.append(apply_denoise)

    return ops


def pipe_to_opencv(ep_in_video, fps=30, cam_width=1920, cam_height=960,
                   brightness=0, contrast=1.0, show_preview=True,
                   use_virtual_cam=True, post_processing=None):
    """4-thread pipeline: decode → post-process → [preview, vcam] (all independent)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("[ERROR] To use preview, you must install opencv and numpy:")
        print("         pip install opencv-python numpy")
        return

    # --- Output resolution (16:9 crop) ---
    target_aspect  = 16.0 / 9.0
    current_aspect = cam_width / cam_height
    if current_aspect > target_aspect:
        out_height = cam_height
        out_width  = int(cam_height * target_aspect)
    else:
        out_width  = cam_width
        out_height = int(cam_width / target_aspect)

    # --- Pre-compute crop slice (avoid per-frame if/else) ---
    if current_aspect > target_aspect:
        new_w   = int(cam_height * target_aspect)
        offset  = (cam_width - new_w) // 2
        crop_sl = (slice(None), slice(offset, offset + new_w))
    else:
        new_h   = int(cam_width / target_aspect)
        offset  = (cam_height - new_h) // 2
        crop_sl = (slice(offset, offset + new_h), slice(None))

    # --- Virtual webcam ---
    vcam = None
    if use_virtual_cam:
        try:
            import pyvirtualcam
            vcam = pyvirtualcam.Camera(width=out_width, height=out_height,
                                       fps=fps, fmt=pyvirtualcam.PixelFormat.BGR)
            print(f"[WEBCAM] Sending stream to virtual webcam: {vcam.device}")
        except ImportError:
            print("[WEBCAM] Note: pyvirtualcam not installed. Running only local preview.")
        except Exception as e:
            print(f"[WEBCAM] Error initializing virtual webcam (missing driver?): {e}")

    if show_preview:
        print(f"[OPENCV] Preview window open ({out_width}x{out_height} - 16:9). Press 'q' or 'ESC' to close.")
    else:
        print("[INFO] Preview GUI disabled. Background stream active. Press Ctrl+C to terminate.")

    # --- Pre-build OpenCV post-processing pipeline ---
    pp_ops = _build_pp_pipeline(post_processing or {}, cv2, np)

    # --- Queues (maxsize=1 everywhere: always latest frame, never backlog) ---
    raw_queue   = queue.Queue(maxsize=1)  # decode  → pp
    frame_queue = queue.Queue(maxsize=1)  # pp      → preview
    vcam_queue  = queue.Queue(maxsize=1)  # pp      → vcam
    stop_event  = threading.Event()

    def _put_latest(q, item):
        """Non-blocking: drop stale, put newest."""
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            pass

    # ── Thread 1: HEVC decode ──────────────────────────────────────────────
    def decode_thread_func():
        codec_ctx = av.CodecContext.create("hevc", "r")
        try:
            codec_ctx.threads     = 1
            codec_ctx.flags      |= 524288  # AV_CODEC_FLAG_LOW_DELAY
            codec_ctx.flags2     |= 1       # AV_CODEC_FLAG2_FAST
            codec_ctx.thread_type = 0       # no frame-level threading
        except Exception:
            pass

        try:
            for payload in unwrap_stream(ep_in_video):
                if stop_event.is_set():
                    break
                packet = av.Packet(payload)
                packet.pts = None  # skip reorder buffer
                try:
                    for frame in codec_ctx.decode(packet):
                        # Minimal work: YUV→BGR only, push to pp
                        bgr = frame.to_ndarray(format='bgr24')
                        _put_latest(raw_queue, bgr)
                except Exception as de:
                    print(f"[VIDEO] Decode error: {de}")
        except Exception as e:
            print(f"[VIDEO] Decoder loop exception: {e}")
        finally:
            _put_latest(raw_queue, None)

    # ── Thread 2: Post-process (crop, resize, filters) ────────────────────
    def pp_thread_func():
        while not stop_event.is_set():
            try:
                raw = raw_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if raw is None:
                _put_latest(frame_queue, None)
                _put_latest(vcam_queue,  None)
                break

            try:
                # Crop (pre-sliced, zero-copy view)
                cropped = raw[crop_sl]

                # Resize to output
                frame = cv2.resize(cropped, (out_width, out_height))

                # Contrast / brightness
                if contrast != 1.0 or brightness != 0:
                    frame = cv2.convertScaleAbs(frame, alpha=contrast, beta=brightness)

                # OpenCV post-processing filters
                for op in pp_ops:
                    frame = op(frame)

            except Exception as pe:
                print(f"[VIDEO] PP error: {pe}")
                continue

            _put_latest(frame_queue, frame)
            if vcam:
                _put_latest(vcam_queue, frame)

    # ── Thread 3: Virtual webcam sender ───────────────────────────────────
    def vcam_thread_func():
        while not stop_event.is_set():
            try:
                frame = vcam_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if frame is None:
                break
            try:
                vcam.send(frame)
            except Exception:
                pass

    # --- Start threads ---
    decode_thread = threading.Thread(target=decode_thread_func, daemon=True)
    pp_thread     = threading.Thread(target=pp_thread_func,     daemon=True)
    decode_thread.start()
    pp_thread.start()

    vcam_thread = None
    if vcam:
        vcam_thread = threading.Thread(target=vcam_thread_func, daemon=True)
        vcam_thread.start()

    # ── Main thread: preview display only ─────────────────────────────────
    try:
        while True:
            try:
                frame = frame_queue.get(timeout=0.1)
            except queue.Empty:
                if not decode_thread.is_alive() and not pp_thread.is_alive():
                    break
                if show_preview:
                    if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                        break
                continue

            if frame is None:
                break

            if show_preview:
                cv2.imshow("Gear 360 Live Preview", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    break
            else:
                time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        if vcam:
            vcam.close()
        if show_preview:
            cv2.destroyAllWindows()
