"""Client WebSocket minimale (solo quel che serve a HORUS per aisstream).

Python non ha un client WebSocket in stdlib e la distro e' spesso offline: qui
c'e' l'essenziale per aprire una wss://, mandare un frame di testo (la
sottoscrizione) e leggere i frame di testo in arrivo per qualche secondo.
Nessuna dipendenza esterna; opzionalmente instrada via Tor (PySocks).

Non e' un'implementazione completa del protocollo: niente permessi di
frammentazione lato client, niente ping/pong attivi (aisstream manda dati
subito). Sufficiente e contenuto.
"""
from __future__ import annotations

import base64
import os
import socket
import ssl
import struct
import time


def _connect_sock(host, port, tor_host=None, tor_port=None):
    if tor_host:
        import socks  # PySocks vendorizzato (vedi server._PYSOCKS su sys.path)
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, tor_host, tor_port, rdns=True)
    else:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(12)
    s.connect((host, port))
    ctx = ssl.create_default_context()
    return ctx.wrap_socket(s, server_hostname=host)


def _handshake(sock, host, path):
    key = base64.b64encode(os.urandom(16)).decode()
    req = ("GET %s HTTP/1.1\r\n"
           "Host: %s\r\n"
           "Upgrade: websocket\r\n"
           "Connection: Upgrade\r\n"
           "Sec-WebSocket-Key: %s\r\n"
           "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host, key))
    sock.sendall(req.encode())
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(1024)
        if not chunk:
            raise IOError("handshake WebSocket fallito")
        data += chunk
        if len(data) > 65536:
            raise IOError("handshake troppo lungo")
    if b" 101 " not in data.split(b"\r\n", 1)[0]:
        raise IOError("upgrade WebSocket rifiutato")


def _send_text(sock, text):
    payload = text.encode("utf-8")
    header = bytearray([0x81])  # FIN + opcode testo
    n = len(payload)
    mask = os.urandom(4)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", n)
    header += mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes(header) + masked)


def read_text_for(sock, seconds):
    """Genera i payload (JSON) dei frame ricevuti entro `seconds`.

    NB: aisstream manda i messaggi come frame BINARI (opcode 0x2), non di testo
    (0x1) - il contenuto e' comunque JSON UTF-8. Accettiamo entrambi."""
    sock.settimeout(seconds)
    end = time.time() + seconds
    buf = b""
    while time.time() < end:
        try:
            chunk = sock.recv(65536)
        except (socket.timeout, ssl.SSLWantReadError):
            break
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        while len(buf) >= 2:
            b0, b1 = buf[0], buf[1]
            opcode = b0 & 0x0f
            masked = b1 & 0x80
            length = b1 & 0x7f
            idx = 2
            if length == 126:
                if len(buf) < 4:
                    break
                length = struct.unpack(">H", buf[2:4])[0]
                idx = 4
            elif length == 127:
                if len(buf) < 10:
                    break
                length = struct.unpack(">Q", buf[2:10])[0]
                idx = 10
            if masked:
                idx += 4
            if len(buf) < idx + length:
                break
            payload = buf[idx:idx + length]
            buf = buf[idx + length:]
            if opcode in (0x1, 0x2):   # testo o binario: entrambi JSON
                yield payload.decode("utf-8", "replace")
            elif opcode == 0x8:  # close
                return


class WSClient:
    """Connessione WebSocket persistente: apri una volta, invia sottoscrizioni e
    leggi i frame man mano (recv con timeout). Serve al flusso AIS continuo:
    resta aperta e alimenta lo store lato server. Gestisce ping->pong per tenere
    viva la connessione a lungo."""

    def __init__(self, host, path, tor=None):
        th, tp = (tor if tor else (None, None))
        self.sock = _connect_sock(host, 443, th, tp)
        _handshake(self.sock, host, path)
        self.buf = b""

    def send_text(self, text):
        _send_text(self.sock, text)

    def _pong(self, payload):
        # frame pong (opcode 0xA) mascherato, come richiede il protocollo lato client
        header = bytearray([0x8A])
        n = len(payload)
        mask = os.urandom(4)
        header.append(0x80 | n)   # i ping sono cortissimi (<126)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _take(self):
        """Estrae UN frame dati completo dal buffer, o None se incompleto."""
        buf = self.buf
        while len(buf) >= 2:
            b0, b1 = buf[0], buf[1]
            opcode = b0 & 0x0f
            masked = b1 & 0x80
            length = b1 & 0x7f
            idx = 2
            if length == 126:
                if len(buf) < 4:
                    break
                length = struct.unpack(">H", buf[2:4])[0]
                idx = 4
            elif length == 127:
                if len(buf) < 10:
                    break
                length = struct.unpack(">Q", buf[2:10])[0]
                idx = 10
            if masked:
                idx += 4
            if len(buf) < idx + length:
                break
            payload = buf[idx:idx + length]
            buf = buf[idx + length:]
            self.buf = buf
            if opcode in (0x1, 0x2):     # testo o binario: JSON
                return payload.decode("utf-8", "replace")
            if opcode == 0x8:            # close
                raise IOError("WebSocket chiuso dal server")
            if opcode == 0x9:            # ping -> pong
                try:
                    self._pong(payload)
                except OSError:
                    raise IOError("invio pong fallito")
                continue
            # pong/altri: ignora e continua
            continue
        self.buf = buf
        return None

    def recv(self, timeout):
        """Ritorna il payload del prossimo frame dati, o None se scade il timeout
        (utile per fare lavoro periodico anche quando non arrivano dati)."""
        fr = self._take()
        if fr is not None:
            return fr
        self.sock.settimeout(timeout)
        try:
            chunk = self.sock.recv(65536)
        except (socket.timeout, ssl.SSLWantReadError):
            return None
        if not chunk:
            raise IOError("connessione chiusa")
        self.buf += chunk
        return self._take()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def snapshot(host, path, subscribe_json, seconds=6, tor=None):
    """Apre wss://host/path, invia subscribe_json, raccoglie i messaggi di
    testo per `seconds` e li ritorna come lista di stringhe. `tor` = (host,port)
    per instradare via SOCKS, oppure None."""
    th, tp = (tor if tor else (None, None))
    sock = _connect_sock(host, 443, th, tp)
    try:
        _handshake(sock, host, path)
        _send_text(sock, subscribe_json)
        return list(read_text_for(sock, seconds))
    finally:
        try:
            sock.close()
        except OSError:
            pass
