# NetPro Setup Obstacles and Fixes

This is the consolidated incident record for the verified NetPro lab build. The VM-specific guides remain the source for complete commands and configuration.

## Host, naming, and operating-system decisions

| Obstacle or decision | Cause | Resolution |
| --- | --- | --- |
| VM login name differed from repository paths | The account is `netpro`, while some source files require `/home/ubuntu/...`. | Kept the consistent `netpro` login and created only the required compatibility paths under `/home/ubuntu`. Renaming the account was unnecessary. |
| Ubuntu version differed between components | DPDK components were developed around Ubuntu 20.04/kernel 5.4, while ordinary Node/Kafka services do not require that older base. | Used Ubuntu 20.04 for Policy, NPB, and Packet Generator; Ubuntu 24.04 for Kafka, Backend, and Frontend. |
| Management DHCP addresses were unsuitable for VM-to-VM configuration | VMware NAT addresses can change. | Added persistent secondary addresses `192.168.0.90` through `192.168.0.95` with netplan overlays while retaining DHCP for host access. |
| NPB initially could not ping the other VMs | Its `192.168.0.92/24` secondary address had not actually been applied. | Corrected the netplan overlay, applied it, and verified both `.90` and `.91` before continuing. |

## Build and package issues

| Obstacle | Cause | Resolution |
| --- | --- | --- |
| `make` availability was unclear | `make` is supplied by the Ubuntu build toolchain, not the application repository. | Installed `build-essential` and the component-specific development libraries. |
| Policy build warned about a future-dated `Makefile` | VM time and file modification times did not agree. | Enabled NTP, restarted time synchronization, refreshed the affected source timestamps, and rebuilt cleanly. |
| `sqlite3: command not found` | The SQLite runtime library was installed, but the CLI package was not. | Installed the `sqlite3` command-line package for inspection. |
| `apt` waited on `/var/lib/dpkg/lock-frontend` | Ubuntu's `unattended-upgr` process was still running. | Waited for it to finish; did not delete the lock file or kill package management. |
| `ldconfig -p` did not list Hyperscan although installation succeeded | The repository build could use the installed static library and `pkg-config` metadata. | Verified `pkg-config --modversion libhs` returned 5.4.2 and continued with the successful NPB build. |

## Policy Server and DPDK issues

| Obstacle | Cause | Resolution |
| --- | --- | --- |
| Policy database appeared as a zero-byte file with no tables | Querying the hard-coded path while the Policy Server was stopped created a new empty SQLite file. A clean Policy shutdown also calls `delete_database()`. | Query the database from a second terminal only while the Policy Server is running. |
| `Cannot get hugepage information` after reboot | Hugepage allocation and DPDK bindings are volatile. | Created `netpro-dpdk-prepare.service` to allocate 2 GB of hugepages and bind the selected VMXNET3 adapters. |
| Hugepage setup reported pages still in use even though the process had stopped | Stale `/dev/hugepages/rtemap_*` mappings remained. | Confirmed no DPDK process was running, removed only the stale mappings, and restarted preparation. |
| `Error: number of ports must be 3` | The message is misleading; DPDK saw no bound data ports after the NICs returned to `vmxnet3`. | Checked `dpdk-devbind.py -s` and rebound the required adapters. |
| Policy PCI/interface mapping changed after VMware adapter repair | Removing or re-adding an adapter can change Linux names and PCI addresses. | Rediscovered the mapping and updated the local preparation helper. Never assume PCI addresses from another VM or an old snapshot. |
| HTTP and TLS could not be monitored simultaneously | The current Policy source polls application port 0 and uses port 1 for RST output. | Added the local `netpro-policy-mode` helper to bind HTTP+RST or TLS+RST safely; HTTP is restored at boot. A source change is still needed for simultaneous inputs. |

## Kafka issues

| Obstacle | Cause | Resolution |
| --- | --- | --- |
| `dpdk-blocked-list` disappeared after a restart/reboot | Default Kafka and ZooKeeper data directories were under `/tmp`, which is not durable. | Moved broker and ZooKeeper data to `/var/lib/netpro-kafka` and `/var/lib/netpro-zookeeper`, then recreated and persistence-tested the topic. |
| The Backend could delete shared topics during shutdown | Its SIGINT handler requests deletion of `logging-dashboard` and `dpdk-blocked-list`. | Set `delete.topic.enable=false`; the Backend systemd service also stops with SIGTERM rather than SIGINT. |
| Topic deletion returned “does not exist” | The topic had already disappeared with the temporary broker data. | Confirmed the topic list, fixed persistent storage, and recreated it once with disposable test data. |

## NPB, VMware, and TRex traffic issues

| Obstacle | Cause | Resolution |
| --- | --- | --- |
| NPB reported all-zero RX counters while TRex transmitted | The problem was the virtual path, not packet generation. | Verified `NetPro-RX` membership and adapter connection state, then used kernel `tcpdump` and DPDK `testpmd` to prove frames reached NPB PCI `0000:0b:00.0`. |
| Traffic reached NPB but Policy initially received nothing | The HTTP/TLS/RST VMware LAN-segment assignments and Policy input binding did not match the active test. | Standardized `NetPro-RX`, `NetPro-HTTP`, and `NetPro-TLS`; Policy RST output shares `NetPro-RX`. Selected the matching Policy mode before each test. |
| TRex reported `Port 0 dest MAC is invalid` | Its generated configuration had no explicit Layer-2 destination. | Regenerated `/etc/trex_cfg.yaml` with the current NPB RX MAC. The value must be rediscovered if VMware regenerates the NIC. |
| TRex port 1 showed no traffic | The repository HTTP/TLS scripts transmit on port 0; port 1 exists only because this TRex configuration requires a pair. | Treated idle port 1 as expected, not a failure. |
| `stl_path.py` could not locate profiles | TRex v3.04's packaged directory layout differs from what the Packet Generator repository expects. | Added the local `automation/stl` and `automation/external_libs` compatibility links and set `PYTHONPATH`. |
| A secondary error reported missing `scapy` from local `http.py` | Python imported the repository file while handling the earlier STL-path failure. | Fixed STL path resolution first; `npb_testing_http.py --help` then worked. |
| Packet Generator repository was cloned in the wrong location | The scripts expect to run inside TRex's interactive Python tree. | Installed it under `/opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test`. |
| Cisco TRex download certificate verification failed | The guest CA store could not validate the presented chain. | Checked the clock and CA package first. `--no-check-certificate` was accepted only as an isolated-lab fallback, followed by verification of extracted TRex files. |
| NPB hugepages and bindings disappeared after reboot | Like Policy, its DPDK runtime state is volatile. | Added `netpro-npb-dpdk-prepare.service` and `netpro-npb.service`. A later reboot verified the stable IP, both services, 2 GB of hugepages, all three DPDK bindings, three-port application output, and successful HTTP and TLS enforcement retests with zero interface/mbuf errors. |
| Packet Generator TLS client could not reach `127.0.0.1:4501` | The TRex server/RPC listener was no longer running. Ubuntu's crash hook then imported the repository's local `http.py`, producing a misleading secondary Scapy permission traceback. | Restarted `sudo ./t-rex-64 -i`, kept its terminal open, and reran the client as `netpro`. The successful retry produced the expected 2:1 RST return ratio. |

## Backend and Frontend issues

| Obstacle | Cause | Resolution |
| --- | --- | --- |
| Backend database initialization hit `pg_type_typname_nsp_index` | Nine model files called `db.sync()` concurrently on an empty database. | Used a one-time local initializer that loads all models and performs one final synchronized `db.sync()`. |
| `GET /` returned HTTP 404 | The Express application has no root route. | Used real endpoints such as `/ps/blocked-list`, `/ps/pss`, and `/npb/npbs`; the 404 proved the HTTPS server was reachable. |
| Policy and NPB rejected Backend HTTPS with curl error 60 | The Backend certificate is self-signed. | Installed only its public certificate in each VM's CA store and verified requests without `-k`. The private key stays on Backend. |
| Frontend at `192.168.0.95:3005` timed out from Windows | The stable `192.168.0.0/24` addresses are for VM-to-VM control; Windows was using VMware NAT access. | Opened Frontend at `https://192.168.31.136:3005` and configured the browser-facing API as `https://192.168.31.135:3000`. |
| Browser API requests needed a separate certificate exception | Frontend and Backend use different self-signed certificates. | Opened the Backend API URL first and accepted its warning, then opened Frontend and accepted its certificate warning. |
| Dashboard cards stayed Inactive although heartbeat rows existed | The Backend's existing 15-second heartbeat status cron block was commented out. | Enabled that block locally, syntax-checked it, restarted Backend, and verified both device cards changed to Active. This source deviation is intentionally uncommitted pending review. |
| Services worked manually but needed to survive restarts | Initial commands were foreground/manual. | Added systemd units for Kafka/ZooKeeper, Backend, Frontend, NPB preparation, and NPB. Policy DPDK preparation is automatic; the Policy application remains manually launched because its HTTP/TLS mode must be selected. |

## Verified but intentionally local values

- NPB ID: `79c57972-db3b-409e-b4e8-ab4ee526f666`
- Policy Server ID: `6f7e663a-dfae-4b31-9e4e-93bc64d3e0a1`
- Native-service Backend URL: `https://192.168.0.94:3000`
- Browser-facing Backend URL: `https://192.168.31.135:3000`
- Browser-facing Frontend URL: `https://192.168.31.136:3005`

Generated configuration files, certificates, private keys, passwords, VM files, captures, logs, and build output remain outside Git.

## Still pending

- Validate mixed HTTP, TLS, and UDP workloads after deciding how to handle the Policy Server's single-input limitation.
- Review the Backend heartbeat scheduler change as a proper source-code change before any upstream push.
- Decide which screenshots, PCAPs, and result files should be retained as formal test evidence.
