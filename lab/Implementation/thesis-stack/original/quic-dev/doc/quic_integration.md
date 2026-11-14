# QUIC Integration — How policyServer.c Interacts with quic-processor

This document explains how the main Policy Server (`policyServer.c`) integrates with the QUIC processing module located in `quic-processor/`.

## Compilation & Linkage

The QUIC module is compiled together with the main application as a single binary:

```makefile
# Makefile
SRCS-pb := policyServer.c \
           quic-processor/packet-processor.c \
           quic-processor/quicFunctions.c

CFLAGS += -Iquic-processor   # Header include path
```

The main file includes the QUIC header directly:
```c
// policyServer.c, line 25
#include "quic-processor/quicFunctions.h"
```

This gives `policyServer.c` access to:
- `QuicCryptoKeys` struct — holds all derived cryptographic material
- `getDomain()` — decrypts QUIC Initial packets and extracts the SNI domain
- `get_dcid()` — parses connection IDs from QUIC headers
- `quic_payload_crafter()` — builds encrypted CONNECTION_CLOSE frames
- Cryptographic primitives: `derive_initial_keys()`, `header_unmask()`, `aead_decrypt()`, etc.

---

## Shared State: The Global `keys` Variable

A single global `QuicCryptoKeys` struct is declared in `policyServer.c` (line 96):

```c
QuicCryptoKeys keys;
```

This struct (defined in `quicFunctions.h`) stores all QUIC cryptographic material:

| Field | Size | Purpose |
|---|---|---|
| `initial_secret` | 32 bytes | Base secret derived from the DCID |
| `client_initial_secret` | 32 bytes | Client-side initial secret |
| `quic_key` | 16 bytes | Client AEAD encryption key (AES-128) |
| `quic_iv` | 12 bytes | Client initialization vector |
| `quic_hp` | 16 bytes | Client header protection key |
| `quic_key_server` | 16 bytes | Server AEAD encryption key |
| `quic_iv_server` | 12 bytes | Server initialization vector |
| `quic_hp_server` | 16 bytes | Server header protection key |

The `keys` struct is populated by `getDomain()` during domain extraction and then reused by `quic_payload_crafter()` when crafting CONNECTION_CLOSE responses.

---

## Interaction Point 1: QUIC Packet Detection

In `packet_checker()` (line 2053), the server identifies QUIC Initial packets from incoming UDP traffic:

```c
// Criteria: destination port is 443 AND first byte matches QUIC Initial pattern
if ((rte_be_to_cpu_16(udp_hdr->dst_port) == 443) &&
    (((uint8_t)udp_payload[0] ^ 0xC0) & 0xF0) == 0) {
    port_statistics[0].quicCount++;
    return UDP_QUIC;  // constant: 312
}
```

The byte check `(udp_payload[0] ^ 0xC0) & 0xF0 == 0` verifies the long header form bit and the Initial packet type bits of the QUIC header.

---

## Interaction Point 2: Domain Extraction — `extractDomainfromQUIC()`

When `packet_checker()` returns `UDP_QUIC`, the main processing loop calls:

```c
// lcore_main_process(), line 2182-2185
char* domain = extractDomainfromQUIC(rx_pkt, true);
domain_check = domain_checker(domain);
```

### Inside `extractDomainfromQUIC()` (line 1198)

This function bridges DPDK packet buffers to the QUIC module:

```
rte_mbuf (DPDK packet)
  │
  ├─ Parse Ethernet → IPv4 → UDP headers
  │
  └─ Extract raw UDP payload (uint8_t pointer + length)
       │
       └─► getDomain(udp_payload, udp_payload_length, isClient, &keys)
             │
             │  ┌─────────────────────────────────────────────────┐
             │  │  getDomain() pipeline (packet-processor.c)      │
             │  │                                                 │
             │  │  1. get_dcid()       → parse DCID from header   │
             │  │  2. derive_initial_keys() → HKDF key derivation │
             │  │  3. header_unmask()  → remove header protection  │
             │  │  4. generate_aead_nonce() → XOR IV with PN      │
             │  │  5. aead_decrypt()   → AES-128-GCM decryption   │
             │  │  6. Parse TLS ClientHello extensions             │
             │  │  7. Extract SNI (Server Name Indication)         │
             │  └─────────────────────────────────────────────────┘
             │
             └─► returns domain string (e.g., "example.com")
```

**Key detail**: `getDomain()` receives a pointer to the global `keys` struct. It populates the struct with the derived keys (client and server) as a side effect, making them available for later use by the CONNECTION_CLOSE crafter.

---

## Interaction Point 3: QUIC Connection Termination

When a blacklisted domain is detected in a QUIC packet, the processing loop crafts and sends a CONNECTION_CLOSE response:

```c
// lcore_main_process(), lines 2254-2336
if (ip_hdr->next_proto_id == IPPROTO_UDP) {
    // 1. Copy the original packet
    struct rte_mbuf *conn_close_pkt_client = rte_pktmbuf_copy(rx_pkt, ...);

    // 2. Craft the CONNECTION_CLOSE response
    conn_close_quic_to_client(conn_close_pkt_client);

    // 3. Transmit via TX NIC
    rte_spinlock_lock(&tx_lock);
    rte_eth_tx_burst(1, 0, &conn_close_pkt_client, 1);
    rte_spinlock_unlock(&tx_lock);
}
```

### Inside `conn_close_quic_to_client()` (line 1501)

This function performs the following steps:

**Step 1 — Swap L2/L3/L4 headers** to make the packet appear as a response:
```
Original:  Client MAC/IP/Port → Server MAC/IP/Port
Swapped:   Server MAC/IP/Port → Client MAC/IP/Port
```

**Step 2 — Extract connection IDs** using `get_dcid()` from `quicFunctions.c`:
```c
uint8_t *dcid = get_dcid(udp_payload, true, &dcid_len);   // client's perspective
uint8_t *scid = get_dcid(udp_payload, false, &scid_len);  // server's perspective
```

**Step 3 — Craft encrypted QUIC payload** using `quic_payload_crafter()` from `packet-processor.c`:
```c
quic_payload_crafter(scid, scid_len, dcid, dcid_len,
                     udp_payload, &udp_payload_len, &keys, false);
```

The `quic_payload_crafter()` function:
1. Builds a `CONNECTION_CLOSE` frame (type `0x1c`) with error code `INTERNAL_ERROR` (0x02) and reason string `"BLOCKED_BY_POLICY_SERVER"`
2. Constructs a QUIC Initial header with correct version, connection IDs, and token
3. Encrypts the frame with AES-128-GCM using the server keys from the global `keys` struct
4. Applies header protection using `header_mask()`
5. Adds PKCS padding to meet QUIC minimum packet size (1200 bytes)
6. Writes the final encrypted packet into the output buffer

**Step 4 — Update packet metadata**:
```c
udp_hdr->dgram_len   = rte_cpu_to_be_16(new_payload_len + sizeof(struct rte_udp_hdr));
ip_hdr->total_length  = rte_cpu_to_be_16(sizeof(rte_ipv4_hdr) + sizeof(rte_udp_hdr) + new_payload_len);
rx_pkt->data_len = rx_pkt->pkt_len = total_frame_size;
ip_hdr->hdr_checksum  = rte_ipv4_cksum(ip_hdr);  // recalculate
```

### Server-Side Reset: `conn_close_quic_to_server()` (line 1446)

This variant sends a Stateless Reset to the origin server instead of a CONNECTION_CLOSE:
```c
generate_quic_stateless_reset(dcid, dcid_len, reset_token_secret,
                              udp_payload, &udp_payload_len);
```

> **Note:** Server-side reset is currently **commented out** in `lcore_main_process()` (line 2302). Only the client-side CONNECTION_CLOSE is active.

---

## Function Call Graph

```
policyServer.c                          quic-processor/
──────────────                          ───────────────

main()
  └─ OpenSSL_add_all_algorithms()       ← Required by QUIC crypto

lcore_main_process()
  │
  ├─ packet_checker()
  │   └─ identifies UDP_QUIC (312)
  │
  ├─ extractDomainfromQUIC()
  │   └──────────────────────────────► getDomain()          [packet-processor.c]
  │                                     ├─ get_dcid()       [quicFunctions.c]
  │                                     ├─ derive_initial_keys()  [quicFunctions.c]
  │                                     │   ├─ hkdf_extract()
  │                                     │   └─ hkdf_expand()
  │                                     ├─ header_unmask()  [quicFunctions.c]
  │                                     ├─ generate_aead_nonce()  [quicFunctions.c]
  │                                     └─ aead_decrypt()   [quicFunctions.c]
  │
  ├─ domain_checker(domain)
  │   └─ checks cache & SQLite
  │
  ├─ conn_close_quic_to_client()
  │   ├─ get_dcid()  ──────────────► get_dcid()            [quicFunctions.c]
  │   └──────────────────────────────► quic_payload_crafter()  [packet-processor.c]
  │                                     ├─ derive_initial_keys()  [quicFunctions.c]
  │                                     ├─ aead_encrypt()   [quicFunctions.c]
  │                                     └─ header_mask()    [quicFunctions.c]
  │
  └─ conn_close_quic_to_server()   (currently disabled)
      └──────────────────────────────► generate_quic_stateless_reset()
```

---

## Crypto Key Lifecycle

```
1. QUIC Initial packet arrives on RX NIC
        │
2. extractDomainfromQUIC() called
        │
3. getDomain() derives keys from DCID:
        │   ┌─────────────────────────────────────────────┐
        │   │  DCID ──► HKDF-Extract ──► initial_secret   │
        │   │  initial_secret ──► HKDF-Expand ──►          │
        │   │    ├── client_initial_secret                 │
        │   │    │    ├── quic_key (AES-128 key)           │
        │   │    │    ├── quic_iv  (nonce IV)              │
        │   │    │    └── quic_hp  (header protection)     │
        │   │    └── server_initial_secret                 │
        │   │         ├── quic_key_server                  │
        │   │         ├── quic_iv_server                   │
        │   │         └── quic_hp_server                   │
        │   └─────────────────────────────────────────────┘
        │
4. Client keys used to DECRYPT incoming packet → extract domain
        │
5. If domain is blacklisted:
        │
6. Server keys used by quic_payload_crafter() to ENCRYPT
   the CONNECTION_CLOSE response (impersonating the server)
```

---

## File Reference

| File | Role |
|---|---|
| `policyServer.c` | Main application; calls QUIC functions, owns the global `keys` struct |
| `quic-processor/quicFunctions.h` | Public API and `QuicCryptoKeys` struct definition |
| `quic-processor/quicFunctions.c` | Low-level crypto: HKDF, AEAD, header protection, VarInt decoding |
| `quic-processor/packet-processor.c` | High-level QUIC operations: `getDomain()`, `quic_payload_crafter()` |
