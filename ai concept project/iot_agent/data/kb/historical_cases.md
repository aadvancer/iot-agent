# Historical Support Cases (synthetic summaries)

## H-01 Garage camera keeps dropping
Customer reported a CAM-S1 in a detached garage going offline several times a day. RSSI was -86 dBm; all other devices normal. Installing an RP-1 repeater solved it. Resolved at frontline.

## H-02 Cannot add ninth sensor
HB-100 owner could not add a new door sensor; app showed E-201. Base station already had 8 devices. Customer removed an old test sensor and pairing succeeded. Resolved at frontline.

## H-03 Indoor camera lost after night update
After HB-200 auto-updated to 4.5, a CAM-I2 running 1.2 disconnected with E-305. OTA not offered for this hardware revision. Escalated; FAE confirmed protocol v2 dropped and arranged a compatibility firmware. Escalated correctly.

## H-04 Whole house offline
All devices offline, base station LED solid red. Router had been replaced the previous day and the Ethernet cable was in the wrong port. Resolved at frontline.

## H-05 Three sensors offline at once
Three sensors in different rooms went offline at the same minute; base station online, RSSI history normal, E-610 in log. Restarting did not help. Escalated; radio module replaced. Escalated correctly.

## H-06 Events not in cloud
Base station online, live view works on local network, but no event notifications; E-503 every few minutes. Router restart and DNS reset did not help. Escalated; expired device certificate on backend. Escalated correctly.

## H-07 Missing motion alerts after base update
SEN-M1 on firmware 1.1 stopped reporting after base update to 4.5 with E-305. OTA to 1.4 succeeded and alerts resumed. Resolved at frontline. Note: initially escalated unnecessarily - an example of avoidable FAE workload.
