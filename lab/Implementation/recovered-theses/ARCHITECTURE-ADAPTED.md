# Current adapted NetPro architecture

31 October 2026. Six running VMs; Luthfi's CSV flow and Rafie's HTTP/TLS lookup adaptation are deployed together. Boxes represent logical services; only the six named VM groups are virtual machines. The operator browser and optional external server are not extra NetPro VMs.

```mermaid
flowchart TB
    USER["Operator browser"]

    subgraph MGMT["VM 1 — Management · 192.168.31.35"]
        UI["nginx + React dashboard<br/>HTTPS :3005"]
        API["NetPro Backend API<br/>HTTPS :3000"]
        CSV["Luthfi adaptation<br/>CSV validation + preview<br/>Reviewed batch activation + retry"]
        PG[("PostgreSQL<br/>Authoritative policies<br/>Durable jobs + outbox")]
        PUB["Outbox publisher"]
        KAFKA["Kafka + ZooKeeper<br/>Policy-update events"]
        UI -->|Authenticated requests| API
        API --> CSV
        CSV -->|Commit policies and events atomically| PG
        PG --> PUB
        PUB --> KAFKA
        API -.->|Socket.IO progress / polling| UI
    end

    subgraph CLIENT["VM 2 — Client · 192.168.31.39"]
        C["HTTP / TLS test client"]
    end
    subgraph TAP["VM 3 — Virtual TAP · 192.168.31.38"]
        BR["Software bridge<br/>Forward originals + mirror copies"]
    end
    subgraph GATEWAY["VM 4 — Gateway · 192.168.31.37"]
        GW["Lab server / network gateway<br/>Dedicated RST-return delivery"]
    end
    TARGET["Optional external server"]

    subgraph NPB["VM 5 — NPB · 192.168.31.33"]
        CLASSIFY["Packet Broker<br/>HTTP / TLS classification<br/>Split ClientHello tracking"]
    end

    subgraph PS["VM 6 — Policy Server · 192.168.31.31"]
        INSPECT["HTTP / TLS inspection<br/>Existing IP check"]
        LOOKUP["Rafie adaptation<br/>Preloaded policy set + LRU<br/>Counting Bloom Filter"]
        SQLITE[("SQLite<br/>Local applied policies")]
        SYNC["Kafka consumer<br/>Commit policy change"]
        RESET["Block decision<br/>TCP RST generation"]
        INSPECT -->|Exact-domain lookup| LOOKUP
        LOOKUP -->|Confirm Bloom-positive misses| SQLITE
        SQLITE -->|Full-set load / lazy rebuild| LOOKUP
        SYNC --> SQLITE
        SYNC -.->|Invalidate all lookup tiers| LOOKUP
        LOOKUP -->|Domain blocked| RESET
        INSPECT -->|IP blocked| RESET
    end

    USER --> UI
    C <-->|Original traffic| BR
    BR <-->|Original traffic| GW
    GW <-->|When testing external destinations| TARGET
    BR -.->|Mirrored copies| CLASSIFY
    CLASSIFY -->|Separate HTTP and TLS inputs| INSPECT
    KAFKA -->|Create / update / delete| SYNC
    RESET ==>|Dedicated NetPro-RST network| GW
    GW -.->|Injected RST follows return path through TAP| C
    CLASSIFY -.->|Statistics via API| API
    INSPECT -.->|Statistics and policy hit counts via API| API

    classDef traffic fill:#e8f3ff,stroke:#2874a6,color:#17202a
    classDef adapted fill:#e8f8ef,stroke:#238443,color:#17202a
    classDef reset fill:#fff0ed,stroke:#c0392b,color:#17202a
    class C,BR,GW,CLASSIFY,INSPECT traffic
    class CSV,LOOKUP adapted
    class RESET reset
```

Original traffic follows Client ↔ Virtual TAP ↔ Gateway. NetPro inspects mirrored copies. A block decision generates a new reset packet delivered over the dedicated reset network to the Gateway, then back toward the Client through the TAP. The dotted Gateway-to-Client reset arrow is a logical return path, not an extra direct network adapter.

Green components identify the newly adapted work. CSV validation and approval happen on Management; policy lookup acceleration happens on Policy Server. Kafka carries policy changes. The depicted NPB/Policy Server statistics use the backend API; PostgreSQL stores dashboard data. Import progress reaches the dashboard through authenticated Socket.IO or polling.

## Detailed domain decision path

```mermaid
flowchart TD
    DOMAIN["Domain extracted from HTTP / TLS"] --> GUARD["Check cache generation and SQLite changes<br/>Rebuild all tiers when invalidated"]
    GUARD --> HOT{"In preloaded policy set?"}
    HOT -->|Yes| BLOCK["Block + retain policy ID for hit telemetry"]
    HOT -->|No| LRU{"In LRU cache?"}
    LRU -->|Cached block| BLOCK
    LRU -->|Cached allow| ALLOW["Allow: no reset generated"]
    LRU -->|Miss| BLOOM{"Counting Bloom says possibly present?"}
    BLOOM -->|No, complete filter verified| NEG["Cache allow decision"]
    NEG --> ALLOW
    BLOOM -->|Yes| DB["Exact SQLite lookup"]
    DB -->|Policy exists| POS["Cache block decision and policy ID"]
    POS --> BLOCK
    DB -->|No policy| NEG
    GUARD -.->|Rebuild failed: bypass accelerators| DB
    CHANGE["Committed policy create / update / delete"] -.->|Invalidate all tiers| GUARD
```

A Bloom-positive result alone never causes blocking. Cache eviction follows real LRU. Saturated counting cells are not decremented on deletion: the complete filter is rebuilt lazily to avoid false negatives. Policy IDs are preserved on cached block decisions.

## Scope and supporting services

- This is the accepted **HTTP/TLS lab architecture**, including tested split ClientHello handling. Luthfi and Rafie were tested together with 1,001 policy additions/removals.
- Original traffic forwarding uses a **software Virtual TAP**. It does not establish hardware passive-TAP fail-open behavior.
- The dedicated Gateway reset return is the current lab attachment arrangement.
- The experimental original QUIC profile remains separate and is **not** represented as fully adapted or proven by the HTTP/TLS tests above.
- Management also hosts SNMP/Zabbix support from the monitoring work. Those services are outside this policy-import/HTTP-TLS acceptance diagram; no new end-to-end monitoring acceptance is implied here.
- Kafka publication acknowledgement is not an automatic Policy Server enforcement acknowledgement. Live acceptance checked SQLite and actual client behavior separately.
- Existing backend caches, CPU/core assignments, management interfaces and sidecar monitoring connections are omitted for readability. See [Luthfi acceptance](LUTHFI-ACCEPTANCE.md), [Rafie acceptance](RAFIE-ACCEPTANCE.md) and `test-results/` for implementation and validation detail.
