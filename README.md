# Motor-Controller-Dashboard
# CANopen Motor Driver Utility

A PyQt5-based CANopen utility for connecting to a motor driver over SocketCAN.

This tool allows you to:

* Connect to a CANopen node using a CAN interface such as `can0`
* Load an EDS/DCF file
* Read the CANopen device type object `0x1000`
* Set heartbeat producer time using object `0x1017`
* Switch the node between `PRE-OPERATIONAL` and `OPERATIONAL` states
* Send the controlword `0x000F` to object `0x6040`
* Read and send RPDO values
* Stream TPDO values as JSON over UDP
* Monitor device status register `0x2000`
* Monitor device temperature register `0x2300`

---

## Requirements

### Hardware

* Linux system with SocketCAN support
* CAN adapter supported by Linux SocketCAN
* CANopen motor driver
* Correct EDS or DCF file for the target device
* CAN wiring connected correctly between the PC CAN adapter and motor driver

### Software

* Ubuntu/Debian-based Linux system
* Python 3
* SocketCAN
* `can-utils`
* `net-tools`
* Python packages listed below

---

## Install System Dependencies

On Ubuntu/Debian-based systems, install CAN utilities and networking tools:

```bash
sudo apt update
sudo apt install net-tools can-utils
```

`net-tools` provides utilities such as:

```bash
ifconfig
```

`can-utils` provides useful CAN debugging tools such as:

```bash
candump
cansend
cansniffer
```

---

## Install Python Dependencies

Install the required Python libraries:

```bash
pip install python-can canopen PyQt5
```

The script uses the following main Python packages:

* `python-can`
* `canopen`
* `PyQt5`

---

## SocketCAN Setup

The motor driver uses a fixed CAN bitrate of **500 kbps**.

### Check CAN Interface

After connecting your CAN adapter, check available network interfaces:

```bash
ifconfig -a
```

You should see a CAN interface such as:

```bash
can0
```

---

## Bring Up CAN Interface

Set the CAN interface bitrate to **500 kbps** and bring it up:

```bash
sudo ip link set can0 type can bitrate 500000 && sudo ip link set can0 up
```

To bring the interface down:

```bash
sudo ip link set can0 down
```

---

## Verify CAN Traffic

Use `candump` to monitor CAN messages:

```bash
candump can0
```

If the motor driver is connected and powered correctly, you should see periodic heartbeat messages from the motor driver.

Example:

```text
can0  702   [1]  05
```

In this example:

* `702` is a CANopen heartbeat COB-ID
* `702` corresponds to heartbeat from node ID `2`
* `05` commonly indicates that the node is in the `OPERATIONAL` state

CANopen heartbeat COB-ID format:

```text
0x700 + Node ID
```

For example:

| Node ID | Heartbeat COB-ID |
| ------: | ---------------: |
|       1 |          `0x701` |
|       2 |          `0x702` |
|       3 |          `0x703` |

---

## Running the Application

Run the Python script:

```bash
python3 canopen_tool.py
```

Replace `canopen_tool.py` with the actual filename if different.

---

## Application Setup

When the GUI opens, configure the following fields:

| Field    | Description                         | Example             |
| -------- | ----------------------------------- | ------------------- |
| Channel  | SocketCAN interface name            | `can0`              |
| Node ID  | CANopen node ID of the motor driver | `1`                 |
| EDS      | Path to the EDS/DCF file            | `DS301_profile.eds` |
| UDP IP   | Destination IP for TPDO JSON stream | `127.0.0.1`         |
| UDP Port | Destination UDP port                | `5005`              |

Then click:

```text
Connect
```

---

## Basic Operations

### Read Device Type

Click:

```text
Read Device Type (0x1000)
```

This reads CANopen object:

```text
0x1000 - Device Type
```

The application displays the raw device type value, profile number, and device-specific information.

---

### Set Heartbeat Producer Time

Enter the heartbeat time in milliseconds and click:

```text
Set Heartbeat (0x1017 ms)
```

This writes to CANopen object:

```text
0x1017 - Producer Heartbeat Time
```

Example value:

```text
1000
```

This configures the device to send a heartbeat every 1000 ms.

---

### Change NMT State

Use the following buttons to change the CANopen NMT state:

```text
PRE-OP
OPERATIONAL
```

`PRE-OP` switches the node to `PRE-OPERATIONAL`.

`OPERATIONAL` sends the CANopen **NMT Start Remote Node** command and switches the drive to `OPERATIONAL` state.

After the drive enters `OPERATIONAL` state, real-time command and feedback exchange happens through PDOs.


---
## Operational Phase

After sending the CANopen **NMT Start Remote Node** command, the drive enters the `OPERATIONAL` state.

In the operational phase, real-time commands are sent using **Receive PDOs (RPDOs)**, and real-time feedback is received using **Transmit PDOs (TPDOs)**.

---

### RPDO Command Mapping

| PDO   |            COB-ID | Purpose                             |
| ----- | ----------------: | ----------------------------------- |
| RPDO1 | `0x200 + node_id` | Controlword, mode, target Iq        |
| RPDO2 | `0x300 + node_id` | Current-loop gains                  |
| RPDO3 | `0x400 + node_id` | Velocity-loop gains                 |
| RPDO4 | `0x500 + node_id` | Position-loop gains                 |
| RPDO5 | `0x680 + node_id` | Target position and target velocity |
| RPDO6 | `0x690 + node_id` | Acceleration and deceleration       |

---

### TPDO Feedback Mapping

| PDO   |            COB-ID | Purpose                          |
| ----- | ----------------: | -------------------------------- |
| TPDO1 | `0x180 + node_id` | Position feedback                |
| TPDO2 | `0x280 + node_id` | Velocity feedback                |
| TPDO3 | `0x380 + node_id` | Current feedback                 |
| TPDO4 | `0x480 + node_id` | Commanded internal motion values |

---

### Example COB-IDs

For node ID `2`, the PDO COB-IDs become:

| PDO   |  COB-ID |
| ----- | ------: |
| RPDO1 | `0x202` |
| RPDO2 | `0x302` |
| RPDO3 | `0x402` |
| RPDO4 | `0x502` |
| RPDO5 | `0x682` |
| RPDO6 | `0x692` |
| TPDO1 | `0x182` |
| TPDO2 | `0x282` |
| TPDO3 | `0x382` |
| TPDO4 | `0x482` |

### Set Controlword

Click:

```text
Set Controlword = 0x000F
```

This writes:

```text
0x000F
```

to CANopen object:

```text
0x6040 - Controlword
```

---

## TPDO to UDP JSON Streaming

Enable:

```text
Stream TPDO → UDP JSON
```

The application reads the configured TPDO mappings and sends received TPDO data as JSON over UDP.

Default UDP target:

```text
127.0.0.1:5005
```

Example JSON output:

```json
{
  "tpdo": 1,
  "data": {
    "Actual velocity": 1200.0,
    "Actual current": 1.25
  }
}
```

The actual field names depend on the EDS file and TPDO mapping.

---

## Listening to UDP Data

You can listen for UDP packets on port `5005` using tools such as `nc`:

```bash
nc -ul 5005
```

---

## RPDO Send

The application can read RPDO mappings and send RPDO values.

Steps:

1. Select the RPDO number from the dropdown.
2. Click:

```text
Refresh Mapping
```

3. Edit the values in the `Value` column.
4. Click:

```text
Send RPDO
```

The application transmits the selected RPDO with the entered values.

---

## Status Monitoring

The application periodically reads status register:

```text
0x2000
```

The following status bits are displayed:

| Bit | Status                     |
| --: | -------------------------- |
|   0 | VCC UVLO                   |
|   1 | Thermal shutdown           |
|   2 | VDS protection             |
|   3 | RESET flag                 |
|   7 | Protected registers locked |

Green indicates inactive/normal.

Red indicates active/fault condition.

---

## Temperature Monitoring

The application periodically reads temperature register:

```text
0x2300
```

The raw value is converted as:

```text
Temperature °C = raw value / 100
```

Temperature display color:

|    Temperature | Color  |
| -------------: | ------ |
|    Below 55 °C | Green  |
| 55 °C to 80 °C | Yellow |
|    Above 80 °C | Red    |

---

## Communication Timeout

The application checks whether the device is responding.

If no valid response is received for more than approximately 2.5 seconds, the GUI displays:

```text
No response received
```

When communication recovers, the warning is cleared automatically.

---

## Troubleshooting

### CAN interface not found

Check available interfaces:

```bash
ifconfig -a
```

Make sure the CAN adapter is connected and its driver is loaded.

---

### CAN interface is down

Bring up the CAN interface:

```bash
sudo ip link set can0 type can bitrate 500000 && sudo ip link set can0 up
```

---

### No CAN messages in candump

Run:

```bash
candump can0
```

If no messages appear:

* Check CAN wiring
* Check CAN_H and CAN_L polarity
* Check that the motor driver is powered
* Check that the CAN bitrate is 500 kbps
* Check CAN termination resistors
* Check that the node ID is correct

---

### Permission error when using CAN

Try running the application with `sudo`:

```bash
sudo python3 canopen_tool.py
```

Alternatively, configure user permissions for CAN/network access as appropriate for your Linux setup.

---

### EDS file error

Make sure the selected EDS/DCF file matches the connected CANopen device.

If the EDS file does not match the device, PDO mapping, SDO access, or object names may not work correctly.

---

## Useful CAN Commands

Bring CAN interface up:

```bash
sudo ip link set can0 type can bitrate 500000 && sudo ip link set can0 up
```

Bring CAN interface down:

```bash
sudo ip link set can0 down
```

Monitor CAN traffic:

```bash
candump can0
```

Send a CAN frame manually:

```bash
cansend can0 702#05
```

Show CAN interface details:

```bash
ip -details link show can0
```

---

## Notes

* The CAN bitrate is fixed at **500 kbps** for this motor driver setup.
* The default CAN channel used by the GUI is `can0`.
* The default EDS filename shown in the GUI is `DS301_profile.eds`.
* The default UDP stream target is `127.0.0.1:5005`.
* Make sure the CAN interface is already up before connecting from the GUI.
  :::{/* empty */}
