#!/usr/bin/env python3
import time
import json
import socket
import canopen
from canopen.sdo import SdoAbortedError

# ---------- Config ----------
CHANNEL = "can0"
NODE_ID = 1
EDS_PATH = "DS301_profile.eds"
UDP_IP = "127.0.0.1"      # Target IP (can be remote)
UDP_PORT = 5005           # Target port
HB_MS = 1000
HB_WAIT = 2.5
# ----------------------------

def main():
    net = canopen.Network()
    net.connect(channel=CHANNEL, bustype="socketcan")

    node = net.add_node(NODE_ID, EDS_PATH)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


    # --- Read device type
    try:
        dt = node.sdo[0x1000].raw
        print(f"Device Type (0x1000): 0x{dt:08X}")
    except SdoAbortedError as e:
        print("ERROR reading 0x1000:", e); net.disconnect(); return

    # --- Heartbeat producer
    try:
        node.sdo[0x1017].raw = HB_MS
        print(f"Producer Heartbeat Time set to {node.sdo[0x1017].raw} ms")
    except SdoAbortedError as e:
        print("ERROR writing 0x1017:", e); net.disconnect(); return

    # --- Configure mode & controlword while in PRE-OP
    node.nmt.state = "PRE-OPERATIONAL"
    print("Node has entered:", node.nmt.state)

    try:
        node.sdo[0x6060].raw = 1   # Profile Position Mode (example)
        # Many drives require the standard controlword sequence; for quick test we set 0x000F
        node.sdo[0x6040].raw = 0x000F
        print(f"Mode (0x6060)={node.sdo[0x6060].raw}, Controlword (0x6040)=0x{node.sdo[0x6040].raw:04X}")
    except SdoAbortedError as e:
        print("ERROR writing operation mode/controlword:", e)

    node.nmt.state = "OPERATIONAL"
    print("Node is OPERATIONAL, waiting for first heartbeat...")
    time.sleep(1.5)
    try:
        node.nmt.wait_for_heartbeat(timeout=max(2.0, HB_WAIT))
        print("Heartbeat OK ")
    except canopen.nmt.NmtError as e:
        print("Heartbeat timeout:", e)

    # ---- 2) Load PDO mapping ----
    node.tpdo.read()  # get current comm + mapping from device

    # ---- 3) Callback to send TPDOs via UDP ----
    def make_cb(n):
        def _cb(_frame):
            values = {}
            for v in node.tpdo[n]:
                name = v.name or f"0x{v.index:04X}/{v.subindex:02X}"
                try:
                    val = float(v.phys)
                except Exception:
                    val = float(v.raw)
                values[name] = val
            json_data = json.dumps(values)
            sock.sendto(json_data.encode("utf-8"), (UDP_IP, UDP_PORT))
            # print(f"[TPDO{n}] Sent: {json_data}")
        return _cb

    # ---- 4) Register callback for each mapped TPDO ----
    for n in range(1, 9):
        try:
            if list(node.tpdo[n]):  # skip empty PDOs
                node.tpdo[n].add_callback(make_cb(n))
                print(f"Listening for TPDO{n}...")
        except KeyError:
            pass

    # ---- 5) Keep alive ----
    print(f"Streaming TPDOs to UDP {UDP_IP}:{UDP_PORT} (Ctrl+C to quit)")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        net.disconnect()
        sock.close()

if __name__ == "__main__":
    main()
