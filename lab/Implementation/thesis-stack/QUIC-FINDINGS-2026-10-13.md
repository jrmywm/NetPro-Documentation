# Real Caddy / HTTP3 curl integration: current checkpoint

## Status

Not ready for permanent QUIC blocking deployment. Caddy HTTP/3 traffic works
through the virtual TAP. Authenticated Close injection is demonstrated, but
the complete curl request can still succeed when one retry outruns injection.
All temporary candidates were rolled back, and owned test policies and return
rules were removed. No upstream repositories were pushed.

## Components actually installed

- Gateway: persistent Caddy 2.6.2, `https://mysite.local` on
  `192.168.80.28:443`, TCP and UDP. Tests use HTTP3-only, not TCP fallback.
- Client: separate curl git tag curl-8_13_0 build, ngtcp2 v1.12.0,
  nghttp3 v1.8.0 and GnuTLS. Binary reports 8.13.0-DEV.
  `/home/netpro/netpro-thesis/http3/prefix/bin/curl`; system curl untouched.
- Policy Server: actual Net-SNMP tools and restricted lab snmpd.
- Backend: actual snmptrapd and Zabbix 6.0.48 at
  `http://192.168.31.35:8081`; separate `zabbix_thesis` database.
- Zabbix actually ingested PS domain traps in `history_log`, item 47920:
  50 records observed at 01:58:46 UTC on 13 October. This is receipt evidence,
  not a throughput or reliable-blocking measurement.

## What the captures establish

`evidence/live-original-stack-20261013T015336Z`:

- A client Initial was followed by an injected Close at 4.868 ms.
- Close authenticated independently using QUIC v1 server Initial keys derived
  from that connection's original DCID. Destination CID matched client SCID.
- Decrypted frame is CONNECTION_CLOSE, error 0x02, reason
  `BLOCKED_BY_POLICY_SERVER`. 0x02 means CONNECTION_REFUSED, not INTERNAL_ERROR.
- Curl reported `QUIC connect ... failed: Weird server reply` then retried
  using a new UDP source port. It eventually received HTTP 200, version 3.
- The Close for that retry arrived too late. SNMP CLI execution was synchronous
  on the packet thread and increased the processing gap.

`evidence/live-original-stack-20261013T015517Z`:

- Reconstructed per-domain notifications moved to a bounded worker queue,
  still invoking the real `/usr/bin/snmptrap` CLI; no substitute BER sender.
- First Close arrived at 1.936 ms, before the server's 3.599 ms response.
- Curl retried through 17 source-port attempts. On the final attempt,
  server response at 77.338 ms beat Close at 78.563 ms. Request succeeded.
- Therefore removing CLI blocking improves timing but does not establish
  dependable enforcement across automatic retries.

`evidence/live-original-stack-20261013T015831Z`:

- Experimental CRYPTO_ERROR + TLS access_denied (0x131) was also insufficient.
  Curl still eventually completed HTTP 200. Error restored to recovered 0x02.

`evidence/live-original-stack-20261013T020054Z`:

- Experimental bidirectional Close used recovered crafter server mode plus
  client PN=1 and a narrowly scoped local-ingress return rule for Caddy.
- Complete deny test still failed. This extension is NOT proven functional,
  and MUST NOT be described as an original thesis result or deployed as a fix.

## Source provenance and adaptations

Immutable recovered sources and SHA manifests: `original/` and
`SOURCE-PINS.json`. Bintang commit e5448b33ecc98446ec769e8c85092fddb3d5b1e8;
Ibrahim quic-dev b641a5819118cb4a18b4faae0d24143f0224052d.

Candidate retains original QUIC key derivation, header protection, AES-GCM,
SNI parsing and Close crafting. Changes include bounded parsing, allocation
fixes, Close/header length agreement and per-thread parse-to-Close key reuse.
Reconstructed per-domain SNMP is labelled in source and trap text. It uses
recovered enterprise OID because original per-domain source/schema is absent.
Zabbix configuration is newly reconstructed, not a recovered thesis export.

Latest candidate is EXPERIMENTAL, not production:
`c8c20765729aae6fa6220846050c5321844a819524e4b65482aa51b5d21fcf9d`.
ASan/UBSan parser/crafter gate passed 1,200 strict prefixes and 256 mutations;
this does not imply end-to-end blocking passed.

## Decision needed for dependable blocking

Keeping the recovered mirror-only Initial injection design means acknowledging
a race: a passive observer cannot hold back the real handshake. Lower latency
may improve success rate but cannot alone establish guaranteed enforcement.

An inline component that briefly holds Initial packets until policy decision,
then forwards allowed traffic and rejects denied traffic, is a material
architecture change. It should be separately approved, implemented and measured;
it must not be presented as passive TAP blocking or identical thesis code.
No such packet-holding/firewall substitute was silently installed here.

## Existing TLS setup regression after rollback

`evidence/tls-regression-20261013/active-baseline-20261013T020153-11efc3bb.json`
completed successfully (exit 0). All 20 deny probes met the expected reset
result, and all 20 allow-after-delete probes returned HTTP 200. Owned test
policy/server/return helper cleanup completed. This verifies the existing TLS
blocking path; it is not a QUIC pass or an exhaustive whole-system audit.

Before permanent deployment, require: repeated real-client deny/allow results,
HTTP/TLS regression, CRUD/persistence verification, genuine periodic SNMP
receipt and workload measurements with clearly stated denominators.
