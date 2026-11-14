# Promoted browser QUIC source snapshot

These are the exact C sources/headers from the candidate build directories promoted on 14 November 2026. Source manifests record file hashes and corresponding binary hashes. This includes the effective Policy Server/dataplane changes assembled by the builder, rather than only its unmodified input templates.

The browser Initial capture fixtures used by the sanitizer gate remain local. The gate C source is retained. Build commands are recorded in `../build-browser-reassembly.py` and `../build-browser-npb.py`; paths to original dependency headers/libraries are lab-specific. Executables are not included in Git.
