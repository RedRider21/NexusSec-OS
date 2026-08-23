#!/usr/bin/env python3
# Client QMP minimale: handshake + screendump PNG (fallback PPM).
import socket, json, sys, time

sock_path = sys.argv[1]
out = sys.argv[2]
fmt = sys.argv[3] if len(sys.argv) > 3 else "png"

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(sock_path)
f = s.makefile("rwb", buffering=0)

def recv():
    line = f.readline()
    return json.loads(line.decode())

def send(obj):
    f.write((json.dumps(obj) + "\n").encode())

recv()  # greeting
send({"execute": "qmp_capabilities"})
recv()
args = {"filename": out}
if fmt:
    args["format"] = fmt
send({"execute": "screendump", "arguments": args})
print(json.dumps(recv()))
time.sleep(0.3)
s.close()
