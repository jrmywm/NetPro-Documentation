# TRex profile MAC correction

This folder contains the five corrected generator profiles, their `MANIFEST.sha256`, the reviewed deployment helper, and read-only telemetry SQL. The deployment changed only the explicit MAC override arguments; it preserved profile traffic rates, timing, and packet contents. Original copies are in `/tmp/netpro-mac-profile-backup.VCd3af` on the Packet Generator VM. See the [controlled mixed retest result](../../docs/trex-profile-mac-fix-2026-10-02.md). Do not run the deployment helper as part of ordinary traffic generation.
