#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 CANopen utility:
- Connect to a node (channel, node id, EDS file)
- Read device type (0x1000)
- Set heartbeat producer time (0x1017)
- Switch NMT state: PRE-OPERATIONAL / OPERATIONAL
- Stream TPDOs as JSON over UDP in the background
- Send values via RPDO (write to any mapped PDO)
"""
import sys
import json
import socket
import traceback
from typing import Dict, List, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets

import canopen
from canopen.sdo import SdoAbortedError


# --------------------------- Backend Worker ---------------------------

class CanopenBackend(QtCore.QObject):
    log = QtCore.pyqtSignal(str)
    hb = QtCore.pyqtSignal(int)                     # heartbeat byte (NMT state)
    deviceTypeRead = QtCore.pyqtSignal(str)         # formatted device type text
    connectedChanged = QtCore.pyqtSignal(bool)
    rpdoMappingReady = QtCore.pyqtSignal(int, list) # (pdo_no, [(name, index, subindex)])
    tpdoJsonSent = QtCore.pyqtSignal(int, str)      # (tpdo_no, json string)

    def __init__(self):
        super().__init__()
        self.net: canopen.Network | None = None
        self.node: canopen.RemoteNode | None = None
        self.sock: socket.socket | None = None
        self.udp_target = ("127.0.0.1", 5005)
        self.streaming = False
        self._tpdo_callbacks_set = False

    # ---------- lifecycle ----------
    @QtCore.pyqtSlot(str, int, str, str, int)
    def connect_node(self, channel: str, node_id: int, eds_path: str, udp_ip: str, udp_port: int):
        try:
            self.disconnect_node()  # clean prior
            self.log.emit(f"Connecting on {channel}, node {node_id} …")
            self.net = canopen.Network()
            self.net.connect(channel=channel, bustype="socketcan")
            self.node = self.net.add_node(node_id, eds_path)
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_target = (udp_ip, int(udp_port))

            # heartbeat callback (fires when HB frames arrive)
            self.node.nmt.add_heartbeat_callback(self._on_heartbeat)

            # Read PDO configuration from device
            self.node.tpdo.read()
            self.node.rpdo.read()

            self.connectedChanged.emit(True)
            self.log.emit("Connected ✔")
        except Exception as e:
            self._emit_exception("connect_node", e)

    @QtCore.pyqtSlot()
    def disconnect_node(self):
        try:
            if self.node:
                # remove TPDO callbacks if any
                if self._tpdo_callbacks_set:
                    for n in range(1, 9):
                        try:
                            tpdo = self.node.tpdo[n]
                            if hasattr(tpdo, "clear_callbacks"):
                                tpdo.clear_callbacks()
                            else:
                                # manually remove callbacks if needed
                                try:
                                    tpdo.callbacks.clear()     # newer python-canopen versions store them here
                                except AttributeError:
                                    pass
                        except Exception:
                            pass
                    self._tpdo_callbacks_set = False
            if self.net:
                self.net.disconnect()
            if self.sock:
                self.sock.close()
        finally:
            self.net = None
            self.node = None
            self.sock = None
            self.connectedChanged.emit(False)

    # ---------- simple ops ----------
    @QtCore.pyqtSlot()
    def read_device_type(self):
        try:
            self._assert_node()
            val = self.node.sdo[0x1000].raw
            profile = (val >> 16) & 0xFFFF
            specific = val & 0xFFFF
            txt = f"Device Type 0x1000: 0x{val:08X}  |  Profile: 0x{profile:04X}  Specific: 0x{specific:04X}"
            self.deviceTypeRead.emit(txt)
            self.log.emit(txt)
        except Exception as e:
            self._emit_exception("read_device_type", e)

    @QtCore.pyqtSlot(int)
    def set_heartbeat(self, ms: int):
        try:
            self._assert_node()
            self.node.sdo[0x1017].raw = int(ms)
            confirmed = self.node.sdo[0x1017].raw
            self.log.emit(f"Heartbeat producer 0x1017 set → {confirmed} ms")
        except Exception as e:
            self._emit_exception("set_heartbeat", e)

    @QtCore.pyqtSlot()
    def set_preop(self):
        try:
            self._assert_node()
            self.node.nmt.state = "PRE-OPERATIONAL"
            self.log.emit("NMT → PRE-OPERATIONAL")
        except Exception as e:
            self._emit_exception("set_preop", e)

    @QtCore.pyqtSlot()
    def set_op(self):
        try:
            self._assert_node()
            self.node.nmt.state = "OPERATIONAL"
            self.log.emit("NMT → OPERATIONAL")
        except Exception as e:
            self._emit_exception("set_op", e)

    # ---------- TPDO streaming (callbacks → UDP) ----------
    @QtCore.pyqtSlot(bool)
    def enable_streaming(self, enable: bool):
        try:
            self._assert_node()
            self.streaming = enable
            if enable:
                # (re)read mapping to be sure
                self.node.tpdo.read()
                # attach callbacks for all mapped TPDOs
                for n in range(1, 9):
                    try:
                        if list(self.node.tpdo[n]):  # non-empty mapping
                            tpdo = self.node.tpdo[n]
                            if hasattr(tpdo, "clear_callbacks"):
                                tpdo.clear_callbacks()
                            else:
                                # manually remove callbacks if needed
                                try:
                                    tpdo.callbacks.clear()     # newer python-canopen versions store them here
                                except AttributeError:
                                    pass
                            self.node.tpdo[n].add_callback(self._make_tpdo_cb(n))
                            self.log.emit(f"Streaming TPDO{n} → UDP {self.udp_target[0]}:{self.udp_target[1]}")
                    except KeyError:
                        pass
                self._tpdo_callbacks_set = True
            else:
                # detach
                for n in range(1, 9):
                    try:
                        tpdo = self.node.tpdo[n]
                        if hasattr(tpdo, "clear_callbacks"):
                            tpdo.clear_callbacks()
                        else:
                            # manually remove callbacks if needed
                            try:
                                tpdo.callbacks.clear()     # newer python-canopen versions store them here
                            except AttributeError:
                                pass
                    except Exception:
                        pass
                self._tpdo_callbacks_set = False
                self.log.emit("Streaming disabled")
        except Exception as e:
            self._emit_exception("enable_streaming", e)

    def _make_tpdo_cb(self, n: int):
        def _cb(_frame):
            if not self.streaming or self.sock is None:
                return
            try:
                values = {}
                for v in self.node.tpdo[n]:
                    name = v.name or f"0x{v.index:04X}/{v.subindex:02X}"
                    try:
                        val = float(v.phys)
                    except Exception:
                        val = float(v.raw)
                    values[name] = val
                js = json.dumps({"tpdo": n, "data": values})
                self.sock.sendto(js.encode("utf-8"), self.udp_target)
                self.tpdoJsonSent.emit(n, js)
            except Exception as e:
                self._emit_exception(f"tpdo{n}_callback", e)
        return _cb

    # ---------- RPDO write ----------
    @QtCore.pyqtSlot(int)
    def refresh_rpdo_mapping(self, pdo_no: int):
        """Emit current mapping *and live SDO values* for RPDO 'pdo_no'"""
        try:
            self._assert_node()
            self.node.rpdo.read()  # refresh comm/mapping
            rpdo = self.node.rpdo[pdo_no]
            items = []

            for v in rpdo:
                name = v.name or f"0x{v.index:04X}/{v.subindex:02X}"
                current_val = None
                try:
                    # Use SDO read from the device directly
                    entry = self.node.sdo[v.index]
                    sub = entry[v.subindex]
                    current_val = sub.raw
                except Exception as e:
                    # fall back to last cached local value
                    try:
                        current_val = getattr(v, "phys", None)
                        if current_val is None:
                            current_val = v.raw
                    except Exception:
                        current_val = None
                items.append((name, v.index, v.subindex, current_val))

            self.rpdoMappingReady.emit(pdo_no, items)
            self.log.emit(f"RPDO{pdo_no} mapping refreshed (live SDO reads): {[(i[0], i[3]) for i in items]}")
        except Exception as e:
            self._emit_exception("refresh_rpdo_mapping", e)



    @QtCore.pyqtSlot(int, dict)
    def send_rpdo_values(self, pdo_no: int, values: Dict[str, float]):
        """
        values: {"name or idx/sub": numeric_value, ...}
        Writes to mapped vars then transmits the RPDO.
        """
        try:
            self._assert_node()
            rpdo = self.node.rpdo[pdo_no]
            if not list(rpdo):
                self.log.emit(f"RPDO{pdo_no} has empty mapping.")
                return
            # assign values
            for v in rpdo:
                key1 = v.name or f"0x{v.index:04X}/{v.subindex:02X}"
                key2 = f"0x{v.index:04X}/{v.subindex:02X}"
                if key1 in values:
                    val = values[key1]
                elif key2 in values:
                    val = values[key2]
                else:
                    continue
                try:
                    v.phys = val
                except Exception:
                    v.raw = int(val)
            rpdo.transmit()
            self.log.emit(f"RPDO{pdo_no} transmitted: {values}")
        except Exception as e:
            self._emit_exception("send_rpdo_values", e)

    # ---------- helpers ----------
    def _on_heartbeat(self, state: int):
        self.hb.emit(state)

    def _assert_node(self):
        if self.node is None or self.net is None:
            raise RuntimeError("Not connected")

    def _emit_exception(self, where: str, e: Exception):
        tb = "".join(traceback.format_exception_only(type(e), e)).strip()
        self.log.emit(f"[{where}] ERROR: {tb}")
        
    @QtCore.pyqtSlot()
    def set_controlword(self):
        """Write 0x000F to Controlword (0x6040)"""
        try:
            self._assert_node()
            self.node.sdo[0x6040].raw = 0x000F
            confirmed = self.node.sdo[0x6040].raw
            self.log.emit(f"Controlword (0x6040) set → 0x{confirmed:04X}")
        except Exception as e:
            self._emit_exception("set_controlword", e)


# --------------------------- UI ---------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CANopen Tool — TPDO→UDP & RPDO TX")
        self.resize(980, 680)

        # backend thread
        self.backend = CanopenBackend()
        self.thread = QtCore.QThread(self)
        self.backend.moveToThread(self.thread)
        self.thread.start()

        # widgets
        w = QtWidgets.QWidget(self)
        self.setCentralWidget(w)
        grid = QtWidgets.QGridLayout(w)

        # Connection row
        self.leChannel = QtWidgets.QLineEdit("can0")
        self.sbNodeId = QtWidgets.QSpinBox(); self.sbNodeId.setRange(1, 127); self.sbNodeId.setValue(1)
        self.leEds = QtWidgets.QLineEdit("DS301_profile.eds")
        btnBrowse = QtWidgets.QPushButton("Browse…")
        self.leUdpIp = QtWidgets.QLineEdit("127.0.0.1")
        self.sbUdpPort = QtWidgets.QSpinBox(); self.sbUdpPort.setRange(1, 65535); self.sbUdpPort.setValue(5005)
        btnConnect = QtWidgets.QPushButton("Connect")
        btnDisconnect = QtWidgets.QPushButton("Disconnect")

        row = 0
        grid.addWidget(QtWidgets.QLabel("Channel"), row, 0); grid.addWidget(self.leChannel, row, 1)
        grid.addWidget(QtWidgets.QLabel("Node ID"), row, 2); grid.addWidget(self.sbNodeId, row, 3)
        grid.addWidget(QtWidgets.QLabel("EDS"), row, 4); grid.addWidget(self.leEds, row, 5); grid.addWidget(btnBrowse, row, 6)
        grid.addWidget(QtWidgets.QLabel("UDP IP"), row, 7); grid.addWidget(self.leUdpIp, row, 8)
        grid.addWidget(QtWidgets.QLabel("UDP Port"), row, 9); grid.addWidget(self.sbUdpPort, row, 10)
        grid.addWidget(btnConnect, row, 11); grid.addWidget(btnDisconnect, row, 12)

        # Ops row
        row += 1
        btnRead1000 = QtWidgets.QPushButton("Read Device Type (0x1000)")
        self.sbHb = QtWidgets.QSpinBox(); self.sbHb.setRange(0, 60000); self.sbHb.setValue(1000)
        btnSetHb = QtWidgets.QPushButton("Set Heartbeat (0x1017 ms)")
        grid.addWidget(btnRead1000, row, 0, 1, 3)
        grid.addWidget(self.sbHb, row, 3)   
        grid.addWidget(btnSetHb, row, 4, 1, 3)
        btnPreOp = QtWidgets.QPushButton("PRE-OP")
        btnOp = QtWidgets.QPushButton("OPERATIONAL")
        btnCtrl = QtWidgets.QPushButton("Set Controlword = 0x000F")
        self.chkStream = QtWidgets.QCheckBox("Stream TPDO → UDP JSON")

        grid.addWidget(btnPreOp, row, 7)
        grid.addWidget(btnOp, row, 8)
        grid.addWidget(btnCtrl, row, 9)
        grid.addWidget(self.chkStream, row, 10, 1, 3)
        btnCtrl.clicked.connect(lambda: QtCore.QMetaObject.invokeMethod(self.backend, "set_controlword"))



        # RPDO panel
        row += 1
        grid.addWidget(self._make_rpdo_group(), row, 0, 1, 13)

        # Log
        row += 1
        self.teLog = QtWidgets.QPlainTextEdit(); self.teLog.setReadOnly(True)
        grid.addWidget(self.teLog, row, 0, 1, 13)

        # Connections
        btnBrowse.clicked.connect(self._browse_eds)
        btnConnect.clicked.connect(self._connect)
        btnDisconnect.clicked.connect(self._disconnect)
        btnRead1000.clicked.connect(lambda: QtCore.QMetaObject.invokeMethod(self.backend, "read_device_type"))
        btnSetHb.clicked.connect(lambda: QtCore.QMetaObject.invokeMethod(self.backend, "set_heartbeat", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(int, self.sbHb.value())))
        btnPreOp.clicked.connect(lambda: QtCore.QMetaObject.invokeMethod(self.backend, "set_preop"))
        btnOp.clicked.connect(lambda: QtCore.QMetaObject.invokeMethod(self.backend, "set_op"))
        self.chkStream.toggled.connect(lambda b: QtCore.QMetaObject.invokeMethod(self.backend, "enable_streaming", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(bool, b)))

        # backend signals
        self.backend.log.connect(self._log)
        self.backend.connectedChanged.connect(lambda b: self._log(f"Connected: {b}"))
        self.backend.hb.connect(lambda s: self._log(f"[HB] NMT={s}"))
        self.backend.deviceTypeRead.connect(self._log)
        self.backend.rpdoMappingReady.connect(self._populate_rpdo_table)
        self.backend.tpdoJsonSent.connect(lambda n, js: self._log(f"[TPDO{n}] UDP {js}"))

    # ----- RPDO UI -----
    def _make_rpdo_group(self):
        g = QtWidgets.QGroupBox("RPDO Send")
        lay = QtWidgets.QGridLayout(g)
        self.cbRpdoNo = QtWidgets.QComboBox()
        self.cbRpdoNo.addItems([str(i) for i in range(1, 9)])
        btnRefresh = QtWidgets.QPushButton("Refresh Mapping")
        self.tblRpdo = QtWidgets.QTableWidget(0, 2)
        self.tblRpdo.setHorizontalHeaderLabels(["Mapped Object", "Value"])
        self.tblRpdo.horizontalHeader().setStretchLastSection(True)
        btnSend = QtWidgets.QPushButton("Send RPDO")

        lay.addWidget(QtWidgets.QLabel("RPDO #"), 0, 0)
        lay.addWidget(self.cbRpdoNo, 0, 1)
        lay.addWidget(btnRefresh, 0, 2)
        lay.addWidget(self.tblRpdo, 1, 0, 1, 3)
        lay.addWidget(btnSend, 2, 2)

        btnRefresh.clicked.connect(self._refresh_rpdo)
        btnSend.clicked.connect(self._send_rpdo)
        return g

    def _refresh_rpdo(self):
        pdo_no = int(self.cbRpdoNo.currentText())
        QtCore.QMetaObject.invokeMethod(
            self.backend, "refresh_rpdo_mapping",
            QtCore.Qt.QueuedConnection, QtCore.Q_ARG(int, pdo_no)
        )

    def _populate_rpdo_table(self, pdo_no: int, items: List[Tuple[str, int, int, float]]):
        self.tblRpdo.setRowCount(0)
        for name, idx, sub, val in items:
            r = self.tblRpdo.rowCount()
            self.tblRpdo.insertRow(r)
            item0 = QtWidgets.QTableWidgetItem(name or f"0x{idx:04X}/{sub:02X}")
            item0.setFlags(item0.flags() ^ QtCore.Qt.ItemIsEditable)
            self.tblRpdo.setItem(r, 0, item0)

            # Pre-fill with the current live value (if any)
            val_str = "0" if val is None else str(val)
            self.tblRpdo.setItem(r, 1, QtWidgets.QTableWidgetItem(val_str))

        if not items:
            self._log(f"RPDO{pdo_no} has no mapped variables.")


    def _send_rpdo(self):
        pdo_no = int(self.cbRpdoNo.currentText())
        values = {}
        for r in range(self.tblRpdo.rowCount()):
            name = self.tblRpdo.item(r, 0).text()
            try:
                val = float(self.tblRpdo.item(r, 1).text())
            except Exception:
                val = 0.0
            values[name] = val
        QtCore.QMetaObject.invokeMethod(
            self.backend, "send_rpdo_values",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(int, pdo_no),
            QtCore.Q_ARG(dict, values),
        )

    # ----- helpers -----
    def _browse_eds(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select EDS/DCF", "", "EDS/DCF (*.eds *.dcf);;All Files (*)")
        if path:
            self.leEds.setText(path)

    def _connect(self):
        QtCore.QMetaObject.invokeMethod(
            self.backend, "connect_node", QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, self.leChannel.text()),
            QtCore.Q_ARG(int, self.sbNodeId.value()),
            QtCore.Q_ARG(str, self.leEds.text()),
            QtCore.Q_ARG(str, self.leUdpIp.text()),
            QtCore.Q_ARG(int, self.sbUdpPort.value()),
        )

    def _disconnect(self):
        QtCore.QMetaObject.invokeMethod(self.backend, "disconnect_node")

    def _log(self, msg: str):
        self.teLog.appendPlainText(msg)


def main():
    app = QtWidgets.QApplication(sys.argv)
    mw = MainWindow()
    mw.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
