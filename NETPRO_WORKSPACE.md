# NetPro Workspace

This repository is the shared documentation and operating record for the NetPro project. The six component repositories remain independent Git repositories under a local `repos/` folder. VM disks, packet captures, secrets, dependencies, and generated data stay outside Git. The documented rebuild keeps Adapter 1 on VMware NAT during installation and validation; bridged/external access is optional only after the isolated lab is healthy.

## Workspace layout

```text
NetPro Documentation/
├── NETPRO_WORKSPACE.md
├── .gitignore
├── docs/
│   ├── README.md
│   ├── policy-server-vm-setup.md
│   ├── kafka-broker-vm-setup.md
│   ├── npb-vm-setup.md
│   ├── packet-generator-vm-setup.md
│   ├── end-to-end-http-validation.md
│   ├── backend-vm-setup.md
│   ├── frontend-vm-setup.md
│   └── setup-obstacles-and-fixes.md
└── repos/                         # local-only; ignored by this repository
    ├── NetPro-Policy-Server/
    ├── NetPro-Network-Packet-Broker/
    ├── NetPro-Kafka-Message-Broker/
    ├── NetPro-Packet-Generator/
    ├── NetPro-Backend/
    └── NetPro-Frontend/
```

## Repository purposes

| Repository | Purpose | Main runtime |
| --- | --- | --- |
| `NetPro-Kafka-Message-Broker` | Delivers blocked-list changes to Policy Servers through `dpdk-blocked-list`. | Kafka 3.6.1 and ZooKeeper |
| `NetPro-Network-Packet-Broker` | Receives traffic, identifies HTTP GET and TLS Client Hello packets, and splits them to the Policy Server. | C, DPDK, Hyperscan |
| `NetPro-Policy-Server` | Checks HTTP/TLS domains against its synchronized SQLite policy database and can send TCP resets. | C, DPDK, SQLite, librdkafka |
| `NetPro-Packet-Generator` | Generates TRex traffic and stores test output/captures. | TRex and Python scripts |
| `NetPro-Backend` | Express REST API, PostgreSQL access, authentication, and Kafka configuration. | Node.js, Express, PostgreSQL |
| `NetPro-Frontend` | React/Tailwind web interface for the NetPro dashboard. | Node.js and React |

## Current verified lab

| VM | OS | Management address | NetPro address | Status |
| --- | --- | --- | --- | --- |
| `Kafka-Broker-VM` | Ubuntu 24.04 | DHCP: `192.168.31.132` | `192.168.0.90/24` | Verified, automatic boot |
| `Policy-Server-VM` | Ubuntu 20.04 | DHCP: `192.168.31.131` | `192.168.0.91/24` | HTTP/TLS policy enforcement and RST output verified |
| `NPB-VM` | Ubuntu 20.04 | DHCP: `192.168.31.133` | `192.168.0.92/24` | HTTP/TLS forwarding and automatic reboot recovery verified |
| `Packet-Generator-VM` | Ubuntu 20.04 | DHCP: `192.168.31.134` | `192.168.0.93/24` | TRex v3.04 HTTP/TLS generation and RST reception verified |
| `Backend-VM` | Ubuntu 24.04 | DHCP: `192.168.31.135` | `192.168.0.94/24` | PostgreSQL, HTTPS API, Kafka, and reboot persistence verified |
| `Frontend-VM` | Ubuntu 24.04 | DHCP/NAT: `192.168.31.136` | `192.168.0.95/24` | HTTPS dashboard, login, systemd startup, and reboot persistence verified |

DHCP/NAT addresses can change. The `192.168.0.90`–`192.168.0.95` secondary addresses are the stable NetPro control addresses used by the current lab configuration. Browser-facing URLs use the VMware NAT addresses because the Windows host does not route the VM-only `192.168.0.0/24` control network. Do not replace Adapter 1 with a bridged adapter during the build; external access can be added later as a separately tested phase.

## VMware LAN segments

| Segment | Connects | Purpose |
| --- | --- | --- |
| `NetPro-RX` | Packet Generator, NPB input, and Policy RST output | Generated traffic entering the NPB and reset frames returning to TRex |
| `NetPro-HTTP` | NPB HTTP output → Policy HTTP NIC (`0b:00.0`) | HTTP GET traffic; this NIC becomes Policy DPDK port 0 in HTTP mode |
| `NetPro-TLS` | NPB TLS output → Policy TLS NIC (`13:00.0`) | TLS Client Hello traffic; this NIC becomes Policy DPDK port 0 in TLS mode |
| `NetPro-PG-AUX` | Packet Generator port 1 only | Unused second TRex port required by the two-port TRex configuration |

The management adapter on every VM uses VMware NAT and must not be bound to DPDK.

## Dependency and startup order

```text
PostgreSQL → Kafka/ZooKeeper → Backend → Frontend
                         └──→ Policy Server
Packet Generator → NPB ─────→ Policy Server
```

Recommended full-lab startup order:

1. Start `Kafka-Broker-VM`; its ZooKeeper and Kafka services start automatically.
2. Start `Backend-VM`; PostgreSQL and `netpro-backend` start automatically.
3. Start `Frontend-VM`; `netpro-frontend` starts automatically.
4. Start `Policy-Server-VM`; `netpro-dpdk-prepare` restores the default HTTP bindings and `netpro-policy` starts the Policy application automatically. Stop the unit before selecting TLS mode.
5. Start `NPB-VM`; `netpro-npb-dpdk-prepare` and `netpro-npb` prepare the three DPDK ports and launch the NPB automatically.
6. Start the Packet Generator last so packets are not sent before consumers are ready.

For packet-path-only testing, the backend and frontend may remain off. Kafka should still run because the current Policy Server always creates its Kafka consumer.

## Configuration values currently in use

| Setting | Value | Location |
| --- | --- | --- |
| Kafka broker | `192.168.0.90:9092` | Hard-coded in Policy Server and Backend source; configured in Kafka `server.properties` |
| Kafka topic | `dpdk-blocked-list` | Policy source and Kafka repo README |
| Policy control address | `192.168.0.91/24` | Policy VM netplan overlay |
| NPB control address | `192.168.0.92/24` | NPB VM netplan overlay |
| Packet Generator control address | `192.168.0.93/24` | Packet Generator VM netplan overlay |
| Backend control address | `192.168.0.94/24` | Backend VM netplan overlay |
| Frontend control address | `192.168.0.95/24` | Frontend VM netplan overlay |
| Policy SQLite path | `/home/ubuntu/NetPro-Policy-Server/policy.db` | Hard-coded in Policy Server source |
| Policy default mode | `HTTP` | `/etc/default/netpro-policy`; boot preparation binds `0b:00.0` and `1b:00.0` |
| Policy DPDK layout | Exactly two ports: selected input + RST/output | HTTP: `0b:00.0` + `1b:00.0`; TLS: `13:00.0` + `1b:00.0` |
| Backend PostgreSQL | `test` on `localhost:5432` | Hard-coded in Backend source; isolated lab only |
| Backend HTTPS URL | `https://192.168.0.94:3000` | Port supplied by systemd; self-signed lab certificate |
| Frontend browser URL | `https://192.168.31.136:3005` | Verified VMware NAT address; self-signed lab certificate |
| Frontend Backend URL | `https://192.168.31.135:3000` | `.env.local`; browser-facing VMware NAT address |
| Frontend certificate paths | `/home/ubuntu/cert/server.crt`, `/home/ubuntu/cert/server.key` | Frontend `package.json` |

Do not store real database passwords, API tokens, TLS private keys, or certificates in this documentation repository. Use an ignored `.env` or machine-local secret store and provide only sanitized `.env.example` templates.

## Clone the workspace and repositories

Clone the documentation repository:

```powershell
git clone https://github.com/jrmywm/NetPro-Documentation.git "NetPro Documentation"
cd "NetPro Documentation"
New-Item -ItemType Directory -Force repos
cd repos
```

Clone the Windows-compatible component repositories:

```powershell
git clone https://github.com/Network-Laboratory-UI/NetPro-Policy-Server.git
git clone https://github.com/Network-Laboratory-UI/NetPro-Network-Packet-Broker.git
git clone https://github.com/Network-Laboratory-UI/NetPro-Kafka-Message-Broker.git
git clone https://github.com/Network-Laboratory-UI/NetPro-Backend.git
git clone https://github.com/Network-Laboratory-UI/NetPro-Frontend.git
```

### Packet Generator on Windows

The Packet Generator repository contains tracked filenames with colon characters, such as `2024-05-09T14:16:11.json`. Windows cannot check these paths out. A clone can download successfully while checkout fails and shows every file as staged for deletion. Do not commit or push that state.

Use Ubuntu WSL instead:

```bash
mkdir -p ~/netpro-repos
cd ~/netpro-repos
git clone https://github.com/Network-Laboratory-UI/NetPro-Packet-Generator.git
```

The WSL checkout is the working copy for this component. Do not duplicate it into the Windows `repos/` folder.

## Update all repositories safely

Run updates only when each repository has a clean working tree. From PowerShell inside `repos/`:

```powershell
Get-ChildItem -Directory | ForEach-Object {
    if (Test-Path (Join-Path $_.FullName '.git')) {
        Write-Host "`n== $($_.Name) =="
        git -C $_.FullName status --short
        git -C $_.FullName pull --ff-only
    }
}
```

Update the Packet Generator separately in WSL:

```bash
git -C ~/netpro-repos/NetPro-Packet-Generator status --short
git -C ~/netpro-repos/NetPro-Packet-Generator pull --ff-only
```

If `status --short` prints anything, stop and inspect it before pulling. Never use `git reset --hard` to solve a laptop-switch problem.

## Laptop-switch checklist

Before leaving laptop A:

1. Stop packet generation and all NetPro processes.
2. Shut down every VM completely; do not suspend it.
3. Confirm each repository with `git status`.
4. Commit and push intentional source changes in that component's repository.
5. Commit and push documentation changes in `NetPro-Documentation`.
6. Keep VM folders, ISO files, captures, and datasets on the designated local disk or portable SSD—not in Git.
7. Eject the portable SSD safely.

On laptop B:

1. Pull `NetPro-Documentation` with `git pull --ff-only`.
2. Pull each clean component repository with `git pull --ff-only`.
3. Connect the portable SSD and open the powered-off VM in VMware.
4. If VMware asks whether the VM was moved or copied, choose **I moved it** to preserve virtual NIC MAC addresses.
5. Verify each VMware LAN segment and **Connect at power on** setting.
6. Start dependencies in the documented order.
7. Run the quick checks in the VM-specific guides.

Never run the same portable VM concurrently on both laptops.

## Local-only assets

Keep these out of Git:

- VMware files and snapshots: `.vmdk`, `.vmx`, `.vmem`, `.vmsn`, `.vmss`, `.nvram`, `.lck`;
- Ubuntu ISO, OVA, and OVF files;
- packet captures, generated Packet Generator output, notebooks containing captured data, and large datasets;
- SQLite runtime databases, PostgreSQL data directories, Kafka log data, and ZooKeeper data;
- `node_modules`, compiled binaries, DPDK build trees, caches, logs, and coverage output;
- `.env` files, tokens, passwords, certificates, and private keys.

Record the machine-local location and backup status in a private inventory, but never put secrets into that inventory.

## Verified end-to-end result

HTTP and TLS policy enforcement have been verified with the repository traffic profiles:

```text
TRex port 0 → NetPro-RX → NPB port 0
NPB HTTP classification → NPB port 1 → NetPro-HTTP → Policy Server port 0
NPB TLS classification  → NPB port 2 → NetPro-TLS  → Policy Server port 0 (TLS mode)
Policy Server port 1 → NetPro-RX → TRex port 0
```

The HTTP test matched `facebook.co.id` at `48.0.0.1`. The TLS test matched SNI `www.ui.ac.id` at `152.118.24.175:443`. In each test, the NPB classified and forwarded approximately 1,000 requests per active interval; the Policy Server blocked matching requests and emitted client- and server-directed RST frames with zero reported interface errors. The TLS run ended with 8,016 TRex transmissions and 16,032 received RST frames.

The Policy runtime accepts exactly two DPDK ports despite its misleading “number of ports must be 3” error string. It supports selectable HTTP and TLS input modes, with the other DPDK port always used for RST/output. The local Policy source fix `d658fa2` maps telemetry to the selected mode; see [Policy Server VM setup](docs/policy-server-vm-setup.md) and [End-to-end HTTP and TLS validation](docs/end-to-end-http-validation.md).

The application control path is also verified:

```text
Backend HTTPS API -> PostgreSQL -> Kafka dpdk-blocked-list
                  -> Policy Server consumer -> SQLite policies
```

A blocked-list record created through `POST /ps/blocked-list` persisted across Backend reboot and appeared in the Policy Server database with the same UUID, domain, and IP. See [Backend VM setup](docs/backend-vm-setup.md).

The Frontend HTTPS dashboard was verified from the Windows host. Registration and login worked, paired NPB and Policy Server records were created, the generated runtime configuration reached both native services, and both cards changed to **Active** after their heartbeats were evaluated. The Frontend and NPB services also start automatically. See [Frontend VM setup](docs/frontend-vm-setup.md).

## Documentation status

- [Policy Server VM setup](docs/policy-server-vm-setup.md): verified through reboot and Kafka-to-SQLite integration.
- [Kafka Broker VM setup](docs/kafka-broker-vm-setup.md): verified through reboot.
- [NPB VM setup](docs/npb-vm-setup.md): verified through HTTP/TLS forwarding, automatic startup, and reboot persistence.
- [Packet Generator VM setup](docs/packet-generator-vm-setup.md): verified with the repository HTTP and TLS scripts and RST reception.
- [End-to-end HTTP and TLS validation](docs/end-to-end-http-validation.md): verified through policy matching, blocking, and TCP-reset return.
- [Backend VM setup](docs/backend-vm-setup.md): verified through reboot and Backend-to-Policy database synchronization.
- [Frontend VM setup](docs/frontend-vm-setup.md): verified through reboot, authentication, device pairing, and active dashboard status.
- [Setup obstacles and fixes](docs/setup-obstacles-and-fixes.md): consolidated record of encountered failures, causes, resolutions, and pending checks.

## Local source and runtime boundary

The lab record includes two machine-local source changes: Policy commit `d658fa2 Fix two-port policy telemetry mapping` and Backend commit `bd3c3fc Enable device heartbeat status checks`. They are evidence for the verified lab state, not instructions to push to any Network-Laboratory repository. Keep the following out of Git: `/etc/systemd/system` units, `/etc/default/netpro-policy`, `/usr/local/sbin` helpers, generated configs, certificates and private keys, SQLite/PostgreSQL/Kafka data, logs, compiled binaries, packet captures, and `*.before-*` backups.
