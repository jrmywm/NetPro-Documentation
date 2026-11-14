# Policy Server
The Policy Server is a high-performance network policy enforcement tool developed using the Data Plane Development Kit (DPDK). It processes HTTP GET requests and TLS Client Hello packets to extract domains and checks them against a blacklist database. If a domain is blacklisted, the server sends a TCP reset to terminate the connection between the client and the server.

Using DPDK provides several key benefits:

- **Enhanced Performance**: DPDK enables the Policy Server to achieve line-rate packet processing, ensuring minimal latency and maximum throughput.
- **Efficient Resource Utilization**: By leveraging DPDK's optimized memory management and CPU usage, the server can handle high traffic volumes with lower resource consumption.
- **Scalability**: The modular nature of DPDK allows the Policy Server to scale easily, accommodating growing network demands without a significant performance drop.
- **Reliability**: DPDK's robust and mature libraries provide a stable foundation, reducing the likelihood of packet loss and ensuring consistent policy enforcement.

These advantages make the Policy Server an ideal solution for high-speed network environments requiring strict policy control and enforcement.

## Architecture

### Policy Server Architecture

![Policy Server Architecture](./doc/assets/Policy%20Server%20Architecture.png)

The Policy Server have a simple architecture that consist of 3 main components:

- RX: Receive HTTP GET and TLS Client from the network
- Policy Server: Process Incoming and Sent Packet
- Database: Store blacklisted domain
- Kafka: Synchronize domain with Dashboard
- TX: Transmit TCP Reset to the network

### Censorship Architecture

![Policy Server Architecture](./doc/assets/Censorship%20System.png)

## Getting Started

### Prerequisites
1. DPDK 20.11.2
2. Sqlite3 Database
3. Kafka Developer Libraries
4. Ubuntu 20.04
5. 4 NICs (2 for RX, 1 for TX, 1 for Management)

### Installation
- [Install DPDK 20.11.2](doc/DPDK%20installation%20guide.md)

### Startup
Run the startup script to bind the NICs to DPDK and setup Hugepages
```bash
sudo ./startup.sh
```

### Build
Build to compile the policy server and create directory needed
```bash
make
```

### Run
Run the policy server
```bash
sudo ./run.sh
```

### Clean
Clean statistics and remove the policy server executable
```bash
make clean
```