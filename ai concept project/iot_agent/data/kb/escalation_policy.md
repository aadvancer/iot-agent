# Frontline Support and FAE Escalation Policy (fictional)

## Purpose
FAE engineers are a scarce resource. Frontline staff should close all self-recoverable interaction faults themselves and escalate only cases that need protocol-level analysis, backend investigation or hardware decisions.

## Close at frontline (L1)
Uplink loss of the base station, pairing timeouts, capacity limit reached, weak signal of a single device, low battery, outdated peripheral firmware that upgrades successfully via OTA, and full storage. Provide the customer with step-by-step instructions and confirm the issue is resolved.

## Escalate to FAE (L2)
Escalate when any of the following holds: (1) two or more peripherals fail at the same time while the base station is online; (2) a firmware or protocol mismatch remains after an OTA attempt or OTA is not possible; (3) the standard frontline fix was executed and the problem persists; (4) the app's device list and the base station binding table disagree; (5) a device fails even next to the base station after a factory reset.

## Escalation ticket content
An escalation ticket must contain: customer symptom summary, base station model and firmware, affected devices with model, firmware, RSSI and battery, fault codes and relevant log lines, the troubleshooting steps already performed with their results, and the suspected root cause.

## What frontline must never do
Never instruct a factory reset of the base station, never downgrade firmware, never promise replacement hardware.
