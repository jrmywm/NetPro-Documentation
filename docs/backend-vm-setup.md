# NetPro Backend VM Setup

> Status: PostgreSQL, HTTPS API, Kafka integration, systemd startup, reboot persistence, and Backend-to-Policy synchronization verified on 16 September 2026.

This guide follows `Network-Laboratory-UI/NetPro-Backend` without modifying tracked repository files. Compatibility files, certificates, database initialization, and the systemd service remain local to the VM.

## Verified result

- Ubuntu 24.04.5 LTS
- Node.js 18.19.1 and npm 9.2.0
- PostgreSQL 16.15
- Repository dependencies installed exactly with `npm ci`
- HTTPS Express API available at `https://192.168.0.94:3000`
- PostgreSQL and Backend services start automatically
- Kafka producer, admin client, and `logging-dashboard` consumer connect to `192.168.0.90:9092`
- A blocked-list record created through the API persisted in PostgreSQL and arrived in the Policy Server SQLite database through Kafka
- Control address, services, HTTPS API, and stored data survived a reboot

## VMware hardware

| Setting | Value |
| --- | --- |
| VM name | `Backend-VM` |
| Hostname | `backend-vm` |
| Username | `netpro` |
| Guest OS | Ubuntu 24.04 |
| CPU | 2 virtual cores |
| Memory | 4 GB |
| Disk | 30 GB |
| Network Adapter | NAT |

The Backend does not use DPDK and needs no additional LAN-segment adapters or VMXNET3 edits.

## Stable NetPro control address

Keep DHCP on `ens33` and add a separate netplan overlay:

```bash
sudo nano /etc/netplan/99-netpro-control.yaml
```

```yaml
network:
  version: 2
  ethernets:
    ens33:
      addresses:
        - 192.168.0.94/24
```

```bash
sudo chmod 600 /etc/netplan/99-netpro-control.yaml
sudo netplan generate
sudo netplan apply
ip -br addr show ens33
ping -c 2 192.168.0.90
```

## Install runtime and database packages

```bash
sudo apt update
sudo apt install -y \
  nodejs npm \
  postgresql postgresql-contrib \
  git openssl build-essential python3

sudo systemctl enable --now postgresql
```

Verified versions:

```text
node v18.19.1
npm 9.2.0
PostgreSQL 16.15
```

## PostgreSQL configuration

The repository hard-codes PostgreSQL on `localhost:5432` with database `test`, user `postgres`, and password `postgres`. This is acceptable only for the isolated lab VM. Do not expose PostgreSQL port 5432 externally.

```bash
sudo -u postgres psql
```

```sql
ALTER USER postgres WITH PASSWORD 'postgres';
CREATE DATABASE test;
\q
```

Verify the same TCP/password path used by Sequelize:

```bash
PGPASSWORD=postgres psql \
  -h 127.0.0.1 \
  -U postgres \
  -d test \
  -c '\conninfo'
```

## Clone and install the Backend

```bash
cd ~
git clone https://github.com/Network-Laboratory-UI/NetPro-Backend.git
cd ~/NetPro-Backend
npm ci
git status --short
```

Use `npm ci` to preserve `package-lock.json`. The verified installation reported dependency vulnerabilities; do not run `npm audit fix` or `--force` during baseline setup because that changes dependency versions.

## Create the repository's hard-coded certificate path

`index.js` reads:

```text
/home/ubuntu/cert/server.key
/home/ubuntu/cert/server.crt
```

Create a VM-local self-signed lab certificate without changing the repository:

```bash
sudo mkdir -p /home/ubuntu/cert
sudo openssl req \
  -x509 \
  -newkey rsa:2048 \
  -nodes \
  -keyout /home/ubuntu/cert/server.key \
  -out /home/ubuntu/cert/server.crt \
  -days 3650 \
  -subj "/CN=backend-vm" \
  -addext "subjectAltName=DNS:backend-vm,DNS:localhost,IP:192.168.0.94"

sudo chown root:netpro /home/ubuntu/cert/server.key
sudo chmod 640 /home/ubuntu/cert/server.key
sudo chmod 644 /home/ubuntu/cert/server.crt
```

The certificate is self-signed, so test clients use `curl -k`. Do not reuse it outside the isolated lab.

## Initialize the Sequelize schema safely

Each of the repository's nine model files calls `db.sync()`. On a new empty PostgreSQL database, those calls execute concurrently and can fail with:

```text
SequelizeUniqueConstraintError
duplicate key value violates unique constraint "pg_type_typname_nsp_index"
```

Create a VM-local one-time initializer that suppresses the per-model calls, loads every model, and invokes one final `db.sync()`:

```bash
nano ~/netpro-init-db.js
```

```javascript
const backend = "/home/netpro/NetPro-Backend";
const db = require(`${backend}/src/config/dpdkDatabase`);

const originalSync = db.sync.bind(db);
db.sync = async () => {};

[
  "npb",
  "ps",
  "configData",
  "npbHeartbeat",
  "npbPacket",
  "psBlockedList",
  "psHeartbeat",
  "psPacket",
  "user",
].forEach((model) => {
  require(`${backend}/src/models/${model}`);
});

db.sync = originalSync;

(async () => {
  try {
    await db.sync();
    console.log("NetPro database schema initialized successfully.");
  } catch (error) {
    console.error("NetPro database initialization failed:", error);
    process.exitCode = 1;
  } finally {
    await db.close();
  }
})();
```

```bash
node ~/netpro-init-db.js
PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres -d test -c '\dt'
```

The verified database contains nine tables:

```text
config_data
npb
npb_heartbeat
npb_packet
ps
ps_blocked_list
ps_heartbeat
ps_packet
users
```

## Protect Kafka topics from the Backend SIGINT handler

The repository's `index.js` requests deletion of `logging-dashboard` and `dpdk-blocked-list` when it receives SIGINT. On the Kafka VM, add this to `~/kafka_2.13-3.6.1/config/server.properties`:

```properties
delete.topic.enable=false
```

Restart Kafka and verify the setting and topic:

```bash
sudo systemctl restart netpro-kafka
grep '^delete.topic.enable=' ~/kafka_2.13-3.6.1/config/server.properties
bin/kafka-topics.sh --describe \
  --topic dpdk-blocked-list \
  --bootstrap-server 192.168.0.90:9092
```

The systemd unit below uses SIGTERM, which does not invoke the repository's SIGINT deletion handler.

## Run the Backend as a service

Port 443 would require elevated privileges. Keep the repository's HTTPS behavior but supply unprivileged port 3000 through the existing `PORT` environment variable:

```bash
sudo nano /etc/systemd/system/netpro-backend.service
```

```ini
[Unit]
Description=NetPro Backend
Wants=network-online.target
After=network-online.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=netpro
Group=netpro
WorkingDirectory=/home/netpro/NetPro-Backend
Environment=PORT=3000
Environment=NODE_ENV=production
Environment=KAFKAJS_NO_PARTITIONER_WARNING=1
ExecStart=/usr/bin/node /home/netpro/NetPro-Backend/index.js
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netpro-backend
systemctl is-active postgresql
systemctl is-active netpro-backend
```

An existing-topic error from KafkaJS during startup is harmless. The repository prints “created successfully” without checking the boolean result of `createTopics`.

## API validation

Basic HTTPS listener:

```bash
curl -k -i https://127.0.0.1:3000/
```

`404 Cannot GET /` is expected because the repository defines no root route.

Read-only API checks:

```bash
curl -k https://192.168.0.94:3000/npb/npbs
curl -k https://192.168.0.94:3000/ps/pss
curl -k https://192.168.0.94:3000/ps/blocked-list
```

## Verified Backend-to-Policy integration

With the Policy Server running, the following API request created a test blocked-list record:

```bash
curl -k -X POST \
  https://192.168.0.94:3000/ps/blocked-list \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"Backend integration test",
    "domain":"backend-test.local",
    "ip_add":"192.0.2.20",
    "category":"Other"
  }'
```

Generated test ID:

```text
7f3fbb19-4064-432c-b9b9-72363c5c1cd9
```

The same record was verified in PostgreSQL:

```text
7f3fbb19-4064-432c-b9b9-72363c5c1cd9 | backend-test.local | 192.0.2.20
```

and in Policy Server SQLite:

```text
7f3fbb19-4064-432c-b9b9-72363c5c1cd9|backend-test.local|192.0.2.20
```

This proves:

```text
Backend REST API -> PostgreSQL -> Kafka dpdk-blocked-list
                 -> Policy Server consumer -> SQLite policies
```

## Reboot verification

After reboot:

- PostgreSQL reported `active`;
- `netpro-backend` reported `active`;
- `192.168.0.94/24` remained assigned;
- `GET /ps/blocked-list` returned HTTP 200 and the saved record; and
- direct PostgreSQL lookup returned the same UUID.

## Local-only and sensitive data

Keep these outside Git:

- `/home/ubuntu/cert/server.key` and `server.crt`;
- PostgreSQL data under `/var/lib/postgresql`;
- `~/netpro-init-db.js`;
- `/etc/systemd/system/netpro-backend.service`;
- local netplan files and service logs.

The current repository hard-codes lab database credentials and infrastructure addresses. Do not expose this VM to an untrusted network without moving credentials into environment variables, replacing the self-signed certificate, and reviewing dependency vulnerabilities.
