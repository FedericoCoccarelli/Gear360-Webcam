import struct
import usb.core
import usb.util
import libusb_package

# ---------------------------------------------------------------------------
# Device identifiers
# ---------------------------------------------------------------------------

VID_MTP = 0x04e8   # Samsung
PID_MTP = 0x6860   # Gear 360 in initial MTP/Tizen mode

# ---------------------------------------------------------------------------
# MTP opcode constants (PTP/MTP spec)
# ---------------------------------------------------------------------------

MTP_OP_OPEN_SESSION       = 0x1002
MTP_OP_CLOSE_SESSION      = 0x1003
MTP_OP_GET_OBJECT_INFO    = 0x1008
MTP_OP_GET_DEVICE_PROP    = 0x1014

# Samsung proprietary device property that triggers the VR360 mode switch
SAMSUNG_PROP_VR360_SWITCH = 0xD407

# Special "current storage" handle used in GetObjectInfo to trigger the switch
MTP_STORAGE_ALL           = 0xFFFFFFFE

# MTP container type for "Data" containers (vs. Command/Response)
MTP_CTYPE_DATA = 2


# ---------------------------------------------------------------------------
# Low-level MTP helpers
# ---------------------------------------------------------------------------

def make_mtp_cmd(opcode: int, transaction_id: int,
                 params: list[int] | None = None) -> bytes:
    """Build a raw MTP command container.

    Layout: <length:4> <type:2=Command> <opcode:2> <txn_id:4> [param:4 ...]
    """
    if params is None:
        params = []
    length  = 12 + 4 * len(params)
    header  = struct.pack('<IHHI', length, 1, opcode, transaction_id)
    payload = b''.join(struct.pack('<I', p) for p in params)
    return header + payload


def send_mtp_cmd_usb(ep_out, ep_in, opcode: int, transaction_id: int,
                     params: list[int] | None = None) -> None:
    """Write an MTP command to ep_out and drain the response from ep_in."""
    if params is None:
        params = []
    cmd_data = make_mtp_cmd(opcode, transaction_id, params)
    try:
        ep_out.write(cmd_data, timeout=1000)
        resp = ep_in.read(1024, timeout=1000)
        if len(resp) >= 12:
            _length, ctype, _code, _txn = struct.unpack_from('<IHHI', bytes(resp), 0)
            if ctype == MTP_CTYPE_DATA:
                ep_in.read(1024, timeout=1000)  # drain the data container
    except Exception as e:
        print(f"[MTP] MTP error 0x{opcode:04X}: {e}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def switch_to_vr360() -> None:
    """Send the PTP/MTP sequence that makes the Gear 360 re-enumerate
    as a VR360 streaming device (VID:04e8 PID:a50c).
    """
    backend = libusb_package.get_libusb1_backend()
    dev = usb.core.find(idVendor=VID_MTP, idProduct=PID_MTP, backend=backend)

    if not dev:
        print("[MTP] Camera not found in MTP mode — already in VR360?")
        return

    print("[MTP] Camera found in MTP mode. Initializing switch...")
    try:
        try:
            dev.set_configuration()
        except Exception:
            pass

        intf = dev[0].interfaces()[0]
        usb.util.claim_interface(dev, intf.bInterfaceNumber)

        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                                   == usb.util.ENDPOINT_OUT)
        ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                                   == usb.util.ENDPOINT_IN)

        # PTP/MTP sequence that triggers the VR360 mode switch
        send_mtp_cmd_usb(ep_out, ep_in, MTP_OP_CLOSE_SESSION,    1)
        send_mtp_cmd_usb(ep_out, ep_in, MTP_OP_OPEN_SESSION,     0, [1])
        send_mtp_cmd_usb(ep_out, ep_in, MTP_OP_GET_DEVICE_PROP,  1, [SAMSUNG_PROP_VR360_SWITCH])
        send_mtp_cmd_usb(ep_out, ep_in, MTP_OP_GET_OBJECT_INFO,  2, [MTP_STORAGE_ALL])
        send_mtp_cmd_usb(ep_out, ep_in, MTP_OP_CLOSE_SESSION,    3)

        usb.util.release_interface(dev, intf.bInterfaceNumber)
        print("[MTP] Switch command sent successfully — waiting for re-enumerate...")
    except Exception as e:
        print(f"[MTP] Error during switch: {e}")
    finally:
        usb.util.dispose_resources(dev)
