# Frontend chart and passive-capture plan

## Frontend chart fix

The frontend chart update preserves ISO timestamps as timestamps and does not convert them to locale-formatted strings and parse those strings again. Chart data is sorted by datetime, axis labels use local `HH:mm`, and tooltips show the full date and timezone. Integer-valued counters use integer Y-axis ticks. Empty and invalid data are handled without breaking chart rendering.

Four chart tests passed and the test process exited successfully. `npm run build` also exited successfully with existing dependency and lint warnings, and `netpro-frontend` is active. The chart fix is verified by the tests and successful build. The frontend source change is local commit `e4a947a`.

## Capture and enforcement architecture

The supplied thesis, `skripsi natthan.pdf`, pages 37–40 (printed pages 22–25), describes a passive physical TAP copying client-to-router traffic to the NPB. In the same design, Policy is active: TCP resets are routed to both endpoints. This is the reference architecture, not evidence that the current virtual lab is passive.

The current inline NAT/software-mirror arrangement is not a physical passive TAP. The next design should separate two paths:

1. A normal-traffic observation path that copies client-to-router packets to the NPB without placing the NPB in the forwarding path.
2. An enforcement path that injects Policy-generated TCP resets toward both endpoints when policy requires blocking.

Use a virtual mirror only to emulate the observation path in the VM lab; describe it as emulation. Do not remove enforcement as the final design. Whether the project requires a physical TAP or accepts virtual capture for the deliverable remains an acceptance decision to record before selecting hardware or claiming passive capture.

## Work sequence

1. Complete and record the frontend build and chart review.
2. Document the normal traffic copy and reset-injection topology separately, including where each packet path connects.
3. Decide whether physical TAP hardware is a project acceptance requirement; if it is, validate the design against that requirement. If virtual mirroring is accepted for demonstration, label the result as virtual emulation.
