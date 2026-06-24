## User Guide (English)

### 1) What is `packet-monitor`

`packet-monitor` is a terminal (TUI) network traffic monitor/analyzer built with Python (Scapy + Urwid). It can capture traffic live (often requires root/admin), show packets in a table, aggregate conversations into flows, apply filters/exclusions, save/load profiles, and follow TCP streams with best-effort reassembly. For TLS it shows **handshake metadata only** (no decryption).

---

### 2) Quick Start

#### Live capture

1. Run with sufficient privileges (usually root/admin).
2. Select the correct interface (or capture on “any/multiple” if enabled).
3. Packets appear in the left panel; stats are on the right.

#### Use BPF to reduce noise (capture-time filter)

Examples:

* HTTPS only: `tcp port 443`
* DNS only: `udp port 53`
* Single host: `host 192.168.1.10`
* DNS + HTTPS: `udp port 53 or tcp port 443`

BPF is applied **before** packets enter the application (better performance, less memory).

---

### 3) Screen Layout

* **Left panel:** Packets list OR Flows view
* **Right panel:** Statistics
* **Bottom bar:** Status + hotkey hints

---

### 4) Keybindings (common defaults)

#### Global

* `F1` / `H` — Help
* `Q` — Quit
* `P` — Pause/Resume capture (live mode)
* `C` — Clear captured buffer
* `A` — Toggle auto-scroll
* `S` — Save/Export (if enabled)
* `/` — Payload search dialog
* `F` — Filter dialog
* `O` — Profiles (save/load/delete + presets)
* `G` — Toggle Flows view (Packets ↔ Flows)
* `E` — Exclusions manager

#### Packets view

* `Enter` — Packet details
* `T` — Follow stream (TCP reassembly / UDP quick filter)
* `X` — Exclude current stream or protocol

#### Flows view

* `V` — Toggle flow source: FILTERED vs ALL
* `Enter` — Drill-down (apply flow filter, return to packets)
* `D` — Flow details
* `T` — Follow stream (TCP stream view / TLS handshake summary)
* `X` — Exclude selected flow
* `B/K/R` — Sort flows (bytes/packets/rate) if enabled in your build

> Some builds also map these keys for non-English layouts.

---

### 5) Filtering (UI filters)

#### How filters combine

Fields in the Filter dialog combine as **AND** (all must match).
So `src_ip=...` AND `dst_ip=...` may easily result in **zero** packets.

Recommended OR-style helpers:

* Use `any_ip` to match packets where **src OR dst** equals the value.
* Use `any_port` to match packets where **src_port OR dst_port** equals the value.

Fields typically available:

* `proto`
* `src_ip`, `dst_ip`, `any_ip`
* `src_port`, `dst_port`, `any_port`
* `interface`
* `info` (regex supported)
* `payload` (regex supported)

#### Payload search (`/`)

Searches inside payload and applies a payload filter if matches are found.

---

### 6) Flows / Conversations View

Flows aggregate by (proto + endpoint A ip:port + endpoint B ip:port), with:

* packets, total bytes
* A→B bytes / B→A bytes
* first_seen / last_seen
* TCP SYN/FIN/RST counters (basic state hints)

#### Flow source: FILTERED vs ALL

* `FILTERED`: build flows from packets that match the current UI filters
* `ALL`: build flows from all captured packets

Toggle with `V`.

#### Drill-down

Press `Enter` on a flow to filter the packet list to that flow.

#### Exclude flow

Press `X` to exclude that flow from views.

---

### 7) Follow Stream (`T`)

#### TCP streams (best-effort reassembly)

* Two directions: Client→Server and Server→Client
* Reassembly by TCP `seq`:

  * segments sorted by sequence number
  * retransmission duplicates removed
  * missing ranges shown as placeholders (gaps)
* Display as UTF-8/ASCII with hex fallback
* Export stream text and raw direction files (if enabled)

#### TLS streams

TLS payload is encrypted. `packet-monitor` shows **handshake summary only**, such as:

* `TLS ClientHello SNI=... ALPN=...`
* `TLS ServerHello ver=... cipher=...`
* `Alert ...`

After handshake, you’ll see `ApplicationData (encrypted)`.

#### UDP streams

For UDP, “Follow stream” behaves like a quick 4-tuple filter (show only that exchange).

---

### 8) Profiles (`O`)

Profiles store:

* current UI filters
* exclusions (streams + protocols)

Location:

* `~/.packet-monitor/config.json`

Includes quick presets:

* `dns-only`
* `syn-only` (SYN without ACK)
* `arp-only`

---

## Troubleshooting (English)

### 1) My filter shows an empty screen

Filters are combined with **AND**.
If you set `src_ip=192.168.1.23` and `dst_ip=192.168.1.23`, it means “src AND dst are both this IP”, which is usually false.

**Fix:**

* Use `any_ip=192.168.1.23` for “src OR dst”.
* Use `any_port=9100` for “src_port OR dst_port”.

---

### 2) I don’t see TLS SNI/ALPN/ServerHello info on HTTPS

Common causes:

* You started `packet-monitor` **after** the connection was already established (handshake happens at the beginning).
* Your BPF/UI filter is too strict and filters out the handshake packets.

**Fix:**

* Start `packet-monitor` first, then run `curl https://google.com` again.
* Use BPF `tcp port 443` and avoid additional strict UI filters initially.

**Where to look:**
In packet `Info`, you should see:

* `TLS ClientHello SNI=... ALPN=...`
* `TLS ServerHello ver=... cipher=...`

---

### 3) Follow Stream does not show HTTPS (HTTP inside TLS) in plaintext

That’s expected: HTTPS is encrypted. Without MITM or key logging/decryption support, the tool cannot show HTTP content inside TLS. You will only see handshake metadata and encrypted ApplicationData.

---

### 4) Follow Stream shows little/no data

Possible reasons:

* The flow is very short (only handshake, little payload).
* You selected a packet that is not part of the intended TCP flow.

**Fix:**

* Switch to Flows view (`G`), select the correct flow, and press `T` there.
* Ensure you are following a TCP flow (UDP behaves differently).

---

### 5) No packets captured in live mode

Typical causes:

* Insufficient privileges (needs root/admin/capabilities).
* Wrong interface selected.
* BPF filter matches nothing.

**Fix:**

* Run with admin privileges.
* Verify interface names (`ip a` / `ifconfig`).
* Remove BPF or try a broad one like `tcp` or `udp`.

---

### 6) Flows view is empty but packet list has data

Possible causes:

* Flow source is set to `FILTERED` and your UI filters hide everything.
* Flows are built mainly for TCP/UDP with ports; other traffic may not appear.

**Fix:**

* In Flows view press `V` to switch source to `ALL`.
* Clear filters or load a clean profile.

---

### 7) Why do I see a TLS summary line next to an ACK line?

Normal behavior: one packet may be a pure ACK (no payload) and the next carries handshake bytes. They appear as separate lines in the packet list.

---

If you want, I can also format these into:

* `README.md` + `docs/user-guide.md` + `docs/troubleshooting.md`
  so GitHub renders them nicely and you can link from the README.
