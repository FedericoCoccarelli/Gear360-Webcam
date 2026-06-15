import struct
import subprocess
import threading
import usb.core
import time

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

def pipe_to_opencv(ep_in_video, fps=30, cam_width=1920, cam_height=960, brightness=0, contrast=1.0, show_preview=True, use_virtual_cam=True):
    """Pipes the decoded HEVC stream to rawvideo in OpenCV to display preview or send to vcam in the background."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("[ERROR] To use preview, you must install opencv and numpy:")
        print("         pip install opencv-python numpy")
        return

    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        print("[VIDEO] Error: ffmpeg not found in PATH!")
        return

    frame_size = cam_width * cam_height * 3

    cmd = [
        ffmpeg_path, '-y',
        '-probesize', '32',
        '-analyzeduration', '0',
        '-fflags', 'nobuffer',
        '-flags', 'low_delay',
        '-f', 'hevc', '-r', str(fps), '-i', 'pipe:0',
        '-f', 'rawvideo', '-pix_fmt', 'bgr24', 'pipe:1'
    ]

    print(f"[VIDEO] Starting FFmpeg decoding ({fps} fps, {cam_width}x{cam_height})...")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def feed_ffmpeg():
        try:
            for payload in unwrap_stream(ep_in_video):
                proc.stdin.write(payload)
        except Exception:
            pass
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    feed_thread = threading.Thread(target=feed_ffmpeg)
    feed_thread.daemon = True
    feed_thread.start()

    # Calculate 16:9 output resolution based on input resolution
    target_aspect = 16.0 / 9.0
    current_aspect = cam_width / cam_height
    if current_aspect > target_aspect:
        # wider than 16:9, crop sides. Height remains, width scales to 16:9
        out_height = cam_height
        out_width = int(cam_height * target_aspect)
    else:
        # taller than 16:9, crop top/bottom. Width remains, height scales to 16:9
        out_width = cam_width
        out_height = int(cam_width / target_aspect)

    # Initialize virtual webcam if enabled and pyvirtualcam is installed
    vcam = None
    if use_virtual_cam:
        try:
            import pyvirtualcam
            vcam = pyvirtualcam.Camera(width=out_width, height=out_height, fps=fps, fmt=pyvirtualcam.PixelFormat.BGR)
            print(f"[WEBCAM] Sending stream to virtual webcam: {vcam.device}")
        except ImportError:
            print("[WEBCAM] Note: pyvirtualcam not installed. Running only local preview.")
        except Exception as e:
            print(f"[WEBCAM] Error initializing virtual webcam (missing driver?): {e}")

    if show_preview:
        print(f"[OPENCV] Preview window open ({out_width}x{out_height} - 16:9). Press 'q' or 'ESC' to close.")
    else:
        print("[INFO] Preview GUI disabled. Background stream active. Press Ctrl+C to terminate.")

    try:
        while True:
            raw_frame = proc.stdout.read(frame_size)
            if len(raw_frame) != frame_size:
                break
            
            # Convert raw bytes to numpy array and reshape to image
            frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((cam_height, cam_width, 3))
            
            # Force 16:9 aspect ratio by cropping and then resizing to output dimensions
            h, w = frame.shape[:2]
            if current_aspect > target_aspect:
                # wider than target, crop left/right sides
                new_w = int(h * target_aspect)
                offset = (w - new_w) // 2
                cropped = frame[:, offset:offset+new_w]
            else:
                # taller than target, crop top/bottom
                new_h = int(w / target_aspect)
                offset = (h - new_h) // 2
                cropped = frame[offset:offset+new_h, :]
            
            preview_frame = cv2.resize(cropped, (out_width, out_height))
            
            # Adjust contrast and brightness
            if contrast != 1.0 or brightness != 0:
                preview_frame = cv2.convertScaleAbs(preview_frame, alpha=contrast, beta=brightness)

            # Send to virtual camera
            if vcam:
                vcam.send(preview_frame)
                vcam.sleep_until_next_frame()

            if show_preview:
                cv2.imshow("Gear 360 Live Preview", preview_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    break
            else:
                # Small sleep to yield CPU if necessary
                time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    finally:
        if vcam:
            vcam.close()
        if show_preview:
            cv2.destroyAllWindows()
        try:
            proc.terminate()
        except Exception:
            pass
