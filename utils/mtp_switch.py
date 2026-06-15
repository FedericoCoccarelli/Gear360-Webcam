import struct
import usb.core
import usb.util
import libusb_package

def make_mtp_cmd(opcode, transaction_id, params=[]):
    length = 12 + 4 * len(params)
    header = struct.pack('<IHHI', length, 1, opcode, transaction_id)
    payload = b''.join(struct.pack('<I', p) for p in params)
    return header + payload

def send_mtp_cmd_usb(ep_out, ep_in, opcode, transaction_id, params=[]):
    cmd_data = make_mtp_cmd(opcode, transaction_id, params)
    try:
        ep_out.write(cmd_data, timeout=1000)
        resp = ep_in.read(1024, timeout=1000)
        if len(resp) >= 12:
            length, ctype, code, txn = struct.unpack_from('<IHHI', bytes(resp), 0)
            if ctype == 2: # Data container
                ep_in.read(1024, timeout=1000) # Read response container
    except Exception as e:
        print(f"[MTP] MTP error 0x{opcode:04X}: {e}")

def switch_to_vr360():
    VID_MTP = 0x04e8
    PID_MTP = 0x6860
    
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
        
        ep_out = usb.util.find_descriptor(intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        ep_in = usb.util.find_descriptor(intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
            
        # PTP/MTP sequence to trigger VR360 mode
        send_mtp_cmd_usb(ep_out, ep_in, 0x1003, 1) # Close session
        send_mtp_cmd_usb(ep_out, ep_in, 0x1002, 0, [1]) # Open session (Txn 0)
        send_mtp_cmd_usb(ep_out, ep_in, 0x1014, 1, [0xD407]) # GetDevicePropDesc
        send_mtp_cmd_usb(ep_out, ep_in, 0x1008, 2, [0xFFFFFFFE]) # GetObjectInfo
        send_mtp_cmd_usb(ep_out, ep_in, 0x1003, 3) # Close session
        
        usb.util.release_interface(dev, intf.bInterfaceNumber)
        print("[MTP] Switch command sent successfully — waiting for re-enumerate...")
    except Exception as e:
        print(f"[MTP] Error during switch: {e}")
    finally:
        usb.util.dispose_resources(dev)
