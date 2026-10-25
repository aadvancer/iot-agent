# Fault Code Reference (fictional)

## E-201 Capacity reached
The base station already holds its maximum number of bound peripherals. Frontline action: remove an unused device. Not an escalation case.

## E-207 Binding write failed
The base station could not write the new binding into its binding table. A single occurrence can follow a power interruption during pairing; retry once after restarting the base station. If E-207 repeats, or the app lists a device that the base station table does not contain, the binding table is likely corrupted: escalate to FAE. Do not factory-reset the base station.

## E-305 Protocol / firmware mismatch
The peripheral firmware speaks a radio protocol the base station no longer supports, or vice versa. Frontline action: trigger OTA upgrade of the peripheral. If OTA is not available for the device or fails twice, escalate to FAE as protocol conflict.

## E-402 Storage full
Base station storage at or above 98 percent with loop recording disabled. Frontline action: enable loop recording or format storage.

## E-503 Cloud reporting failed
The base station could not deliver events to the cloud. Frontline action: verify internet access, restart router and base station, set router DNS to automatic. If E-503 persists after these steps while the base station is online, escalate to FAE (cloud channel or certificate issue).

## E-610 Radio module error
Logged by the base station when its sub-GHz radio fails self-test or multiple peripherals drop simultaneously. Always escalate to FAE.
