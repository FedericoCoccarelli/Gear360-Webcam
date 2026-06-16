import sys
import time

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Known prefixes of human-readable camera response text.
# Used to detect and strip the leading status byte that the camera
# inserts before the actual message inside the STX…ETX frame.
_KNOWN_RESPONSE_STARTS = ("RET ", "SET ", "GET ", "CCTRL", "STATUS")


# ---------------------------------------------------------------------------
# Protocol helpers
# ---------------------------------------------------------------------------

def cctrl_pack(cmd: str) -> bytes:
    """Encapsulates a CCTRL command in the frame observed in pcap:
       01 00 <total_len> 02 <ASCII cmd> 03
    """
    body = b'\x01\x00' + bytes([len(cmd)]) + b'\x02' + cmd.encode('ascii') + b'\x03'
    return body


def cctrl_send(ep_out, ep_in, cmd: str, timeout: int = 3000) -> str:
    """Send a CCTRL command and return the clean human-readable response.

    The camera wraps each response in STX (0x02) … ETX (0x03) framing and
    prefixes the text with a single status byte.  This function strips all
    framing and control characters so the caller receives plain ASCII text
    such as "RET SUCCESS STREAM START".
    """
    data = cctrl_pack(cmd)
    ep_out.write(data, timeout=timeout)
    raw = ep_in.read(4096, timeout=timeout)

    # Decode raw bytes as ASCII, replacing unrecognised bytes with '?'
    decoded = bytes(raw).decode('ascii', errors='replace')

    # Extract text between STX (0x02) and ETX (0x03) when present
    stx = decoded.find('\x02')
    etx = decoded.find('\x03', stx + 1) if stx != -1 else -1
    if stx != -1 and etx != -1:
        text = decoded[stx + 1 : etx]
    else:
        # Fallback: strip known framing bytes from both ends
        text = decoded.strip('\x00\x01\x02\x03\x04\x05\x06\r\n ')

    # Remove all non-printable / control characters (< 0x20), including the
    # leading status byte and ACK (0x06) that precede the readable text
    text = ''.join(ch if ch >= ' ' else '' for ch in text).strip()

    # The camera prefixes the text with a single status byte that may be a
    # printable ASCII char (e.g. 0x59 = 'Y' for success). Skip it when the
    # text does not start with a known response keyword.
    if text and not any(text.startswith(k) for k in _KNOWN_RESPONSE_STARTS):
        text = text[1:].strip()

    return text


def flush_endpoint(ep, timeout: int = 50) -> None:
    """Read from endpoint until timeout to drain any buffered data."""
    try:
        while True:
            ep.read(4096, timeout=timeout)
    except Exception:
        pass


def cctrl_sequence(ep_out, ep_in, lens_mode: int = 1,
                   stream_quality_profile: int = 51) -> None:
    """Send the essential CCTRL configuration commands to start the stream."""
    flush_endpoint(ep_in)
    cmds = [
        f"CCTRL SET STATUS LENS MODE {lens_mode}",
        f"CCTRL SET STATUS STREAM QUALITY PROFILE {stream_quality_profile}",
    ]
    for cmd in cmds:
        try:
            resp = cctrl_send(ep_out, ep_in, cmd)
            print(f"  [{cmd}] -> {resp[:120]}")
        except Exception as e:
            print(f"  [{cmd}] ERROR: {e}")
        time.sleep(0.05)
