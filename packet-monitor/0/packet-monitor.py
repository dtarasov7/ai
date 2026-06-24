#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

"""

import urwid
import sys
import signal
import argparse
import os
import traceback
from datetime import datetime
from scapy.utils import wrpcap, PcapWriter, hexdump
import io
import json
from scapy.all import Packet
from scapy.layers.l2 import Ether, ARP, Dot1Q
from scapy.layers.inet import IP, TCP, UDP, ICMP
from scapy.layers.dns import DNS, DNSQR, DNSRR
from scapy.layers.inet6 import IPv6, ICMPv6EchoRequest, ICMPv6EchoReply
from scapy.all import rdpcap
from scapy.all import sniff, conf, get_if_list
from scapy.packet import Raw
import re
from collections import defaultdict
from collections import Counter
from collections import deque
import threading
import time
import binascii
import hashlib
from typing import Optional

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
except Exception:
    x509 = None
    default_backend = None

__version__="1.6.0"
__author__ = "Tarasov Dmitry"

def sanitize_tui_text(s: str, max_len: int = 5000) -> str:
    if s is None:
        return ""
    s = str(s)
    if len(s) > max_len:
        s = s[:max_len]
    out = []
    for ch in s:
        o = ord(ch)
        # разрешим обычные печатные + пробел
        if ch in ("\n", "\r", "\t"):
            out.append(" ")
        elif o == 0x1b:  # ESC
            out.append("?")
        elif o < 32 or o == 127:  # прочие control
            out.append("?")
        else:
            out.append(ch)
    return "".join(out)

def bytes_to_pretty_text(data: bytes, max_len=200000):
    """
    Пытается показать как UTF-8 текст. Если много непечатного — fallback в hex.
    """
    if not data:
        return ""

    data = data[:max_len]

    # heuristic: если >20% байтов непечатные (кроме таб/переводов строки) -> hex
    bad = 0
    for b in data:
        if b in (9, 10, 13):  # \t \n \r
            continue
        if b < 32 or b == 127:
            bad += 1
    if bad / max(1, len(data)) > 0.20:
        # hex
        hx = binascii.hexlify(data).decode("ascii")
        # форматируем по 32 байта в строку
        lines = []
        for i in range(0, len(hx), 64):
            chunk = hx[i:i+64]
            lines.append(chunk)
        return "[hex]\n" + "\n".join(lines)

    # текст
    return data.decode("utf-8", errors="replace")


def safe_str(value, default='N/A'):
    """Безопасное преобразование в строку"""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def tls_summarize_stream(data: bytes) -> list[str]:
    """
    Из сырого TCP потока (в одном направлении) вынимает подряд TLS records
    и делает список строк: ClientHello SNI/ALPN, ServerHello ver/cipher, Alert fatal xxx, ...
    best-effort, без decryption.
    """
    def _tls_version_name(v: int) -> str:
        # TLS record/legacy versions
        return {
            0x0300: "SSL3.0",
            0x0301: "TLS1.0",
            0x0302: "TLS1.1",
            0x0303: "TLS1.2",
            0x0304: "TLS1.3",
        }.get(v, f"0x{v:04x}")

    def _alert_desc_name(d: int) -> str:
        # RFC 5246 + common
        return {
            0: "close_notify",
            10: "unexpected_message",
            20: "bad_record_mac",
            21: "decryption_failed",
            22: "record_overflow",
            40: "handshake_failure",
            42: "bad_certificate",
            43: "unsupported_certificate",
            44: "certificate_revoked",
            45: "certificate_expired",
            46: "certificate_unknown",
            47: "illegal_parameter",
            48: "unknown_ca",
            49: "access_denied",
            50: "decode_error",
            51: "decrypt_error",
            70: "protocol_version",
            71: "insufficient_security",
            80: "internal_error",
            86: "inappropriate_fallback",
            90: "user_canceled",
            109: "missing_extension",
            110: "unsupported_extension",
            112: "unrecognized_name",
            116: "certificate_required",
            120: "no_application_protocol",
        }.get(d, f"desc={d}")

    def _hs_type_name(t: int) -> str:
        return {
            0x01: "ClientHello",
            0x02: "ServerHello",
            0x0b: "Certificate",
            0x0e: "ServerHelloDone",
            0x10: "ClientKeyExchange",
            0x14: "Finished",
            0x08: "EncryptedExtensions",  # TLS1.3
            0x04: "NewSessionTicket",
            0x0f: "CertificateRequest",
            0x0d: "CertificateVerify",
        }.get(t, f"Handshake type=0x{t:02x}")

    def _parse_client_hello(hs: bytes) -> str:
        # hs = handshake body, starting after handshake header (type+len)
        # Return "ClientHello SNI=... ALPN=..."
        try:
            p = 0
            hs_end = len(hs)

            # legacy_version (2) + random(32)
            if p + 2 + 32 > hs_end:
                return "ClientHello"
            p += 2 + 32

            # session_id
            if p + 1 > hs_end:
                return "ClientHello"
            sid_len = hs[p]
            p += 1 + sid_len
            if p > hs_end:
                return "ClientHello"

            # cipher_suites
            if p + 2 > hs_end:
                return "ClientHello"
            cs_len = int.from_bytes(hs[p:p+2], "big")
            p += 2 + cs_len
            if p > hs_end:
                return "ClientHello"

            # compression_methods
            if p + 1 > hs_end:
                return "ClientHello"
            cm_len = hs[p]
            p += 1 + cm_len
            if p > hs_end:
                return "ClientHello"

            # extensions
            if p + 2 > hs_end:
                # TLS1.0/1.1 могут не иметь extensions
                return "ClientHello"
            ext_len = int.from_bytes(hs[p:p+2], "big")
            p += 2
            ext_end = min(p + ext_len, hs_end)

            sni = None
            alpns: list[str] = []

            while p + 4 <= ext_end:
                etype = int.from_bytes(hs[p:p+2], "big"); p += 2
                elen  = int.from_bytes(hs[p:p+2], "big"); p += 2
                if p + elen > ext_end:
                    break

                # server_name (0x0000)
                if etype == 0x0000 and elen >= 2:
                    q = p
                    list_len = int.from_bytes(hs[q:q+2], "big"); q += 2
                    list_end = min(p + elen, q + list_len)
                    while q + 3 <= list_end:
                        name_type = hs[q]; q += 1
                        name_len = int.from_bytes(hs[q:q+2], "big"); q += 2
                        if q + name_len > list_end:
                            break
                        if name_type == 0:
                            sni = hs[q:q+name_len].decode("utf-8", errors="replace").strip()
                            break
                        q += name_len

                # ALPN (0x0010)
                if etype == 0x0010 and elen >= 2:
                    q = p
                    list_len = int.from_bytes(hs[q:q+2], "big"); q += 2
                    list_end = min(p + elen, q + list_len)
                    while q < list_end:
                        if q + 1 > list_end:
                            break
                        ln = hs[q]; q += 1
                        if q + ln > list_end:
                            break
                        alpns.append(hs[q:q+ln].decode("utf-8", errors="replace"))
                        q += ln

                p += elen

            parts = []
            if sni:
                parts.append(f"SNI={sni}")
            if alpns:
                parts.append("ALPN=" + ",".join(alpns[:8]))
            if parts:
                return "ClientHello " + " ".join(parts)
            return "ClientHello"
        except Exception:
            return "ClientHello"

    def _parse_server_hello(hs: bytes) -> str:
        # hs = handshake body, starting after handshake header (type+len)
        # Return "ServerHello ver=TLS1.3 cipher=0x1301"
        try:
            p = 0
            hs_end = len(hs)

            if p + 2 + 32 > hs_end:
                return "ServerHello"
            legacy_ver = int.from_bytes(hs[p:p+2], "big"); p += 2
            p += 32  # random

            # session_id
            if p + 1 > hs_end:
                return "ServerHello"
            sid_len = hs[p]; p += 1 + sid_len
            if p > hs_end:
                return "ServerHello"

            # cipher_suite
            if p + 2 > hs_end:
                return "ServerHello"
            cipher = int.from_bytes(hs[p:p+2], "big"); p += 2

            # compression
            if p + 1 > hs_end:
                return f"ServerHello ver={_tls_version_name(legacy_ver)} cipher=0x{cipher:04x}"
            p += 1

            # default version by legacy
            ver = legacy_ver

            # extensions: try to find supported_versions (0x002b) for TLS1.3
            if p + 2 <= hs_end:
                ext_len = int.from_bytes(hs[p:p+2], "big"); p += 2
                ext_end = min(p + ext_len, hs_end)

                while p + 4 <= ext_end:
                    etype = int.from_bytes(hs[p:p+2], "big"); p += 2
                    elen  = int.from_bytes(hs[p:p+2], "big"); p += 2
                    if p + elen > ext_end:
                        break

                    if etype == 0x002b and elen >= 2:
                        # ServerHello supported_versions: selected_version(2)
                        sel = int.from_bytes(hs[p:p+2], "big")
                        ver = sel

                    p += elen

            return f"ServerHello ver={_tls_version_name(ver)} cipher=0x{cipher:04x}"
        except Exception:
            return "ServerHello"

    out: list[str] = []
    p = 0
    n = len(data)

    while p + 5 <= n:
        rtype = data[p]
        rver = int.from_bytes(data[p+1:p+3], "big")
        rlen = int.from_bytes(data[p+3:p+5], "big")
        p += 5

        if rlen < 0 or p + rlen > n:
            break

        body = data[p:p+rlen]
        p += rlen

        # Alert
        if rtype == 0x15:
            if len(body) >= 2:
                lvl = body[0]
                desc = body[1]
                lvl_s = {1: "warning", 2: "fatal"}.get(lvl, str(lvl))
                out.append(f"Alert {lvl_s} {_alert_desc_name(desc)}")
            else:
                out.append("Alert")
        # Handshake (может содержать несколько сообщений подряд)
        elif rtype == 0x16:
            q = 0
            while q + 4 <= len(body):
                hs_type = body[q]
                hs_len = int.from_bytes(body[q+1:q+4], "big")
                q += 4
                if hs_len < 0 or q + hs_len > len(body):
                    break
                hs_body = body[q:q+hs_len]
                q += hs_len

                if hs_type == 0x01:
                    out.append(_parse_client_hello(hs_body))
                elif hs_type == 0x02:
                    out.append(_parse_server_hello(hs_body))
                else:
                    out.append(_hs_type_name(hs_type))

                if len(out) >= 200:
                    out.append("... (truncated)")
                    return out

        # Application data
        elif rtype == 0x17:
            out.append("ApplicationData (encrypted)")
        else:
            out.append(f"Record type=0x{rtype:02x} ver={_tls_version_name(rver)} len={len(body)}")
            pass

        if len(out) >= 200:
            out.append("... (truncated)")
            break

    return out


def extract_tcp_payload_from_raw(frame: bytes) -> bytes:
    """
    Best-effort извлечение TCP payload из bytes(pkt) (Ethernet + IPv4/IPv6 + TCP).
    Возвращает payload или b"".
    """
    try:
        if not frame or len(frame) < 54:
            return b""

        # Ethernet type
        eth_type = int.from_bytes(frame[12:14], "big")
        off = 14  # Ethernet header

        # IPv4
        if eth_type == 0x0800:
            # минимум IPv4 header
            if len(frame) < off + 20:
                return b""

            ihl = (frame[off] & 0x0F) * 4
            # IHL должен быть минимум 20 байт и не выходить за frame
            if ihl < 20 or (off + ihl) > len(frame):
                return b""

            proto = frame[off + 9]
            if proto != 6:  # TCP
                return b""

            total_len = int.from_bytes(frame[off + 2:off + 4], "big")
            if total_len < ihl:
                return b""

            ip_off = off + ihl

            # минимум TCP header
            if len(frame) < ip_off + 20:
                return b""

            tcp_hlen = ((frame[ip_off + 12] >> 4) & 0x0F) * 4
            # TCP header length должен быть минимум 20
            if tcp_hlen < 20:
                return b""

            payload_off = ip_off + tcp_hlen

            end = min(off + total_len, len(frame))
            if payload_off >= end:
                return b""
            return frame[payload_off:end]

        # IPv6 (без extension headers)
        if eth_type == 0x86DD:
            if len(frame) < off + 40:
                return b""

            next_hdr = frame[off + 6]
            if next_hdr != 6:  # TCP (без ext headers)
                return b""

            payload_len = int.from_bytes(frame[off + 4:off + 6], "big")
            ip_off = off + 40

            # минимум TCP header
            if len(frame) < ip_off + 20:
                return b""

            tcp_hlen = ((frame[ip_off + 12] >> 4) & 0x0F) * 4
            if tcp_hlen < 20:
                return b""

            payload_off = ip_off + tcp_hlen

            end = min(ip_off + payload_len, len(frame))
            if payload_off >= end:
                return b""
            return frame[payload_off:end]

        return b""
    except Exception:
        return b""


def build_tcp_stream_raw_pair(packets, client_ip, client_port, server_ip, server_port):
    """
    Собирает raw TCP payload по направлениям простым конкатом (не seq-reassembly).
    Возвращает (c2s_bytes, s2c_bytes).
    Достаточно, чтобы распознать TLS handshake и сделать summary.
    """
    c2s = bytearray()
    s2c = bytearray()

    for p in packets:
        proto = str(p.get("proto", ""))
        if "TCP" not in proto:
            continue

        src_ip = p.get("src_ip")
        dst_ip = p.get("dst_ip")
        src_port = p.get("src_port")
        dst_port = p.get("dst_port")

        if not all([src_ip, dst_ip, src_port, dst_port]):
            continue

        is_c2s = (
            str(src_ip) == str(client_ip) and int(src_port) == int(client_port) and
            str(dst_ip) == str(server_ip) and int(dst_port) == int(server_port)
        )
        is_s2c = (
            str(src_ip) == str(server_ip) and int(src_port) == int(server_port) and
            str(dst_ip) == str(client_ip) and int(dst_port) == int(client_port)
        )

        if not (is_c2s or is_s2c):
            continue

        raw = p.get("raw")
        if not raw:
            continue

        payload = extract_tcp_payload_from_raw(raw)
        if not payload:
            continue

        if is_c2s:
            c2s.extend(payload)
        else:
            s2c.extend(payload)

    return bytes(c2s), bytes(s2c)


def looks_like_tls_stream(x: bytes) -> bool:
    """
    Быстрая эвристика TLS по первым байтам:
    record_type in {14,15,16,17} и major_version == 0x03.
    """
    if not x or len(x) < 3:
        return False
    return (x[0] in (0x14, 0x15, 0x16, 0x17)) and (x[1] == 0x03)


def build_tcp_stream_reassembled(packets, client_ip, client_port, server_ip, server_port):
    """Собрать (reassembly) TCP stream по направлениям Client→Server и Server→Client.

        Из списка packet_info (dict) выбирает пакеты TCP, принадлежащие 4-tuple:
        (client_ip:client_port ↔ server_ip:server_port), вытаскивает TCP payload + seq
        (через `extract_tcp_seq_payload`) и передаёт сегменты в `reassemble_tcp_direction()`.

        Важно:
          - reassembly делается best-effort (без учёта TCP window/ACK), но с:
            дедупликацией ретрансляций и вставкой gap placeholder'ов.
          - возвращаемые блоки пригодны для дальнейшего отображения/экспорта.

        Args:
            packets: Список пакетов программы (list[dict]) — обычно `packet_capture.get_packets()`.
            client_ip: IP клиента (str).
            client_port: TCP порт клиента (int|str, будет приведён к int).
            server_ip: IP сервера (str).
            server_port: TCP порт сервера (int|str, будет приведён к int).

        Returns:
            tuple[list[dict], list[dict]]:
                (blocks_c2s, blocks_s2c), где каждый blocks_* — список блоков вида:
                  {"kind":"data","data":bytes} и/или {"kind":"gap","missing":N}.
        """
    c2s_segments = []
    s2c_segments = []

    for p in packets:
        proto = p.get("proto", "")
        if "TCP" not in proto:
            continue
        if p.get("src_ip") is None or p.get("dst_ip") is None:
            continue
        if p.get("src_port") is None or p.get("dst_port") is None:
            continue

        s_ip, d_ip = str(p["src_ip"]), str(p["dst_ip"])
        s_po, d_po = int(p["src_port"]), int(p["dst_port"])

        is_c2s = (s_ip == str(client_ip) and d_ip == str(server_ip) and s_po == int(client_port) and d_po == int(server_port))
        is_s2c = (s_ip == str(server_ip) and d_ip == str(client_ip) and s_po == int(server_port) and d_po == int(client_port))
        if not (is_c2s or is_s2c):
            continue

        seq, payload = extract_tcp_seq_payload(p)
        if seq is None or not payload:
            continue

        seg = {"seq": int(seq), "data": payload, "ts": p.get("timestamp")}
        if is_c2s:
            c2s_segments.append(seg)
        else:
            s2c_segments.append(seg)

    blocks_c2s = reassemble_tcp_direction(c2s_segments)
    blocks_s2c = reassemble_tcp_direction(s2c_segments)
    return blocks_c2s, blocks_s2c


def extract_tcp_seq_payload(packet_dict):
    """
    Возвращает (seq:int|None, payload:bytes).
    Берём из raw, чтобы reassembly не зависел от форматирования info.
    """
    raw = packet_dict.get("raw", b"")
    if not raw:
        return None, b""

    # парсим как scapy packet
    sp = None
    try:
        sp = Ether(raw)
    except Exception:
        try:
            sp = IP(raw)
        except Exception:
            try:
                sp = IPv6(raw)
            except Exception:
                return packet_dict.get("tcp_seq"), b""

    try:
        if sp.haslayer(TCP):
            seq = int(sp[TCP].seq)
            payload = bytes(sp[TCP].payload) if sp[TCP].payload is not None else b""
            return seq, payload
    except Exception:
        pass

    # fallback
    return packet_dict.get("tcp_seq"), b""


def reassemble_tcp_direction(segments):
    """Выполнить reassembly одного направления TCP по seq.

    Алгоритм:
      1) отбрасывает сегменты без payload;
      2) дедуплицирует по seq (оставляет самый длинный payload для данного seq),
         что убирает типичные ретрансляции;
      3) сортирует по seq и собирает поток;
      4) при гэпах вставляет блок gap: {"kind":"gap","missing":N};
      5) при overlap/дубликатах обрезает перекрывающуюся часть.

    Args:
        segments: Список сегментов направления (list[dict]) формата:
            {"seq": int, "data": bytes, "ts": datetime|None}

    Returns:
        list[dict]: Список блоков в порядке следования в потоке:
            - {"kind":"data","data": bytes}
            - {"kind":"gap","missing": int}
    """
    # 1) убрать пустые payload
    segs = [s for s in segments if s.get("data")]
    if not segs:
        return []

    # 2) дедуп по seq: оставляем самый длинный data (часто ретрансляция одинаковая)
    by_seq = {}
    for s in segs:
        seq = int(s["seq"])
        data = s["data"]
        prev = by_seq.get(seq)
        if prev is None or len(data) > len(prev["data"]):
            by_seq[seq] = {"seq": seq, "data": data, "ts": s.get("ts")}

    # 3) сортировка по seq
    ordered = sorted(by_seq.values(), key=lambda x: x["seq"])

    # 4) сборка с учётом гэпов и overlaps
    out = []
    cur = ordered[0]["seq"]

    for s in ordered:
        seq = s["seq"]
        data = s["data"]

        # gap
        if seq > cur:
            out.append({"kind": "gap", "missing": seq - cur})
            cur = seq

        # overlap/duplicate
        if seq < cur:
            overlap = cur - seq
            if overlap >= len(data):
                continue
            data = data[overlap:]

        if data:
            out.append({"kind": "data", "data": data})
            cur += len(data)

    return out


def extract_tcp_payload(packet_dict):
    """
    Возвращает TCP payload bytes из сохранённого raw-пакета.
    packet_dict: твой packet_info (с 'raw', 'src_ip','dst_ip','src_port','dst_port', 'proto')
    """
    raw = packet_dict.get("raw", b"")
    if not raw:
        return b""
    try:
        sp = Ether(raw)
    except Exception:
        try:
            sp = IP(raw)
        except Exception:
            try:
                sp = IPv6(raw)
            except Exception:
                return b""

    try:
        if sp.haslayer(TCP):
            return bytes(sp[TCP].payload) if sp[TCP].payload is not None else b""
    except Exception:
        return b""
    return b""


def guess_tcp_client_server(packets, ip1, port1, ip2, port2):
    """Определить кто Client/Server внутри TCP 4-tuple по SYN без ACK.

        Ищет в `packets` пакет TCP с флагами:
          tcp_syn == True и tcp_ack == False
        и принадлежащий соединению ip1:port1 ↔ ip2:port2 (в любой ориентации).

        Если найден — инициатор SYN считается клиентом.

        Args:
            packets: Список пакетов программы (list[dict]).
            ip1: IP endpoint #1 (str).
            port1: Port endpoint #1 (int|str).
            ip2: IP endpoint #2 (str).
            port2: Port endpoint #2 (int|str).

        Returns:
            tuple[str,int,str,int] | None:
                (client_ip, client_port, server_ip, server_port) или None если SYN без ACK не найден.
        """
    for p in packets:
        proto = p.get("proto", "")
        if "TCP" not in proto:
            continue
        if p.get("src_ip") is None or p.get("dst_ip") is None:
            continue
        if p.get("src_port") is None or p.get("dst_port") is None:
            continue

        s_ip, d_ip = str(p["src_ip"]), str(p["dst_ip"])
        s_po, d_po = int(p["src_port"]), int(p["dst_port"])

        is_12 = (s_ip == str(ip1) and d_ip == str(ip2) and s_po == int(port1) and d_po == int(port2))
        is_21 = (s_ip == str(ip2) and d_ip == str(ip1) and s_po == int(port2) and d_po == int(port1))
        if not (is_12 or is_21):
            continue

        # нужен SYN без ACK
        if p.get("tcp_syn") and not p.get("tcp_ack"):
            # инициатор = src
            return (p["src_ip"], int(p["src_port"]), p["dst_ip"], int(p["dst_port"]))

    return None


def build_tcp_stream_packets(packets, a_ip, a_port, b_ip, b_port):
    """
    Возвращает список событий стрима:
    [{'dir':'c2s'|'s2c', 'ts':datetime, 'data':bytes, 'pkt':packet_dict}, ...]
    где client = (a_ip,a_port), server = (b_ip,b_port) как выбрано при follow.
    """
    events = []
    for p in packets:
        proto = p.get("proto", "")
        if "TCP" not in proto:
            continue
        if p.get("src_ip") is None or p.get("dst_ip") is None:
            continue
        if p.get("src_port") is None or p.get("dst_port") is None:
            continue

        # принадлежит ли пакету данному 4-tuple (в обе стороны)
        s_ip, d_ip = str(p["src_ip"]), str(p["dst_ip"])
        s_po, d_po = int(p["src_port"]), int(p["dst_port"])

        is_ab = (s_ip == str(a_ip) and d_ip == str(b_ip) and s_po == int(a_port) and d_po == int(b_port))
        is_ba = (s_ip == str(b_ip) and d_ip == str(a_ip) and s_po == int(b_port) and d_po == int(a_port))
        if not (is_ab or is_ba):
            continue

        data = extract_tcp_payload(p)
        if not data:
            continue

        direction = "c2s" if is_ab else "s2c"
        events.append({"dir": direction, "ts": p["timestamp"], "data": data, "pkt": p})

    events.sort(key=lambda x: x["ts"])
    return events


def _profiles_path():
    """Вернуть путь к конфигу профилей (~/.packet-monitor/config.json).

    Returns:
        Абсолютный путь к файлу конфигурации профилей.
    """

    home = os.path.expanduser("~")
    d = os.path.join(home, ".packet-monitor")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "config.json")

def load_profiles_config():
    """Загрузить конфигурацию профилей из JSON.

    Returns:
        dict: структура вида {"profiles": {name: profile_dict, ...}}
        Если файла нет/битый — возвращает пустую структуру.
    """

    path = _profiles_path()
    if not os.path.exists(path):
        return {"profiles": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {"profiles": {}}
    except Exception:
        return {"profiles": {}}


def save_profiles_config(cfg):
    """Сохранить конфигурацию профилей в JSON.

    Args:
        cfg: dict с профилями (обычно результат load_profiles_config()).

    Raises:
        Exception: при ошибках записи (если ты не подавляешь исключение внутри).
    """

    path = _profiles_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class PacketExporter:
    """Класс для экспорта пакетов в различные форматы"""

    def __init__(self):
        """Инициализация экспортера"""
        self.default_directory = "./captures"
        self._ensure_directory()

    def _ensure_directory(self):
        """Создать директорию для сохранения если не существует"""
        try:
            if not os.path.exists(self.default_directory):
                os.makedirs(self.default_directory)
        except Exception as e:
            print(f"Warning: Could not create directory {self.default_directory}: {e}")
            self.default_directory = "."

    def save_to_pcapng(self, packets, filename=None):
        """
        Сохранить пакеты в формат pcapng

        Args:
            packets: список packet_info словарей с raw_packet
            filename: имя файла (если None - генерируется автоматически)

        Returns:
            tuple (success: bool, filepath: str, message: str)
        """
        try:
            # Генерируем имя файла если не указано
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"capture_{timestamp}.pcapng"

            # Добавляем расширение если отсутствует
            if not filename.endswith('.pcapng') and not filename.endswith('.pcap'):
                filename += '.pcapng'

            # Формируем полный путь
            filepath = os.path.join(self.default_directory, filename)

            # Извлекаем raw пакеты из packet_info
            raw_packets = []
            for pkt_info in packets:
                raw_packet = pkt_info.get('raw_packet')
                if raw_packet is None:
                    raw_packet = pkt_info.get('raw')
                if raw_packet is not None:
                    raw_packets.append(raw_packet)

            if len(raw_packets) == 0:
                return False, "", "No valid packets to save"

            # Сохраняем используя wrpcap из scapy
            # wrpcap автоматически создает pcapng для Python 3
            wrpcap(filepath, raw_packets)

            return True, filepath, f"Successfully saved {len(raw_packets)} packets"

        except Exception as e:
            return False, "", f"Error saving packets: {str(e)}"

    def save_to_pcap(self, packets, filename=None):
        """
        Сохранить пакеты в формат pcap (старый формат)

        Args:
            packets: список packet_info словарей с raw_packet
            filename: имя файла (если None - генерируется автоматически)

        Returns:
            tuple (success: bool, filepath: str, message: str)
        """
        try:
            # Генерируем имя файла если не указано
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"capture_{timestamp}.pcap"

            # Добавляем расширение если отсутствует
            if not filename.endswith('.pcap'):
                filename += '.pcap'

            # Формируем полный путь
            filepath = os.path.join(self.default_directory, filename)

            # Извлекаем raw пакеты
            raw_packets = []
            for pkt_info in packets:
                raw_packet = pkt_info.get('raw_packet')
                if raw_packet is None:
                    raw_packet = pkt_info.get('raw')
                if raw_packet is not None:
                    raw_packets.append(raw_packet)

            if len(raw_packets) == 0:
                return False, "", "No valid packets to save"

            # Сохраняем в pcap формат
            wrpcap(filepath, raw_packets)

            return True, filepath, f"Successfully saved {len(raw_packets)} packets"

        except Exception as e:
            return False, "", f"Error saving packets: {str(e)}"

    def save_filtered_packets(self, all_packets, packet_filter, filename=None):
        """
        Сохранить отфильтрованные пакеты

        Args:
            all_packets: все пакеты
            packet_filter: экземпляр PacketFilter
            filename: имя файла

        Returns:
            tuple (success: bool, filepath: str, message: str)
        """
        # Применяем фильтр
        filtered = packet_filter.filter_packets(all_packets)

        if len(filtered) == 0:
            return False, "", "No packets match the current filter"

        # Сохраняем
        return self.save_to_pcapng(filtered, filename)

    def get_capture_info(self, filepath):
        """
        Получить информацию о сохраненном файле

        Args:
            filepath: путь к файлу

        Returns:
            dict с информацией о файле
        """
        try:
            if not os.path.exists(filepath):
                return None

            stat = os.stat(filepath)

            return {
                'filename': os.path.basename(filepath),
                'filepath': filepath,
                'size_bytes': stat.st_size,
                'size_human': self._human_readable_size(stat.st_size),
                'created': datetime.fromtimestamp(stat.st_ctime),
                'modified': datetime.fromtimestamp(stat.st_mtime),
            }
        except Exception as e:
            return None

    def _human_readable_size(self, size_bytes):
        """Конвертировать размер в человекочитаемый формат"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"

    def list_saved_captures(self):
        """
        Получить список сохраненных файлов захвата

        Returns:
            список словарей с информацией о файлах
        """
        captures = []

        try:
            if not os.path.exists(self.default_directory):
                return captures

            for filename in os.listdir(self.default_directory):
                if filename.endswith('.pcap') or filename.endswith('.pcapng'):
                    filepath = os.path.join(self.default_directory, filename)
                    info = self.get_capture_info(filepath)
                    if info:
                        captures.append(info)

            # Сортируем по дате изменения (новые первыми)
            captures.sort(key=lambda x: x['modified'], reverse=True)

        except Exception as e:
            print(f"Error listing captures: {e}")

        return captures

    def delete_capture(self, filepath):
        """
        Удалить файл захвата

        Args:
            filepath: путь к файлу

        Returns:
            tuple (success: bool, message: str)
        """
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True, f"Deleted {os.path.basename(filepath)}"
            else:
                return False, "File not found"
        except Exception as e:
            return False, f"Error deleting file: {str(e)}"


class ProfilesDialog(urwid.WidgetWrap):
    """Диалог управления профилями фильтров/исключений.

    Показывает список профилей, позволяет загрузить/сохранить/удалить профиль,
    а также применить быстрые пресеты (dns-only/syn-only/arp-only и т.п.).
    """
    def __init__(self, profile_names, on_load, on_save_as, on_delete, on_preset, on_close):
        """Создать диалог профилей.

          Args:
              profile_names: Список доступных профилей (list[str]).
              on_load: callback(name: str) -> None. Загрузить выбранный профиль.
              on_save_as: callback(name: str) -> None. Сохранить текущие настройки как профиль.
              on_delete: callback(name: str) -> None. Удалить профиль.
              on_preset: callback(preset_name: str) -> None. Применить пресет.
              on_close: callback() -> None. Закрыть диалог.
          """
        self.on_load = on_load
        self.on_save_as = on_save_as
        self.on_delete = on_delete
        self.on_preset = on_preset
        self.on_close = on_close

        self.edit_name = urwid.Edit(("edit", "Profile name: "), edit_text="default")

        # список профилей
        group = []
        self.radios = []
        for i, name in enumerate(profile_names):
            self.radios.append(urwid.RadioButton(group, name, state=(i == 0)))

        if self.radios:
            list_walker = urwid.SimpleFocusListWalker(self.radios)
            profiles_list = urwid.ListBox(list_walker)      # box widget
        else:
            profiles_list = urwid.Filler(urwid.Text("No saved profiles"), valign='top')

        left_panel = urwid.LineBox(profiles_list, title="Saved profiles")

        # правый блок (имя + пресеты) — делаем box через Filler
        preset_buttons = urwid.Pile([
            urwid.Button("Preset: dns-only", on_press=lambda b: self.on_preset("dns-only")),
            urwid.Button("Preset: syn-only", on_press=lambda b: self.on_preset("syn-only")),
            urwid.Button("Preset: arp-only", on_press=lambda b: self.on_preset("arp-only")),
        ])
        right_content = urwid.Pile([
            urwid.Filler(urwid.Text("Save as:"), valign='top'),
            urwid.Divider(),
            self.edit_name,
            urwid.Divider(),
            urwid.Filler(urwid.Text("Presets:"), valign='top'),
            urwid.Divider(),
            preset_buttons
        ])
        right_panel = urwid.LineBox(urwid.Filler(right_content, valign='top'), title="Actions")

        body_cols = urwid.Columns([('weight', 2, left_panel), ('weight', 3, right_panel)], dividechars=2)

        # footer buttons
        btn_load = urwid.Button("Load", on_press=lambda b: self.on_load(self.get_selected_name()))
        btn_save = urwid.Button("Save as", on_press=lambda b: self.on_save_as(self.edit_name.edit_text.strip()))
        btn_del  = urwid.Button("Delete", on_press=lambda b: self.on_delete(self.get_selected_name()))
        btn_close = urwid.Button("Close", on_press=lambda b: self.on_close())
        footer = urwid.Columns([btn_load, btn_save, btn_del, btn_close], dividechars=2)

        # header (делаем Text через Filler, чтобы был box-safe)
        header = urwid.Filler(urwid.Text(("dialog_title", "Profiles"), align='center'), valign='top')

        frame = urwid.Frame(body=body_cols, header=header, footer=footer)
        box = urwid.LineBox(frame)
        super().__init__(urwid.AttrMap(box, "dialog"))

    def get_selected_name(self):
        for r in self.radios:
            if r.state:
                return r.get_label()
        return None


class PacketExportDialog:
    """Диалог для экспорта пакетов (для интеграции с TUI)"""

    def __init__(self, packet_capture, packet_filter, exporter=None):
        """
        Инициализация диалога экспорта

        Args:
            packet_capture: экземпляр PacketCapture
            packet_filter: экземпляр PacketFilter
            exporter: экземпляр PacketExporter (опционально)
        """
        self.packet_capture = packet_capture
        self.packet_filter = packet_filter
        self.exporter = exporter if exporter else PacketExporter()

    def export_all_packets(self, filename=None):
        """
        Экспортировать все захваченные пакеты

        Args:
            filename: имя файла

        Returns:
            tuple (success, filepath, message)
        """
        packets = self.packet_capture.get_packets()
        return self.exporter.save_to_pcapng(packets, filename)

    def export_filtered_packets(self, filename=None):
        """
        Экспортировать только отфильтрованные пакеты

        Args:
            filename: имя файла

        Returns:
            tuple (success, filepath, message)
        """
        packets = self.packet_capture.get_packets()
        return self.exporter.save_filtered_packets(packets, self.packet_filter, filename)

    def export_selected_packets(self, packet_numbers, filename=None):
        """
        Экспортировать выбранные пакеты по номерам

        Args:
            packet_numbers: список номеров пакетов
            filename: имя файла

        Returns:
            tuple (success, filepath, message)
        """
        all_packets = self.packet_capture.get_packets()
        selected = [pkt for pkt in all_packets if pkt['num'] in packet_numbers]

        if len(selected) == 0:
            return False, "", "No packets selected"

        return self.exporter.save_to_pcapng(selected, filename)

class TlsHandshakeView(urwid.WidgetWrap):
    """Окно сводки TLS handshake (без расшифровки).

    Отображает распознанные TLS records/handshake-сообщения по направлениям:
    Client→Server и Server→Client.
    """

    def __init__(self, title: str, c2s_lines: list[str], s2c_lines: list[str], on_close_callback):
        """Создать окно сводки TLS handshake.

        Args:
            title: Заголовок окна.
            c2s_lines: Список строк (summary) для направления Client→Server.
            s2c_lines: Список строк (summary) для направления Server→Client.
            on_close_callback: callback() -> None. Вызывается при закрытии окна.
        """

        self.on_close_callback = on_close_callback

        left = [urwid.Text(("stream_title", "Client → Server"))]
        left += [urwid.AttrMap(urwid.Text(l), "stream_c2s") for l in (c2s_lines or ["(no TLS records)"])]

        right = [urwid.Text(("stream_title", "Server → Client"))]
        right += [urwid.AttrMap(urwid.Text(l), "stream_s2c") for l in (s2c_lines or ["(no TLS records)"])]

        cols = urwid.Columns([
            urwid.LineBox(urwid.ListBox(urwid.SimpleFocusListWalker(left))),
            urwid.LineBox(urwid.ListBox(urwid.SimpleFocusListWalker(right))),
        ], dividechars=1)

        footer = urwid.Text("Esc = Close", align="center")

        pile = urwid.Pile([
            ('weight', 1, cols),
            ('pack', urwid.Divider()),
            ('pack', footer),
        ])

        box = urwid.LineBox(pile, title=title, title_attr="dialog_title")
        super().__init__(urwid.AttrMap(box, "dialog"))

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key in ("esc", "q", "Q"):
            if self.on_close_callback:
                self.on_close_callback()
            return None
        return super().keypress(size, key)



class TcpStreamView(urwid.WidgetWrap):
    """Окно просмотра TCP stream (reassembled payload) по направлениям.

    Показывает два направления (C→S и S→C), поддерживает экспорт текста/сырых байт.
    """

    def __init__(self, title, blocks_c2s, blocks_s2c, on_close_callback, on_export_text, on_export_raw):
        """Создать окно просмотра TCP stream.

        Args:
            title: Заголовок окна.
            blocks_c2s: Список блоков текста/фрагментов для Client→Server.
            blocks_s2c: Список блоков текста/фрагментов для Server→Client.
            on_close_callback: callback() -> None. Закрыть окно.
            on_export_text: callback(text: str) -> None. Экспорт текстового представления.
            on_export_raw: callback((bytes, bytes)) -> None. Экспорт сырых байт (c2s, s2c).
        """

        self.title = title
        self.blocks_c2s = blocks_c2s
        self.blocks_s2c = blocks_s2c
        self.on_close_callback = on_close_callback
        self.on_export_text = on_export_text
        self.on_export_raw = on_export_raw

        self.list_walker = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.list_walker)

        self._render()

        btn_export_text = urwid.Button("Export text", on_press=lambda b: self.on_export_text(self._export_text()))
        btn_export_raw  = urwid.Button("Export raw",  on_press=lambda b: self.on_export_raw(self._export_raw()))
        btn_close       = urwid.Button("Close", on_press=lambda b: self.on_close_callback())

        footer = urwid.Columns([btn_export_text, btn_export_raw, btn_close], dividechars=2)
        header = urwid.Text(("stream_title", title), align='center')

        frame = urwid.Frame(body=self.listbox, header=header, footer=footer)
        box = urwid.LineBox(frame, title="Follow TCP Stream", title_attr='dialog_title')
        super().__init__(urwid.AttrMap(box, "dialog"))

    def _render_dir(self, blocks, dir_tag):
        # dir_tag: "c2s" or "s2c"
        prefix = "C→S" if dir_tag == "c2s" else "S→C"
        attr = "stream_c2s" if dir_tag == "c2s" else "stream_s2c"

        for b in blocks:
            if b.get("kind") == "gap":
                msg = f"{prefix}  [... missing {b.get('missing', 0)} bytes ...]\n"
                t = urwid.Text(msg, wrap='any')
                self.list_walker.append(urwid.AttrMap(t, attr))
                continue

            data = b.get("data", b"")
            text = bytes_to_pretty_text(data)
            msg = f"{prefix}\n{text}\n"
            t = urwid.Text(msg, wrap='any')
            self.list_walker.append(urwid.AttrMap(t, attr))

    def _render(self):
        self.list_walker.clear()
        # печатаем блоки в “диалоговом” виде: чередуем куски как они реально идут
        # Для Wireshark-подобия лучше смешивать по времени, но при reassembly по seq
        # мы показываем собранные направления отдельно, сверху вниз:
        self.list_walker.append(urwid.AttrMap(urwid.Text("=== Client → Server ===\n"), "stream_c2s"))
        self._render_dir(self.blocks_c2s, "c2s")
        self.list_walker.append(urwid.AttrMap(urwid.Text("\n=== Server → Client ===\n"), "stream_s2c"))
        self._render_dir(self.blocks_s2c, "s2c")

    def _export_text(self):
        def blocks_to_text(blocks, tag):
            out = []
            prefix = "C->S" if tag == "c2s" else "S->C"
            for b in blocks:
                if b.get("kind") == "gap":
                    out.append(f"{prefix} [... missing {b.get('missing', 0)} bytes ...]\n")
                else:
                    out.append(f"{prefix}\n{bytes_to_pretty_text(b.get('data', b''))}\n")
            return "".join(out)

        return (
            "=== Client -> Server ===\n" +
            blocks_to_text(self.blocks_c2s, "c2s") +
            "\n=== Server -> Client ===\n" +
            blocks_to_text(self.blocks_s2c, "s2c")
        )

    def _export_raw(self):
        c2s = b"".join(b["data"] for b in self.blocks_c2s if b.get("kind") == "data")
        s2c = b"".join(b["data"] for b in self.blocks_s2c if b.get("kind") == "data")
        return c2s, s2c



class FlowDetailView(urwid.WidgetWrap):
    """Окно деталей выбранного flow.

    Показывает статистику потока и агрегаты по пакетам (порты, длительность, PPS/BPS и т.п.).
    """
    def __init__(self, flow, packets, on_close_callback):
        """Создать окно деталей flow.

        Args:
            flow: Словарь агрегата flow (proto/a_ip/a_port/b_ip/b_port/bytes/first_ts/...).
            packets: Пакеты, относящиеся к данному flow (list[dict]).
            on_close_callback: callback() -> None. Закрыть окно.
        """

        self.flow = flow
        self.packets = packets
        self.on_close_callback = on_close_callback

        text = urwid.Text(self._build_text(), wrap='any')
        hint = urwid.Text("Press any key to close", align='center')

        pile = urwid.Pile([text, urwid.Divider(), hint])

        class ModalKeyCatcher(urwid.WidgetWrap):
            def selectable(self):
                return True
            def keypress(self, size, key):
                self._on_close()
                return None

        box = urwid.LineBox(pile, title="Flow Details", title_attr='dialog_title')
        box = urwid.AttrMap(box, 'dialog')

        popup = ModalKeyCatcher(box)
        popup._on_close = self.on_close_callback

        super().__init__(popup)

    def _build_text(self):
        f = self.flow
        a = f"{f['a_ip']}:{f['a_port']}"
        b = f"{f['b_ip']}:{f['b_port']}"
        proto = f["proto"]

        if not self.packets:
            return f"{proto} {a} ↔ {b}\n\nNo packets."

        first_ts = min(p["timestamp"] for p in self.packets)
        last_ts = max(p["timestamp"] for p in self.packets)
        duration = (last_ts - first_ts).total_seconds()
        duration = max(duration, 0.000001)

        total_bytes = sum(int(p.get("size", 0) or 0) for p in self.packets)
        pps = len(self.packets) / duration
        bps = (total_bytes * 8) / duration

        # top ports
        sp = Counter()
        dp = Counter()
        for p in self.packets:
            if p.get("src_port") is not None:
                sp[int(p["src_port"])] += 1
            if p.get("dst_port") is not None:
                dp[int(p["dst_port"])] += 1
        top_src_ports = ", ".join(f"{port}({cnt})" for port, cnt in sp.most_common(5)) or "n/a"
        top_dst_ports = ", ".join(f"{port}({cnt})" for port, cnt in dp.most_common(5)) or "n/a"

        # RTT (MVP: TCP SYN -> SYN-ACK по строке info)
        rtt_ms = self._estimate_tcp_syn_rtt_ms(f["a_ip"], f["a_port"], f["b_ip"], f["b_port"]) if proto == "TCP" else None
        rtt_line = f"{rtt_ms:.3f} ms" if rtt_ms is not None else "n/a"

        lines = [
            f"{proto} {a} ↔ {b}",
            "",
            f"Packets: {len(self.packets)}",
            f"Bytes:   {total_bytes} (A->B {f.get('bytes_ab', 0)} / B->A {f.get('bytes_ba', 0)})",
            f"First:   {first_ts}",
            f"Last:    {last_ts}",
            f"Duration:{duration:.3f} s",
            f"PPS:     {pps:.2f}",
            f"BPS:     {bps:.2f} (bits/sec)",
            "",
            f"Top src ports: {top_src_ports}",
            f"Top dst ports: {top_dst_ports}",
            "",
            f"RTT (TCP SYN): {rtt_line}",
        ]
        return "\n".join(lines)

    def _estimate_tcp_syn_rtt_ms(self, a_ip, a_port, b_ip, b_port):
        syn_time = None
        for p in self.packets:
            info = (p.get("info") or "").upper()
            if "SYN" in info and "ACK" not in info:
                if str(p.get("src_ip")) == str(a_ip) and int(p.get("src_port")) == int(a_port) and \
                   str(p.get("dst_ip")) == str(b_ip) and int(p.get("dst_port")) == int(b_port):
                    syn_time = p["timestamp"]
                    break
        if syn_time is None:
            return None

        for p in self.packets:
            if p["timestamp"] <= syn_time:
                continue
            info = (p.get("info") or "").upper()
            if "SYN" in info and "ACK" in info:
                if str(p.get("src_ip")) == str(b_ip) and int(p.get("src_port")) == int(b_port) and \
                   str(p.get("dst_ip")) == str(a_ip) and int(p.get("dst_port")) == int(a_port):
                    dt = (p["timestamp"] - syn_time).total_seconds()
                    return dt * 1000.0
        return None



class PacketDetailView(urwid.WidgetWrap):
    """Виджет для детального просмотра пакета"""

    def __init__(self, packet_info, on_close_callback=None, on_prev=None, on_next=None):

        """
        Инициализация детального просмотра

        Args:
            packet_info: информация о пакете из PacketCapture
            on_close_callback: функция для вызова при закрытии
        """
        self.packet_info = packet_info
        self.on_close_callback = on_close_callback

        self.on_prev = on_prev
        self.on_next = on_next

        # Создаем контент
        content = self._create_content()

        # Оборачиваем в LineBox с заголовком
        title = f"Packet #{packet_info['num']} Details - Press ESC to close"
        boxed_content = urwid.LineBox(content, title=title)

        super().__init__(urwid.AttrMap(boxed_content, 'detail_box'))

    def _create_content(self):
        """Создать содержимое детального просмотра"""
        widgets = []

        # === Секция 1: Основная информация ===
        widgets.append(urwid.AttrMap(
            urwid.Text(('detail_header', '═══ Packet Summary ═══')),
            'detail_header'
        ))

        summary_text = [
            f"Packet Number:  {self.packet_info['num']}",
            f"Timestamp:      {self.packet_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}",
            f"Interface:      {safe_str(self.packet_info.get('interface'), 'N/A')}",
            f"Length:         {self.packet_info.get('size', self.packet_info.get('length', 0))} bytes",
            f"Protocol:       {self.packet_info['proto']}",
        ]

        src_ip = self.packet_info.get('src_ip')
        dst_ip = self.packet_info.get('dst_ip')
        src_port = self.packet_info.get('src_port')
        dst_port = self.packet_info.get('dst_port')

        if src_ip or dst_ip:
            src_ep = str(src_ip) if src_ip is not None else "?"
            dst_ep = str(dst_ip) if dst_ip is not None else "?"
            if src_port is not None:
                src_ep += f":{src_port}"
            if dst_port is not None:
                dst_ep += f":{dst_port}"
            summary_text.append(f"Endpoints:      {src_ep} -> {dst_ep}")

        if self.packet_info.get('tcp_flags'):
            summary_text.append(f"TCP Flags:      {self.packet_info['tcp_flags']}")
        if self.packet_info.get('tcp_seq') is not None:
            summary_text.append(f"TCP Seq:        {self.packet_info['tcp_seq']}")
        if self.packet_info.get('tcp_acknum') is not None:
            summary_text.append(f"TCP Ack:        {self.packet_info['tcp_acknum']}")
        if self.packet_info.get('info_long'):
            summary_text.append(f"Info:           {self.packet_info['info_long']}")

        if self.packet_info.get('vlan'):
            summary_text.append(f"VLAN ID:        {self.packet_info['vlan']}")

        if self.packet_info.get('packet_loss'):
            summary_text.append("⚠ PACKET LOSS DETECTED")

        widgets.append(urwid.Text('\n'.join(summary_text)))
        widgets.append(urwid.Divider())

        # === Секция 2: Детали протоколов (разбор слоев) ===
        # Предпочитаем исходный Scapy packet, чтобы сохранить корректный link-layer
        # (например, CookedLinux/SLL/SLL2 для capture с tcpdump -i any).
        raw_packet = self.packet_info.get('raw_packet')

        if not raw_packet and self.packet_info.get('raw'):
            # Fallback для старых packet_info без исходного объекта пакета.
            try:
                raw_packet = Ether(self.packet_info['raw'])
            except:
                raw_packet = None

        if raw_packet:
            widgets.append(urwid.AttrMap(
                urwid.Text(('detail_header', '═══ Protocol Layers ═══')),
                'detail_header'
            ))

            layer_details = self._parse_protocol_layers(raw_packet)
            widgets.append(urwid.Text(layer_details))
            widgets.append(urwid.Divider())

        # === Секция 3: Hexdump ===
        widgets.append(urwid.AttrMap(
            urwid.Text(('detail_header', '═══ Hexdump ═══')),
            'detail_header'
        ))

        hexdump_text = self._create_hexdump(raw_packet if raw_packet else self.packet_info.get('raw'))
        widgets.append(urwid.Text(('hexdump', hexdump_text)))

        # Создаем прокручиваемый список
        listwalker = urwid.SimpleFocusListWalker(widgets)
        listbox = urwid.ListBox(listwalker)

        return listbox

    def _parse_protocol_layers(self, packet):
        """
        Разбор слоев протокола пакета

        Args:
            packet: scapy packet объект

        Returns:
            строка с детальной информацией о слоях
        """
        if not packet:
            return "No packet data available"

        output = []

        try:
            # Используем встроенный метод show() из scapy
            # Перехватываем stdout для получения текста
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

            packet.show()

            result = sys.stdout.getvalue()
            sys.stdout = old_stdout

            # Форматируем вывод
            if result:
                return result

        except Exception as e:
            if 'old_stdout' in locals():
                sys.stdout = old_stdout
            output.append(f"Error parsing packet: {e}")

        # Если show() не сработал, делаем ручной разбор
        if not output or len(output) == 0:
            output = self._manual_layer_parse(packet)

        return '\n'.join(output) if output else "Unable to parse packet layers"

    def _manual_layer_parse(self, packet):
        """Ручной разбор слоев пакета"""
        output = []

        try:
            # Ethernet Layer
            if packet.haslayer(Ether):
                eth = packet[Ether]
                output.append("### Ethernet II")
                output.append(f"  Source MAC:      {eth.src}")
                output.append(f"  Destination MAC: {eth.dst}")
                output.append(f"  EtherType:       0x{eth.type:04x}")
                output.append("")

            # VLAN Layer
            if packet.haslayer(Dot1Q):
                vlan = packet[Dot1Q]
                output.append("### 802.1Q VLAN")
                output.append(f"  VLAN ID:         {vlan.vlan}")
                output.append(f"  Priority:        {vlan.prio}")
                output.append("")

            # ARP Layer
            if packet.haslayer(ARP):
                arp = packet[ARP]
                output.append("### ARP (Address Resolution Protocol)")
                output.append(f"  Hardware Type:   {arp.hwtype}")
                output.append(f"  Protocol Type:   0x{arp.ptype:04x}")
                output.append(f"  Operation:       {['', 'Request', 'Reply'][arp.op] if arp.op <= 2 else arp.op}")
                output.append(f"  Sender MAC:      {arp.hwsrc}")
                output.append(f"  Sender IP:       {arp.psrc}")
                output.append(f"  Target MAC:      {arp.hwdst}")
                output.append(f"  Target IP:       {arp.pdst}")
                output.append("")

            # IP Layer
            if packet.haslayer(IP):
                ip = packet[IP]
                output.append("### IPv4")
                output.append(f"  Version:         {ip.version}")
                output.append(f"  Header Length:   {ip.ihl * 4} bytes")
                output.append(f"  TOS:             0x{ip.tos:02x}")
                output.append(f"  Total Length:    {ip.len}")
                output.append(f"  Identification:  {ip.id}")
                output.append(f"  Flags:           {ip.flags}")
                output.append(f"  Fragment Offset: {ip.frag}")
                output.append(f"  TTL:             {ip.ttl}")
                output.append(f"  Protocol:        {ip.proto}")
                output.append(f"  Checksum:        0x{ip.chksum:04x}")
                output.append(f"  Source IP:       {ip.src}")
                output.append(f"  Destination IP:  {ip.dst}")
                output.append("")

            # IPv6 Layer
            if packet.haslayer(IPv6):
                ipv6 = packet[IPv6]
                output.append("### IPv6")
                output.append(f"  Version:         {ipv6.version}")
                output.append(f"  Traffic Class:   {ipv6.tc}")
                output.append(f"  Flow Label:      {ipv6.fl}")
                output.append(f"  Payload Length:  {ipv6.plen}")
                output.append(f"  Next Header:     {ipv6.nh}")
                output.append(f"  Hop Limit:       {ipv6.hlim}")
                output.append(f"  Source IP:       {ipv6.src}")
                output.append(f"  Destination IP:  {ipv6.dst}")
                output.append("")

            # ICMP Layer
            if packet.haslayer(ICMP):
                icmp = packet[ICMP]
                output.append("### ICMP (Internet Control Message Protocol)")
                output.append(f"  Type:            {icmp.type}")
                output.append(f"  Code:            {icmp.code}")
                output.append(f"  Checksum:        0x{icmp.chksum:04x}")
                if hasattr(icmp, 'id'):
                    output.append(f"  ID:              {icmp.id}")
                if hasattr(icmp, 'seq'):
                    output.append(f"  Sequence:        {icmp.seq}")
                output.append("")

            # TCP Layer
            if packet.haslayer(TCP):
                tcp = packet[TCP]
                payload_len = len(bytes(tcp.payload)) if tcp.payload is not None else 0
                output.append("### TCP (Transmission Control Protocol)")
                output.append(f"  Source Port:     {tcp.sport}")
                output.append(f"  Destination Port:{tcp.dport}")
                output.append(f"  Sequence Number: {tcp.seq}")
                output.append(f"  Ack Number:      {tcp.ack}")
                output.append(f"  Data Offset:     {tcp.dataofs * 4} bytes")

                # TCP Flags
                flags = []
                if tcp.flags & 0x01: flags.append('FIN')
                if tcp.flags & 0x02: flags.append('SYN')
                if tcp.flags & 0x04: flags.append('RST')
                if tcp.flags & 0x08: flags.append('PSH')
                if tcp.flags & 0x10: flags.append('ACK')
                if tcp.flags & 0x20: flags.append('URG')
                if tcp.flags & 0x40: flags.append('ECE')
                if tcp.flags & 0x80: flags.append('CWR')

                output.append(f"  Flags:           0x{tcp.flags:02x} ({', '.join(flags)})")
                output.append(f"  Window Size:     {tcp.window}")
                output.append(f"  Checksum:        0x{tcp.chksum:04x}")
                output.append(f"  Urgent Pointer:  {tcp.urgptr}")
                output.append(f"  Payload Length:  {payload_len}")
                if getattr(tcp, 'options', None):
                    output.append("  Options:")
                    for name, value in tcp.options:
                        if name in ("NOP", "EOL"):
                            output.append(f"    {name}")
                        else:
                            output.append(f"    {name}: {value}")
                output.append("")

            # UDP Layer
            if packet.haslayer(UDP):
                udp = packet[UDP]
                output.append("### UDP (User Datagram Protocol)")
                output.append(f"  Source Port:     {udp.sport}")
                output.append(f"  Destination Port:{udp.dport}")
                output.append(f"  Length:          {udp.len}")
                output.append(f"  Checksum:        0x{udp.chksum:04x}")
                output.append("")

            # DNS Layer
            if packet.haslayer(DNS):
                dns = packet[DNS]
                output.append("### DNS (Domain Name System)")
                output.append(f"  Transaction ID:  0x{dns.id:04x}")
                output.append(f"  Query/Response:  {'Response' if dns.qr else 'Query'}")
                output.append(f"  Opcode:          {dns.opcode}")
                output.append(f"  Questions:       {dns.qdcount}")
                output.append(f"  Answers:         {dns.ancount}")
                output.append(f"  Authority RRs:   {dns.nscount}")
                output.append(f"  Additional RRs:  {dns.arcount}")

                # DNS Queries
                if dns.qdcount > 0 and hasattr(dns, 'qd') and dns.qd:
                    output.append("")
                    output.append("  Queries:")
                    qname = dns.qd.qname
                    if isinstance(qname, bytes):
                        qname = qname.decode('utf-8', errors='ignore')
                    output.append(f"    Name:          {qname}")
                    output.append(f"    Type:          {dns.qd.qtype}")
                    output.append(f"    Class:         {dns.qd.qclass}")

                # DNS Answers
                if dns.ancount > 0 and hasattr(dns, 'an') and dns.an:
                    output.append("")
                    output.append("  Answers:")
                    ans = dns.an
                    count = 0
                    while ans and count < dns.ancount:
                        if hasattr(ans, 'rrname'):
                            rrname = ans.rrname
                            if isinstance(rrname, bytes):
                                rrname = rrname.decode('utf-8', errors='ignore')
                            output.append(f"    [{count + 1}] {rrname}")
                        if hasattr(ans, 'rdata'):
                            output.append(f"         Data: {ans.rdata}")
                        ans = ans.payload if hasattr(ans, 'payload') else None
                        count += 1

                output.append("")

            # Raw payload
            if packet.haslayer('Raw'):
                raw = packet[Raw]
                payload = bytes(raw.load)

                if len(payload) > 0:
                    output.append("### Raw Payload")
                    # Показываем первые 100 байт
                    preview = payload[:100]

                    # Пытаемся декодировать как текст
                    try:
                        text = preview.decode('utf-8', errors='ignore')
                        if text.isprintable() or '\n' in text or '\r' in text:
                            output.append(f"  [Text Preview]")
                            for line in text.split('\n')[:5]:
                                output.append(f"    {line[:80]}")
                        else:
                            output.append(f"  [Binary Data - {len(payload)} bytes]")
                    except:
                        output.append(f"  [Binary Data - {len(payload)} bytes]")

                    output.append("")

        except Exception as e:
            output.append(f"Error during manual parsing: {e}")

        return output

    def _create_hexdump(self, packet):
        """
        Создать hexdump пакета

        Args:
            packet: scapy packet объект или bytes

        Returns:
            строка с hexdump
        """
        if not packet:
            return "No packet data available"

        # Если это Scapy packet
        if hasattr(packet, 'show'):
            try:
                # Используем встроенный hexdump из scapy
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()

                hexdump(packet)

                result = sys.stdout.getvalue()
                sys.stdout = old_stdout

                return result if result else self._manual_hexdump(bytes(packet))

            except Exception as e:
                if 'old_stdout' in locals():
                    sys.stdout = old_stdout
                # Fallback на ручной hexdump
                return self._manual_hexdump(bytes(packet))

        # Если это bytes
        elif isinstance(packet, bytes):
            return self._manual_hexdump(packet)

        return "Unable to create hexdump"

    def _manual_hexdump(self, data):
        """
        Ручная реализация hexdump

        Args:
            data: bytes

        Returns:
            строка с hexdump
        """
        if not isinstance(data, bytes):
            try:
                data = bytes(data)
            except:
                return "Invalid data type for hexdump"

        lines = []

        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]

            # Offset
            offset = f"{i:04x}"

            # Hex bytes
            hex_part = ' '.join(f"{b:02x}" for b in chunk)
            # Дополняем пробелами если неполная строка
            hex_part = hex_part.ljust(16 * 3 - 1)

            # ASCII representation
            ascii_part = ''.join(
                chr(b) if 32 <= b < 127 else '.'
                for b in chunk
            )

            lines.append(f"{offset}  {hex_part}  {ascii_part}")

        return '\n'.join(lines)

    def keypress(self, size, key):
        """Обработка нажатий клавиш"""
        if key == 'esc':
            if self.on_close_callback:
                self.on_close_callback()
            return None
        # Навигация между пакетами прямо в details (стрелки НЕ трогаем — они для скролла)
        if key in ('n', 'N'):
            if self.on_next:
                self.on_next(self.packet_info)
            return None

        if key in ('p', 'P'):
            if self.on_prev:
                self.on_prev(self.packet_info)
            return None

        # Передаем остальные клавиши дальше (для прокрутки)
        return super().keypress(size, key)


class PacketFilter:
    """Фильтрация пакетов с поддержкой исключений"""

    def __init__(self):
        """Инициализация фильтров отображения пакетов.

        Содержит:
          - filters: обычные фильтры по полям пакета (regex/substring)
          - exclude_streams: исключения 5-tuple (src/dst ip+port+proto)
          - exclude_protocols: исключения по протоколу
        """

        self.filters = {}
        self.exclude_streams = []  # Список исключенных стримов
        self.exclude_protocols = set()  # Множество исключенных протоколов

    def set_filter(self, field, value):
        """Установить фильтр для поля"""
        if value:
            self.filters[field] = value
        elif field in self.filters:
            del self.filters[field]

    def to_profile_dict(self):
        return {
            "filters": dict(self.filters),
            "exclude_streams": [list(x) for x in self.exclude_streams],  # (a,b,aport,bport,proto) -> list
            "exclude_protocols": list(self.exclude_protocols),
        }

    def load_profile_dict(self, d):
        self.filters = dict(d.get("filters", {}))
        self.exclude_streams = set(tuple(x) for x in d.get("exclude_streams", []))
        self.exclude_protocols = set(d.get("exclude_protocols", []))

    def clear_filter(self):
        """Очистить все фильтры (кроме exclude)"""
        self.filters.clear()

    def add_exclude_stream(self, src_ip, dst_ip, src_port, dst_port, proto):
        """
        Добавить stream в список исключений

        Args:
            src_ip, dst_ip: IP адреса
            src_port, dst_port: порты
            proto: протокол (TCP/UDP)

        Returns:
            True если добавлен, False если уже существует
        """
        stream = {
            'src_ip': src_ip,
            'dst_ip': dst_ip,
            'src_port': src_port,
            'dst_port': dst_port,
            'proto': proto
        }

        # Проверяем что такой stream еще не исключен
        if not self._is_stream_excluded(stream):
            self.exclude_streams.append(stream)
            return True
        return False

    def clear_exclude_streams(self):
        """Очистить все исключения стримов"""
        self.exclude_streams.clear()

    def add_exclude_protocol(self, protocol):
        """
        Добавить протокол в список исключений

        Args:
            protocol: название протокола (ARP, ICMP, DNS, etc)

        Returns:
            True если добавлен, False если уже существует
        """
        protocol = protocol.upper()
        if protocol not in self.exclude_protocols:
            self.exclude_protocols.add(protocol)
            return True
        return False

    def clear_exclude_protocols(self):
        """Очистить все исключенные протоколы"""
        self.exclude_protocols.clear()

    def _is_stream_excluded(self, stream):
        """Проверить, исключен ли уже этот stream"""
        for excl in self.exclude_streams:
            if (excl['src_ip'] == stream['src_ip'] and
                    excl['dst_ip'] == stream['dst_ip'] and
                    excl['src_port'] == stream['src_port'] and
                    excl['dst_port'] == stream['dst_port'] and
                    excl['proto'] == stream['proto']):
                return True
        return False

    def _match_excluded_stream(self, packet):
        """Проверить, попадает ли пакет в исключенные стримы (bidirectional)"""
        pkt_src_ip = packet.get('src_ip')
        pkt_dst_ip = packet.get('dst_ip')
        pkt_src_port = packet.get('src_port')
        pkt_dst_port = packet.get('dst_port')
        pkt_proto = packet.get('proto', '').upper()

        if not all([pkt_src_ip, pkt_dst_ip, pkt_src_port, pkt_dst_port]):
            return False

        # Нормализуем протокол (TCP/TCPv6 -> TCP)
        if 'TCP' in pkt_proto:
            pkt_proto = 'TCP'
        elif 'UDP' in pkt_proto:
            pkt_proto = 'UDP'
        else:
            return False

        for excl in self.exclude_streams:
            # Проверяем bidirectional match
            forward_match = (
                    excl['src_ip'] == pkt_src_ip and
                    excl['dst_ip'] == pkt_dst_ip and
                    excl['src_port'] == pkt_src_port and
                    excl['dst_port'] == pkt_dst_port and
                    excl['proto'] == pkt_proto
            )

            reverse_match = (
                    excl['src_ip'] == pkt_dst_ip and
                    excl['dst_ip'] == pkt_src_ip and
                    excl['src_port'] == pkt_dst_port and
                    excl['dst_port'] == pkt_src_port and
                    excl['proto'] == pkt_proto
            )

            if forward_match or reverse_match:
                return True

        return False

    def get_active_filters(self):
        """Получить активные фильтры"""
        return self.filters.copy()

    def get_exclude_count(self):
        """Получить количество исключенных стримов"""
        return len(self.exclude_streams)

    def get_exclude_summary(self):
        """Получить краткую информацию об исключениях"""
        if not self.exclude_streams:
            return ""

        summary_parts = []
        for i, excl in enumerate(self.exclude_streams[:3], 1):
            summary_parts.append(
                f"{excl['src_ip']}:{excl['src_port']}↔{excl['dst_ip']}:{excl['dst_port']}"
            )

        if len(self.exclude_streams) > 3:
            summary_parts.append(f"...+{len(self.exclude_streams) - 3} more")

        return ", ".join(summary_parts)

    def filter_packets(self, packets):
        """
        Фильтровать список пакетов

        Args:
            packets: список пакетов

        Returns:
            отфильтрованный список
        """
        if not self.filters and not self.exclude_streams and not self.exclude_protocols:
            return packets

        filtered = []

        for packet in packets:
            # Проверяем исключенные протоколы
            proto = packet.get('proto', '').upper()
            if proto in self.exclude_protocols:
                continue

            # Затем проверяем исключенные стримы
            if self._match_excluded_stream(packet):
                continue

            # Затем применяем обычные фильтры
            if self._match_packet(packet):
                filtered.append(packet)

        return filtered

    def _match_packet(self, packet):
        """Проверить соответствие пакета фильтрам"""
        if not self.filters:
            return True

        for field, pattern in self.filters.items():
            # any_port: совпадение по src_port ИЛИ dst_port
            if field == "any_port":
                src_v = str(packet.get("src_port", "") or "")
                dst_v = str(packet.get("dst_port", "") or "")
                if not src_v and not dst_v:
                    return False

                try:
                    ok = (re.search(pattern, src_v, re.IGNORECASE) is not None) or \
                         (re.search(pattern, dst_v, re.IGNORECASE) is not None)
                except re.error:
                    p = pattern.lower()
                    ok = (p in src_v.lower()) or (p in dst_v.lower())

                if not ok:
                    return False
                continue

            # any_ip: совпадение по src_ip ИЛИ dst_ip
            if field == "any_ip":
                src_v = str(packet.get("src_ip", "") or "")
                dst_v = str(packet.get("dst_ip", "") or "")
                if not src_v and not dst_v:
                    return False

                try:
                    ok = (re.search(pattern, src_v, re.IGNORECASE) is not None) or \
                         (re.search(pattern, dst_v, re.IGNORECASE) is not None)
                except re.error:
                    p = pattern.lower()
                    ok = (p in src_v.lower()) or (p in dst_v.lower())

                if not ok:
                    return False
                continue

            # --- payload отдельно ---
            if field == 'payload':
                if not self._match_payload(packet, pattern):
                    return False
                continue

            # --- TCP флаги (булевые) ---
            if field in ('tcp_syn', 'tcp_ack', 'tcp_fin', 'tcp_rst'):
                want = pattern
                # pattern может быть строкой из UI ("true"/"false")
                if isinstance(want, str):
                    want = want.strip().lower() in ("1", "true", "yes", "y", "on")
                got = bool(packet.get(field, False))
                if got != bool(want):
                    return False
                continue

            # --- TCP флаги строкой: "SYN" или "SYN,ACK" ---
            if field == 'tcp_flags':
                need = str(pattern).strip().upper()
                got = str(packet.get('tcp_flags', '')).upper()
                got_set = set(t.strip() for t in got.split(',') if t.strip())
                need_set = set(t.strip() for t in need.split(',') if t.strip())
                if not need_set.issubset(got_set):
                    return False
                continue

            # --- обычные поля: regex/substring ---
            packet_value = str(packet.get(field, ''))
            if not packet_value:
                return False

            try:
                if not re.search(pattern, packet_value, re.IGNORECASE):
                    return False
            except re.error:
                if str(pattern).lower() not in packet_value.lower():
                    return False

        return True

    def _match_payload(self, packet, pattern):
        """Поиск в payload пакета"""
        raw_data = packet.get('raw', b'')

        if not raw_data:
            return False

        try:
            # Пробуем как регулярное выражение
            pattern_bytes = pattern.encode('utf-8', errors='ignore')
            if re.search(pattern_bytes, raw_data, re.IGNORECASE):
                return True
        except:
            pass

        try:
            # Пробуем простой поиск
            if pattern.lower().encode('utf-8') in raw_data.lower():
                return True
        except:
            pass

        return False

    def search_payload(self, packets, search_string, case_sensitive=False):
        """
        Поиск по payload

        Args:
            packets: список пакетов
            search_string: строка для поиска
            case_sensitive: учитывать регистр

        Returns:
            список найденных пакетов
        """
        results = []

        for packet in packets:
            raw_data = packet.get('raw', b'')

            if not raw_data:
                continue

            try:
                if case_sensitive:
                    pattern = search_string.encode('utf-8')
                    if re.search(pattern, raw_data):
                        results.append(packet)
                else:
                    pattern = search_string.encode('utf-8')
                    if re.search(pattern, raw_data, re.IGNORECASE):
                        results.append(packet)
            except:
                continue

        return results

    def get_filter_summary(self):
        """Получить краткое описание активных фильтров"""
        if not self.filters and not self.exclude_streams and not self.exclude_protocols:
            return "No filters active"

        parts = []

        # Обычные фильтры
        for field, value in self.filters.items():
            parts.append(f"{field}={value}")

        # Исключения стримов
        if self.exclude_streams:
            parts.append(f"ExclStreams:{len(self.exclude_streams)}")

        # Исключения протоколов
        if self.exclude_protocols:
            parts.append(f"ExclProtos:{len(self.exclude_protocols)}")

        return " | ".join(parts) if parts else "No filters active"

    def get_top_ips(self, packets, limit=10):
        """Получить топ IP адресов по количеству пакетов"""
        ip_counter = defaultdict(int)

        for packet in packets:
            src_ip = packet.get('src_ip')
            dst_ip = packet.get('dst_ip')

            if src_ip:
                ip_counter[src_ip] += 1
            if dst_ip:
                ip_counter[dst_ip] += 1

        return sorted(ip_counter.items(), key=lambda x: x[1], reverse=True)[:limit]

    def get_top_talkers(self, packets, limit=10):
        """Получить топ IP адресов по объему трафика"""
        ip_bytes = defaultdict(int)

        for packet in packets:
            size = packet.get('size', 0)
            src_ip = packet.get('src_ip')
            dst_ip = packet.get('dst_ip')

            if src_ip:
                ip_bytes[src_ip] += size
            if dst_ip:
                ip_bytes[dst_ip] += size

        return sorted(ip_bytes.items(), key=lambda x: x[1], reverse=True)[:limit]


class PacketCapture:
    """
    Захват пакетов с кольцевым буфером и поддержкой нескольких интерфейсов
    """

    def __init__(self, interface=None, packet_limit=50000, log_file=None):
        """
        Инициализация захвата пакетов

        Args:
            interface: сетевой интерфейс или список интерфейсов
                      None - автоопределение
                      'any' - все интерфейсы
                      'eth0' - один интерфейс
                      ['eth0', 'wlan0'] - список интерфейсов
            packet_limit: максимальное количество пакетов в буфере
            log_file: путь к файлу логов (None = без логов)
        """
        self.packet_limit = packet_limit
        self.bpf_filter = None  # str|None
        self.log_file = log_file

        self.tls_ch_buffers = {}  # key -> bytearray
        self.tls_ch_parsed = set()  # key -> уже распарсили (чтобы не парсить снова)

        # Определяем список интерфейсов для захвата
        if interface is None:
            # Автоопределение - основной интерфейс
            self.interfaces = [conf.iface]
            self.interface = conf.iface
        elif interface == 'any':
            # Захват со всех интерфейсов
            self.interfaces = self._get_all_interfaces()
            self.interface = 'any'
        elif isinstance(interface, list):
            # Список интерфейсов
            self.interfaces = interface
            self.interface = ','.join(interface)
        else:
            # Один интерфейс
            self.interfaces = [interface]
            self.interface = interface

        # Кольцевой буфер с максимальным размером
        self.packets = deque(maxlen=packet_limit)

        # Lock для thread-safety
        self.lock = threading.Lock()

        # Потоки захвата (по одному на интерфейс)
        self.capture_threads = []
        self.running = False
        self.stop_sniffing = threading.Event()

        # Счетчики для статистики
        self.packet_counter = 0
        self.total_bytes = 0
        self.start_time = None

        # Bandwidth tracking
        self.bytes_last_second = 0
        self.last_bandwidth_check = None
        self.current_bandwidth = 0

        # Latency tracking
        self.latency_samples = deque(maxlen=1000)

        # Packet loss detection
        self.tcp_sequence_tracker = {}
        self.packet_loss_count = 0

        self._log(f"Initialized with interfaces: {self.interfaces}")
        self._log(f"Ring buffer max: {packet_limit} packets")

    def _get_all_interfaces(self):
        """Получить список всех сетевых интерфейсов"""
        try:
            # Получаем все интерфейсы
            all_ifaces = get_if_list()

            # Фильтруем служебные интерфейсы
            filtered = [
                iface for iface in all_ifaces
                if not iface.startswith('lo') and  # loopback
                   not iface.startswith('docker') and  # docker
                   not iface.startswith('veth') and  # virtual ethernet
                   not iface.startswith('br-')  # bridge
            ]

            # Если список пустой - берем все кроме lo
            if not filtered:
                filtered = [iface for iface in all_ifaces if iface != 'lo']

            self._log(f"Detected interfaces: {filtered}")
            return filtered if filtered else [conf.iface]

        except Exception as e:
            self._log(f"Error getting interfaces: {e}")
            return [conf.iface]

    def _tls_flow_key(self, packet_info):
        # направление важно: ClientHello идёт от клиента к серверу.
        # но нам всё равно — просто копим на оба направления отдельно.
        return (
            str(packet_info.get("src_ip")),
            int(packet_info.get("src_port") or 0),
            str(packet_info.get("dst_ip")),
            int(packet_info.get("dst_port") or 0),
            "TCP"
        )

    def _try_parse_tls_summary_buffered(self, pkt, packet_info):
        """
        Буферизуем первые TCP payload по 5-tuple и пытаемся вытащить ClientHello (SNI/ALPN)
        и иногда ServerHello (cipher) если попался.
        Возвращает строку или None.
        """
        try:
            key = self._tls_flow_key(packet_info)
            if key in self.tls_ch_parsed:
                return None

            data = self._get_tcp_payload_bytes(pkt)
            if not data:
                return None

            # Ограничим буфер (ClientHello обычно < 8-12 KB)
            buf = self.tls_ch_buffers.get(key)
            if buf is None:
                buf = bytearray()
                self.tls_ch_buffers[key] = buf

            if len(buf) < 16384:
                need = 16384 - len(buf)
                buf.extend(data[:need])

            # Пытаемся распарсить уже накопленное
            # s = self._try_parse_tls_summary_from_bytes(bytes(buf))
            blob = bytes(buf)

            s = self._try_parse_tls_summary_from_bytes(blob)  # ClientHello: SNI/ALPN
            if not s:
                s = self._try_parse_tls_serverhello_from_bytes(blob)  # ServerHello: cipher

            if s:
                self.tls_ch_parsed.add(key)
                # можно чистить буфер, чтобы не росло
                self.tls_ch_buffers.pop(key, None)
                return s

            # если буфер уже большой, а результата нет — прекращаем
            if len(buf) >= 16384:
                self.tls_ch_parsed.add(key)
                self.tls_ch_buffers.pop(key, None)

            return None
        except Exception:
            return None

    def set_bpf_filter(self, bpf: str | None):
        bpf = (bpf or "").strip()
        self.bpf_filter = bpf if bpf else None
        self._log(f"Set BPF filter: {self.bpf_filter!r}")

    def _log(self, message):
        """Логирование в файл вместо print()"""
        if self.log_file:
            try:
                with open(self.log_file, 'a') as f:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    f.write(f"[{timestamp}] {message}\n")
            except:
                pass

    def _packet_handler(self, pkt):
        """Обработчик пакета (callback для sniff)"""
        if not self.running:
            return

        with self.lock:
            # Парсим пакет
            packet_info = self._parse_packet(pkt)

            # Добавляем номер пакета
            self.packet_counter += 1
            packet_info['num'] = self.packet_counter

            # Добавляем в кольцевой буфер
            self.packets.append(packet_info)

            # Обновляем статистику bandwidth
            packet_size = packet_info.get('size', 0)
            self.total_bytes += packet_size
            self.bytes_last_second += packet_size

            # Обновляем bandwidth каждую секунду
            current_time = time.time()
            if self.last_bandwidth_check is None:
                self.last_bandwidth_check = current_time
            elif current_time - self.last_bandwidth_check >= 1.0:
                self.current_bandwidth = self.bytes_last_second
                self.bytes_last_second = 0
                self.last_bandwidth_check = current_time

            # Детекция packet loss для TCP
            if packet_info['proto'] in ['TCP', 'TCPv4', 'TCPv6']:
                self._detect_packet_loss(packet_info, pkt)

            # Измерение latency
            self._measure_latency(pkt)

    def _detect_packet_loss(self, packet_info, pkt):
        """Улучшенная детекция потери пакетов"""
        try:
            if not pkt.haslayer(TCP):
                return

            tcp = pkt[TCP]
            seq = tcp.seq
            payload_len = len(tcp.payload) if tcp.payload else 0

            src_ip = packet_info.get('src_ip')
            dst_ip = packet_info.get('dst_ip')
            src_port = packet_info.get('src_port')
            dst_port = packet_info.get('dst_port')

            if not all([src_ip, dst_ip, src_port, dst_port]):
                return

            flow_key = (src_ip, dst_ip, src_port, dst_port)

            if flow_key in self.tcp_sequence_tracker:
                last_seq, last_len = self.tcp_sequence_tracker[flow_key]
                expected_seq = last_seq + max(last_len, 1)

                # Разрыв больше чем ожидаемый размер пакета (обычно 1460-1500)
                gap = seq - expected_seq

                # Игнорируем retransmissions (seq меньше expected)
                if gap > 1460:  # MSS для Ethernet
                    self.packet_loss_count += 1
                    packet_info['packet_loss'] = True
                    packet_info['seq_gap'] = gap

            # Сохраняем текущий seq и длину payload
            self.tcp_sequence_tracker[flow_key] = (seq, payload_len)

        except Exception:
            pass

    def _measure_latency(self, pkt):
        """Измерение latency"""
        try:
            if hasattr(pkt, 'time'):
                capture_time = float(pkt.time)
                current_time = time.time()

                latency_us = (current_time - capture_time) * 1000000

                if 0 < latency_us < 1000000:
                    self.latency_samples.append(latency_us)
        except Exception:
            pass

    def _safe_decode_ascii(self, b: bytes, limit=2048) -> str:
        try:
            return b[:limit].decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _format_tcp_options(self, tcp) -> list[str]:
        out = []
        try:
            for name, value in getattr(tcp, "options", []) or []:
                if name == "MSS" and value is not None:
                    out.append(f"MSS={value}")
                elif name == "SAckOK":
                    out.append("SACK_PERM")
                elif name == "Timestamp" and isinstance(value, tuple) and len(value) >= 2:
                    out.append(f"TSval={value[0]}")
                    out.append(f"TSecr={value[1]}")
                elif name == "WScale" and value is not None:
                    out.append(f"WS={value}")
                elif name in ("NOP", "EOL"):
                    continue
                elif value is None:
                    out.append(str(name))
                else:
                    out.append(f"{name}={value}")
        except Exception:
            return []
        return out

    def _build_tcp_info_summary(self, pkt, flag_str: str) -> str:
        try:
            tcp = pkt[TCP]
            payload_len = len(bytes(tcp.payload)) if tcp.payload is not None else 0
            parts = [f"[{flag_str or 'NONE'}]", f"Seq={int(tcp.seq)}"]
            if bool(tcp.flags & 0x10):
                parts.append(f"Ack={int(tcp.ack)}")
            parts.append(f"Win={int(tcp.window)}")
            parts.append(f"Len={payload_len}")

            options = self._format_tcp_options(tcp)
            if options:
                parts.extend(options[:6])

            return " ".join(parts)
        except Exception:
            return f"Len={len(pkt[TCP]):>5}"

    def _get_tcp_payload_bytes(self, pkt) -> bytes:
        try:
            if pkt.haslayer(TCP):
                pl = bytes(pkt[TCP].payload)
                return pl if pl else b""
        except Exception:
            pass
        try:
            if pkt.haslayer(Raw):
                return bytes(pkt[Raw].load) if pkt[Raw].load else b""
        except Exception:
            pass
        return b""

    def _try_parse_http_summary(self, pkt) -> str | None:
        """
        HTTP: Host/URL/Status из Raw.
        Работает как для request, так и для response.
        """
        try:
            if not pkt.haslayer(Raw):
                return None
            raw = bytes(pkt[Raw].load)
            if not raw:
                return None

            s = self._safe_decode_ascii(raw, limit=4096)
            if not s:
                return None

            # request line
            # GET /path HTTP/1.1
            first_line = s.splitlines()[0] if s.splitlines() else ""
            methods = ("GET ", "POST ", "PUT ", "DELETE ", "HEAD ", "OPTIONS ", "PATCH ", "CONNECT ", "TRACE ")
            if first_line.startswith(methods) and " HTTP/" in first_line:
                parts = first_line.split()
                if len(parts) >= 2:
                    method = parts[0]
                    path = parts[1]
                else:
                    return None

                host = ""
                for line in s.splitlines()[1:]:
                    if line.lower().startswith("host:"):
                        host = line.split(":", 1)[1].strip()
                        break

                if host:
                    return f"HTTP {method} {host}{path}"
                return f"HTTP {method} {path}"

            # response line
            # HTTP/1.1 200 OK
            if first_line.startswith("HTTP/") and len(first_line.split()) >= 2:
                parts = first_line.split(None, 2)
                code = parts[1] if len(parts) > 1 else ""
                msg = parts[2] if len(parts) > 2 else ""
                msg = msg.strip()
                if msg:
                    return f"HTTP {code} {msg}"
                return f"HTTP {code}"

            return None
        except Exception:
            return None

    # ---- TLS helpers ----

    def _tls_ver_name(self, v: int) -> str:
        return {
            0x0300: "SSL3.0",
            0x0301: "TLS1.0",
            0x0302: "TLS1.1",
            0x0303: "TLS1.2",
            0x0304: "TLS1.3",
        }.get(v, f"0x{v:04x}")

    def _tls_alert_desc(self, d: int) -> str:
        # неполная таблица 
        m = {
            0: "close_notify",
            10: "unexpected_message",
            20: "bad_record_mac",
            21: "decryption_failed",
            22: "record_overflow",
            30: "decompression_failure",
            40: "handshake_failure",
            41: "no_certificate",
            42: "bad_certificate",
            43: "unsupported_certificate",
            44: "certificate_revoked",
            45: "certificate_expired",
            46: "certificate_unknown",
            47: "illegal_parameter",
            48: "unknown_ca",
            49: "access_denied",
            50: "decode_error",
            51: "decrypt_error",
            60: "export_restriction",
            70: "protocol_version",
            71: "insufficient_security",
            80: "internal_error",
            86: "inappropriate_fallback",
            90: "user_canceled",
            100: "no_renegotiation",
            109: "missing_extension",
            110: "unsupported_extension",
            111: "certificate_unobtainable",
            112: "unrecognized_name",  # SNI
            113: "bad_certificate_status_response",
            114: "bad_certificate_hash_value",
            115: "unknown_psk_identity",
            116: "certificate_required",
            120: "no_application_protocol",
        }
        return m.get(d, f"desc_{d}")

    def _tls_alert_level(self, lvl: int) -> str:
        return {1: "warning", 2: "fatal"}.get(lvl, f"lvl_{lvl}")

    def _read_u8(self, b: bytes, p: int) -> tuple[int, int]:
        return b[p], p + 1

    def _read_u16(self, b: bytes, p: int) -> tuple[int, int]:
        return int.from_bytes(b[p:p + 2], "big"), p + 2

    def _read_u24(self, b: bytes, p: int) -> tuple[int, int]:
        return int.from_bytes(b[p:p + 3], "big"), p + 3

    def _try_parse_tls_serverhello_from_bytes(self, data: bytes) -> str | None:
        """
        Минимально: TLS ServerHello -> версия (по record/hello) + cipher_suite.
        Работает по накопленному потоку server->client.
        """
        try:
            if not data or len(data) < 6:
                return None

            # Найдём начало TLS record (handshake=0x16, version=0x03)
            start = -1
            for i in range(0, min(len(data) - 3, 4096)):
                if data[i] == 0x16 and data[i + 1] == 0x03:
                    start = i
                    break
            if start < 0:
                return None

            data = data[start:]

            if len(data) < 5:
                return None

            rec_ver = data[1:3]  # 03 01 / 03 03 ...
            rec_len = int.from_bytes(data[3:5], "big")
            rec_end = min(5 + rec_len, len(data))
            if rec_end < 9:
                return None

            # handshake header
            hs_type = data[5]
            if hs_type != 0x02:  # ServerHello
                return None
            hs_len = int.from_bytes(data[6:9], "big")
            hs_end = min(9 + hs_len, rec_end)
            if hs_end < 9 + 38:  # минимальная длина ServerHello
                return None

            p = 9

            # legacy_version (2)
            legacy_ver = data[p:p + 2]
            p += 2

            # random (32)
            p += 32
            if p > hs_end:
                return None

            # session_id
            if p + 1 > hs_end:
                return None
            sid_len = data[p]
            p += 1 + sid_len
            if p > hs_end:
                return None

            # cipher_suite (2)
            if p + 2 > hs_end:
                return None
            cipher = int.from_bytes(data[p:p + 2], "big")
            p += 2

            # compression_method (1) - может быть 0
            if p + 1 > hs_end:
                return None
            p += 1

            # Версию красиво (эвристика)
            # В TLS1.3 ServerHello legacy_version = 0x0303 (TLS1.2), реальная версия в supported_versions ext,
            # но без полного парсинга можно показать "TLS1.3?" по наличию 0x0303 и дальнейших encrypted records.
            ver_map = {
                b"\x03\x01": "TLS1.0",
                b"\x03\x02": "TLS1.1",
                b"\x03\x03": "TLS1.2/1.3",
            }
            ver_s = ver_map.get(legacy_ver, f"0x{legacy_ver.hex()}")

            return f"TLS ServerHello ver={ver_s} cipher=0x{cipher:04x}"
        except Exception:
            return None

    def _try_parse_tls_summary_from_bytes(self, data: bytes) -> str | None:
        """
        Минимально: TLS ClientHello -> SNI + ALPN.
        Работает по накопленному потоку.
        """
        # try:
        #     if not data or len(data) < 6:
        #         return None
        try:
            # TLS record header = 5 байт (type(1) + ver(2) + len(2))
            if not data or len(data) < 5:
                return None

            # найдём начало TLS record (handshake=0x16, version=0x03)
            start = -1
            for i in range(0, min(len(data) - 3, 4096)):
                if data[i] == 0x16 and data[i + 1] == 0x03:
                    start = i
                    break
            if start < 0:
                return None

            data = data[start:]

            # record header: type(1)=0x16, version(2), len(2)
            if len(data) < 5:
                return None
            rec_len = int.from_bytes(data[3:5], "big")
            if rec_len <= 0:
                return None
            rec_end = min(5 + rec_len, len(data))

            # handshake header starts at 5: msg_type(1), len(3)
            if rec_end < 9:
                return None
            hs_type = data[5]
            if hs_type != 0x01:  # ClientHello
                return None
            hs_len = int.from_bytes(data[6:9], "big")
            hs_end = min(9 + hs_len, rec_end)
            if hs_end <= 9:
                return None

            p = 9
            # client_version(2) + random(32)
            if p + 2 + 32 > hs_end:
                return None
            p += 2 + 32

            # session id
            if p + 1 > hs_end:
                return None
            sid_len = data[p]
            p += 1 + sid_len
            if p > hs_end:
                return None

            # cipher_suites
            if p + 2 > hs_end:
                return None
            cs_len = int.from_bytes(data[p:p + 2], "big")
            p += 2 + cs_len
            if p > hs_end:
                return None

            # compression_methods
            if p + 1 > hs_end:
                return None
            cm_len = data[p]
            p += 1 + cm_len
            if p > hs_end:
                return None

            # extensions
            if p + 2 > hs_end:
                return None
            ext_len = int.from_bytes(data[p:p + 2], "big")
            p += 2
            ext_end = min(p + ext_len, hs_end)

            sni = None
            alpn = []

            while p + 4 <= ext_end:
                etype = int.from_bytes(data[p:p + 2], "big");
                p += 2
                elen = int.from_bytes(data[p:p + 2], "big");
                p += 2
                if p + elen > ext_end:
                    break

                # server_name (0)
                if etype == 0x0000 and elen >= 2:
                    q = p
                    list_len = int.from_bytes(data[q:q + 2], "big");
                    q += 2
                    list_end = min(p + elen, q + list_len)
                    while q + 3 <= list_end:
                        name_type = data[q];
                        q += 1
                        name_len = int.from_bytes(data[q:q + 2], "big");
                        q += 2
                        if q + name_len > list_end:
                            break
                        if name_type == 0:
                            sni = data[q:q + name_len].decode("utf-8", errors="replace").strip()
                            break
                        q += name_len

                # ALPN (16)
                if etype == 0x0010 and elen >= 2:
                    q = p
                    list_len = int.from_bytes(data[q:q + 2], "big");
                    q += 2
                    list_end = min(p + elen, q + list_len)
                    while q < list_end:
                        if q + 1 > list_end:
                            break
                        ln = data[q];
                        q += 1
                        if q + ln > list_end:
                            break
                        alpn.append(data[q:q + ln].decode("utf-8", errors="replace"))
                        q += ln

                p += elen

            parts = []
            if sni:
                parts.append(f"SNI={sni}")
            if alpn:
                parts.append("ALPN=" + ",".join(alpn[:6]))

            if parts:
                return "TLS ClientHello " + " ".join(parts)
            return None

        except Exception:
            return None

    def _try_parse_tls_summary(self, pkt) -> Optional[str]:
        """
        TLS summary из Raw:
          - ClientHello: SNI + ALPN + версия
          - ServerHello: версия + cipher (и supported_versions, если есть)
          - Alert: level + desc
          - (опц) JA3: md5 fingerprint
        """
        try:
            # if not pkt.haslayer(Raw):
            #     return None
            # data = bytes(pkt[Raw].load)
            data = self._get_tcp_payload_bytes(pkt)
            if not data:
                return None
            if len(data) < 5:
                return None

            # TLS record header: type(1), version(2), length(2)
            rec_type = data[0]
            rec_ver = int.from_bytes(data[1:3], "big")
            rec_len = int.from_bytes(data[3:5], "big")
            if rec_len <= 0:
                return None

            # ограничим конец рекорда
            rec_end = min(len(data), 5 + rec_len)
            body = data[5:rec_end]

            # 0x15 = Alert
            if rec_type == 0x15:
                return self._parse_tls_alert(body, rec_ver)

            # 0x16 = Handshake (в TLS1.3 многие сообщения после SH уже шифруются и идут как 0x17)
            if rec_type != 0x16:
                return None

            # Handshake message header: msg_type(1), len(3)
            if len(body) < 4:
                return None
            hs_type = body[0]
            hs_len = int.from_bytes(body[1:4], "big")
            hs_body = body[4:4 + hs_len]
            if not hs_body:
                return None

            # ClientHello
            if hs_type == 0x01:
                return self._parse_tls_client_hello(hs_body, rec_ver)

            # ServerHello
            if hs_type == 0x02:
                return self._parse_tls_server_hello(hs_body, rec_ver)

            # Certificate (TLS1.2 и ниже часто виден; в TLS1.3 обычно уже шифруется)
            if hs_type == 0x0b:
                cert = self._parse_tls_certificate_brief(hs_body)
                if cert:
                    return cert
                return "TLS Certificate"

            return None
        except Exception:
            return None

    def _parse_tls_alert(self, body: bytes, rec_ver: int) -> Optional[str]:
        try:
            if len(body) < 2:
                return None
            lvl = body[0]
            desc = body[1]
            return f"TLS Alert {self._tls_alert_level(lvl)} {self._tls_alert_desc(desc)} ({self._tls_ver_name(rec_ver)})"
        except Exception:
            return None

    def _parse_tls_client_hello(self, b: bytes, rec_ver: int) -> Optional[str]:
        """
        ClientHello (best effort):
          client_version(2), random(32), session_id, cipher_suites, comp_methods, extensions
        Из extensions достаём:
          - SNI (0x0000)
          - ALPN (0x0010)
          - supported_versions (0x002b) -> TLS1.3 и т.п.
          - supported_groups (0x000a), ec_point_formats (0x000b) для JA3
        """
        try:
            p = 0
            if len(b) < 2 + 32 + 1:
                return None

            client_ver = int.from_bytes(b[p:p + 2], "big");
            p += 2
            p += 32  # random

            sid_len = b[p];
            p += 1
            p += sid_len
            if p >= len(b):
                return None

            cs_len = int.from_bytes(b[p:p + 2], "big");
            p += 2
            cs_end = p + cs_len
            if cs_end > len(b):
                return None
            cipher_suites = b[p:cs_end]
            p = cs_end

            if p + 1 > len(b):
                return None
            cm_len = b[p];
            p += 1
            p += cm_len
            if p > len(b):
                return None

            if p + 2 > len(b):
                # no extensions
                sni = None
                alpn = None
                ver = self._tls_ver_name(client_ver)
                return f"TLS ClientHello ver={ver}" + (f" SNI={sni}" if sni else "")

            ext_len = int.from_bytes(b[p:p + 2], "big");
            p += 2
            ext_end = min(len(b), p + ext_len)

            sni = None
            alpns = []
            supported_versions = None

            # JA3 pieces
            ja3_exts = []
            ja3_groups = []
            ja3_ecpf = []

            while p + 4 <= ext_end:
                etype = int.from_bytes(b[p:p + 2], "big");
                p += 2
                elen = int.from_bytes(b[p:p + 2], "big");
                p += 2
                ebody = b[p:p + elen]
                p += elen
                if len(ebody) != elen:
                    break

                ja3_exts.append(str(etype))

                # SNI
                if etype == 0x0000:
                    # list_len(2), then entries
                    if len(ebody) < 2:
                        continue
                    q = 2
                    while q + 3 <= len(ebody):
                        name_type = ebody[q];
                        q += 1
                        name_len = int.from_bytes(ebody[q:q + 2], "big");
                        q += 2
                        if q + name_len > len(ebody):
                            break
                        if name_type == 0:
                            sni = ebody[q:q + name_len].decode("utf-8", errors="replace").strip()
                            break
                        q += name_len

                # ALPN
                elif etype == 0x0010:
                    # alpn_ext: list_len(2), then (name_len(1), name)
                    if len(ebody) < 2:
                        continue
                    q = 2
                    while q + 1 <= len(ebody):
                        ln = ebody[q];
                        q += 1
                        if q + ln > len(ebody):
                            break
                        proto = ebody[q:q + ln].decode("ascii", errors="replace")
                        q += ln
                        if proto:
                            alpns.append(proto)

                # supported_versions
                elif etype == 0x002b:
                    # client: len(1) then versions(2 each)
                    if len(ebody) < 1:
                        continue
                    ln = ebody[0]
                    q = 1
                    vers = []
                    while q + 2 <= len(ebody) and (q - 1) < ln:
                        vv = int.from_bytes(ebody[q:q + 2], "big")
                        vers.append(self._tls_ver_name(vv))
                        q += 2
                    if vers:
                        supported_versions = vers[0]  # обычно самое новое

                # supported_groups (elliptic curves)
                elif etype == 0x000a:
                    if len(ebody) < 2:
                        continue
                    glen = int.from_bytes(ebody[0:2], "big")
                    q = 2
                    while q + 2 <= len(ebody) and (q - 2) < glen:
                        gid = int.from_bytes(ebody[q:q + 2], "big")
                        ja3_groups.append(str(gid))
                        q += 2

                # ec_point_formats
                elif etype == 0x000b:
                    if len(ebody) < 1:
                        continue
                    flen = ebody[0]
                    q = 1
                    for i in range(min(flen, len(ebody) - 1)):
                        ja3_ecpf.append(str(ebody[q + i]))

            # Версия: для TLS1.3 обычно client_ver=0x0303, реальная в supported_versions
            ver_name = supported_versions or self._tls_ver_name(client_ver)

            parts = [f"TLS ClientHello ver={ver_name}"]
            if sni:
                parts.append(f"SNI={sni}")
            if alpns:
                parts.append(f"ALPN={','.join(alpns)}")

            # JA3 (опционально)
            ja3 = self._build_ja3(client_ver, cipher_suites, ja3_exts, ja3_groups, ja3_ecpf)
            if ja3:
                parts.append(f"JA3={ja3}")

            return " ".join(parts)
        except Exception:
            return None

    def _parse_tls_server_hello(self, b: bytes, rec_ver: int) -> Optional[str]:
        """
        ServerHello (best effort):
          server_version(2), random(32), session_id, cipher_suite(2), comp(1), extensions
        Из extensions:
          - supported_versions (0x002b) -> TLS1.3 реально
        """
        try:
            p = 0
            if len(b) < 2 + 32 + 1:
                return None

            srv_ver = int.from_bytes(b[p:p + 2], "big");
            p += 2
            p += 32

            sid_len = b[p];
            p += 1
            p += sid_len
            if p + 2 + 1 > len(b):
                return None

            cipher = int.from_bytes(b[p:p + 2], "big");
            p += 2
            _comp = b[p];
            p += 1

            tls13_ver = None
            if p + 2 <= len(b):
                ext_len = int.from_bytes(b[p:p + 2], "big");
                p += 2
                ext_end = min(len(b), p + ext_len)
                while p + 4 <= ext_end:
                    etype = int.from_bytes(b[p:p + 2], "big");
                    p += 2
                    elen = int.from_bytes(b[p:p + 2], "big");
                    p += 2
                    ebody = b[p:p + elen];
                    p += elen
                    if etype == 0x002b and len(ebody) >= 2:
                        vv = int.from_bytes(ebody[0:2], "big")
                        tls13_ver = self._tls_ver_name(vv)

            ver_name = tls13_ver or self._tls_ver_name(srv_ver)
            return f"TLS ServerHello ver={ver_name} cipher=0x{cipher:04x}"
        except Exception:
            return None

    def _parse_tls_certificate_brief(self, b: bytes) -> Optional[str]:
        """
        Попытка вытащить CN/SAN.
        Реально работает нормально в TLS1.2 и ниже (в TLS1.3 cert обычно в шифрованных record'ах).
        Используем cryptography если доступна.
        """
        try:
            # TLS1.2 Certificate:
            # cert_list_len(3), then repeated: cert_len(3) + cert_der
            if len(b) < 3:
                return None
            total_len = int.from_bytes(b[0:3], "big")
            p = 3
            if p + 3 > len(b):
                return None
            cert_len = int.from_bytes(b[p:p + 3], "big");
            p += 3
            cert_der = b[p:p + cert_len]
            if len(cert_der) < 16:
                return None

            if x509 is None or default_backend is None:
                return "TLS Certificate"

            cert = x509.load_der_x509_certificate(cert_der, default_backend())

            # CN
            cn = ""
            try:
                for attr in cert.subject:
                    if attr.oid.dotted_string == "2.5.4.3":  # CN
                        cn = str(attr.value)
                        break
            except Exception:
                cn = ""

            # SAN (DNS)
            san_dns = []
            try:
                ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                san_dns = ext.value.get_values_for_type(x509.DNSName)[:3]
            except Exception:
                san_dns = []

            parts = ["TLS Certificate"]
            if cn:
                parts.append(f"CN={cn}")
            if san_dns:
                parts.append("SAN=" + ",".join(san_dns))
            return " ".join(parts)
        except Exception:
            return None

    def _build_ja3(self, client_ver: int, cipher_suites_bytes: bytes, exts: list[str], groups: list[str],
                   ecpf: list[str]) -> Optional[str]:
        """
        JA3: <version>,<ciphers>,<extensions>,<elliptic_curves>,<ec_point_formats>
        Реализация best-effort; если что-то не удалось — вернёт None.
        """
        try:
            # ciphers: 2 bytes each
            ciphers = []
            for i in range(0, len(cipher_suites_bytes), 2):
                if i + 2 > len(cipher_suites_bytes):
                    break
                cid = int.from_bytes(cipher_suites_bytes[i:i + 2], "big")
                # игнорируем GREASE (0x?A?A)
                if (cid & 0x0f0f) == 0x0a0a:
                    continue
                ciphers.append(str(cid))

            # extensions: тоже фильтруем GREASE
            exts2 = []
            for e in exts:
                try:
                    ei = int(e)
                except Exception:
                    continue
                if (ei & 0x0f0f) == 0x0a0a:
                    continue
                exts2.append(str(ei))

            # groups/ecpf тоже фильтруем GREASE для groups
            groups2 = []
            for g in groups:
                try:
                    gi = int(g)
                except Exception:
                    continue
                if (gi & 0x0f0f) == 0x0a0a:
                    continue
                groups2.append(str(gi))

            ja3_str = f"{client_ver},{'-'.join(ciphers)},{'-'.join(exts2)},{'-'.join(groups2)},{'-'.join(ecpf)}"
            md5 = hashlib.md5(ja3_str.encode("ascii", errors="ignore")).hexdigest()
            return md5
        except Exception:
            return None

    def _try_parse_tls_sni(self, pkt) -> str | None:
        """
        TLS ClientHello SNI (очень лёгкий парсер по байтам).
        Ищем TLS record(0x16) -> Handshake(ClientHello=0x01) -> extensions -> server_name(0x0000).
        """
        try:
            data = self._get_tcp_payload_bytes(pkt)
            if not data:
                return None

            if len(data) < 6:
                return None

            # TLS record header: type(1)=0x16, version(2), length(2)
            if data[0] != 0x16:
                return None

            # record length
            rec_len = int.from_bytes(data[3:5], "big")
            if rec_len <= 0 or 5 + rec_len > len(data):
                # иногда пакет урезан/фрагментирован
                rec_end = min(len(data), 5 + rec_len)
            else:
                rec_end = 5 + rec_len

            # handshake header starts at 5
            if len(data) < 9:
                return None
            hs_type = data[5]
            if hs_type != 0x01:  # ClientHello
                return None
            hs_len = int.from_bytes(data[6:9], "big")
            hs_end = 9 + hs_len
            hs_end = min(hs_end, rec_end)

            p = 9
            # client_version(2)
            if p + 2 > hs_end: return None
            p += 2
            # random(32)
            if p + 32 > hs_end: return None
            p += 32
            # session_id
            if p + 1 > hs_end: return None
            sid_len = data[p]
            p += 1 + sid_len
            if p > hs_end: return None
            # cipher_suites
            if p + 2 > hs_end: return None
            cs_len = int.from_bytes(data[p:p + 2], "big")
            p += 2 + cs_len
            if p > hs_end: return None
            # compression_methods
            if p + 1 > hs_end: return None
            cm_len = data[p]
            p += 1 + cm_len
            if p > hs_end: return None
            # extensions length
            if p + 2 > hs_end:
                return None
            ext_len = int.from_bytes(data[p:p + 2], "big")
            p += 2
            ext_end = min(p + ext_len, hs_end)

            # parse extensions
            while p + 4 <= ext_end:
                etype = int.from_bytes(data[p:p + 2], "big");
                p += 2
                elen = int.from_bytes(data[p:p + 2], "big");
                p += 2
                if p + elen > ext_end:
                    break

                if etype == 0x0000:  # server_name
                    # ServerNameList length(2)
                    if elen < 2:
                        break
                    q = p
                    list_len = int.from_bytes(data[q:q + 2], "big")
                    q += 2
                    list_end = min(p + elen, q + list_len)
                    # entries: name_type(1)=0, name_len(2), name(bytes)
                    while q + 3 <= list_end:
                        name_type = data[q];
                        q += 1
                        name_len = int.from_bytes(data[q:q + 2], "big");
                        q += 2
                        if q + name_len > list_end:
                            break
                        if name_type == 0:
                            sni = data[q:q + name_len].decode("utf-8", errors="replace")
                            sni = sni.strip()
                            if sni:
                                return f"TLS SNI {sni}"
                        q += name_len

                p += elen

            return None
        except Exception:
            return None

    def _dns_answers_summary(self, dns_layer) -> str:
        """
        Вернёт краткий список ответов DNS (A/AAAA/CNAME/NS/MX/TXT...) как строку.
        """
        try:
            if dns_layer is None:
                return ""
            if getattr(dns_layer, "ancount", 0) == 0:
                return ""

            answers = []
            an = dns_layer.an
            # scapy: DNSRR / chain (an.payload -> next)
            for _ in range(int(dns_layer.ancount)):
                if an is None:
                    break
                try:
                    rtype = int(getattr(an, "type", 0))
                    rdata = getattr(an, "rdata", None)
                    rrname = getattr(an, "rrname", b"")
                    rrname_s = rrname.decode(errors="ignore") if isinstance(rrname, (bytes, bytearray)) else str(rrname)

                    # Превращаем rdata в норм строку
                    if isinstance(rdata, (bytes, bytearray)):
                        rdata_s = rdata.decode(errors="ignore")
                    else:
                        rdata_s = str(rdata)

                    # типы (минимально)
                    # 1=A, 28=AAAA, 5=CNAME, 2=NS, 15=MX, 16=TXT
                    type_name = {
                        1: "A", 28: "AAAA", 5: "CNAME", 2: "NS", 15: "MX", 16: "TXT"
                    }.get(rtype, f"T{rtype}")

                    answers.append(f"{type_name}:{rdata_s}")
                except Exception:
                    pass

                # следующий RR
                an = getattr(an, "payload", None)
                if an is None or an.__class__.__name__ == "NoPayload":
                    break

            if not answers:
                return ""
            # ограничим длину
            s = ", ".join(answers[:6])
            if len(answers) > 6:
                s += ", ..."
            return s
        except Exception:
            return ""

    def _parse_packet(self, pkt):
        """Разобрать scapy-пакет в единый словарь `packet_info`, используемый UI/фильтрами.

            Метод выделяет L2/L3/L4 параметры (MAC/IP/ports), определяет proto (TCP/UDP/DNS/ARP/ICMP...),
            заполняет служебные поля для фильтрации и анализа (tcp_syn/tcp_ack/tcp_seq и т.п.),
            а также формирует человекочитаемые строки `info_short` / `info_long` / `info`.

            Args:
                pkt: Объект scapy packet, полученный в callback sniff(prn=...).
                     Обычно содержит атрибут `.time`, может иметь `.sniffed_on`.

            Returns:
                dict: packet_info со стандартным набором ключей, как ожидают:
                      PacketListBox/FlowListBox/PacketFilter/PacketDetailView/FollowStream.
            """

        packet_info = {
            'timestamp': datetime.fromtimestamp(float(pkt.time)),
            'proto': 'UNKNOWN',
            'src': '',
            'dst': '',
            'src_ip': None,
            'dst_ip': None,
            'src_port': None,
            'dst_port': None,
            'info': '',
            'info_short': '',
            'info_long': '',
            'size': len(pkt),
            'raw_packet': pkt,
            'raw': bytes(pkt),
            'interface': None,
            'packet_loss': False,
            'tcp_flags': '',
            'tcp_syn': False,
            'tcp_ack': False,
            'tcp_fin': False,
            'tcp_rst': False,
            'tcp_seq': None,
            'tcp_acknum': None,

        }

        # Получаем интерфейс и ВСЕГДА преобразуем в строку
        if hasattr(pkt, 'sniffed_on'):
            iface = pkt.sniffed_on
            # Преобразуем в строку независимо от типа
            packet_info['interface'] = str(iface) if iface else str(self.interface)
        else:
            packet_info['interface'] = str(self.interface)

        # Дополнительная проверка
        if packet_info['interface'] and not isinstance(packet_info['interface'], str):
            packet_info['interface'] = str(packet_info['interface'])

        # Ethernet layer
        if pkt.haslayer(Ether):
            packet_info['src'] = pkt[Ether].src
            packet_info['dst'] = pkt[Ether].dst

        # ARP
        if pkt.haslayer(ARP):
            packet_info['proto'] = 'ARP'
            packet_info['src_ip'] = pkt[ARP].psrc
            packet_info['dst_ip'] = pkt[ARP].pdst
            packet_info['info'] = f"Who has {pkt[ARP].pdst}? Tell {pkt[ARP].psrc}"

        # IPv4
        elif pkt.haslayer(IP):
            packet_info['src_ip'] = pkt[IP].src
            packet_info['dst_ip'] = pkt[IP].dst

            # TCP
            if pkt.haslayer(TCP):
                packet_info['proto'] = 'TCP'
                packet_info['src_port'] = pkt[TCP].sport
                packet_info['dst_port'] = pkt[TCP].dport

                packet_info['tcp_seq'] = int(pkt[TCP].seq)
                packet_info['tcp_acknum'] = int(pkt[TCP].ack)

                flags = pkt[TCP].flags
                flag_str = self._get_tcp_flags(flags)

                # --- tcp flags для точной фильтрации ---
                # Scapy flags — это битовая маска
                packet_info['tcp_syn'] = bool(flags & 0x02)
                packet_info['tcp_ack'] = bool(flags & 0x10)
                packet_info['tcp_fin'] = bool(flags & 0x01)
                packet_info['tcp_rst'] = bool(flags & 0x04)

                # строковое представление (опционально, но удобно)
                parts = []
                if packet_info['tcp_syn']: parts.append("SYN")
                if packet_info['tcp_ack']: parts.append("ACK")
                if packet_info['tcp_fin']: parts.append("FIN")
                if packet_info['tcp_rst']: parts.append("RST")
                packet_info['tcp_flags'] = ",".join(parts)

                info_short = f"Len={len(pkt[TCP]):>5}"
                info_long = self._build_tcp_info_summary(pkt, flag_str)

                http = self._try_parse_http_summary(pkt)
                if http:
                    info_short = info_short + " | " + http
                    info_long = info_long + " | " + http
                else:
                    tls = self._try_parse_tls_summary_buffered(pkt, packet_info)
                    if tls:
                        info_short = info_short + " | " + tls
                        info_long = info_long + " | " + tls

                packet_info['info_short'] = info_short
                packet_info['info_long'] = info_long

                # по умолчанию показываем short (UI сможет переключать)
                packet_info['info'] = info_short

            # UDP
            elif pkt.haslayer(UDP):
                packet_info['proto'] = 'UDP'
                packet_info['src_port'] = pkt[UDP].sport
                packet_info['dst_port'] = pkt[UDP].dport

                # DNS
                if pkt.haslayer(DNS):
                    packet_info['proto'] = 'DNS'
                    try:
                        dns_query = pkt[DNS].qd.qname.decode() if pkt[DNS].qd else ''
                    except:
                        dns_query = ''

                    ans = self._dns_answers_summary(pkt[DNS]) if pkt.haslayer(DNS) else ""
                    if ans:
                        packet_info['info'] = f"DNS {dns_query} | Ans: {ans}"
                    else:
                        packet_info['info'] = f"DNS {dns_query}"

                else:
                    # packet_info['info'] = f"{pkt[UDP].sport} → {pkt[UDP].dport} Len={len(pkt[UDP])}"
                    packet_info['info'] = f"Len={len(pkt[UDP])}"

            # ICMP
            elif pkt.haslayer(ICMP):
                packet_info['proto'] = 'ICMP'
                packet_info['info'] = f"Type {pkt[ICMP].type} Code {pkt[ICMP].code}"

        # IPv6
        elif pkt.haslayer(IPv6):
            packet_info['src_ip'] = pkt[IPv6].src
            packet_info['dst_ip'] = pkt[IPv6].dst

            # TCP over IPv6
            if pkt.haslayer(TCP):
                packet_info['proto'] = 'TCPv6'
                packet_info['src_port'] = pkt[TCP].sport
                packet_info['dst_port'] = pkt[TCP].dport

                packet_info['tcp_seq'] = int(pkt[TCP].seq)
                packet_info['tcp_acknum'] = int(pkt[TCP].ack)

                flags = pkt[TCP].flags
                flag_str = self._get_tcp_flags(flags)

                # --- tcp flags для точной фильтрации ---
                packet_info['tcp_syn'] = bool(flags & 0x02)
                packet_info['tcp_ack'] = bool(flags & 0x10)
                packet_info['tcp_fin'] = bool(flags & 0x01)
                packet_info['tcp_rst'] = bool(flags & 0x04)

                parts = []
                if packet_info['tcp_syn']: parts.append("SYN")
                if packet_info['tcp_ack']: parts.append("ACK")
                if packet_info['tcp_fin']: parts.append("FIN")
                if packet_info['tcp_rst']: parts.append("RST")
                packet_info['tcp_flags'] = ",".join(parts)

                info_short = f"Len={len(pkt[TCP]):>5}"
                info_long = self._build_tcp_info_summary(pkt, flag_str)

                http = self._try_parse_http_summary(pkt)
                if http:
                    info_short = info_short + " | " + http
                    info_long = info_long + " | " + http
                else:
                    tls = self._try_parse_tls_summary_buffered(pkt, packet_info)
                    if tls:
                        info_short = info_short + " | " + tls
                        info_long = info_long + " | " + tls

                packet_info['info_short'] = info_short
                packet_info['info_long'] = info_long
                packet_info['info'] = info_short

            # UDP over IPv6
            elif pkt.haslayer(UDP):
                # packet_info['proto'] = 'UDPv6'
                # packet_info['src_port'] = pkt[UDP].sport
                # packet_info['dst_port'] = pkt[UDP].dport
                # packet_info['info'] = f"Len={len(pkt[UDP])}"
                # # packet_info['info'] = f"{pkt[UDP].sport} → {pkt[UDP].dport}"
                packet_info['proto'] = 'UDPv6'
                packet_info['src_port'] = pkt[UDP].sport
                packet_info['dst_port'] = pkt[UDP].dport

                if pkt.haslayer(DNS):
                    packet_info['proto'] = 'DNS'
                    try:
                        dns_query = pkt[DNS].qd.qname.decode() if pkt[DNS].qd else ''
                    except:
                        dns_query = ''
                    ans = self._dns_answers_summary(pkt[DNS])
                    if ans:
                        packet_info['info'] = f"DNS {dns_query} | Ans: {ans}"
                    else:
                        packet_info['info'] = f"DNS {dns_query}"
                else:
                    packet_info['info'] = f"Len={len(pkt[UDP])}"


            # ICMPv6
            elif pkt.haslayer(ICMPv6EchoRequest) or pkt.haslayer(ICMPv6EchoReply):
                packet_info['proto'] = 'ICMPv6'
                packet_info['info'] = 'Echo Request/Reply'

        # Если протокол не определен
        if packet_info['proto'] == 'UNKNOWN':
            packet_info['proto'] = 'ETHER'
            packet_info['info'] = pkt.summary()

        return packet_info

    def _get_tcp_flags(self, flags):
        """Преобразовать TCP флаги в строку"""
        flag_list = []
        if flags & 0x01:
            flag_list.append('FIN')
        if flags & 0x02:
            flag_list.append('SYN')
        if flags & 0x04:
            flag_list.append('RST')
        if flags & 0x08:
            flag_list.append('PSH')
        if flags & 0x10:
            flag_list.append('ACK')
        if flags & 0x20:
            flag_list.append('URG')

        return ', '.join(flag_list) if flag_list else 'None'

    def _sniff_thread(self, interface):
        """Поток для захвата пакетов с одного интерфейса"""
        self._log(f"Sniff thread started on {interface} (bpf={self.bpf_filter!r})")

        try:
            sniff_kwargs = dict(
                iface=interface,
                prn=self._packet_handler,
                store=False,
                stop_filter=lambda x: self.stop_sniffing.is_set()
            )

            # BPF применяется на уровне libpcap (до попадания пакетов в Python)
            if self.bpf_filter:
                sniff_kwargs["filter"] = self.bpf_filter

            sniff(**sniff_kwargs)

        except Exception as e:
            self._log(f"Error in sniff thread ({interface}): {e}")
        finally:
            self._log(f"Sniff thread stopped ({interface})")

    def start_capture(self):
        """Запустить захват пакетов на всех интерфейсах"""
        if self.running:
            self._log("Already running")
            return

        self._log(f"Starting capture on interfaces: {self.interfaces}")

        self.start_time = time.time()
        self.last_bandwidth_check = time.time()
        self.stop_sniffing.clear()
        self.running = True

        try:
            # Запускаем отдельный поток для каждого интерфейса
            for iface in self.interfaces:
                thread = threading.Thread(
                    target=self._sniff_thread,
                    args=(iface,),
                    daemon=True,
                    name=f"Sniffer-{iface}"
                )
                thread.start()
                self.capture_threads.append(thread)
                self._log(f"Started thread for {iface}")

            time.sleep(0.1)
            self._log(f"Capture started on {len(self.capture_threads)} interfaces")

        except Exception as e:
            self._log(f"Error starting capture: {e}")
            self.running = False

    def stop_capture(self):
        """Остановить захват пакетов на всех интерфейсах"""
        if not self.running:
            self._log("Not running")
            return

        self._log("Stopping capture...")

        try:
            # Сигнализируем всем потокам об остановке
            self.stop_sniffing.set()
            self.running = False

            # Ждем завершения всех потоков
            for thread in self.capture_threads:
                if thread.is_alive():
                    thread.join(timeout=2.0)

            self.capture_threads.clear()
            self._log("Capture stopped")

        except Exception as e:
            self._log(f"Error stopping capture: {e}")

    def get_packets(self):
        """Получить список захваченных пакетов (thread-safe)"""
        with self.lock:
            return list(self.packets)

    def clear_packets(self):
        """Очистить буфер пакетов"""
        with self.lock:
            self.packets.clear()
            self.packet_counter = 0
            self.total_bytes = 0
            self.bytes_last_second = 0
            self.current_bandwidth = 0
            self.packet_loss_count = 0
            self.tcp_sequence_tracker.clear()
            self.latency_samples.clear()
            self._log("Buffer cleared")

    def get_bandwidth(self):
        """Получить текущую пропускную способность в bytes/sec"""
        return self.current_bandwidth

    def get_bandwidth_mbps(self):
        """Получить пропускную способность в Mbps"""
        return (self.current_bandwidth * 8) / 1_000_000

    def get_average_latency(self):
        """Получить среднюю latency в микросекундах"""
        if not self.latency_samples:
            return None
        return sum(self.latency_samples) / len(self.latency_samples)

    def get_packet_loss_count(self):
        """Получить количество обнаруженных потерянных пакетов"""
        return self.packet_loss_count

    def get_statistics(self):
        """Получить полную статистику захвата"""
        with self.lock:
            uptime = time.time() - self.start_time if self.start_time else 0

            return {
                'total_packets': self.packet_counter,
                'buffer_size': len(self.packets),
                'buffer_limit': self.packet_limit,
                'total_bytes': self.total_bytes,
                'bandwidth_bps': self.current_bandwidth,
                'bandwidth_mbps': self.get_bandwidth_mbps(),
                'uptime_seconds': uptime,
                'avg_latency_us': self.get_average_latency(),
                'packet_loss_count': self.packet_loss_count,
                'active_threads': len([t for t in self.capture_threads if t.is_alive()]),
            }


class SelectableText(urwid.Text):
    """Selectable Text widget для ListBox с поддержкой wrap"""
    
    def __init__(self, markup, wrap='space'):
        """Текстовый виджет urwid, который можно фокусировать/выбирать.

        Args:
            text: Отображаемая строка.
            wrap: Режим переноса (обычно 'clip' для таблиц).
        """

        super().__init__(markup, wrap=wrap)
        self._selectable = True
    
    def selectable(self):
        return self._selectable
    
    def keypress(self, size, key):
        return key


class StatisticsPanel(urwid.WidgetWrap):
    """Расширенная панель статистики справа - ПОЛНОСТЬЮ ИСПРАВЛЕНО"""
    
    def __init__(self, enable_ipv6_stats=False):
        """Панель статистики по текущему отображаемому набору пакетов.

        Args:
            enable_ipv6_stats: Если True — показывать IPv6-статистику отдельно/расширенно.
        """

        self.enable_ipv6_stats = enable_ipv6_stats
        
        # Создаем SimpleFocusListWalker с пустым списком
        self.listwalker = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.listwalker)
        
        content = urwid.LineBox(
            self.listbox,
            title='Statistics'
        )
        
        super().__init__(urwid.AttrMap(content, 'stat_panel'))
    
    def update(self, packets, packet_filter, packet_capture):
        """Обновить статистику с расширенной информацией"""
        # Счетчики протоколов
        proto_count = defaultdict(int)
        ipv4_addrs = set()
        ipv6_addrs = set()
        tcp_flags = defaultdict(int)
        
        for pkt in packets:
            proto = pkt['proto']
            
            if 'TCP' in proto:
                if '::' in str(pkt.get('src_ip', '')) or '::' in str(pkt.get('dst_ip', '')):
                    proto_count['TCPv6'] += 1
                else:
                    proto_count['TCPv4'] += 1
            elif 'UDP' in proto:
                if '::' in str(pkt.get('src_ip', '')) or '::' in str(pkt.get('dst_ip', '')):
                    proto_count['UDPv6'] += 1
                else:
                    proto_count['UDPv4'] += 1
            elif proto == 'ARP':
                proto_count['ARP'] += 1
            elif proto == 'ICMP':
                proto_count['ICMP'] += 1
            elif proto == 'ICMPv6':
                proto_count['ICMPv6'] += 1
            else:
                proto_count[proto] += 1
            
            src_ip = pkt.get('src_ip')
            dst_ip = pkt.get('dst_ip')
            
            if src_ip:
                if ':' in src_ip and '.' not in src_ip:
                    ipv6_addrs.add(src_ip)
                elif '.' in src_ip:
                    ipv4_addrs.add(src_ip)
            
            if dst_ip:
                if ':' in dst_ip and '.' not in dst_ip:
                    ipv6_addrs.add(dst_ip)
                elif '.' in dst_ip:
                    ipv4_addrs.add(dst_ip)
            
            if 'TCP' in proto:
                info = pkt.get('info', '')
                if 'RST' in info:
                    tcp_flags['RST'] += 1
                if 'SYN' in info:
                    tcp_flags['SYN'] += 1
                if 'FIN' in info:
                    tcp_flags['FIN'] += 1
                if 'PSH' in info:
                    tcp_flags['PSH'] += 1
        
        stats = packet_capture.get_statistics()
        top_ips = packet_filter.get_top_ips(packets, limit=10)
        top_talkers = packet_filter.get_top_talkers(packets, limit=10)
        
        bw_mbps = stats.get('bandwidth_mbps', 0)
        bw_kbps = (stats.get('bandwidth_bps', 0) / 1000)
        avg_latency = stats.get('avg_latency_us')
        latency_str = f"{avg_latency:.0f} μs" if avg_latency else "N/A"
        packet_loss = stats.get('packet_loss_count', 0)
        excluded_streams = packet_filter.get_exclude_count()
        excluded_protos = len(packet_filter.exclude_protocols)
        
        # ИСПРАВЛЕНИЕ: Создаем СПИСОК виджетов
        widgets = []
        
        # Protocol Stats - ВСЕГДА ПОКАЗЫВАЕМ ВСЕ
        widgets.append(urwid.AttrMap(urwid.Text('═══ Protocol Stats ═══'), 'stat_title'))
        widgets.append(urwid.AttrMap(urwid.Text(f"TCPv4:  {proto_count.get('TCPv4', 0)}"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"UDPv4:  {proto_count.get('UDPv4', 0)}"), 'stat_label'))
        
        if self.enable_ipv6_stats:
            widgets.append(urwid.AttrMap(urwid.Text(f"TCPv6:  {proto_count.get('TCPv6', 0)}"), 'stat_label'))
            widgets.append(urwid.AttrMap(urwid.Text(f"UDPv6:  {proto_count.get('UDPv6', 0)}"), 'stat_label'))
        
        widgets.append(urwid.AttrMap(urwid.Text(f"ARP:    {proto_count.get('ARP', 0)}"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"ICMP:   {proto_count.get('ICMP', 0)}"), 'stat_label'))
        
        if self.enable_ipv6_stats:
            widgets.append(urwid.AttrMap(urwid.Text(f"ICMPv6: {proto_count.get('ICMPv6', 0)}"), 'stat_label'))
        
        # Unique IPs - ВСЕГДА ПОКАЗЫВАЕМ
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ Unique IPs ═══'), 'stat_title'))
        widgets.append(urwid.AttrMap(urwid.Text(f"IPv4:   {len(ipv4_addrs)}"), 'stat_label'))
        
        if self.enable_ipv6_stats:
            widgets.append(urwid.AttrMap(urwid.Text(f"IPv6:   {len(ipv6_addrs)}"), 'stat_label'))
        
        # TCP Flags - ВСЕГДА ПОКАЗЫВАЕМ
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ TCP Flags ═══'), 'stat_title'))
        widgets.append(urwid.AttrMap(urwid.Text(f"SYN:    {tcp_flags.get('SYN', 0)}"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"FIN:    {tcp_flags.get('FIN', 0)}"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"RST:    {tcp_flags.get('RST', 0)}"), 'stat_rst'))
        widgets.append(urwid.AttrMap(urwid.Text(f"PSH:    {tcp_flags.get('PSH', 0)}"), 'stat_label'))
        
        # Performance
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ Performance ═══'), 'stat_title'))
        widgets.append(urwid.AttrMap(urwid.Text(f"BW:     {bw_mbps:.2f} Mbps"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"        {bw_kbps:.0f} KB/s"), 'stat_label'))
        widgets.append(urwid.AttrMap(urwid.Text(f"Latency:{latency_str}"), 'stat_label'))
        
        if packet_loss > 0:
            widgets.append(urwid.AttrMap(urwid.Text(f"Loss:   {packet_loss}"), 'stat_rst_value'))
        else:
            widgets.append(urwid.AttrMap(urwid.Text(f"Loss:   {packet_loss}"), 'stat_label'))
        
        # Excluded info
        if excluded_streams > 0 or excluded_protos > 0:
            widgets.append(urwid.Divider())
            widgets.append(urwid.AttrMap(urwid.Text('═══ Excluded ═══'), 'stat_title'))
            if excluded_streams > 0:
                widgets.append(urwid.AttrMap(urwid.Text(f"Streams: {excluded_streams}"), 'stat_rst'))
            if excluded_protos > 0:
                widgets.append(urwid.AttrMap(urwid.Text(f"Protocols: {excluded_protos}"), 'stat_rst'))
        
        # Top 10 IPs - ИСПРАВЛЕНО: одна строка
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ Top 10 IPs ═══'), 'stat_title'))
        
        if top_ips:
            for i, (ip, count) in enumerate(top_ips[:10], 1):
                ip_short = ip[:18] if len(ip) > 18 else ip
                # ОДНА СТРОКА: номер, IP и счетчик
                line = f"{i}. {ip_short:<18} {count} pkts"
                widgets.append(urwid.AttrMap(urwid.Text(line), 'stat_label'))
        else:
            widgets.append(urwid.AttrMap(urwid.Text("No data"), 'stat_value'))
        
        # Top Talkers - ИСПРАВЛЕНО: одна строка
        widgets.append(urwid.Divider())
        widgets.append(urwid.AttrMap(urwid.Text('═══ Top Talkers ═══'), 'stat_title'))
        
        if top_talkers:
            for i, (ip, bytes_count) in enumerate(top_talkers[:5], 1):
                ip_short = ip[:18] if len(ip) > 18 else ip
                kb = bytes_count / 1024
                # ОДНА СТРОКА: номер, IP и размер
                line = f"{i}. {ip_short:<18} {kb:.1f} KB"
                widgets.append(urwid.AttrMap(urwid.Text(line), 'stat_label'))
        else:
            widgets.append(urwid.AttrMap(urwid.Text("No data"), 'stat_value'))
        
        # КРИТИЧНО: Очищаем walker и добавляем все виджеты
        self.listwalker.clear()
        self.listwalker.extend(widgets)
    
class ExcludeManagerDialog(urwid.WidgetWrap):
    """Диалог управления исключениями"""
    
    def __init__(self, packet_filter, on_close_callback):
        """Диалог управления исключениями.

        Args:
            packet_filter: Экземпляр PacketFilter, содержащий exclude_streams/exclude_protocols.
            on_close_callback: callback() -> None. Закрыть диалог.
        """

        self.packet_filter = packet_filter
        self.on_close_callback = on_close_callback
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Excluded Streams & Protocols Manager\n')))
        widgets.append(urwid.Divider())
        
        exclude_stream_count = self.packet_filter.get_exclude_count()
        exclude_proto_count = len(packet_filter.exclude_protocols)
        
        if exclude_stream_count == 0 and exclude_proto_count == 0:
            widgets.append(urwid.Text('No exclusions\n'))
            widgets.append(urwid.Divider())
            widgets.append(urwid.Text('Press X on any packet to exclude'))
            widgets.append(urwid.Text('  - TCP/UDP packet → exclude stream'))
            widgets.append(urwid.Text('  - ARP/ICMP/etc  → exclude protocol'))
        else:
            # Excluded Protocols
            if exclude_proto_count > 0:
                widgets.append(urwid.Text([
                    ('info', f'Excluded Protocols: {exclude_proto_count}\n')
                ]))
                for proto in sorted(self.packet_filter.exclude_protocols):
                    widgets.append(urwid.Text(f"  • {proto}"))
                widgets.append(urwid.Divider())
            
            # Excluded Streams
            if exclude_stream_count > 0:
                widgets.append(urwid.Text([
                    ('info', f'Excluded Streams: {exclude_stream_count}\n')
                ]))
                
                for i, excl in enumerate(self.packet_filter.exclude_streams, 1):
                    stream_text = (
                        f"{i:2}. {excl['proto']:<4} "
                        f"{excl['src_ip']}:{excl['src_port']} ↔ "
                        f"{excl['dst_ip']}:{excl['dst_port']}"
                    )
                    widgets.append(urwid.Text(stream_text))
        
        widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Clear All', on_press=self._on_clear_all),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Close', on_press=self._on_close),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('ESC/ENTER: close'))
        
        listwalker = urwid.SimpleFocusListWalker(widgets)
        listbox = urwid.ListBox(listwalker)
        content = urwid.LineBox(listbox, title='Exclude Manager')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key in ('esc', 'enter'):
            self._on_close(None)
            return None
        return super().keypress(size, key)
    
    def _on_clear_all(self, button):
        self.packet_filter.clear_exclude_streams()
        self.packet_filter.clear_exclude_protocols()
        self._on_close(None)
    
    def _on_close(self, button):
        if self.on_close_callback:
            self.on_close_callback()


class PayloadSearchDialog(urwid.WidgetWrap):
    """Диалог поиска по payload"""
    
    def __init__(self, on_search_callback, on_cancel_callback):
        """Диалог поиска по payload.

        Args:
            on_search_callback: callback(search_string: str, case_sensitive: bool) -> None.
            on_cancel_callback: callback() -> None.
        """

        self.on_search_callback = on_search_callback
        self.on_cancel_callback = on_cancel_callback
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Payload Search\n')))
        widgets.append(urwid.Divider())
        
        widgets.append(urwid.Text('Search string (supports regex):'))
        self.search_edit = urwid.Edit(edit_text='')
        widgets.append(urwid.AttrMap(self.search_edit, 'edit', 'edit_focus'))
        widgets.append(urwid.Divider())
        
        self.case_sensitive = urwid.CheckBox('Case sensitive')
        widgets.append(urwid.AttrMap(self.case_sensitive, 'radio', 'radio_focus'))
        widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Search', on_press=self._on_search),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Cancel', on_press=self._on_cancel),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('ENTER: search | ESC: cancel'))
        
        pile = urwid.Pile(widgets)
        filler = urwid.Filler(pile, valign='top')
        content = urwid.LineBox(filler, title='Payload Search')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key == 'enter':
            self._on_search(None)
            return None
        elif key == 'esc':
            self._on_cancel(None)
            return None
        return super().keypress(size, key)
    
    def _on_search(self, button):
        search_string = self.search_edit.get_edit_text().strip()
        case_sensitive = self.case_sensitive.get_state()
        
        if self.on_search_callback and search_string:
            self.on_search_callback(search_string, case_sensitive)
    
    def _on_cancel(self, button):
        if self.on_cancel_callback:
            self.on_cancel_callback()


class BpfFilterDialog(urwid.WidgetWrap):
    """Диалог настройки BPF capture filter (фильтр на уровне захвата).

    BPF применяется ДО попадания пакетов в программу и экономит CPU/память.
    """

    def __init__(self, current_bpf, on_apply, on_cancel):
        """Создать диалог BPF.

        Args:
            current_bpf: Текущая строка BPF (str|None).
            on_apply: callback(bpf_text: str) -> None. Применить BPF (пустая строка = очистить).
            on_cancel: callback() -> None. Закрыть диалог без изменений.
        """

        self.on_apply = on_apply
        self.on_cancel = on_cancel

        cur = (current_bpf or "")
        self.edit = urwid.Edit(("edit", "Capture BPF: "), edit_text=cur)

        hint = urwid.Text(
            "Enter = Apply | Esc = Cancel\n"
            "Examples: tcp port 443 | udp port 53 | host 192.168.1.10\n"
            "Empty = no BPF (capture everything)",
            align='left'
        )

        btn_apply = urwid.Button("Apply", on_press=lambda b: self._apply())
        btn_clear = urwid.Button("Clear", on_press=lambda b: self._clear_and_apply())
        btn_cancel = urwid.Button("Cancel", on_press=lambda b: self.on_cancel())

        buttons = urwid.Columns([btn_apply, btn_clear, btn_cancel], dividechars=2)

        self.body = urwid.Pile([
            urwid.Text(("dialog_title", "Set Capture Filter (BPF)")),
            urwid.Divider(),
            self.edit,
            urwid.Divider(),
            hint,
            urwid.Divider(),
            buttons
        ])

        box = urwid.LineBox(urwid.Padding(self.body, left=1, right=1), title="BPF", title_attr='dialog_title')
        super().__init__(urwid.AttrMap(box, "dialog"))

    def selectable(self):
        return True

    def keypress(self, size, key):
        # Esc всегда закрывает
        if key == "esc":
            self.on_cancel()
            return None

        # Enter: Apply ТОЛЬКО если фокус на поле ввода
        if key == "enter":
            focus_w = self.body.get_focus()
            if focus_w is self.edit:
                self._apply()
                return None
            # иначе (кнопки/прочее) — отдать обработку кнопкам
            return super().keypress(size, key)

        return super().keypress(size, key)

    def _apply(self):
        self.on_apply(self.edit.edit_text)

    def _clear(self):
        self.edit.set_edit_text("")
        self.edit.set_edit_pos(0)

    def _clear_and_apply(self):
        self._clear()
        self._apply()


class FieldValuePickerDialog(urwid.WidgetWrap):
    """
    Показывает список уникальных значений поля из packets: value (count)
    Enter -> выбрать, Esc -> закрыть
    """
    def __init__(self, field, packets, on_select, on_cancel):
        """Создать диалог выбора значения поля из уже захваченных пакетов.

        Диалог строит список уникальных значений для указанного поля и показывает
        их в формате "value (count)". Enter — выбрать значение, Esc — закрыть.

        Args:
            field: Имя поля пакета, для которого собираются уникальные значения
                (например: "src_ip", "dst_ip", "proto", "src_port", "dst_port", "interface", "any_ip", "any_port").
            packets: Список пакетов (list[dict]) из которых собираются значения.
                Обычно это либо все захваченные пакеты, либо уже отфильтрованные.
            on_select: callback(value: str) -> None. Вызывается при выборе значения (Enter).
            on_cancel: callback() -> None. Вызывается при закрытии диалога (Esc/Cancel).
        """

        self.field = field
        self.on_select = on_select
        self.on_cancel = on_cancel

        self.search = urwid.Edit(("edit", "Search: "), edit_text="")
        self.search = urwid.AttrMap(self.search, "edit", "edit_focus")

        self._all_items = self._build_items(field, packets)  # list of (value_str, count)
        self._filtered_items = list(self._all_items)

        self.listwalker = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.listwalker)

        self._render_list()

        header = urwid.Text(("dialog_title", f"Select value for: {field}"))
        footer = urwid.Text("↑/↓ navigate | Enter select | Esc close")

        self.pile = urwid.Pile([
            ('pack', header),
            ('pack', urwid.Divider()),
            ('pack', self.search),
            ('pack', urwid.Divider()),
            ('weight', 1, urwid.LineBox(self.listbox)),
            ('pack', urwid.Divider()),
            ('pack', footer),
        ])

        # фокус на область списка (это 4-й элемент pile: LineBox(listbox))
        self.pile.focus_position = 4

        # и внутри списка — на первую строку
        if len(self.listwalker) > 0:
            self.listbox.focus_position = 0

        box = urwid.LineBox(self.pile, title="Values", title_attr="dialog_title")

        super().__init__(urwid.AttrMap(box, "dialog"))

    def _build_items(self, field, packets):
        c = Counter()

        if field == "any_ip":
            for p in packets:
                for k in ("src_ip", "dst_ip"):
                    v = p.get(k)
                    if v is None:
                        continue
                    s = str(v).strip()
                    if s:
                        c[s] += 1

        elif field == "any_port":
            for p in packets:
                for k in ("src_port", "dst_port"):
                    v = p.get(k)
                    if v is None:
                        continue
                    s = str(v).strip()
                    if s:
                        c[s] += 1

        else:
            for p in packets:
                v = p.get(field)
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                c[s] += 1

        items = sorted(c.items(), key=lambda x: (-x[1], x[0]))
        return items[:400]

    def _render_list(self):
        self.listwalker.clear()
        if not self._filtered_items:
            self.listwalker.append(urwid.Text("No values"))
            return

        for val, cnt in self._filtered_items:
            txt = f"{val}  ({cnt})"
            item = urwid.SelectableIcon(txt, cursor_position=0)
            self.listwalker.append(urwid.AttrMap(item, "default", "selected"))

    def selectable(self):
        return True

    def keypress(self, size, key):
        # Esc
        if key == "esc":
            self.on_cancel()
            return None
        if key == "tab":
            # 2 = Search, 4 = List
            if getattr(self, "pile", None):
                self.pile.focus_position = 4 if self.pile.focus_position != 4 else 2
            return None

        # Enter: если фокус на списке — выбрать
        if key == "enter":
            focus_widget = self.listwalker.get_focus()
            # В urwid может возвращать widget или (widget,pos). Поймаем оба
            if isinstance(focus_widget, tuple):
                w = focus_widget[0]
            else:
                w = focus_widget

            if isinstance(w, urwid.AttrMap):
                text = w.base_widget.get_text()[0]
                # text выглядит как: "VALUE  (COUNT)"
                val = text.rsplit("  (", 1)[0]
                self.on_select(val)
                return None

        # Обработка поиска: если меняем search -> фильтруем
        if key in ("backspace",) or (len(key) == 1 and not key.startswith("shift")):
            # Сначала дать отработать edit
            res = super().keypress(size, key)
            # Потом обновить фильтрацию
            self._apply_search_filter()
            return res

        return super().keypress(size, key)

    def _apply_search_filter(self):
        q = self.search.base_widget.edit_text.strip().lower()
        if not q:
            self._filtered_items = list(self._all_items)
        else:
            self._filtered_items = [(v, c) for (v, c) in self._all_items if q in v.lower()]
        self._render_list()


class FilterDialog(urwid.WidgetWrap):
    """Диалог для настройки фильтров"""
    
    def __init__(self, packet_filter, on_apply_callback, on_cancel_callback, on_open_picker=None):
        """Диалог настройки фильтров отображения.

        Args:
            packet_filter: Экземпляр PacketFilter (куда будут записаны значения фильтров).
            on_apply_callback: callback() -> None. Вызывается после применения фильтров.
            on_cancel_callback: callback() -> None. Закрыть диалог без применения.
        """

        self.packet_filter = packet_filter
        self.on_apply_callback = on_apply_callback
        self.on_cancel_callback = on_cancel_callback
        self.on_open_picker = on_open_picker

        self.filter_fields = {}
        
        filter_labels = {
            'proto': 'Protocol (TCP, UDP, DNS, etc.):',
            'any_ip': 'Any IP (src OR dst):',
            'any_port': 'Any Port (src_port OR dst_port):',
            'src_ip': 'Source IP Address:',
            'dst_ip': 'Destination IP Address:',
            'src_port': 'Source Port:',
            'dst_port': 'Destination Port:',
            'interface': 'Network Interface (eth0, wlan0, etc.):',
            'info': 'Info (regex supported):',
            'payload': 'Payload Search (regex):',
        }
        
        current_filters = self.packet_filter.get_active_filters()
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Packet Filter Configuration\n')))
        widgets.append(urwid.Divider())
        
        for field, label in filter_labels.items():
            widgets.append(urwid.Text(label))
            edit = urwid.Edit(edit_text=current_filters.get(field, ''))
            self.filter_fields[field] = edit
            widgets.append(urwid.AttrMap(edit, 'edit', 'edit_focus'))
            widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Apply', on_press=self._on_apply),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Clear All', on_press=self._on_clear),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Cancel', on_press=self._on_cancel),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('TAB: navigate | ENTER: apply | L: values | ESC: cancel'))

        self.listwalker = urwid.SimpleFocusListWalker(widgets)
        listbox = urwid.ListBox(self.listwalker)
        content = urwid.LineBox(listbox, title='Filter Settings')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))

    def keypress(self, size, key):
        if key == 'enter':
            try:
                focus_widget, _ = self.listwalker.get_focus()
                if isinstance(focus_widget, urwid.AttrMap):
                    base = focus_widget.base_widget
                    if isinstance(base, urwid.Edit):
                        self._on_apply(None)
                        return None
            except:
                pass
        elif key in ('L', 'l'):
            # определить, какое поле сейчас в фокусе
            try:
                focus = self.listwalker.get_focus()
                w = focus[0] if isinstance(focus, tuple) else focus

                if isinstance(w, urwid.AttrMap) and isinstance(w.base_widget, urwid.Edit):
                    field = self._field_for_edit(w.base_widget)
                    if field and self.on_open_picker:
                        self.on_open_picker(field, None)
                        return None
            except:
                pass

        elif key == 'esc':
            self._on_cancel(None)
            return None

        return super().keypress(size, key)

    def _on_apply(self, button):
        for field, edit_widget in self.filter_fields.items():
            value = edit_widget.get_edit_text().strip()
            self.packet_filter.set_filter(field, value)
        
        if self.on_apply_callback:
            self.on_apply_callback()
    
    def _on_clear(self, button):
        self.packet_filter.clear_filter()
        for edit_widget in self.filter_fields.values():
            edit_widget.set_edit_text('')
    
    def _on_cancel(self, button):
        if self.on_cancel_callback:
            self.on_cancel_callback()

    def _field_for_edit(self, edit_widget):
        for field, ew in self.filter_fields.items():
            if ew is edit_widget:
                return field
        return None

    def _on_value_picked(self, value):
        """
        Вызывается picker'ом. Подставляем значение в текущее поле и возвращаемся к фильтрам.
        """
        # вернём overlay обратно на текущий FilterDialog:
        # это делается на уровне MainApplication.show_overlay -> он просто перерисует overlay
        # но нам нужно закрыть picker и открыть обратно filter dialog.
        # Проще: пусть MainApplication.on_select сам откроет FilterDialog заново.
        # Поэтому: этот метод будет переопределён callback'ом в MainApplication.
        pass


class ConfirmDialog(urwid.WidgetWrap):
    """Диалог подтверждения"""
    
    def __init__(self, message, on_yes_callback, on_no_callback):
        """Диалог подтверждения действия.

        Args:
            message: Текст сообщения.
            on_yes_callback: callback() -> None. Подтвердить.
            on_no_callback: callback() -> None. Отменить/закрыть.
        """

        self.on_yes_callback = on_yes_callback
        self.on_no_callback = on_no_callback
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Confirmation\n')))
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text(message))
        widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Yes', on_press=self._on_yes),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('No', on_press=self._on_no),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('Y: Yes | N/ESC: No'))
        
        pile = urwid.Pile(widgets)
        filler = urwid.Filler(pile, valign='top')
        content = urwid.LineBox(filler, title='Confirm')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key in ('y', 'Y'):
            self._on_yes(None)
            return None
        elif key in ('n', 'N', 'esc'):
            self._on_no(None)
            return None
        return super().keypress(size, key)
    
    def _on_yes(self, button):
        if self.on_yes_callback:
            self.on_yes_callback()
    
    def _on_no(self, button):
        if self.on_no_callback:
            self.on_no_callback()


class SaveDialog(urwid.WidgetWrap):
    """Диалог для сохранения пакетов"""
    
    def __init__(self, export_dialog, on_save_callback, on_cancel_callback):
        """Диалог сохранения/экспорта пакетов.

        Args:
            export_dialog: UI/логика экспорта (обычно PacketExportDialog).
            on_save_callback: callback(success: bool, filepath: str, message: str) -> None.
            on_cancel_callback: callback() -> None.
        """

        self.export_dialog = export_dialog
        self.on_save_callback = on_save_callback
        self.on_cancel_callback = on_cancel_callback
        
        widgets = []
        widgets.append(urwid.Text(('dialog_title', 'Save Captured Packets\n')))
        widgets.append(urwid.Divider())
        
        widgets.append(urwid.Text('Filename (leave empty for auto-generated):'))
        self.filename_edit = urwid.Edit(edit_text='')
        widgets.append(urwid.AttrMap(self.filename_edit, 'edit', 'edit_focus'))
        widgets.append(urwid.Divider())
        
        self.save_mode = []
        
        widgets.append(urwid.Text('Save mode:'))
        rb1 = urwid.RadioButton(self.save_mode, 'All captured packets', state=True)
        rb2 = urwid.RadioButton(self.save_mode, 'Only filtered packets')
        
        widgets.append(urwid.AttrMap(rb1, 'radio', 'radio_focus'))
        widgets.append(urwid.AttrMap(rb2, 'radio', 'radio_focus'))
        widgets.append(urwid.Divider())
        
        total_packets = len(self.export_dialog.packet_capture.get_packets())
        filtered_packets = len(self.export_dialog.packet_filter.filter_packets(
            self.export_dialog.packet_capture.get_packets()
        ))
        
        widgets.append(urwid.Text([
            ('info', f'Total packets: {total_packets}\n'),
            ('info', f'Filtered packets: {filtered_packets}\n'),
        ]))
        widgets.append(urwid.Divider())
        
        buttons = urwid.Columns([
            urwid.AttrMap(
                urwid.Button('Save', on_press=self._on_save),
                'button', 'button_focus'
            ),
            urwid.AttrMap(
                urwid.Button('Cancel', on_press=self._on_cancel),
                'button', 'button_focus'
            ),
        ])
        
        widgets.append(buttons)
        widgets.append(urwid.Divider())
        widgets.append(urwid.Text('TAB: navigate | ENTER: save | ESC: cancel'))
        
        listwalker = urwid.SimpleFocusListWalker(widgets)
        listbox = urwid.ListBox(listwalker)
        content = urwid.LineBox(listbox, title='Save Packets')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))
    
    def keypress(self, size, key):
        if key == 'esc':
            self._on_cancel(None)
            return None
        return super().keypress(size, key)
    
    def _on_save(self, button):
        filename = self.filename_edit.get_edit_text().strip()
        filename = filename if filename else None
        
        save_all = self.save_mode[0].get_state()
        
        if save_all:
            success, filepath, message = self.export_dialog.export_all_packets(filename)
        else:
            success, filepath, message = self.export_dialog.export_filtered_packets(filename)
        
        if self.on_save_callback:
            self.on_save_callback(success, filepath, message)
    
    def _on_cancel(self, button):
        if self.on_cancel_callback:
            self.on_cancel_callback()


class HelpDialog(urwid.WidgetWrap):
    """Диалог помощи"""
    
    def __init__(self, on_close_callback):
        """Окно справки по горячим клавишам и возможностям программы.

        Args:
            on_close_callback: callback() -> None. Закрыть окно помощи.
        """

        self.on_close_callback = on_close_callback

        help_text = [
            ('help_title', 'Packet Monitor\n\n'),

            ('help_section', 'Navigation:\n'),
            '  ↑/↓            - Navigate list\n',
            '  Page Up/Down    - Scroll faster\n',
            '  Home/End        - Jump to start/end\n\n',

            ('help_section', 'Packet List:\n'),
            '  ENTER          - View packet details\n',
            '  A              - Toggle auto-scroll\n',
            '  C              - Clear captured packets\n',
            '  P              - Pause/Resume capture (live)\n',
            '  F              - Open filter dialog\n',
            '  /              - Payload search\n',
            '  S              - Save/export packets\n\n',

            ('help_section', 'Flows / Conversations:\n'),
            '  G              - Toggle Flows view\n',
            '  ENTER (on flow) - Drill down (apply flow filter -> packets)\n',
            '  D (on flow)     - Flow details\n',
            '  X (on flow)     - Exclude flow\n',
            '  T (on flow)     - Follow stream / open TCP Stream view\n',
            '  V (on flow)     - Toggle flow source: filtered vs all packets\n',
            '  B / K / R       - Sort flows: bytes / packets / rate (if enabled)\n\n',

            ('help_section', 'Follow Stream:\n'),
            '  T              - Follow stream\n',
            '                   TCP: open reassembled stream (SEQ-based)\n',
            '                   UDP: apply stream filter (if enabled)\n',
            '  In stream view: Export text/raw, Close\n\n',

            ('help_section', 'Exclude & Manage:\n'),
            '  X              - Exclude stream (TCP/UDP) or protocol\n',
            '  E              - Manage exclusions\n\n',

            ('help_section', 'Profiles:\n'),
            '  O              - Profiles: Save/Load/Delete\n',
            '                   Presets: dns-only, syn-only, arp-only\n\n',

            ('help_section', 'General:\n'),
            '  H / F1         - Show this help\n',
            '  Q              - Quit (with confirmation)\n',
            '  Ctrl-C         - Quit (with confirmation)\n\n',

            ('help_note', 'Press ESC to close'),
        ]

        text_widget = urwid.Text(help_text)
        filler = urwid.Filler(text_widget, valign='top')
        content = urwid.LineBox(filler, title='Help')
        
        super().__init__(urwid.AttrMap(content, 'dialog'))

    def selectable(self):
        # AttrMap/LineBox/Filler обычно не selectable, поэтому без этого
        # обработчик keypress() может вообще не вызываться.
        return True

    def keypress(self, size, key):
        # Закрываем help-окно ТОЛЬКО по ESC и глушим остальные клавиши,
        # чтобы они не "пробивались" в основной интерфейс.
        if key == 'esc':
            if self.on_close_callback:
                self.on_close_callback()
            return None
        return None


class PacketListBox(urwid.WidgetWrap):
    """Виджет для отображения списка пакетов"""
    
    def __init__(self, packet_capture, packet_filter):
        """Левая панель со списком пакетов (таблица).

        Args:
            packet_capture: Источник пакетов (PacketCapture).
            packet_filter: Фильтры отображения (PacketFilter).
        """

        self.packet_capture = packet_capture
        self.packet_filter = packet_filter
        self.packet_widgets = []
        self.auto_scroll = True
        self.wide_info = False  # False=short, True=long

        self.header = self._create_header()
        self.packet_list = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.packet_list)
        
        self.frame = urwid.Frame(
            body=self.listbox,
            header=self.header
        )
        
        super().__init__(self.frame)

    def _create_header(self):
        header_text = f"{'No':<5}{'Time':<12} {'Iface':<8}{'Proto':<8}{'Src IP':<16}{'Dst IP':<16}{'SPort':<6}{'DPort':<6}{'Info'}"
        return urwid.AttrMap(urwid.Text(header_text, wrap='clip'), 'header')

    def toggle_wide_info(self):
        self.wide_info = not self.wide_info
        self.update_packets(force_rebuild=True)

    def _flow_key_from_agg(self, f):
        # тот же формат, что в _canon_flow_key()
        return (f["proto"], f["a_ip"], int(f["a_port"]), f["b_ip"], int(f["b_port"]))

    def _format_packet_line(self, pkt):
        """Форматировать строку пакета с выделением RST и packet loss"""
        time_str = pkt['timestamp'].strftime('%H:%M:%S.%f')[:-3]
        
        iface = safe_str(pkt.get('interface'), 'N/A')[:7]
        src_ip = safe_str(pkt['src_ip'] if pkt['src_ip'] else pkt.get('src', '')[:15], '')[:15]
        dst_ip = safe_str(pkt['dst_ip'] if pkt['dst_ip'] else pkt.get('dst', '')[:15], '')[:15]
        src_port = str(pkt['src_port']) if pkt['src_port'] else ''
        dst_port = str(pkt['dst_port']) if pkt['dst_port'] else ''

        # Обрезаем info и убираем переводы строк
        if getattr(self, "wide_info", False):
            info_src = pkt.get("info_long") or pkt.get("info") or ""
        else:
            info_src = pkt.get("info_short") or pkt.get("info") or ""

        # info = str(info_src).replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        info = sanitize_tui_text(pkt.get('info', ''))

        max_info_len = 120 if getattr(self, "wide_info", False) else 60

        if len(info) > max_info_len:
            info = info[:max_info_len-3] + '...'
        
        if pkt.get('packet_loss'):
            info = f"[LOSS] {info}"
        
        # Определяем цвет
        if pkt.get("tcp_rst") or pkt.get('packet_loss'):
            color = 'rst'

        else:
            proto_colors = {
                'TCP': 'tcp', 'TCPv6': 'tcp', 'UDP': 'udp', 'UDPv6': 'udp',
                'ICMP': 'icmp', 'ICMPv6': 'icmp', 'ARP': 'arp',
                'DNS': 'dns', 'HTTP': 'http', 'ETHER': 'ether',
            }
            color = proto_colors.get(pkt['proto'], 'default')
        
        # Формируем ОДНУ строку
        line = f"{pkt['num']:<5}{time_str:<12} {iface:<8}{pkt['proto']:<8}{src_ip:<16}{dst_ip:<16}{src_port:<6}{dst_port:<6}{info}"
        
        # Создаем SelectableText с wrap='clip' и оборачиваем в AttrMap
        text_widget = SelectableText(line, wrap='clip')
        wrapped = urwid.AttrMap(text_widget, color, focus_map='selected')
        wrapped.packet_data = pkt
        return wrapped

    
    def toggle_auto_scroll(self):
        """Переключить автоскролл"""
        self.auto_scroll = not self.auto_scroll
        return self.auto_scroll

    def update_packets(self, force_rebuild=False):
        """Обновить список пакетов"""
        all_packets = self.packet_capture.get_packets()
        filtered_packets = self.packet_filter.filter_packets(all_packets)

        current_count = len(self.packet_list)
        new_count = len(filtered_packets)

        # запомним фокус
        try:
            focus_pos = self.listbox.get_focus()[1]
            if focus_pos is None:
                focus_pos = 0
        except Exception:
            focus_pos = 0

        # При force_rebuild — пересобираем все строки
        if force_rebuild:
            self.packet_list.clear()
            for pkt in filtered_packets:
                self.packet_list.append(self._format_packet_line(pkt))

            if len(self.packet_list) > 0:
                if self.auto_scroll:
                    self.listbox.set_focus(len(self.packet_list) - 1)
                else:
                    self.listbox.set_focus(min(focus_pos, len(self.packet_list) - 1))
            return

        # Старое поведение (инкрементально)
        if new_count < current_count:
            self.packet_list.clear()
            for pkt in filtered_packets:
                self.packet_list.append(self._format_packet_line(pkt))

            if len(self.packet_list) > 0:
                if self.auto_scroll:
                    self.listbox.set_focus(len(self.packet_list) - 1)
                else:
                    self.listbox.set_focus(min(focus_pos, len(self.packet_list) - 1))

        elif new_count > current_count:
            for pkt in filtered_packets[current_count:]:
                self.packet_list.append(self._format_packet_line(pkt))

            if len(self.packet_list) > 0 and self.auto_scroll:
                self.listbox.set_focus(len(self.packet_list) - 1)

    def get_selected_packet(self):
        """Получить выбранный пакет"""
        if len(self.packet_list) > 0:
            focus_widget, _ = self.listbox.get_focus()
            if hasattr(focus_widget, 'packet_data'):
                return focus_widget.packet_data
        return None
    
    def clear(self):
        """Очистить список"""
        self.packet_list.clear()


class FlowListBox(urwid.WidgetWrap):
    """Виджет для отображения таблицы flows/conversations"""

    def __init__(self, packet_capture, packet_filter):
        """Левая панель со списком flow/conversations (агрегация по 5-tuple).

        Args:
            packet_capture: Источник пакетов (PacketCapture).
            packet_filter: Фильтры отображения (PacketFilter).
        """

        self.packet_capture = packet_capture
        self.packet_filter = packet_filter

        self.header = self._create_header()
        self.flow_list = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.flow_list)

        self.sort_mode = "bytes"  # bytes | pkts | rate

        self.use_all_packets = False  # False = по текущему фильтру, True = по всем пакетам

        self.frame = urwid.Frame(body=self.listbox, header=self.header)
        super().__init__(self.frame)

        # Кэш, чтобы не пересчитывать всё без надобности
        self._last_seen_packet_num = 0
        self._cache = {}  # flow_key -> agg dict

    def toggle_source(self):
        self.use_all_packets = not self.use_all_packets
        self.reset_cache()
        # обновим заголовок, если он показывает режим
        try:
            self.frame.header = self._create_header()
        except:
            pass

    def _create_header(self):
        header_text = (
            f"{'Proto':<6} "
            f"{'Endpoint A':<28} {'Endpoint B':<28} "
            f"{'Pkts':>6} {'A->B':>10} {'B->A':>10} {'Total':>10} "
            f"{'First':<12} {'Last':<12} {'State':<5} {'TCP':<12}"
        )

        return urwid.AttrMap(urwid.Text(header_text, wrap='clip'), 'header')

    @staticmethod
    def _truncate(s: str, width: int) -> str:
        """Обрезает строку до width, добавляя многоточие, если нужно."""
        s = "" if s is None else str(s)
        if width <= 0:
            return ""
        if len(s) <= width:
            return s
        if width <= 1:
            return s[:width]
        return s[:width - 1] + "…"

    @staticmethod
    def _base_proto(pkt_proto: str) -> str:
        p = (pkt_proto or "").upper()
        if "TCP" in p:
            return "TCP"
        if "UDP" in p:
            return "UDP"
        return p

    @staticmethod
    def _is_ip_packet(pkt) -> bool:
        return bool(pkt.get("src_ip")) and bool(pkt.get("dst_ip"))

    @staticmethod
    def _has_ports(pkt) -> bool:
        return pkt.get("src_port") is not None and pkt.get("dst_port") is not None

    @staticmethod
    def _canon_endpoint(ip: str, port) -> str:
        if port is None or port == "":
            return f"{ip}"
        return f"{ip}:{port}"

    @staticmethod
    def _canon_flow_key(proto: str, src_ip: str, src_port, dst_ip: str, dst_port):
        """
        Bidirectional canonical key: (proto, ep_low, ep_high)
        """
        a = (str(src_ip), int(src_port))
        b = (str(dst_ip), int(dst_port))
        ep1, ep2 = (a, b) if a <= b else (b, a)
        return (proto, ep1[0], ep1[1], ep2[0], ep2[1])

    @staticmethod
    def _tcp_flag_counters_from_info(info: str):
        # info у вас выглядит как: "Len= ... [SYN, ACK] Seq=..."
        # Для MVP достаточно простых contains
        info_u = (info or "").upper()
        return {
            "syn": 1 if "SYN" in info_u else 0,
            "fin": 1 if "FIN" in info_u else 0,
            "rst": 1 if "RST" in info_u else 0,
        }

    def get_selected_flow_key(self):
        flow = self.get_selected_flow()
        if not flow:
            return None
        return self._canon_flow_key(flow["proto"], flow["a_ip"], flow["a_port"], flow["b_ip"], flow["b_port"])

    def packets_for_flow_key(self, packets, flow_key):
        # packets: список пакетов, из которого выбираем
        if not flow_key:
            return []
        proto, a_ip, a_port, b_ip, b_port = flow_key
        out = []
        for p in packets:
            if self._base_proto(p.get("proto")) != proto:
                continue
            if not self._is_ip_packet(p) or not self._has_ports(p):
                continue
            try:
                key = self._canon_flow_key(proto, p["src_ip"], p["src_port"], p["dst_ip"], p["dst_port"])
            except Exception:
                continue
            if key == flow_key:
                out.append(p)
        return out

    def update_flows_from(self, displayed_packets):
        """
        Обновить flows view на основании переданного набора пакетов.

        Это “точка входа” из MainApplication.refresh_display().
        Принимает уже выбранный источник пакетов:
          - либо filtered (по текущим фильтрам),
          - либо all_packets (если включён режим "ALL").

        Делает:
          1) обновление заголовка таблицы (колонки/режим);
          2) инкрементальное обновление кэша агрегации flows (_update_cache);
          3) перерисовку списка flows (_render).

        Args:
            displayed_packets: Список packet_info (list[dict]), который считается источником агрегации flows.
    """

        try:
            self.frame.header = self._create_header()
        except:
            pass

        self._update_cache(displayed_packets)
        self._render()

    def _update_cache(self, packets):
        """
        Инкрементально обновляем кэш flows по номеру пакета.
        В offline режиме номера тоже есть (num), поэтому работает одинаково.
        """
        # packets сюда лучше передавать уже ОТОБРАННЫЕ (как отображаемые), см. update_flows()
        # Если фильтр поменялся — проще сбросить кэш целиком.
        # (Мы сбросим кэш при любом изменении summary строкой — см. MainApplication ниже)
        for pkt in packets:
            num = pkt.get("num", 0)
            if num <= self._last_seen_packet_num:
                continue

            if not self._is_ip_packet(pkt):
                continue

            proto = self._base_proto(pkt.get("proto"))
            if proto not in ("TCP", "UDP"):
                continue

            if not self._has_ports(pkt):
                continue

            src_ip, dst_ip = pkt.get("src_ip"), pkt.get("dst_ip")
            src_port, dst_port = pkt.get("src_port"), pkt.get("dst_port")
            if not all([src_ip, dst_ip]):
                continue

            try:
                key = self._canon_flow_key(proto, src_ip, src_port, dst_ip, dst_port)
            except Exception:
                continue

            agg = self._cache.get(key)
            if agg is None:
                agg = {
                    "proto": proto,
                    "a_ip": key[1], "a_port": key[2],
                    "b_ip": key[3], "b_port": key[4],
                    "pkts": 0,
                    "bytes": 0,
                    "bytes_ab": 0,  # A -> B
                    "bytes_ba": 0,  # B -> A
                    "first_ts": pkt["timestamp"],
                    "last_ts": pkt["timestamp"],
                    "tcp_syn": 0,
                    "tcp_fin": 0,
                    "tcp_rst": 0,
                }
                self._cache[key] = agg

            agg["pkts"] += 1
            size = int(pkt.get("size", 0) or 0)
            agg["bytes"] += size

            # направление относительно канонических endpoint'ов A/B
            # если исходник совпадает с A, считаем A->B, иначе B->A
            if str(pkt.get("src_ip")) == str(agg["a_ip"]) and int(pkt.get("src_port")) == int(agg["a_port"]):
                agg["bytes_ab"] += size
            else:
                agg["bytes_ba"] += size

            ts = pkt["timestamp"]
            if ts < agg["first_ts"]:
                agg["first_ts"] = ts
            if ts > agg["last_ts"]:
                agg["last_ts"] = ts

            if proto == "TCP":
                agg["tcp_syn"] += 1 if pkt.get("tcp_syn") else 0
                agg["tcp_fin"] += 1 if pkt.get("tcp_fin") else 0
                agg["tcp_rst"] += 1 if pkt.get("tcp_rst") else 0

            self._last_seen_packet_num = max(self._last_seen_packet_num, num)

    def reset_cache(self):
        self._cache = {}
        self._last_seen_packet_num = 0

    def _render(self):
        # --- 1) Сохраняем текущий фокус: сначала пытаемся по flow_key, иначе по позиции ---
        prev_key = None
        prev_pos = 0

        try:
            prev_pos = self.listbox.focus_position
        except:
            prev_pos = 0

        try:
            fw, _ = self.listbox.get_focus()
            fdata = None
            if fw is not None:
                if hasattr(fw, "flow_data"):
                    fdata = fw.flow_data
                elif hasattr(fw, "original_widget") and hasattr(fw.original_widget, "flow_data"):
                    fdata = fw.original_widget.flow_data

            if fdata:
                prev_key = (fdata["proto"], fdata["a_ip"], int(fdata["a_port"]), fdata["b_ip"], int(fdata["b_port"]))
        except:
            prev_key = None

        # --- 2) Готовим отсортированный список ---
        # flows = sorted(
        #     self._cache.values(),
        #     key=lambda x: (x.get("bytes", 0), x.get("pkts", 0)),
        #     reverse=True
        # )

        def _rate(f):
            try:
                dt = (f["last_ts"] - f["first_ts"]).total_seconds()
                if dt <= 0:
                    return 0.0
                return float(f.get("bytes", 0)) / dt
            except Exception:
                return 0.0

        if self.sort_mode == "pkts":
            flows = sorted(self._cache.values(), key=lambda x: (x.get("pkts", 0), x.get("bytes", 0)), reverse=True)
        elif self.sort_mode == "rate":
            flows = sorted(self._cache.values(), key=lambda x: (_rate(x), x.get("bytes", 0)), reverse=True)
        else:
            flows = sorted(self._cache.values(), key=lambda x: (x.get("bytes", 0), x.get("pkts", 0)), reverse=True)

        # --- 3) Пересоздаём список и ищем индекс предыдущего выделенного flow ---
        self.flow_list.clear()
        focus_index = None

        for idx, f in enumerate(flows):
            a = self._truncate(self._canon_endpoint(f["a_ip"], f["a_port"]), 28)
            b = self._truncate(self._canon_endpoint(f["b_ip"], f["b_port"]), 28)

            first = f["first_ts"].strftime("%H:%M:%S.%f")[:-3]
            last = f["last_ts"].strftime("%H:%M:%S.%f")[:-3]

            tcp = ""
            if f["proto"] == "TCP":
                tcp = f"S:{f.get('tcp_syn', 0)} F:{f.get('tcp_fin', 0)} R:{f.get('tcp_rst', 0)}"

            state = "-"
            if f["proto"] == "TCP":
                if f.get("tcp_rst", 0) > 0:
                    state = "RST"
                elif f.get("tcp_fin", 0) > 0:
                    state = "FIN"
                elif f.get("tcp_syn", 0) > 0:
                    state = "SYN"
                else:
                    state = "-"
            line = (
                f"{f['proto']:<6} "
                f"{a:<28} {b:<28} "
                f"{f.get('pkts', 0):>6} {f.get('bytes_ab', 0):>10} {f.get('bytes_ba', 0):>10} {f.get('bytes', 0):>10} "
                f"{first:<12} {last:<12} {state:<5} {tcp:<12}"
            )

            # line = (
            #     f"{f['proto']:<6} "
            #     f"{a:<28} {b:<28} "
            #     f"{f.get('pkts', 0):>6} "
            #     f"{f.get('bytes_ab', 0):>10} {f.get('bytes_ba', 0):>10} {f.get('bytes', 0):>10} "
            #     f"{first:<12} {last:<12} {tcp:<12}"
            # )

            txt = SelectableText(line, wrap='clip')
            row = urwid.AttrMap(txt, 'default', focus_map='selected')

            # flow_data на оба уровня
            row.flow_data = f
            txt.flow_data = f

            self.flow_list.append(row)

            if prev_key is not None:
                cur_key = (f["proto"], f["a_ip"], int(f["a_port"]), f["b_ip"], int(f["b_port"]))
                if cur_key == prev_key:
                    focus_index = idx

        # --- 4) Восстанавливаем фокус ---
        if len(self.flow_list) > 0:
            try:
                if focus_index is not None:
                    self.listbox.set_focus(focus_index)
                else:
                    # если не нашли предыдущий flow (изменился список) — вернёмся на прежнюю позицию
                    self.listbox.set_focus(min(prev_pos, len(self.flow_list) - 1))
            except:
                pass

    def update_flows(self):
        """
        Обновить таблицу flows на основе текущего display set:
        берём packets -> применяем packet_filter -> агрегируем
        """
        all_packets = self.packet_capture.get_packets()
        displayed = self.packet_filter.filter_packets(all_packets)

        self._update_cache(displayed)
        self._render()

    def get_selected_flow(self):
        if len(self.flow_list) == 0:
            return None

        w, _ = self.listbox.get_focus()
        if w is None:
            return None

        # flow_data может быть либо на AttrMap, либо на original_widget
        if hasattr(w, "flow_data"):
            return w.flow_data
        if hasattr(w, "original_widget") and hasattr(w.original_widget, "flow_data"):
            return w.original_widget.flow_data

        return None


class StatusBar(urwid.WidgetWrap):
    """Статусная строка"""
    
    def __init__(self):
        """Статусная строка внизу: режим, интерфейс, счётчики, фильтры и хоткеи."""

        self.text = urwid.Text('')
        self.help_text = urwid.Text('')
        
        self.pile = urwid.Pile([
            urwid.AttrMap(self.text, 'status'),
            urwid.AttrMap(self.help_text, 'default')
        ])
        
        super().__init__(self.pile)
        self._update_help_text()

    def set_mode(self, showing_flows: bool):
        self._update_help_text(showing_flows=showing_flows)

    def _update_help_text(self, showing_flows=False):
        """Обновить подсказки"""
        help_content = [
            ('help', ' F1/H'),
            ('default', ':Help '),
            ('help', 'T'),
            ('default', ':Follow '),
            ('help', 'X'),
            ('default', ':Exclude '),
            ('help', 'E'),
            ('default', ':Manage '),
            ('help', 'F'),
            ('default', ':Filter '),
            ('help', '/'),
            ('default', ':Search '),
            ('help', 'A'),
            ('default', ':Auto '),
            ('help', 'S'),
            ('default', ':Save '),
            ('help', 'P'),
            ('default', ':Pause '),
            ('help', 'C'),
            ('default', ':Clear '),
            ('help', 'W'),
            ('default', ':WideInfo '),
        ]

        if showing_flows:
            help_content.extend([
                ('help', 'B'),
                ('default', ':Sort '),
            ])
        else:
            help_content.extend([
                ('help', 'B'),
                ('default', ':BPF '),
            ])

        help_content.extend([
            ('help', 'G'),
            ('default', ':Flows '),
            ('help', 'Q'),
            ('default', ':Quit '),
        ])

        self.help_text.set_text(help_content)

    def update(self, total_packets, filtered_packets, filter_summary, interface, capture_running,
                   offline_mode=False, auto_scroll=False, bpf_filter=None):

        """Обновить статус"""
        status_text = []
        
        if offline_mode:
            status_text.extend([
                ('status_label', 'Mode: '),
                ('status_value', 'OFFLINE  '),
            ])
        else:
            status_text.extend([
                ('status_label', 'Interface: '),
                ('status_value', f'{interface}  '),
                ('status_label', 'Status: '),
            ])
            
            if capture_running:
                status_text.append(('status_running', 'CAPTURING  '))
            else:
                status_text.append(('status_paused', 'PAUSED  '))
        
        status_text.extend([
            ('status_label', 'Total: '),
            ('status_value', f'{total_packets}  '),
            ('status_label', 'Displayed: '),
            ('status_value', f'{filtered_packets}  '),
            ('status_label', 'AutoScroll: '),
        ])
        
        if auto_scroll:
            status_text.append(('status_running', 'ON  '))
        else:
            status_text.append(('status_paused', 'OFF  '))

        # Display filter (UI)
        if filter_summary != "No filters active":
            status_text.extend([
                ('status_label', 'Filter: '),
                ('status_filter', f'{filter_summary}  '),
            ])

        # Capture filter (BPF)
        if not offline_mode:
            bpf = (bpf_filter or "").strip()
            status_text.extend([
                ('status_label', 'BPF: '),
                ('status_filter', bpf if bpf else 'none'),
            ])

        self.text.set_text(status_text)


class MainApplication:
    """Главное приложение """
    
    def __init__(self, packet_capture, packet_filter, packet_exporter, bpf_filter=None, offline_mode=False, enable_ipv6_stats=False):
        """Инициализация главного приложения (TUI).

        Args:
            packet_capture: Захват/буфер пакетов (PacketCapture).
            packet_filter: Фильтры отображения/исключения (PacketFilter).
            packet_exporter: Экспорт в pcap/pcapng/text (PacketExporter).
            bpf_filter: Строка BPF для capture (str|None).
            offline_mode: True если работа из pcap (без live capture).
            enable_ipv6_stats: Включить расширенную IPv6 статистику.
        """

        self.packet_capture = packet_capture
        self.packet_filter = packet_filter
        self.packet_exporter = packet_exporter
        self.bpf_filter = bpf_filter
        self.offline_mode = offline_mode

        self.PacketDetailView = PacketDetailView
        self.PacketExportDialog = PacketExportDialog
        
        self.packet_list = PacketListBox(packet_capture, packet_filter)

        self.flow_view = FlowListBox(packet_capture, packet_filter)
        self.showing_flows = False
        self._last_filter_summary = None

        self.status_bar = StatusBar()

        self.status_bar.set_mode(self.showing_flows)

        self.stats_panel = StatisticsPanel(enable_ipv6_stats=enable_ipv6_stats)

        self.left_panel = self.packet_list

        self.columns = urwid.Columns([
            ('weight', 3, self.left_panel),
            (43, self.stats_panel),
        ], dividechars=1)

        self.main_frame = urwid.Frame(
            body=self.columns,
            footer=self.status_bar
        )
        
        self.overlay = None
        self.current_view = self.main_frame
        
        self.palette = [
            ('header', 'white,bold', 'dark blue'),
            ('status', 'white', 'dark blue'),
            ('status_label', 'white,bold', 'dark blue'),
            ('status_value', 'yellow', 'dark blue'),
            ('status_filter', 'light green', 'dark blue'),
            ('status_running', 'light green,bold', 'dark blue'),
            ('status_paused', 'light red,bold', 'dark blue'),
            ('selected', 'black', 'yellow'),
            
            ('tcp', 'light cyan', 'default'),
            ('udp', 'light green', 'default'),
            ('icmp', 'light magenta', 'default'),
            ('arp', 'yellow', 'default'),
            ('dns', 'light blue', 'default'),
            ('http', 'light red', 'default'),
            ('ether', 'dark gray', 'default'),
            ('rst', 'light red,bold', 'default'),
            ('default', 'white', 'default'),
            
            ('stat_panel', 'white', 'default'),
            ('stat_title', 'yellow,bold', 'default'),
            ('stat_label', 'light cyan', 'default'),
            ('stat_value', 'white', 'default'),
            ('stat_rst', 'light red,bold', 'default'),
            ('stat_rst_value', 'light red,bold', 'default'),
            
            ('dialog', 'white', 'dark blue'),
            ('dialog_title', 'yellow,bold', 'dark blue'),
            ('button', 'white', 'dark red'),
            ('button_focus', 'white,bold', 'dark green'),
            ('edit', 'white', 'dark blue'),
            ('edit_focus', 'white,bold', 'dark cyan'),
            ('radio', 'white', 'dark blue'),
            ('radio_focus', 'white,bold', 'dark cyan'),
            ('info', 'light green', 'dark blue'),
            
            ('detail_box', 'white', 'default'),
            ('detail_header', 'yellow,bold', 'default'),
            ('hexdump', 'light cyan', 'default'),
            
            ('help', 'white', 'dark red'),
            ('help_title', 'yellow,bold', 'default'),
            ('help_section', 'light cyan,bold', 'default'),
            ('help_note', 'light green', 'default'),

            ('stream_c2s', 'light green', 'default'),
            ('stream_s2c', 'light cyan', 'default'),
            ('stream_title', 'yellow,bold', 'default'),

        ]
        
        self.loop = urwid.MainLoop(
            self.current_view,
            palette=self.palette,
            unhandled_input=self.handle_input,
            handle_mouse=False
        )
        self.running = False
        # прокидываем BPF в PacketCapture (если задан при старте)
        if getattr(self, "bpf_filter", None):
            self.packet_capture.set_bpf_filter(self.bpf_filter)

    def handle_input(self, key):
        """Обработка клавиш"""
        if key in ('q', 'Q','й'):
            self.confirm_quit()
        elif key in ('d', 'D','в'):
            if self.showing_flows:
                self.show_flow_details()
        elif key in ('c', 'C','с'):
            self.clear_packets()
        elif key in ('w', 'W', 'ц'):
            self.packet_list.toggle_wide_info()
        elif key in ('v', 'V', 'м'):
            if self.showing_flows:
                self.flow_view.toggle_source()
        elif key in ('f', 'F','а'):
            self.show_filter_dialog()
        elif key in ('o', 'O', 'щ'):
            self.show_profiles_dialog()
        elif key == '/':
            self.show_payload_search()
        elif key in ('t', 'T','е'):
            self.follow_stream()
        elif key in ('x', 'X','ч'):
            self.exclude_current_stream_or_protocol()
        elif key in ('e', 'E','у'):
            self.show_exclude_manager()
        elif key in ('a', 'A','ф'):
            self.toggle_auto_scroll()
        elif key in ('s', 'S','ы'):
            self.show_save_dialog()
        elif key in ('b', 'B', 'и'):
            if self.showing_flows:
                self.flow_view.sort_mode = "bytes"
            else:
                # packets view: Set BPF
                if not self.offline_mode:
                    self.show_bpf_dialog()
                else:
                    self.show_message("BPF is capture-level and not available in offline mode")
        elif key in ('k', 'K', 'л'):
            if self.showing_flows:
                self.flow_view.sort_mode = "pkts"
        elif key in ('r', 'R', 'к'):
            if self.showing_flows:
                self.flow_view.sort_mode = "rate"
        elif key in ('h', 'H', 'f1'):
            self.show_help_dialog()
        elif key in ('g', 'G','п'):
            self.toggle_flows_view()
        elif key in ('p', 'P','з'):
            if not self.offline_mode:
                self.toggle_capture()
        elif key == 'enter':
            if self.showing_flows:
                flow = self.flow_view.get_selected_flow()
                if flow:
                    self.drill_down_flow(flow)
            else:
                self.show_packet_details()

    def export_stream_text(self, text: str):
        path = os.path.expanduser("~/packet-monitor-stream.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.close_dialog()
            self.show_message(f"Saved stream text:\n{path}")
        except Exception as e:
            self.show_message(f"Export failed: {e}")

    def export_stream_raw(self, raw_pair):
        c2s, s2c = raw_pair
        base = os.path.expanduser("~/packet-monitor-stream")
        p1 = base + "-c2s.bin"
        p2 = base + "-s2c.bin"
        try:
            with open(p1, "wb") as f:
                f.write(c2s)
            with open(p2, "wb") as f:
                f.write(s2c)
            self.close_dialog()
            self.show_message(f"Saved stream raw:\n{p1}\n{p2}")
        except Exception as e:
            self.show_message(f"Export failed: {e}")

    def show_bpf_dialog(self):
        dialog = BpfFilterDialog(
            current_bpf=self.packet_capture.bpf_filter,
            on_apply=self.apply_bpf_filter,
            on_cancel=self.close_dialog
        )
        self.show_overlay(dialog, width=80, height=14)

    def apply_bpf_filter(self, bpf_text):
        # 1) сохранить в PacketCapture
        self.packet_capture.set_bpf_filter(bpf_text)
        self.bpf_filter = self.packet_capture.bpf_filter

        # 2) перезапуск live capture, чтобы фильтр начал действовать
        restarted = False
        if (not self.offline_mode) and self.packet_capture.running:
            self.packet_capture.stop_capture()
            self.packet_capture.start_capture()
            restarted = True

        self.close_dialog()
        if restarted:
            self.show_message(f"BPF applied and capture restarted:\n{self.packet_capture.bpf_filter or '(none)'}")
        else:
            self.show_message(f"BPF applied:\n{self.packet_capture.bpf_filter or '(none)'}")

    def _get_displayed_packets(self):
        """Пакеты, которые сейчас отображаются (с учётом фильтра)."""
        all_packets = self.packet_capture.get_packets()
        return self.packet_filter.filter_packets(all_packets)

    def detail_prev_packet(self, current_pkt):
        pkts = self._get_displayed_packets()
        if not pkts:
            return
        cur_num = current_pkt.get("num")
        idx = 0
        try:
            idx = next(i for i, p in enumerate(pkts) if p.get("num") == cur_num)
        except Exception:
            idx = 0
        idx = max(0, idx - 1)
        self._open_packet_detail(pkts[idx])

    def detail_next_packet(self, current_pkt):
        pkts = self._get_displayed_packets()
        if not pkts:
            return
        cur_num = current_pkt.get("num")
        idx = 0
        try:
            idx = next(i for i, p in enumerate(pkts) if p.get("num") == cur_num)
        except Exception:
            idx = 0
        idx = min(len(pkts) - 1, idx + 1)
        self._open_packet_detail(pkts[idx])

    def _open_packet_detail(self, pkt):
        """Открыть detail для конкретного пакета + синхронизировать фокус списка."""
        # 1) поставить фокус в списке пакетов (чтобы после выхода курсор был на правильной строке)
        try:
            target_num = pkt.get("num")
            for i, w in enumerate(self.packet_list.packet_list):
                pd = getattr(w, "packet_data", None)
                if pd and pd.get("num") == target_num:
                    self.packet_list.listbox.set_focus(i)
                    break
        except Exception:
            pass

        # 2) открыть detail view заново
        self.loop.widget = self.PacketDetailView(
            pkt,
            on_close_callback=self.close_packet_details,
            on_prev=self.detail_prev_packet,
            on_next=self.detail_next_packet
        )

    def show_profiles_dialog(self):
        cfg = load_profiles_config()
        names = sorted(cfg.get("profiles", {}).keys())
        dialog = ProfilesDialog(
            profile_names=names,
            on_load=self.load_profile_by_name,
            on_save_as=self.save_profile_as,
            on_delete=self.delete_profile_by_name,
            on_preset=self.apply_preset,
            on_close=self.close_dialog
        )
        self.show_overlay(dialog, width=80, height=25)

    def save_profile_as(self, name):
        if not name:
            self.show_message("Profile name is empty")
            return

        cfg = load_profiles_config()
        cfg.setdefault("profiles", {})
        cfg["profiles"][name] = {
            "display": self.packet_filter.to_profile_dict(),
            "bpf": self.packet_capture.bpf_filter
        }

        save_profiles_config(cfg)

        self.close_dialog()
        self.show_message(f"Saved profile: {name}")

    def load_profile_by_name(self, name):
        if not name:
            self.show_message("No profile selected")
            return

        cfg = load_profiles_config()
        prof = cfg.get("profiles", {}).get(name)
        if not prof:
            self.show_message("Profile not found")
            return

        # поддержка старого формата (когда prof был просто dict фильтров)
        if isinstance(prof, dict) and "display" in prof:
            self.packet_filter.load_profile_dict(prof.get("display") or {})
            bpf = prof.get("bpf")
        else:
            self.packet_filter.load_profile_dict(prof)
            bpf = None

        # применяем bpf (если есть)
        if bpf is not None:
            self.packet_capture.set_bpf_filter(bpf)
            self.bpf_filter = self.packet_capture.bpf_filter
            if (not self.offline_mode) and self.packet_capture.running:
                self.packet_capture.stop_capture()
                self.packet_capture.start_capture()

        # важно: после смены фильтров сбросить flow cache
        if hasattr(self, "flow_view"):
            self.flow_view.reset_cache()

        self.close_dialog()
        self.show_message(f"Loaded profile: {name}")

    def delete_profile_by_name(self, name):
        if not name:
            self.show_message("No profile selected")
            return

        cfg = load_profiles_config()
        if name in cfg.get("profiles", {}):
            del cfg["profiles"][name]
            save_profiles_config(cfg)
            self.close_dialog()
            self.show_message(f"Deleted profile: {name}")
        else:
            self.show_message("Profile not found")

    def apply_preset(self, preset_name):
        # пресеты — быстрые, без сохранения
        self.packet_filter.clear_filter()

        if preset_name == "dns-only":
            # DNS: либо proto=DNS (как ты ставишь в parse), либо udp port 53
            self.packet_filter.set_filter("proto", "DNS")
        elif preset_name == "syn-only":
            # # в текущей архитектуре проще по info
            # # (лучше будет, если позже добавим отдельное поле tcp_flags)
            # self.packet_filter.set_filter("proto", "TCP")
            # self.packet_filter.set_filter("info", "SYN")
            self.packet_filter.set_filter("proto", "TCP")
            self.packet_filter.set_filter("tcp_syn", True)
            self.packet_filter.set_filter("tcp_ack", False)
        elif preset_name == "arp-only":
            self.packet_filter.set_filter("proto", "ARP")

        if hasattr(self, "flow_view"):
            self.flow_view.reset_cache()

        self.close_dialog()
        self.show_message(f"Applied preset: {preset_name}")

    def show_flow_details(self):
        flow = self.flow_view.get_selected_flow()
        if not flow:
            self.show_message("No flow selected")
            return

        # источник пакетов (см. toggle источника ниже)
        all_packets = self.packet_capture.get_packets()
        filtered = self.packet_filter.filter_packets(all_packets)

        base_packets = all_packets if self.flow_view.use_all_packets else filtered
        flow_key = self.flow_view.get_selected_flow_key()
        pkts = self.flow_view.packets_for_flow_key(base_packets, flow_key)

        detail = FlowDetailView(flow, pkts, on_close_callback=self.close_dialog)
        self.show_overlay(detail, width=80, height=25)

    def toggle_flows_view(self):
        self.showing_flows = not self.showing_flows
        self.left_panel = self.flow_view if self.showing_flows else self.packet_list
        self.columns.contents[0] = (self.left_panel, self.columns.options('weight', 3))
        if hasattr(self, "status_bar"):
            self.status_bar.set_mode(self.showing_flows)

    def drill_down_flow(self, flow):
        # применяем фильтр на выбранный flow и возвращаемся к пакетам
        proto = flow["proto"]
        a_ip, a_port = flow["a_ip"], str(flow["a_port"])
        b_ip, b_port = flow["b_ip"], str(flow["b_port"])

        self.packet_filter.clear_filter()
        self.packet_filter.set_filter('proto', proto)
        self.packet_filter.set_filter('src_ip', f'({a_ip}|{b_ip})')
        self.packet_filter.set_filter('dst_ip', f'({a_ip}|{b_ip})')
        self.packet_filter.set_filter('src_port', f'({a_port}|{b_port})')
        self.packet_filter.set_filter('dst_port', f'({a_port}|{b_port})')

        # переключаемся обратно
        if self.showing_flows:
            self.toggle_flows_view()

    def exclude_current_stream_or_protocol(self):
        """Исключить stream ИЛИ протокол"""

        if self.showing_flows:
            flow = self.flow_view.get_selected_flow()
            if not flow:
                self.show_message("No flow selected")
                return
            added = self.packet_filter.add_exclude_stream(
                flow["a_ip"], flow["b_ip"], flow["a_port"], flow["b_port"], flow["proto"]
            )
            if added:
                self.show_message(
                    f"✓ Excluded flow:\n{flow['a_ip']}:{flow['a_port']} ↔ {flow['b_ip']}:{flow['b_port']}\n\n"
                    f"Total excluded streams: {self.packet_filter.get_exclude_count()}\n\n"
                    f"Press E to manage exclusions"
                )
            else:
                self.show_message("This flow is already excluded")
            return

        selected = self.packet_list.get_selected_packet()
        if not selected:
            self.show_message("No packet selected")
            return
        
        proto = selected.get('proto', '')
        
        if 'TCP' in proto or 'UDP' in proto:
            src_ip = selected.get('src_ip')
            dst_ip = selected.get('dst_ip')
            src_port = selected.get('src_port')
            dst_port = selected.get('dst_port')
            
            if not all([src_ip, dst_ip, src_port, dst_port]):
                self.show_message("Missing stream information")
                return
            
            base_proto = 'TCP' if 'TCP' in proto else 'UDP'
            
            added = self.packet_filter.add_exclude_stream(
                src_ip, dst_ip, src_port, dst_port, base_proto
            )
            
            if added:
                count = self.packet_filter.get_exclude_count()
                self.show_message(
                    f"✓ Excluded stream:\n"
                    f"{src_ip}:{src_port} ↔ {dst_ip}:{dst_port}\n\n"
                    f"Total excluded streams: {count}\n\n"
                    f"Press E to manage exclusions"
                )
            else:
                self.show_message("This stream is already excluded")
        
        else:
            added = self.packet_filter.add_exclude_protocol(proto)
            
            if added:
                proto_count = len(self.packet_filter.exclude_protocols)
                self.show_message(
                    f"✓ Excluded protocol: {proto}\n\n"
                    f"Total excluded protocols: {proto_count}\n\n"
                    f"Press E to manage exclusions"
                )
            else:
                self.show_message(f"Protocol {proto} is already excluded")
    
    def show_exclude_manager(self):
        """Показать менеджер исключений"""
        dialog = ExcludeManagerDialog(
            self.packet_filter,
            on_close_callback=self.close_dialog
        )
        self.show_overlay(dialog, width=70, height=25)
    
    def show_payload_search(self):
        """Показать диалог поиска по payload"""
        dialog = PayloadSearchDialog(
            on_search_callback=self.do_payload_search,
            on_cancel_callback=self.close_dialog
        )
        self.show_overlay(dialog, width=60, height=15)
    
    def do_payload_search(self, search_string, case_sensitive):
        """Выполнить поиск по payload"""
        self.close_dialog()
        
        all_packets = self.packet_capture.get_packets()
        results = self.packet_filter.search_payload(all_packets, search_string, case_sensitive)
        
        if results:
            self.packet_filter.clear_filter()
            self.packet_filter.set_filter('payload', search_string)
            msg = f"Found {len(results)} packets containing '{search_string}'"
        else:
            msg = f"No packets found containing '{search_string}'"
        
        self.show_message(msg)
    
    def toggle_auto_scroll(self):
        """Переключить автоскролл"""
        self.packet_list.toggle_auto_scroll()

    def follow_stream(self):
        """Follow stream: TCP -> показать reassembled payload, TLS -> handshake summary, UDP -> старый фильтр"""

        # 1) если в режиме flows
        if self.showing_flows:
            flow = self.flow_view.get_selected_flow()
            if not flow:
                return

            proto = flow.get("proto")
            if proto != "TCP":
                # для UDP просто drill down (как раньше)
                self.drill_down_flow(flow)
                return

            ip1, port1 = flow["a_ip"], int(flow["a_port"])
            ip2, port2 = flow["b_ip"], int(flow["b_port"])

            base_packets = self.packet_capture.get_packets()

            g = guess_tcp_client_server(base_packets, ip1, port1, ip2, port2)
            if g:
                a_ip, a_port, b_ip, b_port = g  # client -> server
            else:
                # fallback: оставляем как было (A -> B)
                a_ip, a_port, b_ip, b_port = ip1, port1, ip2, port2

            blocks_c2s, blocks_s2c = build_tcp_stream_reassembled(base_packets, a_ip, a_port, b_ip, b_port)
            title = f"{a_ip}:{a_port}  <->  {b_ip}:{b_port}"

            # --- raw payload по направлениям (для TLS-детекта и summary) ---
            raw_pair = build_tcp_stream_raw_pair(base_packets, a_ip, a_port, b_ip, b_port)
            c2s_raw, s2c_raw = raw_pair

            if looks_like_tls_stream(c2s_raw) or looks_like_tls_stream(s2c_raw):
                c2s_lines = tls_summarize_stream(c2s_raw)
                s2c_lines = tls_summarize_stream(s2c_raw)

                view = TlsHandshakeView(
                    title="TLS Handshake Summary: " + title,
                    c2s_lines=c2s_lines,
                    s2c_lines=s2c_lines,
                    on_close_callback=self.close_dialog
                )
                self.show_overlay(view, width=110, height=35)
            else:
                view = TcpStreamView(
                    title=title,
                    blocks_c2s=blocks_c2s,
                    blocks_s2c=blocks_s2c,
                    on_close_callback=self.close_dialog,
                    on_export_text=self.export_stream_text,
                    on_export_raw=self.export_stream_raw
                )
                self.show_overlay(view, width=110, height=35)

            return

        # 2) если выбран пакет
        selected = self.packet_list.get_selected_packet()
        if not selected:
            return

        proto = selected.get('proto', '')
        if 'TCP' not in proto:
            # старое поведение для UDP и прочего
            if selected.get('proto') in ['UDP', 'UDPv6'] and selected.get('src_port') and selected.get('dst_port'):
                src_ip = selected['src_ip']
                dst_ip = selected['dst_ip']
                src_port = str(selected['src_port'])
                dst_port = str(selected['dst_port'])

                self.packet_filter.clear_filter()
                self.packet_filter.set_filter('src_ip', f'({src_ip}|{dst_ip})')
                self.packet_filter.set_filter('dst_ip', f'({src_ip}|{dst_ip})')
                self.packet_filter.set_filter('src_port', f'({src_port}|{dst_port})')
                self.packet_filter.set_filter('dst_port', f'({src_port}|{dst_port})')
                self.packet_filter.set_filter('proto', 'UDP')
            else:
                self.show_message("Follow stream works only for TCP (payload/TLS) or UDP (filter)")
            return

        # TCP: определяем endpoints
        if not selected.get('src_port') or not selected.get('dst_port'):
            self.show_message("Missing ports for stream")
            return

        base_packets = self.packet_capture.get_packets()

        ip1 = selected['src_ip']
        ip2 = selected['dst_ip']
        port1 = int(selected['src_port'])
        port2 = int(selected['dst_port'])

        g = guess_tcp_client_server(base_packets, ip1, port1, ip2, port2)
        if g:
            a_ip, a_port, b_ip, b_port = g  # client -> server
        else:
            a_ip, a_port, b_ip, b_port = ip1, port1, ip2, port2

        blocks_c2s, blocks_s2c = build_tcp_stream_reassembled(base_packets, a_ip, a_port, b_ip, b_port)
        title = f"{a_ip}:{a_port}  <->  {b_ip}:{b_port}"

        raw_pair = build_tcp_stream_raw_pair(base_packets, a_ip, a_port, b_ip, b_port)
        c2s_raw, s2c_raw = raw_pair

        if looks_like_tls_stream(c2s_raw) or looks_like_tls_stream(s2c_raw):
            c2s_lines = tls_summarize_stream(c2s_raw)
            s2c_lines = tls_summarize_stream(s2c_raw)

            view = TlsHandshakeView(
                title="TLS Handshake Summary: " + title,
                c2s_lines=c2s_lines,
                s2c_lines=s2c_lines,
                on_close_callback=self.close_dialog
            )
            self.show_overlay(view, width=110, height=35)
        else:
            view = TcpStreamView(
                title=title,
                blocks_c2s=blocks_c2s,
                blocks_s2c=blocks_s2c,
                on_close_callback=self.close_dialog,
                on_export_text=self.export_stream_text,
                on_export_raw=self.export_stream_raw
            )
            self.show_overlay(view, width=110, height=35)

    def toggle_capture(self):
        """Переключить capture"""
        if self.packet_capture.running:
            self.packet_capture.stop_capture()
        else:
            self.packet_capture.start_capture()
    
    def confirm_quit(self):
        """Подтверждение выхода"""
        total = len(self.packet_capture.get_packets())
        stats = self.packet_capture.get_statistics()
        
        message = (f"Quit?\n\n"
                  f"Packets: {total}\n"
                  f"Traffic: {stats['total_bytes']:,} bytes\n"
                  f"Bandwidth: {stats['bandwidth_mbps']:.2f} Mbps")
        
        dialog = ConfirmDialog(
            message,
            on_yes_callback=self.quit_application,
            on_no_callback=self.close_dialog
        )
        
        self.show_overlay(dialog, width=50, height=14)
    
    def quit_application(self):
        """Выход"""
        self.running = False
        raise urwid.ExitMainLoop()
    
    def show_packet_details(self):
        """Детали пакета"""
        selected = self.packet_list.get_selected_packet()
        if selected:
            # detail_view = self.PacketDetailView(
            #     selected,
            #     on_close_callback=self.close_packet_details
            # )
            detail_view = self.PacketDetailView(
                selected,
                on_close_callback=self.close_packet_details,
                on_prev=self.detail_prev_packet,
                on_next=self.detail_next_packet
            )

            self.loop.widget = detail_view
    
    def close_packet_details(self):
        """Закрыть детали"""
        self.loop.widget = self.main_frame

    def open_value_picker(self, field, on_select_value):
        all_packets = self.packet_capture.get_packets()
        # можно сделать по filtered, если захочешь: filtered = self.packet_filter.filter_packets(all_packets)
        picker = FieldValuePickerDialog(
            field=field,
            packets=all_packets,
            on_select=on_select_value,
            on_cancel=self.close_dialog
        )
        self.show_overlay(picker, width=80, height=25)

    def show_filter_dialog(self):
        """Диалог фильтров"""
        dialog = FilterDialog(
            self.packet_filter,
            on_apply_callback=self.apply_filters,
            on_cancel_callback=self.close_dialog,
            on_open_picker=self._open_filter_value_picker
        )
        self.show_overlay(dialog, width=60, height=32)
        self._filter_dialog_ref = dialog  # запомним, чтобы вернуть фокус/редактирование

    def _open_filter_value_picker(self, field, on_value_picked):
        # запоминаем текущее поле, чтобы вставить выбранное значение
        self._filter_picker_field = field
        self._filter_dialog_ref = self.overlay.top_w if self.overlay else getattr(self, "_filter_dialog_ref", None)

        def _select(value):
            # 1) подставляем в edit поле
            dlg = self._filter_dialog_ref
            if dlg and hasattr(dlg, "filter_fields") and field in dlg.filter_fields:
                dlg.filter_fields[field].set_edit_text(value)

            # 2) закрываем picker и возвращаем filter dialog (показываем его снова)
            #   (у тебя show_overlay всегда строит новый Overlay, так что просто покажем dlg снова)
            self.show_overlay(dlg, width=60, height=32)

        # открываем picker поверх main_frame
        self.open_value_picker(field, on_select_value=_select)

    def apply_filters(self):
        """Применить фильтры"""
        self.close_dialog()
    
    def show_save_dialog(self):
        """Сохранение"""
        export_dialog = self.PacketExportDialog(
            self.packet_capture,
            self.packet_filter,
            self.packet_exporter
        )
        
        dialog = SaveDialog(
            export_dialog,
            on_save_callback=self.on_save_complete,
            on_cancel_callback=self.close_dialog
        )
        self.show_overlay(dialog, width=60, height=20)
    
    def on_save_complete(self, success, filepath, message):
        """После сохранения"""
        self.close_dialog()
        msg = f"✓ {message}\nFile: {filepath}" if success else f"✗ {message}"
        self.show_message(msg)
    
    def show_help_dialog(self):
        """Помощь"""
        dialog = HelpDialog(on_close_callback=self.close_dialog)
        self.show_overlay(dialog, width=75, height=50)
    
    def show_overlay(self, widget, width, height):
        """Overlay"""
        self.overlay = urwid.Overlay(
            widget,
            self.main_frame,
            align='center',
            width=width,
            valign='middle',
            height=height
        )
        self.loop.widget = self.overlay
    
    def close_dialog(self):
        """Закрыть диалог"""
        self.loop.widget = self.main_frame
        self.overlay = None
    
    def show_message(self, message):
        """Сообщение (модальное окно поверх основного интерфейса)"""
        # Нормализуем текст
        if message is None:
            message = ""
        message = str(message).rstrip()

        msg_lines = message.splitlines() or [""]
        max_len = max(len(l) for l in msg_lines)
        
        # + рамка и отступы; ограничиваем разумными размерами терминала
        width = min(max(24, max_len + 6), 100)
        height = min(max(7, len(msg_lines) + 6), 40)

        text = urwid.Text(message)
        hint = urwid.Text("Press any key to close", align='center')

        pile = urwid.Pile([
            text,
            urwid.Divider(),
            hint
        ])

        class ModalKeyCatcher(urwid.WidgetWrap):
            def selectable(self):
                return True
        
            def keypress(self, size, key):
                self._on_close()
                return None

        box = urwid.LineBox(pile, title="Message", title_attr='dialog_title')
        box = urwid.AttrMap(box, 'dialog')

        popup = ModalKeyCatcher(box)
        popup._on_close = self.close_dialog
        self.show_overlay(popup, width=width, height=height)

    def clear_packets(self):
        """Очистить"""
        self.packet_capture.clear_packets()
        self.packet_list.clear()

    def refresh_display(self, loop, user_data):
        """Callback для периодического обновления"""
        if not self.running:
            return

        try:
            # 1) Берём данные один раз
            all_packets = self.packet_capture.get_packets()
            filtered = self.packet_filter.filter_packets(all_packets)

            # 2) Если фильтры изменились — сбрасываем кэш flows
            filter_summary = self.packet_filter.get_filter_summary()
            if getattr(self, "_last_filter_summary", None) is None:
                self._last_filter_summary = filter_summary
            elif filter_summary != self._last_filter_summary:
                if hasattr(self, "flow_view"):
                    self.flow_view.reset_cache()
                self._last_filter_summary = filter_summary

            # 3) Обновляем левую панель (packets или flows)
            if getattr(self, "showing_flows", False):
                base_packets = all_packets if self.flow_view.use_all_packets else filtered
                self.flow_view.update_flows_from(base_packets)
            else:
                self.packet_list.update_packets()

            # 4) Stats панель — по filtered
            self.stats_panel.update(filtered, self.packet_filter, self.packet_capture)

            # 5) Status bar
            total = len(all_packets)
            self.status_bar.update(
                total,
                len(filtered),
                filter_summary,
                self.packet_capture.interface,
                self.packet_capture.running,
                self.offline_mode,
                self.packet_list.auto_scroll,
                self.packet_capture.bpf_filter
            )

            # 6) Принудительно перерисовываем экран
            self.loop.draw_screen()

        except Exception as e:
            if self.packet_capture.log_file:
                try:
                    with open(self.packet_capture.log_file, 'a') as f:
                        f.write(f"[ERROR in refresh_display] {e}\n{traceback.format_exc()}\n")
                except:
                    pass

        self.loop.set_alarm_in(0.1, self.refresh_display)

    def reset_terminal(self):
        """Сброс терминала"""
        try:
            sys.stdout.write('\033[0m\033[?25h')
            sys.stdout.flush()
        except:
            pass
    
    def start(self):
        """Старт приложения"""
        self.running = True
        self.loop.set_alarm_in(0.1, self.refresh_display)
        
        try:
            self.loop.run()
        finally:
            self.reset_terminal()
    
    def stop(self):
        """Стоп"""
        self.running = False
        self.reset_terminal()


def parse_arguments():
    """Аргументы командной строки"""
    parser = argparse.ArgumentParser(
        description=f'Packet Monitor v{__version__}',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('-i', '--interface', metavar='<iface>', default=None,
                       help='Network interface (use "any" for all)')
    parser.add_argument('-r', '--read', metavar='<file>', default=None,
                       help='Read from pcap/pcapng file')
    parser.add_argument('-f', '--filter', metavar='<filter>', default=None,
                       help='BPF filter (tcpdump syntax)')
    parser.add_argument('--ipv6', action='store_true',
                       help='Enable IPv6 statistics collection')
    parser.add_argument('--version', action='version', version=f'Packet Monitor v{__version__}')
    
    return parser.parse_args()


def main():
    """Main"""
    args = parse_arguments()
    
    # Подавляем вывод scapy в stderr
    stderr_backup = sys.stderr
    try:
        sys.stderr = open(os.devnull, 'w')
        sys.stderr.close()
        sys.stderr = stderr_backup
    except Exception as e:
        if sys.stderr != stderr_backup:
            sys.stderr.close()
        sys.stderr = stderr_backup
        print(f"\n[ERROR] Import failed: {e}")
        sys.exit(1)
    
    print("=" * 70)
    print(f"Packet Monitor v{__version__}")
    print("=" * 70)
    
    print("\nInitializing...")
    
    offline_mode = args.read is not None
    
    if offline_mode:
        print(f"  Reading {args.read}...")
        capture = PacketCapture(interface='offline', log_file='./packet_monitor.log')
        capture.running = False
        
        try:
            packets = rdpcap(args.read)
            print(f"  Loaded {len(packets)} packets")
            
            for i, pkt in enumerate(packets, 1):
                packet_info = capture._parse_packet(pkt)
                packet_info['num'] = i
                if hasattr(pkt, 'sniffed_on'):
                    packet_info['interface'] = str(pkt.sniffed_on)
                capture.packets.append(packet_info)
            
            print(f"  ✓ Ready")
        except Exception as e:
            print(f"\n[ERROR] Failed: {e}")
            sys.exit(1)
    else:
        if args.interface == 'any':
            interface = 'any'
        else:
            interface = args.interface
        
        capture = PacketCapture(
            interface=interface,
            packet_limit=50000,
            log_file='./packet_monitor.log'
        )
        
        print(f"  ✓ Interface: {capture.interface}")
        print(f"  ✓ Monitoring: {capture.interfaces}")
        print(f"  ✓ Buffer limit: 50000")
        print("  ✓ Starting PAUSED (press P to start)")
    
    pfilter = PacketFilter()
    exporter = PacketExporter()
    
    print("  ✓ Components initialized")
    print(f"  ✓ Log file: ./packet_monitor.log")
    
    if args.ipv6:
        print("  ✓ IPv6 statistics: ENABLED")
    
    app = MainApplication(
        capture, pfilter, exporter,
        bpf_filter=args.filter,
        offline_mode=offline_mode,
        enable_ipv6_stats=args.ipv6
    )
    
    def signal_handler(sig, frame):
        app.confirm_quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print("\nStarting TUI...")
    print("=" * 70)
    
    try:
        app.start()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n\nShutdown...")
        if not offline_mode:
            capture.stop_capture()
        
        stats = capture.get_statistics()
        print(f"Packets captured: {stats['total_packets']}")
        print(f"Traffic: {stats['total_bytes']:,} bytes")
        print(f"Bandwidth: {stats['bandwidth_mbps']:.2f} Mbps")
        
        all_pkts = capture.get_packets()
        print(f"Packets in buffer: {len(all_pkts)}")
        
        if all_pkts:
            print("\nLast 5 packets:")
            for pkt in all_pkts[-5:]:
                iface_str = safe_str(pkt.get('interface'), 'N/A')
                proto_str = safe_str(pkt.get('proto'), 'N/A')
                src_ip_str = safe_str(pkt.get('src_ip'), 'N/A')
                dst_ip_str = safe_str(pkt.get('dst_ip'), 'N/A')
                
                print(f"  [{pkt['num']}] {iface_str:<8} {proto_str:<8} {src_ip_str} -> {dst_ip_str}")
        
        print("\nCheck log: tail -f ./packet_monitor.log")
        print("\nGoodbye!")


if __name__ == '__main__':
    main()
