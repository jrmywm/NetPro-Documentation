# Offline TLS regression harness

This harness compiles the ClientHello flow and parser functions extracted directly from `policyServer.c`, with small Ethernet, IPv4, TCP, mbuf, endian, and lock stubs. It separately compiles the production `tls_record_tracker.h` against byte-coverage cases. SHA-256 checks pin both code inputs:

- `policyServer.c`: `bf51e1c98b1d2c3a323270fa87e0bebc1759f6d5b5032c316c6c2e302438d819`
- `tls_record_tracker.h`: `e52d75d29585f3e2339fdfa4df4291254ec7dcc164ecb743898eaaba579d7112`

Pass the paths to those two production files and to the classic Ethernet PCAP explicitly. The fixture is reconstructed without assuming a fixed record length or packet sizes. GCC and Python 3 must be on `PATH`; `--gcc` overrides the compiler executable.

The source, tracker, and fixture arguments are required. Replace the example paths below with the locations in your checkout. GCC and Python 3 must be available on `PATH`; use `--gcc` when the compiler executable is elsewhere.

From the documentation repository root on Linux:

```sh
python3 scripts/tls-regression/run_regression.py \
  --source /path/to/NetPro-Policy-Server/policyServer.c \
  --tracker /path/to/NetPro-Policy-Server/tls_record_tracker.h \
  --fixture /path/to/netpro-long-hello.pcap
```

From the documentation repository root in Windows PowerShell:

```powershell
python scripts/tls-regression/run_regression.py `
  --source 'C:\path\to\NetPro-Policy-Server\policyServer.c' `
  --tracker 'C:\path\to\NetPro-Policy-Server\tls_record_tracker.h' `
  --fixture 'C:\path\to\netpro-long-hello.pcap' `
  --gcc 'C:\path\to\gcc.exe'
```

Cases cover in-order delivery, duplicate retransmission, identical overlap, inconsistent overlap, an out-of-order gap, and TCP sequence wrap. Production policy parsing discards gaps and out-of-order delivery; this harness treats that behavior as a rejection and does not claim arbitrary TCP reassembly. Tracker checks separately cover gaps, retransmission idempotence, and wraparound.

This provides offline algorithm coverage only. It does not start a service, send traffic, or establish live end-to-end behavior.
