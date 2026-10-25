# Peripheral Devices Manual (fictional)

## Pairing a peripheral
Put the base station into pairing mode from the app (Add Device). Then hold the SYNC button on the camera or sensor for 3 seconds until its LED blinks blue. Keep the peripheral within 1 metre of the base station during pairing. Pairing times out after 120 seconds. After pairing, the device can be moved to its final location.

## Wireless range and signal strength
Peripherals talk to the base station over a sub-GHz proprietary radio. Signal strength (RSSI) is shown in Device Settings > Device Info. Above -70 dBm is good, -70 to -80 dBm is acceptable, below -80 dBm causes intermittent disconnections, delayed notifications and choppy live view. Concrete walls, metal doors and fridges strongly attenuate the signal. Fix: move the device or base station, or install the official RP-1 repeater.

## Battery cameras (CAM-S1)
CAM-S1 runs on a rechargeable battery lasting 3 to 6 months. Below 10 percent the camera disables live view and may miss events; below 3 percent it goes offline. Charge with the supplied USB-C cable for about 6 hours. Frequent motion events in busy areas shorten battery life; enable power-saving mode.

## Peripheral firmware and OTA
Peripheral firmware is upgraded over the air (OTA) from the base station. Requirements: device within normal signal range, battery above 30 percent. CAM-S1 1.x upgrades to 2.1 (protocol v3). SEN-D1 1.0 upgrades to 1.3, SEN-M1 1.1 upgrades to 1.4. CAM-I2 hardware revision A with firmware 1.2 cannot be upgraded to protocol v3.

## Factory reset of a peripheral
Hold SYNC for 15 seconds until the LED flashes white. This removes the peripheral's own binding but does not remove it from the base station table; remove it in the app first, then reset, then pair again.
