# packet-monitor

`packet-monitor` is a terminal (TUI) packet monitor and analyzer written in Python (Scapy + Urwid).  
It supports live capture, offline analysis (if enabled in your build), packet list view, flows/conversations view, filtering, exclusions, profiles, and “Follow Stream” with best-effort TCP reassembly and TLS handshake summaries (no decryption).

> **Note:** This tool is intended for debugging and analysis on systems you own or have permission to inspect.

---

## Features

### Live capture (multi-interface)
- Capture from a single interface or multiple interfaces (e.g. `any`).
- Ring buffer (bounded memory) for captured packets.

### Packet list view
- Table view with timestamp, interface, protocol, endpoints, ports, and an `info` summary.
- Protocol highlighting (TCP/UDP/DNS/ARP/ICMP).
- Packet details view (raw bytes/hex and parsed fields).

### Flows / Conversations view
Aggregates packets into flows (5-tuple):
- `proto`, `ip:port A`, `ip:port B`
- packets/bytes
- A→B bytes and B→A bytes
- first_seen/last_seen
- basic TCP state counters (SYN/FIN/RST)

Includes quick actions:
- Drill-down to packets for selected flow
- Exclude flow

### Filtering and search
- UI filters by: `proto`, `src_ip`, `dst_ip`, `any_ip`, `src_port`, `dst_port`, `any_port`, `interface`, `info` (regex), `payload` (regex)
- Payload search dialog (`/`) that applies a payload filter.

### Exclusions
- Exclude protocol(s)
- Exclude streams/flows (by endpoints + proto)
- Exclusions manager UI

### Profiles
- Save/load/delete filter+exclusion profiles
- Stored at: `~/.packet-monitor/config.json`
- Quick presets: `dns-only`, `syn-only`, `arp-only`

### Capture BPF filter
- Optional BPF filter applied at capture time (before packets enter the application).
- Great for performance and reducing noise.

### Follow Stream (Wireshark-like, best-effort)
- **TCP:** reassembles payload by TCP sequence numbers:
  - sorts segments by `seq`
  - removes retransmission duplicates
  - inserts placeholders for missing bytes (gaps)
  - shows two directions (client→server and server→client)
  - export text + raw direction files
- **TLS (no keys):** handshake summary view:
  - ClientHello: SNI, ALPN
  - ServerHello: version, selected cipher
  - Alerts, record types
  - ApplicationData shown as encrypted

---

## Requirements

- Python 3.x
- `scapy`
- `urwid`
- Root/admin privileges for live capture on most systems

Example Debian/Ubuntu packages (adjust as needed):
- `python3`
- `python3-scapy`
- `python3-urwid`

---

## Running

### Live capture
Run as root (or with capture permissions):

```bash
sudo python3 packet-monitor.py
````

If your build supports interface selection flags, use them accordingly.
Otherwise, use the built-in UI dialogs.

### Offline mode

If your build includes offline/pcap reading, start in offline mode (implementation-specific).

---

## BPF Examples

BPF is applied **at capture time**:

* HTTPS only:

  * `tcp port 443`
* DNS only:

  * `udp port 53`
* Single host:

  * `host 192.168.1.10`
* DNS + HTTPS:

  * `udp port 53 or tcp port 443`

---

## Keybindings (default)

> Some builds include additional mappings for non-English keyboard layouts.

### Global

* `F1` / `H` — Help
* `Q` — Quit
* `P` — Pause/Resume capture (live mode)
* `C` — Clear buffer
* `A` — Toggle auto-scroll
* `S` — Save/Export
* `/` — Payload search dialog
* `F` — Filter dialog
* `O` — Profiles dialog
* `G` — Toggle Flows view (Packets ↔ Flows)
* `E` — Manage exclusions

### Packets view

* `Enter` — Packet details
* `T` — Follow stream (TCP reassembly / UDP quick filter)
* `X` — Exclude current stream or protocol

### Flows view

* `V` — Toggle flows source: FILTERED vs ALL
* `Enter` — Drill-down (apply flow filter and return to packets view)
* `D` — Flow details
* `T` — Follow stream (TCP reassembly or TLS handshake summary)
* `X` — Exclude selected flow
* `B/K/R` — Sort flows (bytes/packets/rate) if enabled in your build

---

## Typical Workflows

### 1) Identify top talkers

1. Press `G` to open Flows view
2. Toggle source `V` (ALL vs FILTERED)
3. Sort by bytes (`B`) or rate (`R`)
4. Drill down with `Enter` or exclude with `X`

### 2) Inspect TLS handshake metadata

1. Set BPF: `tcp port 443`
2. Generate traffic: `curl https://google.com`
3. Look for:

   * `TLS ClientHello SNI=... ALPN=...`
   * `TLS ServerHello ver=... cipher=...`
4. Press `T` on the flow to view handshake summary

### 3) Reassemble a TCP stream (plaintext protocols)

1. Filter or capture on a plaintext port (e.g. `tcp port 80`)
2. Select a packet and press `T`
3. View both directions; export if needed

---

## Security / Privacy Notes

* The tool can capture sensitive data (payloads, endpoints, metadata). Use responsibly.
* TLS decryption is **not** performed; only handshake metadata is parsed.
* Running as root is typically required for sniffing.

---

## License

MIT License - see [LICENSE](LICENSE) for details.

```
MIT License

Copyright (c) 2026 Tarasov Dmitry

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Contributing

PRs and issues are welcome. Please include:

* OS + Python version
* capture mode (live/offline)
* reproduction steps
* sample packets/pcap if possible

## Attribution
Parts of this code were generated with assistance

