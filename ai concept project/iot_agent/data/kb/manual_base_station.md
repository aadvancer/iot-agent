# HB Series Base Station Manual (fictional)

## LED status indicators
Solid blue: online and connected to cloud. Blinking blue: pairing mode (lasts 120 seconds). Solid red: no internet uplink. Blinking red: booting or firmware update in progress, do not unplug. Solid purple: storage almost full (over 95 percent).

## Network uplink
The base station connects to the home router by Ethernet (recommended) or 2.4 GHz Wi-Fi. If all cameras and sensors show offline in the app at the same time, first check whether the base station itself is online. Power-cycle the router, wait 2 minutes, then power-cycle the base station. The base station requires outbound TCP 443 and 8883 to the cloud.

## Device capacity
HB-100 supports up to 8 bound peripherals. HB-200 supports up to 16 bound peripherals. When the limit is reached, pairing a new device fails with error E-201 even if the device is in pairing mode. Remove an unused device in the app (Device Settings > Remove Device) to free a slot.

## Orphaned binding (device removed in app but still bound in base station)
If a device is removed in the app while it is offline or out of range, the base station may keep its entry. This orphaned ("ghost") binding still occupies a slot, so the base station can report E-201 although the app lists fewer devices than the limit. Frontline cannot clear it: the app only removes devices it lists, re-pairing does not free the slot, and a base-station factory reset is not allowed. Treat it as a binding-table inconsistency (app and base station disagree) and escalate to FAE, who remove the entry with the backend binding tool. Put the orphaned device id and the bound count (for example 8/8) in the ticket.

## Local storage
Event clips are stored on the base station's internal eMMC (HB-100: 16 GB, HB-200: 32 GB). When loop recording is disabled and storage reaches 98 percent, new events are not recorded and error E-402 is shown. Enable loop recording in Base Station Settings > Storage, or format the storage after exporting clips.

## Firmware update
Base station firmware updates are pushed automatically at night. HB-200 firmware 4.5 removes support for the legacy v2 radio protocol. Peripherals still running v2 firmware must be upgraded to v3 firmware before or after the base station update, otherwise they disconnect.

## Restart and reset
A short press (1 s) on the rear button restarts the base station without data loss. A long press (10 s) performs a factory reset and erases all bindings; frontline staff must never instruct customers to factory-reset the base station without FAE approval.
