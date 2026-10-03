# Professor discussion: OVS mirroring, passive capture, and reset return

## Current evidence

The current virtual TAP is a Linux bridge plus `tc` ingress mirroring to a separate monitor NIC whose ingress is dropped. The client/Gateway local HTTP/TLS check succeeded in all three monitor states (on, off, on): 12/12 requests returned HTTP 200, while the NPB had no request-matched receive-count row during monitor-off and resumed afterward. This is evidence for the tested mirror-branch independence only. It does not test TAP-VM power loss, physical fail-open behavior, or packet loss/latency; no PCAP was recorded. See the [test report](virtual-tap-independence-test-2026-10-03.md).

The later active reset-injection experiment failed safety validation: one blocked-phase request escaped and 68,032 RST packets were counted over 27 seconds. A return/mirroring loop is a probable explanation, not a packet-capture-proven trace. Temporary test policy and state were cleaned; active injection is disabled. No active reset test should be repeated on shared `NetPro-RX` without a separate return path and reviewed loop controls. See the [failed-test record](virtual-tap-active-blocking-test-2026-10-03.md).

## What the official OVS documentation establishes

Open vSwitch documents SPAN-style mirroring with a dedicated mirror output port; its example states that packets arriving on the mirror destination are dropped. The OVS database manual describes mirror selection by source/destination ports and says that an `output_port` is reserved exclusively for mirroring. These are OVS behaviors, not evidence that OVS is installed or used in this lab. See the [OVS Basic Configuration FAQ](https://docs.openvswitch.org/en/stable/faq/configuration/) and [`ovs-vswitchd.conf.db(5)` Mirror schema](https://www.openvswitch.org/support/dist-docs/ovs-vswitchd.conf.db.5.html).

This suggests an important architecture boundary for discussion: a mirror destination is a copy/observation port, not automatically a bidirectional Policy reset-return path. The project must decide whether a second, explicitly isolated injection path is needed. Neither the current Linux mirror nor an OVS SPAN configuration should be called fail-open without a separate, measured failure test.

## Questions for the professor

1. Is the required deliverable passive traffic observation, active Policy enforcement, or both? If both, should the Policy RST return path be physically or logically separate from the monitor copy path?
2. Is a software mirror on an ordinary VM bridge or virtual switch acceptable for the demonstration, or is a hardware TAP / physical fail-open property required?
3. What does “fail-open” mean for grading: monitor NIC loss, monitoring VM process failure, VM power-off, host/vSwitch failure, or loss of power to an inline device? Which must be demonstrated?
4. Is it acceptable for the mirror destination to discard ingress frames as documented by OVS, with Policy return traffic handled on a different interface/segment?
5. What measurable evidence is required—per-phase client results, NPB counters, packet captures, drop/overlimit counters, a dedicated RST-path test, or all of these?

## Safe next design gate

Do not deploy OVS or change the production lab based on this note alone. After clarifying acceptance criteria, draw the observation and enforcement paths separately, isolate any RST injection return from shared `NetPro-RX`, and define bounded pass/fail tests with explicit cleanup. Keep the current passive mirror configuration until a reviewed design proves otherwise. This note records discussion questions, not an OVS implementation decision.
