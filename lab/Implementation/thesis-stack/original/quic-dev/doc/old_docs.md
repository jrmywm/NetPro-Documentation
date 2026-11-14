# policyServer.c — Code Documentation

This document covers all non-QUIC functions in `policyServer.c` (2620 lines). For QUIC-specific documentation, see [quic_docs.md](quic_docs.md) and [quic_integration.md](quic_integration.md).

**Source:** [policyServer.c](../policyServer.c)

---

## Table of Contents

1. [Global State & Data Structures](#global-state--data-structures)
2. [Logging & Utilities](#logging--utilities)
3. [Configuration](#configuration)
4. [DPDK Port Initialization](#dpdk-port-initialization)
5. [Statistics & Telemetry](#statistics--telemetry)
6. [Domain Extraction](#domain-extraction)
7. [Connection Reset (TCP)](#connection-reset-tcp)
8. [Database & Caching](#database--caching)
9. [Kafka Synchronization](#kafka-synchronization)
10. [Heartbeat](#heartbeat)
11. [Lcore Functions](#lcore-functions)
12. [Main Entry Point](#main-entry-point)

---

## Global State & Data Structures

### Constants & Macros

```c
#define MAX_PACKET_LEN     // from config
#define BURST_SIZE         // from config
#define CACHE_SIZE    1000
#define MAX_STRINGS   200

#define HTTP_GET_MAGIC     "GET /"
#define TLS_MAGIC          "\x16\x03\x01"
#define HTTP_GET           112    // packet_checker return code
#define TLS_CLIENT_HELLO   212    // packet_checker return code
#define UDP_QUIC           312    // packet_checker return code
```

### `LogLevel` enum

```c
typedef enum { LOG_LEVEL_INFO, LOG_LEVEL_WARNING, LOG_LEVEL_ERROR } LogLevel;
```

### `port_statistics_data`

Per-port traffic counters updated by `collect_stats()`:

| Field             | Type       | Description                         |
| ----------------- | ---------- | ----------------------------------- |
| `tx_count`        | `uint64_t` | Packets transmitted                 |
| `rx_count`        | `uint64_t` | Packets received                    |
| `tx_size`         | `uint64_t` | Bytes transmitted                   |
| `rx_size`         | `uint64_t` | Bytes received                      |
| `dropped`         | `uint64_t` | Dropped packets                     |
| `rstClient`       | `uint64_t` | TCP RST sent to clients             |
| `rstServer`       | `uint64_t` | TCP RST sent to servers             |
| `quicCount`       | `uint64_t` | QUIC packets detected               |
| `connectionClose` | `uint64_t` | QUIC CONNECTION_CLOSE sent          |
| `throughput`      | `long int` | Calculated throughput (bytes/period) |
| `err_rx`          | `uint64_t` | RX errors                           |
| `err_tx`          | `uint64_t` | TX errors                           |

### `DomainCache`

In-memory hash table for fast domain lookups:

```c
typedef struct {
    char domain[MAX_STRINGS];
    char id[MAX_STRINGS];
} DomainCache;

static DomainCache domain_cache[CACHE_SIZE];
```

### `IPCache`

Cache for IP address lookups:

```c
typedef struct {
    char ip_address[INET_ADDRSTRLEN];
    char id[MAX_STRINGS];
} IPCache;

static IPCache ip_cache[CACHE_SIZE];
```

### Key Global Variables

| Variable            | Type              | Description                                 |
| ------------------- | ----------------- | ------------------------------------------- |
| `db`                | `sqlite3*`        | SQLite database handle                      |
| `db_path`           | `const char*`     | Hardcoded path to `policy.db`               |
| `force_quit`        | `bool`            | Graceful shutdown flag                      |
| `tx_lock`           | `rte_spinlock_t`  | Spinlock for TX port access                 |
| `port_statistics[]` | `port_stats_data` | Per-port statistics array                   |
| `domain_cache[]`    | `DomainCache`     | Hash table for cached domain lookups        |
| `hitCount[][]`      | `char[][]`        | Buffer of policy IDs that were hit          |
| `hitCounter`        | `int`             | Current index in `hitCount`                 |
| `HOSTNAME`          | `char*`           | Dashboard API base URL (from config)        |
| `PS_ID`             | `char*`           | Policy Server ID (from config)              |
| `KAFKA_BROKER`      | `char*`           | Kafka bootstrap server address (from config)|
| `KAFKA_TOPIC`       | `char*`           | Kafka topic name (from config)              |

---

## Logging & Utilities

### `logMessage()` — line 226

```c
void logMessage(LogLevel level, const char *filename, int line,
                const char *format, ...);
```

Writes a timestamped, leveled log message to `log/policyServer.log`. Creates the `log/` directory and file if they don't exist.

**Log format:**
```
[2026-02-18 12:00:00] [INFO] [policyServer.c:2504] Configuration File Updated
```

### `getLogLevelString()` — line 162

```c
char getLogLevelString(LogLevel level);
```

Returns the string label for a `LogLevel` value: `"INFO"`, `"WARNING"`, or `"ERROR"`.

### `generate_string_time()` — line 205

```c
char generate_string_time(int type);
```

Allocates and returns a formatted timestamp string. The `type` parameter selects the timezone:

| Type    | Value | Format                          |
| ------- | ----- | ------------------------------- |
| `LOCAL` | 0     | `YYYY-MM-DD HH:MM:SS` (local)  |
| `GMT`   | 1     | `YYYY-MM-DDTHH:MM:SS.000Z` (UTC) |

### `sleep_5_65ms()` — line 183

```c
void sleep_5_65ms();
```

Inline busy-wait sleep for 5.65 milliseconds using `nanosleep()`.

### `segfault_handler()` — line 191

```c
void segfault_handler(int sig);
```

`SIGSEGV` signal handler that logs a backtrace (up to 64 frames) and terminates. Registered in `main()`.

### `signal_handler()` — line 867

```c
void signal_handler(int signum);
```

`SIGINT` / `SIGTERM` handler that sets `force_quit = true` for graceful shutdown.

### `write_callback()` — line 882

```c
size_t write_callback(void *contents, size_t size, size_t nmemb, void *userp);
```

libcurl write callback. Silently discards response body data (returns `size * nmemb` without storing it).

---

## Configuration

### `load_config_file()` — line 778

```c
int load_config_file();
```

Reads `config/config.cfg` and sets global variables. The config file uses `key = value` format.

**Parsed keys:**

| Config key            | Global variable       | Type     |
| --------------------- | --------------------- | -------- |
| `MAX_PACKET_LEN`      | `MAX_PACKET_LEN`      | `int`    |
| `RX_RING_SIZE`        | `RX_RING_SIZE`        | `int`    |
| `TX_RING_SIZE`        | `TX_RING_SIZE`        | `int`    |
| `NUM_MBUFS`           | `NUM_MBUFS`           | `int`    |
| `MBUF_CACHE_SIZE`     | `MBUF_CACHE_SIZE`     | `int`    |
| `BURST_SIZE`          | `BURST_SIZE`          | `int`    |
| `MAX_TCP_PAYLOAD_LEN` | `MAX_TCP_PAYLOAD_LEN` | `int`    |
| `HOSTNAME`            | `HOSTNAME`            | `string` |
| `PS_ID`               | `PS_ID`               | `string` |
| `TIMER_PERIOD_STATS`  | `TIMER_PERIOD_STATS`  | `int`    |
| `TIMER_PERIOD_SEND`   | `TIMER_PERIOD_SEND`   | `int`    |
| `KAFKA_BROKER`        | `KAFKA_BROKER`        | `string` |
| `KAFKA_TOPIC`         | `KAFKA_TOPIC`         | `string` |

**Returns:** `0` on success, `1` if the config file cannot be opened.

---

## DPDK Port Initialization

### `port_init()` — line 434

```c
int port_init(uint16_t port, struct rte_mempool *mbuf_pool);
```

Configures and starts a DPDK Ethernet port:

1. Queries device info via `rte_eth_dev_info_get()`
2. Configures the port with `rte_eth_dev_configure()` (1 RX queue, 1 TX queue)
3. Adjusts RX/TX descriptor counts with `rte_eth_dev_adjust_nb_rx_tx_desc()`
4. Sets up the RX and TX queues
5. Starts the port with `rte_eth_dev_start()`
6. Enables promiscuous mode with `rte_eth_promiscuous_enable()`

**Returns:** `0` on success, negative value on error.

---

## Statistics & Telemetry

### `collect_stats()` — line 979

```c
void collect_stats();
```

Retrieves per-port statistics from DPDK (`rte_eth_stats_get()`), updates the global `port_statistics[]` array, resets hardware counters, and calculates throughput.

### `clear_stats()` — line 536

```c
void clear_stats(void);
```

Zeroes out all `port_statistics[]` entries.

### `print_stats()` — line 586

```c
void print_stats();
```

Prints a formatted statistics table to stdout using ANSI color codes. Includes RX/TX counts, sizes, errors, throughput, domain cache size, and QUIC counters.

### `generate_filename()` — line 545

```c
char generate_filename();
```

Generates a CSV filename based on the current date in the format: `stat/stat_YYYY-MM-DD.csv`. Creates the `stat/` directory if needed.

### `open_file()` — line 518

```c
FILE open_file(const char *filename);
```

Opens a file in append mode (`"a"`). Exits the program on failure.

### `print_stats_csv_header()` — line 743

```c
void print_stats_csv_header(FILE *f);
```

Writes the CSV header row with column names for all statistics fields.

### `print_stats_csv()` — line 754

```c
void print_stats_csv(FILE *f, char *timestamp);
```

Writes a single CSV data row with the current statistics and the given timestamp.

### `print_stats_file()` — line 1023

```c
void print_stats_file(FILE **f_stat);
```

Manages the statistics output file lifecycle. Opens a new file (with header) if `*f_stat` is NULL, then writes the current stats as a CSV row.

### `populate_json_stats()` — line 933

```c
void populate_json_stats(json_t *jsonArray, char *timestamp);
```

Creates a JSON object with all current statistics and appends it to the provided JSON array. Uses the Jansson library.

### `populate_json_hitcount()` — line 900

```c
void populate_json_hitcount(json_t *jsonArray);
```

Iterates over `db_hit_count[]` and appends JSON objects (with `id` and `hit_count`) for entries with non-zero hit counts.

### `send_stats()` — line 1126

```c
void send_stats(json_t *jsonArray);
```

Sends the accumulated statistics JSON array to the dashboard API via HTTP POST (`{HOSTNAME}/ps/stats`). Uses libcurl. Clears the JSON array after a successful send.

### `send_hitcount_to_server()` — line 1053

```c
void send_hitcount_to_server(json_t *jsonArray);
```

Sends hit count data to the dashboard API via HTTP POST (`{HOSTNAME}/ps/hitcount`). Resets the `db_hit_count[]` array after sending.

### `runner_scheduler()` — line 1933

```c
void runner_scheduler(int *run_stats, int *run_send, int *run_file,
                      int *last_run_stats, int *last_run_send, int *last_run_file);
```

Time-based scheduler that sets run flags based on the current clock:

| Flag         | Trigger condition                            |
| ------------ | -------------------------------------------- |
| `run_stats`  | Current second is divisible by `TIMER_PERIOD_STATS` |
| `run_send`   | Current minute is divisible by `TIMER_PERIOD_SEND`  |
| `run_file`   | Same as `run_send`, but only at second 59    |

---

## Domain Extraction

### `extractDomainfromHTTP()` — line 1325

```c
char extractDomainfromHTTP(struct rte_mbuf *pkt);
```

Extracts the domain from an HTTP GET request by scanning the TCP payload for the `Host:` header. Parses L2 → L3 → L4 headers from the DPDK mbuf, then searches for `"Host: "` in the payload.

**Returns:** Allocated string with the domain name, or `NULL` if not found.

### `extractDomainfromHTTPS()` — line 1236

```c
char extractDomainfromHTTPS(struct rte_mbuf *pkt);
```

Extracts the domain from a TLS ClientHello by parsing the SNI (Server Name Indication) extension:

1. Parses L2 → L3 → L4 → TLS record headers
2. Skips the TLS handshake header, session ID, cipher suites, and compression methods
3. Walks the TLS extensions list looking for extension type `0x0000` (SNI)
4. Extracts the server name from the SNI extension data

**Returns:** Allocated string with the domain name, or `NULL` if not found.

### `packet_checker()` — line 2053

```c
int packet_checker(struct rte_mbuf *pkt);
```

Classifies an incoming packet by inspecting its protocol headers:

```
Ethernet → IPv4 → TCP or UDP
                    │         │
                    │         └─ Port 443 + QUIC Initial header → UDP_QUIC (312)
                    │
                    ├─ Payload starts with "GET /" → HTTP_GET (112)
                    ├─ Payload starts with 0x16 0x03 0x01 + type 0x01 → TLS_CLIENT_HELLO (212)
                    └─ Otherwise → 0 (ignored)
```

**Returns:** `HTTP_GET` (112), `TLS_CLIENT_HELLO` (212), `UDP_QUIC` (312), or `0`.

---

## Connection Reset (TCP)

### `reset_tcp_client()` — line 1388

```c
void reset_tcp_client(struct rte_mbuf *rx_pkt);
```

Crafts and sends a TCP RST packet **to the client** to terminate a blacklisted connection. The RST appears to come from the server.

**Steps:**

1. Clone the received packet
2. Swap source/destination MAC addresses
3. Swap source/destination IP addresses
4. Set TCP flags to `RST | ACK`
5. Set the sequence number to match the client's expected value (`ack_num` from original packet)
6. Recalculate IP and TCP checksums
7. Transmit via Port 1 (TX NIC) with spinlock protection

### `reset_tcp_server()` — line 1567

```c
void reset_tcp_server(struct rte_mbuf *rx_pkt);
```

Crafts and sends a TCP RST packet **to the server** to tear down the server-side connection. Operates similarly to `reset_tcp_client()` but keeps the original direction (client→server MAC/IP) and adjusts the sequence number accordingly.

---

## Database & Caching

### `init_database()` — line 1648

```c
void init_database();
```

Opens (or creates) the SQLite database at `db_path`. If the `policies` table doesn't exist, creates it with columns `(id TEXT PRIMARY KEY, ip_address TEXT, domain TEXT)` and inserts a test entry for `mysite.local`.

### `delete_database()` — line 1729

```c
void delete_database();
```

Closes the SQLite database handle and deletes the database file from disk. Called during shutdown in `main()`.

### `hash_function()` — line 1826

```c
unsigned int hash_function(const char *str);
```

DJB2 hash function for domain cache lookups. Returns `hash % CACHE_SIZE`.

### `domain_checker()` — line 1839

```c
bool domain_checker(char *domain);
```

Checks if a domain is blacklisted using a two-tier lookup:

1. **Cache check** — hash the domain and probe `domain_cache[]` (linear probing)
2. **Database fallback** — if not in cache, query SQLite: `SELECT id FROM policies WHERE domain = '<domain>'`
3. **Cache update** — on a database hit, insert the domain into the cache for future lookups
4. **Hit counting** — records the policy ID in `hitCount[]` for telemetry

**Returns:** `true` if the domain is blacklisted, `false` otherwise.

> [!WARNING]
> The SQL query on line 1883 uses string formatting (`snprintf`) instead of parameterized queries, creating a potential SQL injection vector. Should be replaced with `sqlite3_bind_text()`.

### `ip_checker()` — line 1753

```c
bool ip_checker(struct rte_mbuf *rx_pkt);
```

Extracts the source IP from a packet and checks it against the `ip_cache[]`. Uses a similar hash + linear probing strategy as `domain_checker()`.

**Returns:** `true` if the IP is found in the cache, `false` otherwise.

### `countStrings()` — line 1604

```c
void countStrings(char strings[CACHE_SIZE][MAX_STRINGS], int numStrings);
```

Counts occurrences of each unique policy ID string in the `hitCount` buffer and accumulates the counts in `db_hit_count[]`. Called periodically from `lcore_stats_process()`.

---

## Kafka Synchronization

### `msg_consume()` — line 293

```c
void msg_consume(rd_kafka_message_t *rkmessage, sqlite3 *db);
```

Processes a single Kafka message. Parses the JSON payload and performs database operations:

**Expected JSON operations:**

| `operation` field | Action |
| ----------------- | ------ |
| `"create"`        | `INSERT INTO policies (id, ip_address, domain) VALUES (...)` |
| `"delete"`        | `DELETE FROM policies WHERE id = '...'` |

Also handles error messages and end-of-partition notifications.

---

## Heartbeat

### `lcore_heartbeat_process()` — line 2347

```c
void lcore_heartbeat_process();
```

Runs on the **main lcore** (not a worker). Sends a JSON heartbeat to `{HOSTNAME}/ps/heartbeat` every 5 seconds via HTTP POST using libcurl.

**Payload:**
```json
[{"ps_id": "<PS_ID>", "time": "2026-02-18T12:00:00.000Z"}]
```

Runs until `force_quit` is set.

---

## Lcore Functions

### `lcore_main_process()` — line 2132

```c
void lcore_main_process(void);
```

The main packet processing loop, running on **N worker lcores**. Each iteration:

1. **Receive** a burst of packets from Port 0 (RX NIC) using `rte_eth_rx_burst()`
2. **Classify** each packet with `packet_checker()`
3. **Extract domain** based on protocol:
   - `HTTP_GET` → `extractDomainfromHTTP()`
   - `TLS_CLIENT_HELLO` → `extractDomainfromHTTPS()`
   - `UDP_QUIC` → `extractDomainfromQUIC()`
4. **Check blacklist** with `domain_checker()`
5. **Block if blacklisted:**
   - TCP → clone packet, call `reset_tcp_client()` (and optionally `reset_tcp_server()`)
   - UDP/QUIC → clone packet, call `conn_close_quic_to_client()`
6. **Free** processed packets

### `lcore_stats_process()` — line 1963

```c
void lcore_stats_process(void);
```

The statistics collection loop, running on **1 dedicated lcore**. Uses `runner_scheduler()` to time the following tasks:

| Task                    | Trigger                 | Actions |
| ----------------------- | ----------------------- | ------- |
| Collect stats           | Every `TIMER_PERIOD_STATS` seconds | `collect_stats()`, `print_stats()`, `print_stats_file()`, `populate_json_stats()`, `clear_stats()` |
| Send stats to dashboard | Every `TIMER_PERIOD_SEND` minutes  | `populate_json_hitcount()`, `send_hitcount_to_server()`, `send_stats()` |
| Rotate CSV file         | At second 59 of send intervals     | `fclose()` current file (a new one is opened on next collect) |

### `lcore_sync_database()` — line 2404

```c
void lcore_sync_database();
```

The Kafka consumer loop, running on **1 dedicated lcore**:

1. Creates a Kafka consumer (`rd_kafka_new()`)
2. Subscribes to `KAFKA_TOPIC`
3. Opens the SQLite database
4. Loops until `force_quit`:
   - `rd_kafka_consume()` with 1-second timeout
   - Passes each message to `msg_consume()` for database updates
5. Cleans up Kafka handles and closes the database

---

## Main Entry Point

### `main()` — line 2480

```c
int main(int argc, char *argv[]);
```

Initialization and lcore dispatch sequence:

```
1.  Register SIGSEGV handler
2.  init_database()
3.  OpenSSL_add_all_algorithms()
4.  load_config_file()
5.  rte_eal_init()          ← DPDK EAL initialization
6.  Register SIGINT/SIGTERM handlers
7.  Clear port_statistics[]
8.  Check available ports (expects 2)
9.  Create mbuf memory pool
10. port_init() for each port
11. Check lcore count (requires ≥ 4)
12. Assign lcores:
    ├─ N-3 lcores → lcore_main_process  (packet workers)
    ├─ 1 lcore    → lcore_stats_process (statistics)
    └─ 1 lcore    → lcore_sync_database (Kafka consumer)
13. Launch worker lcores via rte_eal_remote_launch()
14. Run lcore_heartbeat_process() on main lcore (blocking)
15. Wait for all worker lcores to finish
16. delete_database()
17. rte_eal_cleanup()
```

**Minimum requirements:**

| Resource  | Minimum | Purpose                               |
| --------- | ------- | ------------------------------------- |
| Ports     | 2       | Port 0 (RX), Port 1 (TX)             |
| Lcores    | 4       | 1 main + 1 stats + 1 Kafka + 1 worker|
| Hugepages | Yes     | Required by DPDK for packet buffers   |
