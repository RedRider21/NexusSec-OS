#!/usr/bin/env python3
# Click assoluto via QMP input-send-event (richiede -device usb-tablet).
# uso: click.py <sock> <x_px> <y_px> [W H]  (default 1280x800)
import socket, json, sys, time
sock_path, xpx, ypx = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
W = int(sys.argv[4]) if len(sys.argv) > 4 else 1280
H = int(sys.argv[5]) if len(sys.argv) > 5 else 800
ax = int(xpx / W * 32767)
ay = int(ypx / H * 32767)
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(sock_path)
f = s.makefile("rwb", buffering=0)
def send(o): f.write((json.dumps(o) + "\n").encode())
def recv(): return f.readline()
recv(); send({"execute": "qmp_capabilities"}); recv()
def ev(events): send({"execute": "input-send-event", "arguments": {"events": events}}); recv()
# muovi
ev([{"type": "abs", "data": {"axis": "x", "value": ax}},
    {"type": "abs", "data": {"axis": "y", "value": ay}}])
time.sleep(0.2)
# press + release
ev([{"type": "btn", "data": {"button": "left", "down": True}}])
time.sleep(0.12)
ev([{"type": "btn", "data": {"button": "left", "down": False}}])
time.sleep(0.3)
s.close()
print("click @ %d,%d" % (xpx, ypx))
