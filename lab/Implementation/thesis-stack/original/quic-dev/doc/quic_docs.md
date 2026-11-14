# quicFunctions Module Documentation

This document provides a complete reference for the `quicFunctions.c` module — the low-level QUIC cryptographic library used by the Policy Server to decrypt incoming QUIC Initial packets and encrypt CONNECTION_CLOSE responses.

> [!CAUTION]
> **Testing Mode — Static Database**
>
> The current QUIC implementation does **not** query the live dashboard database. Instead, it uses a hardcoded local SQLite file:
>
> ```c
> // policyServer.c, line 81
> static const char *db_path = "/home/ir-policyserver/Documents/policyserver/NetPro-Policy-Server/policy.db";
> ```
>
> On startup, `init_database()` creates the `policies` table if it doesn't exist and inserts a single test entry:
>
> ```sql
> INSERT OR IGNORE INTO policies (id, ip_address, domain)
> VALUES ('0001', '192.168.69.12', 'mysite.local');
> ```
>
> This means QUIC blocking will only trigger for the domain `mysite.local` unless additional entries are added manually or Kafka sync is enabled.

> [!TIP]
> **How to enable the production database**
>
> 1. **Update `db_path`** in `policyServer.c` (line 81) to point to your production database location, or make it configurable via `config/config.cfg`.
> 2. **Ensure Kafka is running** — the `lcore_sync_database()` function consumes messages from a Kafka topic and populates the SQLite database with blacklisted domains pushed from the dashboard.
> 3. **Configure the Kafka broker** — set `KAFKA_BROKER` and `KAFKA_TOPIC` in `config/config.cfg` to match your deployment.
> 4. **Remove the test insert** — delete or comment out the hardcoded `INSERT OR IGNORE INTO policies ...` line in `init_database()` (around line 1710 of `policyServer.c`) so the database is populated solely by Kafka messages.
> 5. **Rebuild** — run `make` to recompile with the changes.

---

**Source files:**

- [quicFunctions.c](../quic-processor/quicFunctions.c) — Implementation (719 lines)
- [quicFunctions.h](../quic-processor/quicFunctions.h) — Public API and data structures (325 lines)

**Dependencies:** OpenSSL (`libcrypto`) — `EVP`, `HMAC`, `AES` APIs

---

## Table of Contents

1. [Data Structures](#data-structures)
2. [Header Parsing Functions](#header-parsing-functions)
3. [Header Protection Functions](#header-protection-functions)
4. [Key Derivation (HKDF)](#key-derivation-hkdf)
5. [AEAD Encryption / Decryption](#aead-encryption--decryption)
6. [Constants & Defines](#constants--defines)
7. [RFC References](#rfc-references)

---

## Data Structures

### `QuicCryptoKeys`

The central data structure that holds all cryptographic material needed for QUIC Initial packet processing. Defined in `quicFunctions.h`.

```c
typedef struct {
    uint8_t initial_secret[SECRET_SIZE];           // 32 bytes
    uint8_t client_initial_secret[SECRET_SIZE];    // 32 bytes
    uint8_t server_initial_secret[SECRET_SIZE];    // 32 bytes

    // Client keys (for decrypting incoming Initial packets)
    uint8_t quic_key[QUIC_KEY_SIZE];               // 16 bytes — AES-128 key
    uint8_t quic_iv[QUIC_IV_SIZE];                 // 12 bytes — Initialization Vector
    uint8_t quic_hp[QUIC_HP_SIZE];                 // 16 bytes — Header Protection key

    // Server keys (for encrypting CONNECTION_CLOSE responses)
    uint8_t quic_key_server[QUIC_KEY_SIZE];        // 16 bytes
    uint8_t quic_iv_server[QUIC_IV_SIZE];          // 12 bytes
    uint8_t quic_hp_server[QUIC_HP_SIZE];          // 16 bytes
} QuicCryptoKeys;
```

### `HkdfExpandArgs`

Helper struct for passing arguments to `hkdf_expand_thread()`, enabling potential parallelization of key derivation.

```c
typedef struct {
    const uint8_t* secret;
    size_t secret_len;
    const uint8_t* info;
    size_t info_len;
    uint8_t* output;
    size_t output_len;
} HkdfExpandArgs;
```

---

## Header Parsing Functions

These functions parse the QUIC Long Header format to extract connection IDs, packet numbers, and field offsets.

### `pn_length()`

```c
int pn_length(const uint8_t* demasked_header);
```

Extracts the packet number length from a **demasked** (unprotected) header. The length is encoded in the lowest 2 bits of the first byte.

| First byte bits 0–1 | Packet number length |
| -------------------- | -------------------- |
| `0b00`               | 1 byte               |
| `0b01`               | 2 bytes              |
| `0b10`               | 3 bytes              |
| `0b11`               | 4 bytes              |

**Formula:** `(demasked_header[0] & 0x03) + 1`

### `pn()`

```c
uint32_t pn(const uint8_t *demasked_header, int pn_length, int header_length);
```

Extracts the actual packet number value from the last `pn_length` bytes of the demasked header. The bytes are read in big-endian order and assembled into a 32-bit integer.

**Parameters:**

| Name              | Description                                     |
| ----------------- | ----------------------------------------------- |
| `demasked_header` | Pointer to the full demasked header              |
| `pn_length`       | Number of bytes used for the packet number (1–4) |
| `header_length`   | Total length of the demasked header              |

### `pn_offset()`

```c
int pn_offset(const uint8_t* header);
```

Computes the byte offset where the packet number begins in a QUIC Long Header. Uses a simplified fixed-layout calculation:

```
offset = 5 (fixed header) + DCID_len + SCID_len + token_length + 1 + 2 + 2
```

> [!NOTE]
> This is a simpler version used internally. For robust parsing with bounds checking, see [`get_pn_offset()`](#get_pn_offset).

### `get_dcid()`

```c
uint8_t* get_dcid(const uint8_t* header, bool isClient, uint8_t* dcid_length);
```

Extracts a Connection ID from the QUIC header. The `isClient` flag determines which CID to return:

| `isClient` | Returns                | Location         |
| ---------- | ---------------------- | ---------------- |
| `true`     | Destination CID (DCID) | Byte 6 onwards   |
| `false`    | Source CID (SCID)      | After DCID field |

**QUIC Long Header layout:**

```
Byte 0:       Flags
Bytes 1–4:    Version
Byte 5:       DCID Length
Bytes 6...:   DCID
Next byte:    SCID Length
Next bytes:   SCID
```

### `decode_varint()`

```c
int decode_varint(const uint8_t *buf, uint64_t *value);
```

Decodes a QUIC Variable-Length Integer (RFC 9000, Section 16). The first 2 bits of the first byte encode the length:

| Prefix bits | Byte length | Max value                 |
| ----------- | ----------- | ------------------------- |
| `00`        | 1           | 63                        |
| `01`        | 2           | 16,383                    |
| `10`        | 4           | 1,073,741,823             |
| `11`        | 8           | 4,611,686,018,427,387,903 |

**Returns:** Number of bytes consumed (1, 2, 4, or 8), or `-1` on error.

### `get_pn_offset()`

```c
int get_pn_offset(const uint8_t *header, size_t header_len);
```

Computes the packet number offset with full bounds checking and VarInt decoding. This is the robust version used by `header_unmask()` and `header_mask()`.

**Parsing sequence:**

```
Fixed header (5 bytes)
  → DCID length (1 byte) → DCID (variable)
    → SCID length (1 byte) → SCID (variable)
      → Token length (VarInt) → Token (variable)
        → Payload length (VarInt)
          → PN starts here ←
```

**Returns:** The byte offset where the packet number begins, or `-1` on error.

---

## Header Protection Functions

QUIC encrypts parts of the header (first byte flags + packet number) using AES-ECB. These functions apply and remove that protection.

### `header_unmask()`

```c
void header_unmask(const uint8_t* protected_packet, size_t packet_len,
                   const uint8_t* hp_key, uint8_t** output, size_t* output_len);
```

Removes header protection from an incoming QUIC packet. This is required before the packet number can be read and AEAD decryption can proceed.

**Algorithm (per RFC 9001, Section 5.4):**

1. Compute `pn_offset` using `get_pn_offset()`
2. Extract a 16-byte **sample** starting at `pn_offset + 4`
3. Encrypt the sample with AES-ECB using the HP key → produces a **mask**
4. XOR `mask[0] & 0x0F` with the first byte to reveal the PN length bits
5. Try PN lengths 1–4 until `(first_byte & 0x03) + 1` matches the attempted length
6. XOR `mask[1..N]` with the PN bytes to reveal the actual packet number
7. Output the demasked header via `realloc`'ed buffer

```
Protected:   [flags⊕mask] [version] [CIDs...] [length] [PN⊕mask]
                 ↓ unmask                                    ↓ unmask
Demasked:    [flags]       [version] [CIDs...] [length] [PN]
```

### `header_mask()`

```c
void header_mask(const uint8_t* protected_packet, size_t packet_len,
                 int header_offset, const uint8_t* hp_key,
                 uint8_t** output, size_t* output_len);
```

The inverse of `header_unmask()` — applies header protection to an outgoing packet. Used by `quic_payload_crafter()` when constructing CONNECTION_CLOSE responses.

**Steps:**

1. Extract 16-byte sample at `pn_offset + 4`
2. AES-ECB encrypt the sample → mask
3. Read PN length from (currently unmasked) first byte
4. XOR `mask[0] & 0x0F` with the first byte
5. XOR `mask[1..N]` with the PN bytes

---

## Key Derivation (HKDF)

These functions implement the HKDF key derivation scheme (RFC 5869) as specified by QUIC-TLS (RFC 9001) for Initial packet encryption.

### `hkdf_extract()`

```c
void hkdf_extract(const uint8_t* salt, size_t salt_len,
                  const uint8_t* ikm, size_t ikm_len,
                  uint8_t* prk, size_t prk_len);
```

Performs HKDF-Extract: `PRK = HMAC-SHA256(salt, IKM)`

Used to derive the initial secret from the QUIC Initial Salt and the Destination Connection ID.

### `hkdf_expand()`

```c
void hkdf_expand(const uint8_t* prk, size_t prk_len,
                 const uint8_t* info, size_t info_len,
                 uint8_t* output, size_t output_len);
```

Performs HKDF-Expand: iteratively computes `T(i) = HMAC-SHA256(PRK, T(i-1) | info | i)` until enough key material is generated.

Used to derive:

- Client/server initial secrets from the initial secret
- AEAD keys, IVs, and HP keys from the initial secrets

### `hkdf_expand_thread()`

```c
void* hkdf_expand_thread(void* arg);
```

Wrapper around `hkdf_expand()` that accepts `HkdfExpandArgs*`. Designed for potential pthread parallelization, though currently executed sequentially.

### `derive_initial_keys()`

```c
void derive_initial_keys(const uint8_t* dcid, int dcid_size,
                         bool is_client, QuicCryptoKeys* keys);
```

The top-level key derivation function. Derives all 6 cryptographic keys (client + server × key/IV/HP) from a single Destination Connection ID.

**Derivation tree:**

```
DCID
 │
 ├─ HKDF-Extract(initial_salt, DCID) ──► initial_secret
 │
 ├─ HKDF-Expand(initial_secret, "tls13 client in") ──► client_initial_secret
 │   ├─ HKDF-Expand(..., "tls13 quic key") ──► quic_key        (16 bytes, AES-128)
 │   ├─ HKDF-Expand(..., "tls13 quic iv")  ──► quic_iv         (12 bytes)
 │   └─ HKDF-Expand(..., "tls13 quic hp")  ──► quic_hp         (16 bytes)
 │
 └─ HKDF-Expand(initial_secret, "tls13 server in") ──► server_initial_secret
     ├─ HKDF-Expand(..., "tls13 quic key") ──► quic_key_server (16 bytes, AES-128)
     ├─ HKDF-Expand(..., "tls13 quic iv")  ──► quic_iv_server  (12 bytes)
     └─ HKDF-Expand(..., "tls13 quic hp")  ──► quic_hp_server  (16 bytes)
```

**Initial Salt** (QUIC v1, RFC 9001):

```
0x38762cf7f55934b34d179ae6a4c80cadccbb7f0a
```

**HKDF Info labels** (TLS 1.3 format):

| Label                | Encoded info bytes                                          | Output                |
| -------------------- | ----------------------------------------------------------- | --------------------- |
| `"tls13 client in"`  | `00 20 0f 74 6c 73 31 33 20 63 6c 69 65 6e 74 20 69 6e 00` | Client initial secret |
| `"tls13 server in"`  | `00 20 0f 74 6c 73 31 33 20 73 65 72 76 65 72 20 69 6e 00` | Server initial secret |
| `"tls13 quic key"`   | `00 10 0e 74 6c 73 31 33 20 71 75 69 63 20 6b 65 79 00`    | AEAD key              |
| `"tls13 quic iv"`    | `00 0c 0d 74 6c 73 31 33 20 71 75 69 63 20 69 76 00`       | Initialization vector |
| `"tls13 quic hp"`    | `00 10 0d 74 6c 73 31 33 20 71 75 69 63 20 68 70 00`       | Header protection key |

---

## AEAD Encryption / Decryption

QUIC uses AES-128-GCM for authenticated encryption of packet payloads. These functions handle encryption and decryption using OpenSSL's EVP interface.

### `generate_aead_nonce()`

```c
void generate_aead_nonce(const uint8_t *iv, size_t iv_len,
                         uint64_t packet_number, uint8_t *nonce);
```

Generates the AEAD nonce by XORing the IV with the packet number (RFC 9001, Section 5.3):

```
nonce[i] = iv[i] ⊕ padded_packet_number[i]
```

The packet number (up to 62 bits) is zero-padded to match the IV length (12 bytes) before XOR.

### `aead_decrypt()`

```c
int aead_decrypt(
    const uint8_t *encryption_key, uint32_t key_len,
    const uint8_t *iv, uint32_t iv_len,
    const uint8_t *associated_data, uint32_t ad_len,
    const uint8_t *ciphertext_with_tag, uint32_t ciphertext_with_tag_len,
    uint8_t *plaintext);
```

Decrypts an AES-GCM protected QUIC payload. Used to decrypt incoming QUIC Initial packets to reveal the inner TLS ClientHello.

**Parameters:**

| Name                     | Description                                                    |
| ------------------------ | -------------------------------------------------------------- |
| `encryption_key`         | The AEAD key (`quic_key`, 16 bytes for AES-128)                |
| `iv`                     | The nonce generated by `generate_aead_nonce()`                 |
| `associated_data`        | The demasked QUIC header (authenticated but not encrypted)     |
| `ciphertext_with_tag`    | Encrypted payload + 16-byte GCM authentication tag at the end |
| `plaintext`              | Output buffer for the decrypted TLS record                     |

**Returns:** Length of decrypted plaintext on success, `-1` on failure.

**Cipher selection:** `key_len == 16` → AES-128-GCM, otherwise → AES-256-GCM.

### `aead_encrypt()`

```c
int aead_encrypt(
    const uint8_t *encryption_key, uint32_t key_len,
    const uint8_t *iv, uint32_t iv_len,
    const uint8_t *associated_data, uint32_t ad_len,
    const uint8_t *plaintext, uint32_t plaintext_len,
    uint8_t *ciphertext_with_tag);
```

Encrypts a QUIC payload using AES-GCM. Used by `quic_payload_crafter()` in `packet-processor.c` to encrypt CONNECTION_CLOSE frames before transmission.

**Output format:**

```
[ciphertext (N bytes)] [GCM tag (16 bytes)]
```

**Returns:** Total output length (`ciphertext_len + 16`) on success, `-1` on failure.

---

## Constants & Defines

Defined in `quicFunctions.h`:

```c
#define SECRET_SIZE   32    // HMAC-SHA256 output size
#define QUIC_KEY_SIZE 16    // AES-128 key size
#define QUIC_IV_SIZE  12    // GCM nonce / IV size
#define QUIC_HP_SIZE  16    // Header protection key size (AES-128)
```

---

## RFC References

| Specification                                                      | Relevant sections                                                             |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| [RFC 9000](https://www.rfc-editor.org/rfc/rfc9000) — QUIC Transport | Section 16 (Variable-Length Integer), Section 17 (Packet Formats)              |
| [RFC 9001](https://www.rfc-editor.org/rfc/rfc9001) — QUIC-TLS       | Section 5.2 (Initial Secrets), Section 5.3 (AEAD Nonce), Section 5.4 (Header Protection) |
| [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869) — HKDF           | Extract and Expand operations                                                  |
| [RFC 5116](https://www.rfc-editor.org/rfc/rfc5116) — AEAD           | AES-GCM interface                                                              |
