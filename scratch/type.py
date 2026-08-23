#!/usr/bin/env python3
# Invia una stringa come tasti alla VM via QMP human-monitor-command 'sendkey',
# poi INVIO. Per leggere output a schermo nelle VM senza seriale.
import socket, json, sys, time

sock_path = sys.argv[1]
text = sys.argv[2]

KMAP = {
    ' ': 'spc', '\n': 'ret', '/': 'slash', '.': 'dot', '-': 'minus',
    '_': 'shift-minus', '|': 'shift-backslash', ':': 'shift-semicolon',
    '=': 'equal', ',': 'comma', '*': 'shift-8', '"': 'shift-apostrophe',
    ';': 'semicolon', '&': 'shift-7', '>': 'shift-dot', '<': 'shift-comma',
    '(': 'shift-9', ')': 'shift-0', '$': 'shift-4', "'": 'apostrophe',
    '!': 'shift-1', '#': 'shift-3', '%': 'shift-5', '^': 'shift-6',
    '+': 'shift-equal', '?': 'shift-slash', '@': 'shift-2',
    '[': 'bracket_left', ']': 'bracket_right', '\\': 'backslash',
    '{': 'shift-bracket_left', '}': 'shift-bracket_right',
    '`': 'grave_accent', '~': 'shift-grave_accent',
}
def keyname(c):
    if c in KMAP: return KMAP[c]
    if c.isdigit(): return c
    if c.isalpha(): return c.lower() if c.islower() else 'shift-'+c.lower()
    return None

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(sock_path)
f = s.makefile('rwb', buffering=0)
def cmd(line):
    f.readline()  # consume async/greeting line as available
def send(obj):
    f.write((json.dumps(obj)+'\n').encode())
def recv():
    return f.readline()

recv()  # greeting
send({'execute':'qmp_capabilities'}); recv()

def hmc(c):
    send({'execute':'human-monitor-command','arguments':{'command-line':c}})
    recv()

for ch in text:
    k = keyname(ch)
    if k is None: continue
    hmc('sendkey '+k)
    time.sleep(0.03)
hmc('sendkey ret')
time.sleep(0.2)
s.close()
