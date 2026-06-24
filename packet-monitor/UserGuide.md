## Table of Contents

* [1) What This Program Is And What It Does](#1-what-this-program-is-and-what-it-does)
* [2) Quick Start](#2-quick-start)
* [3) Hotkeys](#3-hotkeys-main)
* [4) Filtering](#4-filtering-how-it-works-and-how-to-expect-the-result-correctly)
* [5) Flows/Conversations View](#5-flowsconversations-view-g)
* [6) Follow Stream](#6-follow-stream-t--wireshark-like-whats-currently-implemented)
* [7) Packet Details](#7-packet-details-enter-on-a-packet)
* [8) BPF Capture Filter](#8-bpf-capture-filter--what-it-gives-you-and-how-to-use-it)
* [9) Profiles](#9-profiles-o)
* [10) User Cases](#10-user-case-usage-scenarios)
* [11) Practical Tips](#11-practical-tips)
* [Troubleshooting](#troubleshooting)

## 1) What This Program Is And What It Does

`packet-monitor` is a terminal (TUI) network traffic analyzer:

* **Live capture**: capture packets from a single interface or from `any` (multiple interfaces).
* **Offline**: analyze a `pcap`/`pcapng` file.
* **Packet list**: a packet table with the main fields plus `info`.
* **Flows/Conversations**: a flow table (5-tuple aggregation), sorting, drill-down to packets, and flow details.
* **Packet details**: a detailed view of packet contents (raw/hex/info and more).
* **Follow stream**:

  * TCP: payload reassembly by sequence number (best effort, with retransmission deduplication and gap placeholders).
  * TLS: handshake summary (SNI/ALPN/ServerHello version/cipher, alerts) without decryption.
  * UDP/other: a "classic" follow-stream style filter by ip/port/proto.
* **Filtering** (UI level): by proto/ip/port/interface/info/payload.
* **Exclusions**: exclude a stream or a protocol.
* **Profiles**: save/load filter sets and exclusions in `~/.packet-monitor/config.json`.
* **BPF**: a capture-time filter applied before packets enter the application.

---

## 2) Quick Start

### 2.1 Live Capture

The simplest way:

* run as root/admin (or with sniff permissions)
* choose the interface if you pass one, or use the default main interface
* packets will start appearing in the UI

BPF examples:

* HTTPS only:

  * `tcp port 443`
* DNS only:

  * `udp port 53`
* traffic to a single host:

  * `host 192.168.1.10`
* DNS + HTTPS:

  * `udp port 53 or tcp port 443`

### 2.2 Offline Mode

If you already have a capture file:

```bash
python packet-monitor.py -r capture.pcap
```

or:

```bash
python packet-monitor.py -r capture.pcapng
```

This opens the file for analysis without live capture.

> Important: BPF is unavailable in offline mode because it is a capture-time filter.

### 2.3 CLI Parameters

Supported parameters:

* `-i <iface>` / `--interface <iface>`: capture interface
* `-r <file>` / `--read <file>`: open `pcap`/`pcapng`
* `-f <expr>` / `--filter <expr>`: BPF filter in `tcpdump` syntax
* `--ipv6`: enable extended IPv6 statistics
* `--version`: print the version

### 2.4 Screen Layout

* **Left panel**: packet list or flows table (Flows view).
* **Right panel**: statistics.
* **Bottom bar**: status (interface/mode, total/displayed, filter) plus hotkeys.

---

## 3) Hotkeys (Main)

### Global

* `F1` / `H` -> Help
* `Q` -> Quit
* `P` -> Pause/Resume capture (live mode)
* `C` -> Clear the packet buffer
* `A` -> Auto-scroll on/off
* `S` -> Save/Export
* `/` -> Payload search
* `F` -> Filter dialog (UI filters)
* `O` -> Profiles (Save/Load/Delete + Presets)
* `G` -> Flows view (toggle packets <-> flows)
* `W` -> switch `Info`: compact mode <-> wide mode (`info_short`/`info_long`)

### In Flows Mode

* `V` -> switch flow source: **FILTERED** vs **ALL**
* `D` -> Flow details
* `Enter` -> drill-down: apply a filter for the selected flow and return to packets
* `T` -> Follow stream (TCP -> stream view / TLS handshake summary)
* `X` -> Exclude flow
* `B` / `K` / `R` -> sort flows (bytes / packets / rate)

### In Packets Mode

* `Enter` -> Packet details
* `T` -> Follow stream (TCP -> reassembly view, UDP -> 4-tuple filter)
* `X` -> Exclude stream or protocol (depending on the selected packet)
* `E` -> Exclusions manager
* `B` -> open the BPF dialog (live mode only)

---

## 4) Filtering: How It Works And How To Expect The Result Correctly

### 4.1 UI Filters (F)

The filter dialog contains fields such as:

* `proto`
* `src_ip`
* `dst_ip`
* `any_ip`
* `src_port`
* `dst_port`
* `any_port`
* `interface`
* `info` (regex supported)
* `payload` (regex search)

**Important:**
If you set both `src_ip=...` and `dst_ip=...`, that means **AND** (both conditions at once).
To match "src OR dst = 192.168.1.23", use:

* `any_ip = 192.168.1.23` (recommended)
  or
* do not expect `src_ip=(192\.168\.1\.23)` plus `dst_ip=(192\.168\.1\.23)` to work as OR; it is still AND.

### 4.2 Picking Values From Captured Packets (L/F2)

The filter dialog includes a picker that shows all values already present in captured packets (for example for `src_ip`, `dst_ip`, `any_ip`, ports, or `interface`).

Expected behavior:

* select a field
* press `L` (or `F2` if remapped)
* you get a list of `value (count)`
* `Enter` inserts the selected value into the filter field

---

## 5) Flows/Conversations View (G)

### 5.1 What A Flow Means In This Program

A flow is aggregated by 5-tuple:

* proto (TCP/UDP)
* endpoint A (`ip:port`)
* endpoint B (`ip:port`)

Displayed fields include:

* packets
* total bytes
* bytes A->B / B->A
* first_seen / last_seen
* TCP hints: SYN/FIN/RST counters

### 5.2 Flow Source

* **FILTERED**: only packets that passed the current UI filters
* **ALL**: all captured packets, ignoring the current UI filter for flow aggregation

Toggle with `V`.

### 5.3 Drill-Down

Press `Enter` on a flow:

* the program applies filters so the packet list contains only packets from that flow.

### 5.4 Exclude Flow

Press `X` on a flow:

* the flow is added to exclusions and disappears from the views
* manage exclusions with `E`

### 5.5 Flow Details (D)

`D` opens a flow details window (duration, pps/bps, top ports, and similar values depending on the current implementation).

---

## 6) Follow Stream (T) - "Wireshark-like" (What's Currently Implemented)

### 6.1 TCP Stream View

If you select a TCP flow or packet and press `T`:

* the program determines client/server (using SYN without ACK if available)
* it collects TCP payload in both directions:

  * Client -> Server
  * Server -> Client
* it reassembles by `seq`:

  * segments are sorted
  * retransmissions/duplicates are removed
  * a placeholder such as `[...] missing N bytes [...]` is inserted for gaps
* display is UTF-8/ASCII with hex fallback
* you can export:

  * text
  * raw bytes by direction (`*-c2s.bin`, `*-s2c.bin`)

### 6.2 TLS Handshake View (In Follow Stream)

If the flow looks like TLS (based on record headers), instead of the regular TCP stream view you get a TLS handshake summary:

Examples:

* `ClientHello SNI=google.com ALPN=h2,http/1.1`
* `ServerHello ver=TLS1.3 cipher=0x1301`
* `Alert fatal handshake_failure`
* `ApplicationData (encrypted)` once encrypted traffic starts

> Important: you cannot see HTTP inside TLS without MITM/keys/SSLKEYLOGFILE and similar mechanisms.
> This view only shows handshake metadata.

### 6.3 UDP "Follow Stream"

For UDP, `T` works as a quick 4-tuple filter (show only this exchange).

---

## 7) Packet Details (Enter On A Packet)

The details window typically shows:

* header information (number/time/interface/addresses/ports/protocol)
* info summary
* raw/hex dump
* extra fields (tcp flags/seq/ack, packet_loss marker)

Navigation inside details:

* `Esc` -> close details
* `N` -> next packet
* `P` -> previous packet
* arrows / PgUp / PgDn -> scroll content

## 7.1 Save / Export (`S`)

The save dialog supports two modes:

* `All captured packets`: save the entire current buffer
* `Only filtered packets`: save only packets that passed the current UI filters and exclusions

UI export currently targets `pcapng` saving.

---

## 8) BPF Capture Filter - What It Gives You And How To Use It

BPF is applied **at capture time**, meaning packets that do not match the filter **never enter** the application buffer.

Benefits:

* lower CPU and RAM usage
* more convenient on high traffic rates

Drawback:

* once something was filtered out, it cannot be recovered inside the program

Examples:

* `tcp port 443`: HTTPS only (you will see ClientHello/ServerHello summary)
* `tcp port 9100`: one specific service
* `host 10.0.0.5 and tcp`: TCP to one host only

---

## 9) Profiles (O)

A profile stores:

* filters (`proto/src_ip/.../payload`)
* exclusions (`exclude_streams`, `exclude_protocols`)
* the current `BPF` (if set)

### 9.1 Where It Is Stored

`~/.packet-monitor/config.json`

### 9.2 What You Can Do

* Save As: save current filters/exclusions and the current `BPF`
* Load: load a profile and restore `BPF` if it was saved
* Delete: remove it
* Presets:

  * `dns-only`
  * `syn-only` (correctly implemented as `tcp_syn=True`, `tcp_ack=False`)
  * `arp-only`

---

# 10) User Case (Usage Scenarios)

## Scenario 1: "Quickly See Who Is Making Noise In The Network" (Top Flows)

**Goal:** in one minute, identify the "fattest" flows.

1. Start capture without BPF.
2. Press `G` (Flows view).
3. Switch source with `V` -> `ALL` if you want to see everything.
4. Sort by bytes (`B`) or rate (`R`).
5. Select a suspicious flow -> `Enter` (drill-down) -> inspect the packets.
6. If it is just noise -> go back to flows -> `X` (Exclude flow).

**Result:** you remove noise quickly and focus on the relevant traffic.

---

## Scenario 2: "Find DNS Answers And See Where A Domain Resolves"

**Goal:** see DNS answers directly in the packet list.

1. Set preset `O` -> `dns-only` (or `F` -> `proto=DNS`).
2. Check the `info` field: `DNS example.com | Ans: A:..., AAAA:..., CNAME:...`
3. If you need only responses, filter `info` by `Ans:`.

---

## Scenario 3: "Inspect A TLS Handshake: SNI/ALPN/Version/Cipher"

**Goal:** see SNI and ALPN during connection establishment.

1. Set BPF: `tcp port 443`
2. In another terminal:

   * `curl https://google.com`
3. In the packet list, look for:

   * `TLS ClientHello SNI=google.com ALPN=h2,http/1.1`
   * `TLS ServerHello ver=TLS1.3 cipher=...`
4. Press `T` on the flow to open the TLS handshake summary view.

---

## Scenario 4: "Follow A TCP Stream And See Plain HTTP"

**Goal:** reconstruct HTTP requests/responses when the traffic is not encrypted.

1. Set a filter (or BPF): `tcp port 80`
2. Open a site over HTTP or run `curl http://...`
3. Select a packet -> `T`
4. In the stream view, you will see request/response text by direction.

---

## Scenario 5: "Find A Packet By Payload (For Example A Token Or String)"

**Goal:** find a specific string in the data.

1. Press `/`
2. Enter the string (regex is allowed)
3. Apply -> if matches are found, a payload filter is applied and only matching packets remain

---

## Scenario 6: "SYN-Only For Diagnosing Scans/Connections"

**Goal:** see only TCP connection attempts.

1. `O` -> preset `syn-only`
2. In the packet list you will see only SYN without ACK (connection initiations)
3. Switch to flows (`G`) and see where the connections go.

---

## Scenario 7: "I Only Have A Problem With One Service - Minimize Noise"

**Goal:** monitor one specific port/service.

1. Set BPF: `tcp port 9100` (node-exporter) or the port you need.
2. In the flow list you will see only relevant entries.
3. If you need to remove recurring noise, use `X` to exclude a flow.

---

# 11) Practical Tips

* If traffic volume is high, start with **BPF** to save resources.
* For "src or dst", use `any_ip`; for ports, use `any_port`.
* If "nothing is visible", check that you did not set two fields that combine as AND (for example `src_ip` and `dst_ip` together).
* If "TLS shows nothing", the handshake may have been split across multiple TCP segments: buffering should help; if not, increase the buffer or verify payload extraction on your interface.

### Troubleshooting

#### 1) Empty Screen After Setting A Filter

**Cause:** filters in the `Filter` dialog are applied together (logical **AND**).
For example, if you set both `src_ip=192.168.1.23` and `dst_ip=192.168.1.23`, you only get packets where **both** fields equal that IP, which is usually none.

**What to do:**

* to get "src **or** dst = 192.168.1.23", use `any_ip=192.168.1.23`
* to get "src_port **or** dst_port = 9100", use `any_port=9100`

---

#### 2) I Do Not See TLS SNI/ALPN/ServerHello (On HTTPS)

**Causes and fixes:**

* **The monitor was started after the connection was already established.** TLS handshake happens at the start.

  * Fix: start `packet-monitor` **before** `curl/browser`, then repeat the request.
* **BPF or UI filter is too strict.**

  * Fix: try BPF `tcp port 443` and make sure HTTPS traffic is actually present.

**Where to look:**

* In the packet list, in the `Info` column, you should see lines like:

  * `TLS ClientHello SNI=... ALPN=...`
  * `TLS ServerHello ver=... cipher=...`

---

#### 3) "Follow Stream" Does Not Show HTTPS Contents (HTTP Inside TLS)

This is expected: **HTTPS traffic is encrypted**.
Without keys and without MITM, `packet-monitor` does **not decrypt** ApplicationData, so at best it shows:

* TLS handshake summary (SNI/ALPN/version/cipher/alerts)
* `ApplicationData (encrypted)` after the handshake

**What to do if you need HTTP text:**

* use unencrypted HTTP (for example port 80) or separate proxy/decryption tools; this is not part of the current `packet-monitor`

---

#### 4) I Press Follow Stream But I See "Empty/Little Data"

**Causes:**

* the connection is short and has almost no payload (for example, handshake only)
* the selected packet is not part of the intended TCP flow

**What to do:**

* switch to `Flows` (`G`), select the required flow, and press `T` there
* verify that it is actually a TCP flow (for UDP, Follow Stream behaves like a quick filter)

---

#### 5) Packets Are Not Captured (Live Mode)

**Typical causes:**

* not enough privileges for capture (usually needs root/admin)
* wrong interface selected
* BPF filter matches nothing

**What to do:**

* run with admin privileges: `sudo ...`
* verify the interface name (for example `ip a`)
* temporarily disable BPF or use a broad one like `tcp` / `udp`

---

#### 6) Flows View Shows Nothing But Packets Exist

**Causes:**

* flow source is `FILTERED`, but the current filter is too strict
* selected protocol/packets are not TCP/UDP with ports (flows are built for TCP/UDP traffic)

**What to do:**

* in Flows press `V` and switch source to `ALL`
* clear filters (`Filter` -> Clear All), or load a profile without filters

---

#### 7) Why Is TLS Summary Visible As A Separate Packet Next To ACK?

This is normal.
One packet can be a plain ACK (without payload), while the next one carries part of the TLS handshake. That is why they appear as separate lines in the packet list.

---
