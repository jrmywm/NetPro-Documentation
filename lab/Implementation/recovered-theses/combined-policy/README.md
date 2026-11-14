# Active HTTP/TLS monitoring and lookup build

Collected from Policy VM after the 7 November combined acceptance run. DEPLOYED.json pins the active binary and remote source hashes. This directory preserves the actual C/header source used by that build, including Rafie lookup, Kafka startup retry, consolidated broker address and Bintang monitoring. The local Makefile has trailing whitespace removed for Git checks; its recorded remote hash refers to the original deployed Makefile.

The per-domain notification and Zabbix configuration remain labelled reconstructions. The monitoring worker uses control CPU 0 in the current four-core lab; change that mapping deliberately if CPU allocation changes. Original recovered source archives are separate and unchanged.

The staged combined QUIC candidate is separate. It was temporarily tested, failed full-path deny acceptance and was not left selected. See INTEGRATION-RESULTS-2026-11-07.md one directory above for results, evidence locations, known intermittent TCP reset failures and fidelity limits.

Build with the retained Makefile and DPDK/SQLite/rdkafka/curl/jansson/pthread dependencies on the Policy VM. Do not invoke the Makefile shared target on the live checkout without a guarded rollout: it changes the selected binary symlink. No upstream repository was pushed.
