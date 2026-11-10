"""Generate the 12 challenge cases C041-C052 (split = "challenge").

The core set (C001-C040) turned out to be largely solvable by shortcuts: the
deterministic rules alone reach 92% and a complaint-only LLM 85%. Each
challenge case targets one such shortcut while keeping the label consistent
with the evidence definitions in data/taxonomy.yaml:

  * stale or misleading console readings that only the customer can correct
    (requires_interaction = true: the decisive fact comes from a question or a
    failed fix, so the rule matcher alone cannot reach the label);
  * a wrong self-diagnosis in the complaint that complaint-only systems follow.

These cases were written by the author to probe known failure modes; report
them separately from the core set rather than as an independent benchmark.
Usage: python -m eval.generate_challenge_cases [--force]
"""
import argparse
import json

from eval.generate_cases import CASES_DIR, _device, _healthy_base

NOISE = [
    "02:00:03 scheduled housekeeping completed (event database vacuum 0.4 s)",
    "04:10:48 cloud time sync ok (drift 1 s)",
    "06:30:12 radio channel scan: channel 4 selected, utilisation 18%",
    "23:57:40 remote app session authenticated",
]


def _healthy_v3():
    return [
        _device("door_front", "Front Door", "SEN-D1", "1.3", rssi=-57, battery=83),
        _device("motion_hall", "Hallway Motion", "SEN-M1", "1.4", rssi=-63, battery=66),
        _device("cam_front", "Front Cam", "CAM-S1", "2.1", rssi=-67, battery=58),
        _device("win_kitchen", "Kitchen Window", "SEN-D1", "1.3", rssi=-61, battery=47),
        _device("cam_hall", "Hall Cam", "CAM-I2", "2.0", rssi=-59, battery=None),
    ]


def _healthy_v2():
    return [
        _device("door_front", "Front Door", "SEN-D1", "1.0", rssi=-55, battery=90),
        _device("door_back", "Back Door", "SEN-D1", "1.0", rssi=-60, battery=86),
        _device("win_kitchen", "Kitchen Window", "SEN-D1", "1.0", rssi=-62, battery=71),
        _device("motion_hall", "Hallway Motion", "SEN-M1", "1.1", rssi=-59, battery=66),
        _device("motion_stairs", "Stairs Motion", "SEN-M1", "1.1", rssi=-64, battery=52),
        _device("cam_garden", "Garden Cam", "CAM-S1", "1.8", rssi=-66, battery=58),
    ]


def _without(devices, *ids):
    return [d for d in devices if d["id"] not in ids]


def _case(case_id, cause, tier, complaint, base, devices, logs, knowledge, outcomes,
          checks, requires_interaction, notes):
    return {
        "case_id": case_id,
        "complaint": complaint,
        "hidden_state": {"base_station": base, "devices": devices, "logs": logs},
        "user_knowledge": knowledge,
        "action_outcomes": outcomes,
        "gt_root_cause": cause,
        "gt_tier": tier,
        "gt_key_checks": checks,
        "difficulty": "hard",
        "split": "challenge",
        "requires_interaction": requires_interaction,
        "notes": notes,
    }


def build_cases():
    return [
        _case(
            "C041", "HW_FAULT_SUSPECTED", "L2",
            "Our garage camera has been offline for two days. The garage is at the far end of the house, "
            "so I assume the signal is just too weak out there. Is there a booster or repeater I can buy? "
            "Everything else seems to work fine and I haven't changed anything in the app.",
            _healthy_base(),
            [_device("cam_garage", "Garage Cam", "CAM-I2", "2.0", status="offline", rssi=-83, battery=None),
             *_healthy_v3()],
            [NOISE[0], "cam_garage last RSSI -83 dBm (recorded 2 days ago at the garage location)",
             "cam_garage offline since 2 days 14:22", NOISE[1],
             "cam_garage power-on event 09:12 yesterday, no heartbeat followed", NOISE[2]],
            {"device_location": "next to the base station",
             "move_history": "Yesterday I brought the camera inside and put it right next to the base station "
                             "to test; it still did not come online.",
             "reset_performed": "I held its reset button for 10 seconds yesterday; the LED goes solid, then dark.",
             "recent_changes": "none"},
            {"move_device_closer": "It is already sitting right next to the base station since yesterday and "
                                   "it is still offline.",
             "install_repeater": "I don't own a repeater, and the camera is next to the base station anyway; "
                                 "still offline.",
             "restart_base_station": "No change, the camera stays offline.",
             "re_pair_device": "Pairing starts, but the camera drops off again within a minute."},
            ["S1", "S3", "S5"], True,
            "The console RSSI is a stale reading from the garage. The customer already tested the camera next "
            "to the base after a reset. Rules and complaint point to WEAK_SIGNAL; only dialogue reveals a "
            "hardware fault.",
        ),
        _case(
            "C042", "PROTOCOL_CONFLICT", "L2",
            "Since the automatic update the night before last, my garage motion sensor doesn't trigger anything. "
            "Its light still blinks when I walk past and the app shows a little update badge on it, so I suppose "
            "it just needs an update? Please tell me the quickest way to get it working again.",
            _healthy_base(fw="4.5", error_codes=["E-305"]),
            [_device("motion_garage", "Garage Motion", "SEN-M1", "1.1", status="connected_no_events",
                     rssi=-63, battery=68),
             *_healthy_v3()],
            [NOISE[0], "base station firmware updated 4.2 -> 4.5 at 03:05",
             "motion_garage: E-305 protocol v2 not supported",
             "motion_garage: OTA to 1.4 failed at 61% (image checksum mismatch), retry 1/3",
             "motion_garage: OTA to 1.4 failed at 61% (image checksum mismatch), retry 2/3", NOISE[1]],
            {"ota_attempts": "I tapped the update button twice this morning; both times it said 'update failed'.",
             "sensor_led": "blinks normally when I walk past",
             "recent_changes": "nothing that I did; there was an automatic update"},
            {"ota_upgrade": "The update runs to about 60% and then the app says 'Update failed (E-305)'. "
                            "The sensor still sends no alerts.",
             "move_device_closer": "Placed it next to the base station and tried the update again: same failure "
                                   "at 60%.",
             "restart_base_station": "No change, still no alerts.",
             "replace_battery": "New battery, still no alerts."},
            ["S1", "S4"], False,
            "An OTA path exists in the catalogue (so the rules say PERIPHERAL_FW_OUTDATED, L1), but the base "
            "log already shows the OTA failing twice, which makes it a protocol conflict needing FAE (cf. H-03). "
            "The decisive fact is on the console, so no dialogue is required; complaint-only systems follow the "
            "customer's 'it just needs an update'.",
        ),
        _case(
            "C043", "BS_NETWORK_DOWN", "L1",
            "The garden camera is offline again. Its battery was low last week and I thought charging it would "
            "fix it, but it's still not working. Can you just send me a new battery for it? I didn't really "
            "check the rest of the system, I only use that camera.",
            _healthy_base(online=False, uplink_status="no_internet"),
            [_device("cam_garden", "Garden Cam", "CAM-S1", "2.1", status="offline", rssi=None, battery=6),
             *[{**d, "status": "offline", "rssi": None} for d in _healthy_v3()]],
            [NOISE[0], "Monday 18:02 uplink lost: ethernet link down", "Monday 18:02 cloud session closed",
             "cam_garden low battery warning 6% (last report before uplink loss)", NOISE[2]],
            {"base_led": "blinking red",
             "router": "We changed internet provider on Monday; the new router is in the hallway.",
             "other_devices": "Now that you mention it, the app shows everything as offline.",
             "recent_changes": "new internet provider and router on Monday"},
            {"charge_camera": "I charged it fully again; it still shows offline.",
             "restart_base_station": "The base station still blinks red.",
             "reconnect_uplink_and_power_cycle": "After plugging the base station's Ethernet cable into the new "
                                                 "router and power-cycling router then base, the LED turns blue "
                                                 "and all devices come back online.",
             "replace_battery": "No change."},
            ["S1"], False,
            "The master is down, so every peripheral looks offline; the low-battery garden camera the customer "
            "blames is a distractor that topology-ordered checking prunes.",
        ),
        _case(
            "C044", "BATTERY_LOW", "L1",
            "Two of my sensors went offline overnight, the back door and the back window. Two at once seems like "
            "something bigger is wrong with the system. Should I be worried that the base station is failing? "
            "It's quite new and I don't want to lose the warranty period.",
            _healthy_base(),
            [_device("door_back", "Back Door", "SEN-D1", "1.3", status="offline", rssi=None, battery=3),
             _device("win_back", "Back Window", "SEN-D1", "1.3", status="offline", rssi=None, battery=5),
             *_healthy_v3()],
            [NOISE[0], "Thursday 08:12 door_back low battery warning (7%)",
             "Thursday 08:15 win_back low battery warning (9%)", "02:14:51 door_back lost",
             "05:47:09 win_back lost", "rssi history (7 days) door_back -58 to -61 dBm, win_back -60 to -63 dBm"],
            {"sensor_age": "Both were installed on the same day about 14 months ago.",
             "battery_warnings": "I think I dismissed some low battery notifications last week.",
             "base_led": "solid blue"},
            {"replace_battery": "After putting new batteries in both sensors they come back online within a "
                                "minute.",
             "restart_base_station": "No change, both still offline.",
             "move_device_closer": "No change."},
            ["S1", "S2", "S5"], False,
            "Two devices offline looks like a batch failure, but they dropped hours apart and both batteries are "
            "nearly empty; no E-610, so it is not escalated.",
        ),
        _case(
            "C045", "BINDING_TABLE_CORRUPT", "L2",
            "I can't add my new garage door sensor, the app says the system is full. That makes no sense: I only "
            "have 7 devices in the app and the manual says this base station supports 8. I already removed the "
            "old hallway sensor from the app last year, so there should be a free slot.",
            _healthy_base(model="HB-100", fw="3.4", error_codes=["E-201"]),
            [*_healthy_v2(),
             _device("cam_porch", "Porch Cam", "CAM-S1", "1.8", rssi=-63, battery=61),
             _device("motion_old", "Sensor 7", "SEN-M1", "1.1", status="offline", rssi=None, battery=None,
                     bound=True, app_bound=False),
             _device("door_garage", "New Garage Door", "SEN-D1", "1.0", status="not_paired", rssi=None,
                     battery=100, bound=False, app_bound=False)],
            [NOISE[0], "pairing request rejected: E-201 capacity reached (8/8)",
             "binding slot 7 (motion_old) has no matching account record", NOISE[1], NOISE[3]],
            {"devices_in_app": "7",
             "removed_device": "I deleted the old hallway motion sensor from the app last spring and threw it "
                               "away.",
             "error_message": "Something like 'device limit reached'.",
             "distance_during_pairing": "right next to the base station"},
            {"remove_unused_device": "I can't find anything to remove; the app only lists my 7 devices and I use "
                                     "all of them.",
             "restart_base_station": "Still says the limit is reached.",
             "retry_pairing": "Same error.",
             "re_add_removed_device": "I don't have that old sensor any more."},
            ["S1", "S2"], False,
            "The base table is full (8/8) while the app lists 7 devices: slot 7 is a ghost binding of a sensor "
            "the customer deleted in the app. It looks like CAPACITY_EXCEEDED, but the standard 'remove an "
            "unused device' fix is impossible from the app, so FAE tooling is needed. The app/base mismatch is "
            "visible on the console (no dialogue required).",
        ),
        _case(
            "C046", "WEAK_SIGNAL", "L1",
            "The camera on the garden shed is clearly defective. It keeps freezing and going offline and the "
            "picture is choppy. It's only four months old and still under warranty, so I'd like a replacement "
            "unit sent out please. I've already restarted it a few times and it makes no difference.",
            _healthy_base(),
            [_device("cam_shed", "Shed Cam", "CAM-S1", "2.1", status="intermittent", rssi=-87, battery=64),
             *_healthy_v3()],
            [NOISE[0], "cam_shed heartbeat lost 9 times in last 24h", "cam_shed reconnected (rssi -87)",
             NOISE[1], NOISE[2]],
            {"camera_location": "on the shed at the bottom of the garden, about 25 m from the house",
             "obstacles": "The signal has to pass the kitchen wall and our new metal garden fence.",
             "recent_changes": "We put up a metal fence last month."},
            {"restart_camera": "It comes back but freezes again later.",
             "move_device_closer": "As a test I held the camera at the back door and it streamed perfectly.",
             "install_repeater": "With the RP-1 repeater in the conservatory the shed camera has stayed online "
                                 "for two days.",
             "restart_base_station": "No change."},
            ["S1", "S3"], False,
            "The customer asks for a replacement (hardware), but the console shows -87 dBm on one device only "
            "and a new metal fence; a repeater fixes it.",
        ),
        _case(
            "C047", "PERIPHERAL_FW_OUTDATED", "L1",
            "The living room motion sensor stopped sending alerts since yesterday. The app shows that its battery "
            "is getting low (12%), so I guess that's the reason? I'll buy batteries, but wanted to check first "
            "because its light still blinks when I walk past it.",
            _healthy_base(fw="4.5", error_codes=["E-305"]),
            [_device("motion_living", "Living Motion", "SEN-M1", "1.1", status="connected_no_events",
                     rssi=-60, battery=12),
             *_healthy_v3()],
            [NOISE[0], "base station firmware updated 4.2 -> 4.5 at 02:58",
             "motion_living: E-305 protocol v2 not supported", NOISE[1], NOISE[3]],
            {"sensor_led": "blinks when I walk past",
             "app_badge": "There is an orange update dot on that sensor.",
             "recent_changes": "none by me"},
            {"replace_battery": "New battery in, it shows 100%, but still no alerts.",
             "ota_upgrade": "The sensor updates to 1.4 in about three minutes; alerts work again.",
             "restart_base_station": "No change."},
            ["S1", "S4"], False,
            "The customer blames a 12% battery; the decisive evidence is the base update to 4.5 and E-305 with "
            "an OTA path.",
        ),
        _case(
            "C048", "PAIR_TIMEOUT", "L1",
            "My new window sensor won't pair. I think we've hit the maximum number of devices, my neighbour had the "
            "same problem with the same base station. Do I need to buy the bigger base station? I've tried three "
            "times from the living room sofa and it fails every time.",
            _healthy_base(model="HB-100", fw="3.4"),
            [*_healthy_v2(),
             _device("win_new", "New Window", "SEN-D1", "1.0", status="not_paired", rssi=None, battery=100,
                     bound=False, app_bound=False)],
            [NOISE[0], "19:02:10 pairing window opened", "19:04:10 pairing window expired: no join request received",
             "19:05:40 pairing window opened", "19:07:40 pairing window expired: no join request received", NOISE[1]],
            {"distance_during_pairing": "The base station is upstairs in the office; I was downstairs on the sofa.",
             "sensor_button": "I pressed the button once; the LED flashed once and went off.",
             "error_message": "The app says 'pairing timed out'."},
            {"retry_pairing_close_hold_sync": "Holding the button for 3 seconds right next to the base station, "
                                              "the LED blinks blue and the sensor pairs straight away.",
             "restart_base_station": "Still times out.",
             "remove_unused_device": "I use all of my devices."},
            ["S1", "S2"], False,
            "The customer is sure the base is full, but 7/8 slots are used and the log shows join requests "
            "never arrived: the sensor was far away and the SYNC button not held.",
        ),
        _case(
            "C049", "STORAGE_FULL", "L1",
            "Our camera recordings stopped about two weeks ago. Live view works fine, but there are no new clips in "
            "the event list after the 3rd. I think the internet must be dropping at night, our broadband has been "
            "flaky. Should I call my internet provider about it?",
            _healthy_base(storage_used_pct=99, loop_recording=False, error_codes=["E-402"]),
            _healthy_v3(),
            [NOISE[0], "E-402 recording storage full (99%)", "event clip discarded: no free space",
             "event clip discarded: no free space", NOISE[1]],
            {"loop_recording_setting": "I don't know what that is.",
             "storage": "We never changed the storage.",
             "internet": "Streaming and everything else at home works fine, actually."},
            {"restart_router": "No change, still no new clips.",
             "enable_loop_recording": "After switching on loop recording, new clips appear again within minutes.",
             "format_storage": "After backing up and formatting, recordings resume."},
            ["S1"], False,
            "Blamed on the internet; the base station is online but storage is 99% full with loop recording off.",
        ),
        _case(
            "C050", "HW_FAULT_SUSPECTED", "L2",
            "Porch camera offline. It said low battery a few days ago, so maybe that's all it is. I don't have much "
            "time to deal with this, so please just tell me what to do or send me whatever part I need and I'll "
            "swap it myself this weekend.",
            _healthy_base(),
            [_device("cam_porch", "Porch Cam", "CAM-S1", "2.1", status="offline", rssi=-64, battery=7),
             *_healthy_v3()],
            [NOISE[0], "cam_porch low battery warning 7% (3 days ago, last report)",
             "cam_porch offline since yesterday 18:40", "cam_porch power-on event 07:15, disconnect 07:16",
             NOISE[1]],
            {"device_location": "next to the base station",
             "charging": "I charged it to 100% overnight with the original cable and brought it next to the base "
                         "station this morning.",
             "reset_performed": "I also did the 10-second reset; the LED goes green and then off.",
             "recent_changes": "none"},
            {"charge_battery": "It has been fully charged since this morning and is still offline.",
             "move_device_closer": "It's already next to the base station and still offline.",
             "re_pair_device": "It pairs, then drops off again within a minute.",
             "restart_base_station": "No change."},
            ["S1", "S3", "S5"], True,
            "The console battery (7%) is the last report before the fault; the customer has already charged, "
            "moved and reset it. Rules say BATTERY_LOW; only dialogue reveals the hardware fault.",
        ),
        _case(
            "C051", "BATCH_LINK_FAILURE", "L2",
            "The back door sensor shows a low battery and has gone offline, so I'll change the battery tonight. "
            "While I have you on the line, is there anything else I should check? I haven't looked at the rest "
            "of the system today, I've been at work.",
            _healthy_base(error_codes=["E-610"]),
            [_device("door_back", "Back Door", "SEN-D1", "1.3", status="offline", rssi=None, battery=8),
             _device("motion_living", "Living Motion", "SEN-M1", "1.4", status="offline", rssi=None, battery=71),
             _device("win_bed", "Bedroom Window", "SEN-D1", "1.3", status="offline", rssi=None, battery=66),
             *_without(_healthy_v3(), "motion_hall")],
            [NOISE[0], "21:14:02 door_back lost", "21:14:02 motion_living lost", "21:14:03 win_bed lost",
             "E-610 radio module self-test warning",
             "rssi history (7 days) for the three sensors: -54 to -65 dBm", "door_back low battery warning (8%)"],
            {"other_devices": "I hadn't noticed, but the living room motion and bedroom window also say offline.",
             "base_led": "solid blue",
             "recent_changes": "none"},
            {"replace_battery": "New battery in the back door sensor; it and the other two still show offline.",
             "restart_base_station": "All three stay offline.",
             "move_device_closer": "Still offline even next to the base station."},
            ["S1", "S2", "S3"], False,
            "The customer's low-battery explanation covers only one of three sensors that dropped within one "
            "second together with E-610.",
        ),
        _case(
            "C052", "UPLINK_BLOCKED_PERSIST", "L2",
            "Since last week we don't get any push notifications on our phones, even though the siren works when "
            "the alarm goes off at home. I reinstalled the app on both phones and it didn't help. Maybe the latest "
            "app version is just buggy? Is there an older version I can install?",
            _healthy_base(error_codes=["E-503"]),
            _healthy_v3(),
            [NOISE[0], "E-503 cloud report failed: TLS handshake error", "local recording ok",
             "E-503 cloud report failed: TLS handshake error", NOISE[1]],
            {"internet": "Internet works fine for everything else.",
             "router_restarted": "Not yet.",
             "recent_changes": "none"},
            {"restart_router": "Rebooted the router; notifications still don't arrive.",
             "reset_router_dns": "Set DNS back to automatic and rebooted; still no notifications.",
             "reinstall_app": "Already did it, no change.",
             "restart_base_station": "No change."},
            ["S1"], True,
            "Blamed on the app. E-503 with a working local system first suggests an uplink problem (L1); only "
            "after router reboot and DNS reset fail does it become a persistent cloud-channel fault (L2).",
        ),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Overwrite existing C041-C052 files.")
    a = ap.parse_args()
    for case in build_cases():
        path = CASES_DIR / f"{case['case_id']}.json"
        if path.exists() and not a.force:
            raise SystemExit(f"{path.name} exists; use --force to overwrite")
        path.write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(build_cases())} challenge cases to {CASES_DIR}")


if __name__ == "__main__":
    main()
