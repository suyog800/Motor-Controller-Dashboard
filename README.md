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
python3 canopen_gui_v3.py
```

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


## Mental Model for Programming the Motion Controller

Programming the Motion Controller can be understood in three main stages:

1. Connect to the CANopen node
2. Initialize motor parameters
3. Enable the controller and send motion commands

The important point is that **putting the node into Operational state does not automatically engage the motor**. Operational state enables PDO communication. The motor is engaged only after the controller is enabled using the controlword.

---

## 1. Connect to the CANopen Node

The first step is to establish communication with the CANopen node.

Typical setup:

* Bring up the CAN interface, for example `can0`
* Use the fixed CAN bitrate of `500 kbps`
* Select the correct node ID
* Load the correct EDS/DCF file
* Connect to the node from the GUI

After connection, verify communication by reading a known object such as:

```text
0x1000 - Device Type
```

You can also configure the heartbeat producer time using:

```text
0x1017 - Producer Heartbeat Time
```

At this stage, the device can communicate using SDOs.

---

## 2. Initialize Motor Parameters

After basic communication is working, set the node to `OPERATIONAL`.

In `OPERATIONAL` state, the drive can communicate using both SDOs and PDOs. However, the motor is still not engaged until the controlword is set to enable operation.

During initialization, configure the parameters required for your selected control mode.

Recommended initialization order:

1. Set current-loop gains
2. Set velocity-loop gains
3. Set position-loop gains
4. Select the required control mode
5. Set acceleration and deceleration values if required

---

### Set Current-Loop Gains

Use RPDO2 to configure the current-loop gains.

| PDO   |            COB-ID | Purpose            |
| ----- | ----------------: | ------------------ |
| RPDO2 | `0x300 + node_id` | Current-loop gains |

Typical parameters:

|   Object | Description                                    |
| -------: | ---------------------------------------------- |
| `0x2200` | q-axis current-loop proportional gain, `iq_kp` |
| `0x2201` | q-axis current-loop integral gain, `iq_ki`     |

---

### Set Velocity-Loop Gains

Use RPDO3 to configure the velocity-loop gains.

| PDO   |            COB-ID | Purpose             |
| ----- | ----------------: | ------------------- |
| RPDO3 | `0x400 + node_id` | Velocity-loop gains |

Typical parameters:

|   Object | Description                                               |
| -------: | --------------------------------------------------------- |
| `0x2202` | Velocity-loop proportional gain, `speed_kp`               |
| `0x2203` | Velocity-loop integral gain, `speed_ki`                   |
| `0x2204` | Velocity-loop derivative gain, `speed_kd`                 |
| `0x2205` | Velocity-loop derivative filter time constant, `speed_Tc` |

For these gain values, multiply the required value by `100` before sending.

Example:

```text
Required Kp = 0.3
Value to send = 0.3 × 100 = 30
```

---

### Set Position-Loop Gains

Use RPDO4 to configure the position-loop gains.

| PDO   |            COB-ID | Purpose             |
| ----- | ----------------: | ------------------- |
| RPDO4 | `0x500 + node_id` | Position-loop gains |

Typical parameters:

|   Object | Description                                             |
| -------: | ------------------------------------------------------- |
| `0x2206` | Position-loop proportional gain, `pos_kp`               |
| `0x2207` | Position-loop integral gain, `pos_ki`                   |
| `0x2208` | Position-loop derivative gain, `pos_kd`                 |
| `0x2209` | Position-loop derivative filter time constant, `pos_Tc` |

For these gain values, multiply the required value by `100` before sending.

---

### Select Mode of Operation

Select the required control mode by setting:

```text
0x6060 - Modes of Operation
```

Common mode values:

| Value | Mode                             |
| ----: | -------------------------------- |
|   `1` | Profile Position Mode            |
|   `3` | Profile Velocity Mode            |
|   `4` | Torque / Iq Control Mode         |
|   `8` | Cyclic Synchronous Position Mode |
|   `9` | Cyclic Synchronous Velocity Mode |

The drive reports the currently active mode through:

```text
0x6061 - Modes of Operation Display
```

---

### Set Acceleration and Deceleration

Use RPDO6 to configure acceleration and deceleration.

| PDO   |            COB-ID | Purpose                       |
| ----- | ----------------: | ----------------------------- |
| RPDO6 | `0x690 + node_id` | Acceleration and deceleration |

Typical parameters:

|   Object | Description         |
| -------: | ------------------- |
| `0x6083` | Target acceleration |
| `0x6084` | Target deceleration |

Acceleration and deceleration values are in `rps²`.

Multiply the required value by `100` before sending.

---

## 3. Enable the Controller and Send Commands

After all required parameters are initialized, engage the motor by setting the controlword to `15`.

```text
0x6040 - Controlword = 15
```

Hex equivalent:

```text
15 = 0x000F
```

After this command, the controller is enabled and starts acting on the motor based on the configured gains, selected mode of operation, acceleration/deceleration values, and incoming command references.

---

### Sending Motion Commands

Use the appropriate RPDO depending on the selected mode of operation.

RPDO1 is used for controlword, mode, and torque/Iq command.

| PDO   |            COB-ID | Purpose                      |
| ----- | ----------------: | ---------------------------- |
| RPDO1 | `0x200 + node_id` | Controlword, mode, target Iq |

RPDO5 is used for target position and target velocity.

| PDO   |            COB-ID | Purpose                             |
| ----- | ----------------: | ----------------------------------- |
| RPDO5 | `0x680 + node_id` | Target position and target velocity |

In position control mode, RPDO5 can be used to send:

* Target position
* Target velocity

In velocity control mode, RPDO5 can be used to send:

* Target velocity

In velocity control mode, the target position field is not considered by the controller.

---

## 4. Monitor Motor Data Using TPDOs

After the controller is enabled and commands are being sent, monitor real-time feedback using TPDOs.

### TPDO Feedback Mapping

| PDO   |            COB-ID | Purpose                          |
| ----- | ----------------: | -------------------------------- |
| TPDO1 | `0x180 + node_id` | Position feedback                |
| TPDO2 | `0x280 + node_id` | Velocity feedback                |
| TPDO3 | `0x380 + node_id` | Current feedback                 |
| TPDO4 | `0x480 + node_id` | Commanded internal motion values |

TPDO feedback helps verify whether the motor is following the commanded position, velocity, and current references correctly.

---

## Important Note: Changing Mode of Operation

If you want to change the `mode_of_operation`, first disengage the motor.

Recommended sequence:

1. Set the controlword to `0`
2. Change `mode_of_operation`
3. Set the appropriate gain values for the new mode
4. Set acceleration and deceleration values if required
5. Set the controlword to `15` to engage the motor again

Do not change the control mode while the motor is actively engaged unless the application has been specifically designed to handle that transition safely.


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
## Motor Parameters and Pre-Tuned Gains

Motor parameters and gains for some pre-tuned motors are available in the following Excel file:

[Click here to open Motor Charastics.xlsx](https://optivalhealthsolutions-my.sharepoint.com/:x:/r/personal/suyog_ch_optivalhealthsolutions_onmicrosoft_com/Documents/Motor%20Charastics.xlsx?d=w4f0457540f744b2aa9a45eddf709d8af&csf=1&web=1&e=ggayEA)

Use this file as a reference when selecting motor parameters, current-loop gains, velocity-loop gains, and position-loop gains for supported motors.

* The CAN bitrate is fixed at **500 kbps** for this motor driver setup.
* The default CAN channel used by the GUI is `can0`.
* The default EDS filename shown in the GUI is `DS301_profile.eds`.
* The default UDP stream target is `127.0.0.1:5005`.
* Make sure the CAN interface is already up before connecting from the GUI.
  :::{/* empty */}
