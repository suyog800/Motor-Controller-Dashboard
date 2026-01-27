#!/usr/bin/env python3
import time
import canopen
from canopen.sdo import SdoAbortedError
# from canopen.nmt import HeartbeatError

# ---------- Config ----------
CHANNEL = "can0"                 # socketcan interface (configure with `ip link` beforehand)
NODE_ID = 1                      # your node ID
EDS_PATH = "DS301_profile.eds"   # path to your EDS/DCF
HB_MS = 1000                     # Producer Heartbeat Time to set (milliseconds)
HB_WAIT = 2.5                    # Wait timeout when expecting 1s heartbeat (a bit > HB_MS)
# ----------------------------

def decode_device_type(dt: int):
    """CiA 301: upper 16 bits = device profile number, lower 16 = profile-specific revision/type."""
    profile = (dt >> 16) & 0xFFFF
    specific = dt & 0xFFFF
    return profile, specific

def main():
    net = canopen.Network()
    net.connect(channel=CHANNEL, bustype="socketcan")

    # Add node with EDS for SDO dictionary
    node = net.add_node(NODE_ID, EDS_PATH)

    # ---- 1) Read Device Type (0x1000:00) ----
    try:
        device_type = node.sdo[0x1000].raw
        prof, spec = decode_device_type(device_type)
        print(f"Device Type (0x1000): 0x{device_type:08X}")
        print(f"  Profile: 0x{prof:04X}  |  Specific/Revision: 0x{spec:04X}")
    except SdoAbortedError as e:
        print(f"ERROR reading 0x1000: {e}")
        net.disconnect()
        return

    # ---- 2) Set Producer Heartbeat Time (0x1017) ----
    try:
        node.sdo[0x1017].raw = HB_MS
        confirmed = node.sdo[0x1017].raw
        print(f"Producer Heartbeat Time set to {confirmed} ms")
    except SdoAbortedError as e:
        print(f"ERROR writing 0x1017: {e}")
        net.disconnect()
        return


    node.nmt.state = "PRE-OPERATIONAL"
    print("Node has entered:", node.nmt.state)
    time.sleep(2)
    # Configure TPDO1 comm params (DO NOT clear mapping since you already have it)
    
    try:
        # 1 = Profile Position Mode (per CiA-402 standard)
        node.sdo[0x6060].raw = 1
        node.sdo[0x6040].raw = 1<<0 | 1 <<1 | 1<< 2 | 1<<3
        print(f"Controlword (0x6040) set to {node.sdo[0x6040].raw}")
        mode_confirm = node.sdo[0x6060].raw
        print(f"Mode of Operation (0x6060) set to {mode_confirm}")
    except SdoAbortedError as e:
        print(f"ERROR writing 0x6060: {e}")

    # ---- 3) Go OPERATIONAL & verify first heartbeat ----
    node.nmt.state = "OPERATIONAL"
    time.sleep(0.5)
    print(f"Node state is now: {node.nmt.state}")

    node.nmt.send_command(0x01)  # 0x01 = Start Remote Node      # equivalent to sending NMT Start Remote Node (0x01)
    print("NMT state:", node.nmt.state) 
    
    try:
        node.nmt.wait_for_heartbeat(timeout=max(2.0, HB_WAIT))
        print("First heartbeat received ✔")
    except canopen.nmt.HeartbeatError as e:
        print(f"Heartbeat not received in time: {e}")

    # ---- 4) Subscribe to heartbeat state changes ----
    def on_hb(state):
        print(f"[HB] Node {NODE_ID} NMT state: {state}")

    node.nmt.add_heartbeat_callback(on_hb)

    
    print(f"Listening for heartbeats from node {NODE_ID}… (Ctrl+C to quit)")
    try:
        while True:
            try:
                node.nmt.wait_for_heartbeat(timeout=HB_WAIT)
            except canopen.nmt.NmtError as e:
                print(f"[MISS] Heartbeat timeout: {e}", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        net.disconnect()

if __name__ == "__main__":
    main()
