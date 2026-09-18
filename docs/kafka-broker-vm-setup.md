# NetPro Kafka Broker VM Setup

This guide records the Kafka VM that was tested with the NetPro Policy Server. The NetPro Kafka repository supplies the Kafka version, ZooKeeper startup model, topic, and console tests. Persistent networking and systemd units are local VM additions; they do not modify a component repository.

## Verified result

- Kafka 3.6.1 and ZooKeeper run on Ubuntu 24.04 with OpenJDK 17.
- Kafka listens on `9092`; ZooKeeper listens on `2181`.
- `dpdk-blocked-list` has one partition and replication factor one.
- The Policy Server consumed a create-policy JSON message and wrote it to SQLite.
- The secondary address, services, topic metadata, and a test message survived a VM reboot.

## VMware and operating system

| Setting | Value |
| --- | --- |
| VM name | `Kafka-Broker-VM` |
| Hostname | `kafka-broker-vm` |
| Username | `netpro` |
| Guest OS | Ubuntu 24.04 |
| CPU | 2 virtual cores |
| Memory | 4 GB |
| Disk | 20 GB |
| Network | One NAT adapter |

Ubuntu 20.04 is not required by the Kafka repository. It requires Java 8 or newer. OpenJDK 17 was selected for Kafka 3.6.1.

## Install Java and tools

```bash
sudo apt update
sudo apt install -y openjdk-17-jre-headless wget
java -version
```

## Install Kafka 3.6.1

The repository names Kafka 3.6.1. Old releases may no longer exist on Apache's current-download mirror, so use the official archive when necessary:

```bash
cd ~
wget https://archive.apache.org/dist/kafka/3.6.1/kafka_2.13-3.6.1.tgz
tar -xzf kafka_2.13-3.6.1.tgz
cd ~/kafka_2.13-3.6.1
```

## Add the stable NetPro address

Keep DHCP for NAT/SSH and add the address hard-coded by the Policy Server:

```bash
sudo nano /etc/netplan/99-netpro-control.yaml
```

```yaml
network:
  version: 2
  ethernets:
    ens33:
      addresses:
        - 192.168.0.90/24
```

```bash
sudo chmod 600 /etc/netplan/99-netpro-control.yaml
sudo netplan apply
ip -br addr show ens33
```

## Configure Kafka networking

```bash
cd ~/kafka_2.13-3.6.1
cp config/server.properties config/server.properties.original
sed -i 's|^#listeners=.*|listeners=PLAINTEXT://0.0.0.0:9092|' config/server.properties
sed -i 's|^#advertised.listeners=.*|advertised.listeners=PLAINTEXT://192.168.0.90:9092|' config/server.properties
grep -E '^(listeners|advertised.listeners|zookeeper.connect)=' config/server.properties
```

Expected:

```text
listeners=PLAINTEXT://0.0.0.0:9092
advertised.listeners=PLAINTEXT://192.168.0.90:9092
zookeeper.connect=localhost:2181
```

Keep the shared topic from being removed by the Backend shutdown handler:

```bash
grep -q '^delete.topic.enable=' config/server.properties \
  && sed -i 's/^delete.topic.enable=.*/delete.topic.enable=false/' config/server.properties \
  || printf '\ndelete.topic.enable=false\n' >> config/server.properties
grep '^delete.topic.enable=' config/server.properties
```

Expected: `delete.topic.enable=false`. Restart Kafka after changing this setting. It does not restore messages already lost from a `/tmp` data directory, so configure persistent storage before the first reboot.

`PLAINTEXT` is appropriate only for this isolated lab network. Do not expose port 9092 to an untrusted network.

## Use permanent Kafka and ZooKeeper storage

The default Kafka 3.6.1 configuration stores broker data in `/tmp/kafka-logs` and ZooKeeper data in `/tmp/zookeeper`. Ubuntu can clear `/tmp` during reboot, which caused the first `dpdk-blocked-list` topic to disappear even though both services restarted successfully.

Stop both services before changing the data locations:

```bash
sudo systemctl stop netpro-kafka
sudo systemctl stop netpro-zookeeper
```

Create persistent directories owned by the service account:

```bash
sudo install -d -o netpro -g netpro /var/lib/netpro-kafka
sudo install -d -o netpro -g netpro /var/lib/netpro-zookeeper
```

Update the two configuration files:

```bash
cd ~/kafka_2.13-3.6.1
sed -i 's|^log.dirs=.*|log.dirs=/var/lib/netpro-kafka|' config/server.properties
sed -i 's|^dataDir=.*|dataDir=/var/lib/netpro-zookeeper|' config/zookeeper.properties

grep -E '^log.dirs=' config/server.properties
grep -E '^dataDir=' config/zookeeper.properties
```

Expected:

```text
log.dirs=/var/lib/netpro-kafka
dataDir=/var/lib/netpro-zookeeper
```

Start ZooKeeper first, followed by Kafka:

```bash
sudo systemctl start netpro-zookeeper
sudo systemctl start netpro-kafka
```

## Manual repository-baseline test

Start ZooKeeper in one terminal:

```bash
cd ~/kafka_2.13-3.6.1
bin/zookeeper-server-start.sh config/zookeeper.properties
```

Start Kafka in another:

```bash
cd ~/kafka_2.13-3.6.1
bin/kafka-server-start.sh config/server.properties
```

Verify ports:

```bash
sudo ss -ltnp | grep -E ':(2181|9092)'
```

## Create the NetPro topic

```bash
cd ~/kafka_2.13-3.6.1
bin/kafka-topics.sh \
  --create \
  --if-not-exists \
  --topic dpdk-blocked-list \
  --bootstrap-server 192.168.0.90:9092 \
  --partitions 1 \
  --replication-factor 1
```

```bash
bin/kafka-topics.sh \
  --describe \
  --topic dpdk-blocked-list \
  --bootstrap-server 192.168.0.90:9092
```

Expected: partition count 1, replication factor 1, leader 0, ISR 0.

## Console smoke test

Producer:

```bash
bin/kafka-console-producer.sh \
  --topic dpdk-blocked-list \
  --bootstrap-server 192.168.0.90:9092
```

Consumer:

```bash
bin/kafka-console-consumer.sh \
  --topic dpdk-blocked-list \
  --from-beginning \
  --bootstrap-server 192.168.0.90:9092
```

The Policy Server expects JSON, not arbitrary text. A valid create message is:

```json
{"type":"create","createdBlockedList":{"domain":"example.com","ip_add":"93.184.216.34","id":"netpro-test-001"}}
```

Update and delete use `updatedBlockedList` and `deletedBlockedList`, respectively, and still require string fields `domain`, `ip_add`, and `id`.

## Run ZooKeeper automatically

Stop any manually running ZooKeeper and Kafka processes before enabling services.

```bash
sudo nano /etc/systemd/system/netpro-zookeeper.service
```

```ini
[Unit]
Description=NetPro ZooKeeper
After=network.target

[Service]
Type=simple
User=netpro
Group=netpro
WorkingDirectory=/home/netpro/kafka_2.13-3.6.1
ExecStart=/home/netpro/kafka_2.13-3.6.1/bin/zookeeper-server-start.sh /home/netpro/kafka_2.13-3.6.1/config/zookeeper.properties
Restart=on-failure
RestartSec=5
SuccessExitStatus=143

[Install]
WantedBy=multi-user.target
```

## Run Kafka automatically

```bash
sudo nano /etc/systemd/system/netpro-kafka.service
```

```ini
[Unit]
Description=NetPro Kafka Broker
Requires=netpro-zookeeper.service
After=network-online.target netpro-zookeeper.service
Wants=network-online.target

[Service]
Type=simple
User=netpro
Group=netpro
WorkingDirectory=/home/netpro/kafka_2.13-3.6.1
ExecStart=/home/netpro/kafka_2.13-3.6.1/bin/kafka-server-start.sh /home/netpro/kafka_2.13-3.6.1/config/server.properties
Restart=on-failure
RestartSec=10
SuccessExitStatus=143
LimitNOFILE=100000

[Install]
WantedBy=multi-user.target
```

Enable both:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netpro-zookeeper
sudo systemctl enable --now netpro-kafka
```

## Reboot verification

```bash
systemctl is-active netpro-zookeeper
systemctl is-active netpro-kafka
ip -br addr show ens33
sudo ss -ltnp | grep -E ':(2181|9092)'

cd ~/kafka_2.13-3.6.1
bin/kafka-topics.sh \
  --describe \
  --topic dpdk-blocked-list \
  --bootstrap-server 192.168.0.90:9092

bin/kafka-console-consumer.sh \
  --topic dpdk-blocked-list \
  --from-beginning \
  --max-messages 1 \
  --bootstrap-server 192.168.0.90:9092
```

Both services must report `active`, `ens33` must include `192.168.0.90/24`, both ports must listen, the topic description must show an active leader, and the consumer must return the pre-reboot test message.

Verified persistence-test payload:

```json
{"type":"create","createdBlockedList":{"domain":"persistence-test.local","ip_add":"192.0.2.10","id":"kafka-persistence-test"}}
```

## Topic cleanup warning

Deleting `dpdk-blocked-list` deletes every message in it. Only delete and recreate the topic when it contains disposable test data and all consumers are stopped. Never delete Kafka's `__consumer_offsets` internal topic.
