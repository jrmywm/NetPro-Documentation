# Frontend chart and passive-capture plan

## Frontend chart fix

The frontend chart update preserves ISO timestamps as timestamps and does not convert them to locale-formatted strings and parse those strings again. Chart data is sorted by datetime, axis labels use local `HH:mm`, and tooltips show the full date and timezone. Integer-valued counters use integer Y-axis ticks. Empty and invalid data are handled without breaking chart rendering.

Four chart tests passed and the test process exited successfully. `npm run build` also exited successfully with existing dependency and lint warnings, and `netpro-frontend` is active. The chart fix is verified by the tests and successful build. The frontend source change is local commit `e4a947a`.

## Capture and enforcement architecture

The supplied thesis, `skripsi natthan.pdf`, Chapter 3 (printed pages 22–25; PDF pages 37–40), describes `PassiveTap` as a separate component between client and router that copies packets passing along the link to the NPB. It does not specify a hardware model or say that a PC must implement the component. Chapter 4's experiments use virtual machines and adapters including VMXNET3 and VMBR bridges (printed pages 57–59; PDF pages 72–74), including Ubuntu and Windows VMs and a cloud web-server VM. These passages do not establish a physical TAP requirement or prescribe a PC-as-TAP implementation.

The thesis distinguishes the capture-copy function from Policy enforcement; Policy's reset path remains active in the architecture. The current inline NAT/software-mirror arrangement has not yet demonstrated independent capture. A gateway software mirror can emulate the copy function in this virtual lab, but is not evidence of a hardware TAP or of a specified PC implementation. The next design should separate two paths:

1. A normal-traffic observation path that copies client-to-router packets to the NPB without placing the NPB in the forwarding path.
2. An enforcement path that injects Policy-generated TCP resets toward both endpoints when policy requires blocking.

Use a virtual mirror to emulate the observation path in the VM lab and label the result as emulation. Keep enforcement as a separate design path. The thesis itself does not settle whether the project deliverable must use hardware; ask the professor to confirm that acceptance criterion before making a hardware claim or choosing equipment.

## Work sequence

1. Complete and record the frontend build and chart review.
2. Document the normal traffic copy and reset-injection topology separately, including where each packet path connects.
3. Confirm the project's acceptance criterion with the professor. If virtual mirroring is sufficient for a demonstration, label it as virtual emulation; if hardware capture is required, validate a hardware design against that requirement.
