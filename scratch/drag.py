#!/usr/bin/env python3
# Drag col tasto sinistro da (x1,y1) a (x2,y2), assoluto via QMP. Per testare il
# resize: partire sul bordo/handle della finestra. uso: drag.py sock x1 y1 x2 y2 [W H]
import socket, json, sys, time
sk, x1, y1, x2, y2 = sys.argv[1], *map(int, sys.argv[2:6])
W = int(sys.argv[6]) if len(sys.argv) > 6 else 1280
H = int(sys.argv[7]) if len(sys.argv) > 7 else 800
def A(v, M): return int(v / M * 32767)
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.connect(sk)
f = s.makefile("rwb", buffering=0)
def send(o): f.write((json.dumps(o)+"\n").encode())
f.readline(); send({"execute":"qmp_capabilities"}); f.readline()
def ev(e): send({"execute":"input-send-event","arguments":{"events":e}}); f.readline()
ev([{"type":"abs","data":{"axis":"x","value":A(x1,W)}},{"type":"abs","data":{"axis":"y","value":A(y1,H)}}]); time.sleep(0.2)
ev([{"type":"btn","data":{"button":"left","down":True}}]); time.sleep(0.2)
# muovi a step
for i in range(1,11):
    xi = x1+(x2-x1)*i//10; yi = y1+(y2-y1)*i//10
    ev([{"type":"abs","data":{"axis":"x","value":A(xi,W)}},{"type":"abs","data":{"axis":"y","value":A(yi,H)}}]); time.sleep(0.05)
ev([{"type":"btn","data":{"button":"left","down":False}}]); time.sleep(0.3)
s.close(); print("drag %d,%d -> %d,%d"%(x1,y1,x2,y2))
