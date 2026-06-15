import sys
import time

def cctrl_pack(cmd: str) -> bytes:
    """Encapsulates a CCTRL command in the frame observed in pcap:
       01 00 <total_len> 02 <ASCII cmd> 03
    """
    body = b'\x01\x00' + bytes([len(cmd)]) + b'\x02' + cmd.encode('ascii') + b'\x03'
    return body

def cctrl_send(ep_out, ep_in, cmd: str, timeout=3000) -> str:
    data = cctrl_pack(cmd)
    ep_out.write(data, timeout=timeout)
    raw = ep_in.read(4096, timeout=timeout)
    # Response: header 4 bytes + STX + text + ETX
    text = bytes(raw).decode('ascii', errors='replace').strip('\x01\x06\x02\x03\x00 \r\n')
    return text

def flush_endpoint(ep, timeout=50):
    """Reads from endpoint until timeout to empty buffer."""
    try:
        while True:
            ep.read(4096, timeout=timeout)
    except Exception:
        pass

def cctrl_sequence(ep_out, ep_in, lens_mode=1, stream_quality_profile=51):
    """Sends the essential CCTRL configuration commands to start the stream."""
    flush_endpoint(ep_in)
    cmds = [
        f"CCTRL SET STATUS LENS MODE {lens_mode}",
        f"CCTRL SET STATUS STREAM QUALITY PROFILE {stream_quality_profile}",
    ]
    for cmd in cmds:
        try:
            resp = cctrl_send(ep_out, ep_in, cmd)
            resp_safe = resp[:80].encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
            print(f"  [{cmd}] -> {resp_safe}")
        except Exception as e:
            print(f"  [{cmd}] ERROR: {e}")
        time.sleep(0.05)
