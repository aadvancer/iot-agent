"""Generate 35 additional deterministic synthetic support cases (C006-C040)."""
import argparse
import json
from pathlib import Path


CASES_DIR = Path(__file__).resolve().parents[1] / "data" / "cases"


def _device(device_id, name, model, fw, status="online", rssi=-62, battery=70,
            bound=True, app_bound=True):
    return {
        "id": device_id,
        "name": name,
        "model": model,
        "fw": fw,
        "bound_in_base": bound,
        "bound_in_app": app_bound,
        "rssi": rssi,
        "battery": battery,
        "status": status,
    }


def _case(case_id, complaint, cause, base, devices, logs, knowledge=None,
          outcomes=None, checks=None, difficulty="medium", notes=""):
    return {
        "case_id": case_id,
        "complaint": complaint,
        "hidden_state": {
            "base_station": base,
            "devices": devices,
            "logs": logs,
        },
        "user_knowledge": knowledge or {"recent_changes": "none"},
        "action_outcomes": outcomes or {},
        "gt_root_cause": cause,
        "gt_tier": "L2" if cause in {
            "PROTOCOL_CONFLICT", "BATCH_LINK_FAILURE", "UPLINK_BLOCKED_PERSIST",
            "BINDING_TABLE_CORRUPT", "HW_FAULT_SUSPECTED",
        } else "L1",
        "gt_key_checks": checks or ["S1", "S2"],
        "difficulty": difficulty,
        "notes": notes,
    }


def _healthy_base(model="HB-200", fw="4.2", **changes):
    return {
        "model": model,
        "fw": fw,
        "online": True,
        "uplink_status": "ok",
        "storage_used_pct": 42,
        "loop_recording": True,
        "error_codes": [],
        **changes,
    }


def _supporting_devices():
    return [
        _device("door_front", "Front Door", "SEN-D1", "1.3", rssi=-58, battery=82),
        _device("motion_hall", "Hallway Motion", "SEN-M1", "1.4", rssi=-64, battery=74),
    ]


def _build_cases():
    cases = []

    # S1: base-station internet/uplink faults.
    for i, (model, fw, complaint, location) in enumerate([
        ("HB-100", "3.4", "All my cameras and sensors are offline after a router change.",
         "the router was replaced yesterday"),
        ("HB-200", "4.2", "Nothing is reaching the app and the base station has a red light.",
         "the Ethernet cable may have been moved"),
        ("HB-200", "4.5", "Every device shows offline, although they all worked last night.",
         "the home internet stopped working this morning"),
    ], start=6):
        base = _healthy_base(
            model, fw, online=False, uplink_status="no_internet",
            error_codes=["E-503"],
        )
        devices = [
            _device("cam_main", "Main Camera", "CAM-S1", "2.1", "offline", -65, 72),
            *_supporting_devices(),
        ]
        cases.append(_case(
            f"C{i:03d}", complaint, "BS_NETWORK_DOWN", base, devices,
            ["base station uplink lost: E-503", "all peripherals unavailable"],
            {"recent_changes": location, "base_led": "solid red"},
            {"restart_base_station": "Devices remain offline while the router has no internet."},
            ["S1"], "easy", "Base station uplink is down; peripheral symptoms are downstream.",
        ))

    # S2: capacity limits and pairing timeouts.
    for i, (complaint, distance, led) in enumerate([
        ("A new window sensor will not join the system.", "within one metre", "blinking blue"),
        ("The new hallway sensor times out while pairing.", "next to the base station", "blinking blue"),
        ("I cannot add the replacement door sensor; pairing expires.", "beside the base station", "blue"),
    ], start=9):
        devices = [
            _device("sensor_pending", "New Sensor", "SEN-D1", "1.0",
                    "not_paired", None, 100, False, False),
            *_supporting_devices(),
        ]
        cases.append(_case(
            f"C{i:03d}", complaint, "PAIR_TIMEOUT", _healthy_base(), devices,
            ["pairing request timed out after 120 seconds"],
            {"distance_during_pairing": distance, "device_led": led, "recent_changes": "none"},
            {"retry_pairing": "The sensor still times out although it is in pairing mode."},
            ["S1", "S2"], "easy",
            "Pending device is not bound, and the base station has unused capacity.",
        ))

    capacity_devices = [
        _device("cam_garden", "Garden Cam", "CAM-S1", "1.8", rssi=-66, battery=58),
        _device("cam_drive", "Driveway Cam", "CAM-S1", "1.8", rssi=-71, battery=80),
        _device("door_front", "Front Door", "SEN-D1", "1.0", rssi=-55, battery=90),
        _device("door_back", "Back Door", "SEN-D1", "1.0", rssi=-60, battery=88),
        _device("win_kitchen", "Kitchen Window", "SEN-D1", "1.0", rssi=-62, battery=71),
        _device("motion_hall", "Hallway Motion", "SEN-M1", "1.1", rssi=-59, battery=66),
        _device("motion_stairs", "Stairs Motion", "SEN-M1", "1.1", rssi=-64, battery=52),
        _device("old_test", "Old Test Sensor", "SEN-M1", "1.1",
                "offline", None, 0),
        _device("new_door", "New Door Sensor", "SEN-D1", "1.0",
                "not_paired", None, 100, False, False),
    ]
    for i, complaint in enumerate([
        "The app rejects my new sensor even though it is in pairing mode.",
        "I cannot register another door sensor; the app shows capacity reached.",
        "Pairing the new garage sensor fails immediately with an error.",
    ], start=12):
        cases.append(_case(
            f"C{i:03d}", complaint, "CAPACITY_EXCEEDED",
            _healthy_base("HB-100", "3.4", error_codes=["E-201"]),
            capacity_devices,
            ["pairing rejected: E-201 capacity reached (8/8)"],
            {"error_message": "The app showed E-201.", "distance_during_pairing": "next to the base"},
            {"remove_unused_device": "After removing the unused test sensor, pairing succeeds."},
            ["S1", "S2"], "easy", "HB-100 has eight bound slots occupied; one is an unused sensor.",
        ))

    # S3: isolated weak-link failures.
    for i, (device_id, name, rssi, place, complaint) in enumerate([
        ("cam_garage", "Garage Cam", -86, "detached garage",
         "My garage camera drops offline several times each day."),
        ("motion_cellar", "Cellar Motion", -83, "basement behind concrete walls",
         "The cellar motion sensor misses alerts, but the other devices work."),
        ("door_shed", "Shed Door", -88, "metal-sided garden shed",
         "The shed door sensor keeps disconnecting intermittently."),
    ], start=15):
        devices = [
            _device(device_id, name, "CAM-S1" if "Cam" in name else "SEN-D1",
                    "2.1" if "Cam" in name else "1.3",
                    "intermittent", rssi, 67),
            *_supporting_devices(),
        ]
        cases.append(_case(
            f"C{i:03d}", complaint, "WEAK_SIGNAL", _healthy_base(), devices,
            [f"{device_id} heartbeat lost repeatedly (RSSI {rssi} dBm)"],
            {"device_location": place, "recent_changes": "none"},
            {"move_device_closer": "After moving the base station closer, the device remains online."},
            ["S1", "S3"], "easy", "Only one peripheral is affected and its RSSI is below -80 dBm.",
        ))

    # S5: low-battery faults.
    for i, (device_id, name, model, fw, battery, complaint) in enumerate([
        ("cam_porch", "Porch Cam", "CAM-S1", "2.1", 7,
         "My porch camera stopped starting live view and says its battery is nearly empty."),
        ("door_side", "Side Door", "SEN-D1", "1.3", 6,
         "The side-door sensor is offline and the app says the battery is low."),
        ("motion_attic", "Attic Motion", "SEN-M1", "1.4", 8,
         "The attic motion detector misses events; its battery warning appeared today."),
    ], start=18):
        devices = [
            _device(device_id, name, model, fw, "offline", -62, battery),
            *_supporting_devices(),
        ]
        cases.append(_case(
            f"C{i:03d}", complaint, "BATTERY_LOW", _healthy_base(), devices,
            [f"{device_id} battery level {battery}%"],
            {"battery_warning": "The app shows a low-battery warning."},
            {"replace_battery": "After charging or replacing the battery, the device works normally."},
            ["S1", "S3", "S5"], "easy", "A single offline peripheral has less than 10% battery.",
        ))

    # S4: outdated firmware with a supported OTA path.
    for i, (device_id, name, model, fw, ota, complaint) in enumerate([
        ("motion_entry", "Entry Motion", "SEN-M1", "1.1", "1.4",
         "My entry motion sensor stopped sending alerts after the base updated."),
        ("door_garage", "Garage Door", "SEN-D1", "1.0", "1.3",
         "The garage sensor is connected but its events no longer arrive."),
        ("cam_yard", "Yard Cam", "CAM-S1", "1.8", "2.1",
         "The yard camera stopped uploading clips after an overnight update."),
    ], start=21):
        devices = [
            _device(device_id, name, model, fw, "connected_no_events", -63, 72),
            *_supporting_devices(),
        ]
        cases.append(_case(
            f"C{i:03d}", complaint, "PERIPHERAL_FW_OUTDATED",
            _healthy_base("HB-200", "4.5", error_codes=["E-305"]),
            devices,
            [f"{device_id}: E-305 protocol v2 not supported"],
            {"recent_changes": "The base station updated overnight.",
             "app_update_badge": f"An update is offered for {name}."},
            {"ota_upgrade": f"The device updated to {ota}; events now work again."},
            ["S1", "S3", "S4"], "medium",
            "The peripheral uses protocol v2; an OTA path to compatible protocol v3 exists.",
        ))

    # S1: storage full while loop recording is disabled.
    for i, (used, complaint) in enumerate([
        (99, "New recordings are missing and playback stops at last month."),
        (100, "The system stopped saving event clips; storage shows full."),
        (98, "I no longer see new recordings, and the base station shows a storage warning."),
    ], start=24):
        cases.append(_case(
            f"C{i:03d}", complaint, "STORAGE_FULL",
            _healthy_base(storage_used_pct=used, loop_recording=False, error_codes=["E-402"]),
            _supporting_devices(),
            [f"storage used {used}%; loop recording disabled; E-402"],
            {"recent_changes": "No recent changes."},
            {"enable_loop_recording": "After enabling loop recording, new events are saved."},
            ["S1"], "easy", "Storage is at least 98% full and loop recording is disabled.",
        ))

    # S4: protocol conflicts without any available OTA recovery.
    for i, (device_id, name, complaint, hardware) in enumerate([
        ("cam_guest", "Guest Room Cam",
         "The guest-room camera went offline after the base updated and cannot update.",
         "hardware revision A"),
        ("cam_office", "Office Cam",
         "My office camera no longer connects since the overnight base-station update.",
         "legacy hardware"),
        ("cam_den", "Den Cam",
         "The den camera remains offline; the app says no camera firmware update is available.",
         "an older camera revision"),
    ], start=27):
        devices = [
            _device(device_id, name, "CAM-I2", "1.2", "offline", -62, None),
            *_supporting_devices(),
        ]
        cases.append(_case(
            f"C{i:03d}", complaint, "PROTOCOL_CONFLICT",
            _healthy_base("HB-200", "4.5", error_codes=["E-305"]),
            devices,
            [f"base firmware updated to 4.5", f"{device_id}: E-305 protocol v2 not supported",
             f"{device_id}: OTA unavailable for {hardware}"],
            {"recent_changes": "The base station updated overnight.",
             "update_message": "No compatible camera update is offered."},
            {"ota_upgrade": "The app reports that no update is available."},
            ["S1", "S3", "S4"], "medium",
            "Legacy camera firmware is protocol v2; HB-200 4.5 supports v3 and OTA is unavailable.",
        ))

    # S3: simultaneous multi-device radio failures.
    for i, (complaint, code, moment) in enumerate([
        ("Three sensors in different rooms went offline together.", "E-610", "14:02"),
        ("Several devices dropped at once although the base is still online.", "E-610", "09:17"),
        ("Two sensors and a camera stopped responding within seconds of each other.", "E-610", "21:44"),
    ], start=30):
        devices = [
            _device("door_back", "Back Door", "SEN-D1", "1.3", "offline", None, 81),
            _device("motion_living", "Living Motion", "SEN-M1", "1.4", "offline", None, 74),
            _device("win_bed", "Bedroom Window", "SEN-D1", "1.3", "offline", None, 66),
            _device("cam_front", "Front Cam", "CAM-S1", "2.1", rssi=-65, battery=70),
        ]
        cases.append(_case(
            f"C{i:03d}", complaint, "BATCH_LINK_FAILURE", _healthy_base(error_codes=[code]),
            devices,
            [f"{moment}:00 door_back lost", f"{moment}:01 motion_living lost",
             f"{moment}:02 win_bed lost", f"{code} radio module self-test warning",
             "RSSI history for affected sensors: -55 to -66 dBm"],
            {"base_led": "solid blue", "recent_changes": "none"},
            {"restart_base_station": "All affected sensors remain offline."},
            ["S1", "S2", "S3"], "hard",
            "Multiple peripherals failed simultaneously with normal RSSI and the base online.",
        ))

    # S1: persistent cloud reporting failures despite frontline steps.
    for i, (complaint, code) in enumerate([
        ("Local live view works but event notifications never reach my phone.", "E-503"),
        ("The base station is online, but none of today's events appeared in the cloud.", "E-503"),
        ("My cameras work locally, but remote notifications have stopped.", "E-503"),
    ], start=33):
        cases.append(_case(
            f"C{i:03d}", complaint, "UPLINK_BLOCKED_PERSIST",
            _healthy_base(error_codes=[code]),
            [_device("cam_local", "Local Camera", "CAM-S1", "2.1", rssi=-64, battery=68),
             *_supporting_devices()],
            [f"{code} cloud reporting failed repeatedly", "local stream remains available"],
            {"local_live_view": "Works on the home network.",
             "recent_changes": "Router and DNS settings were checked."},
            {"restart_base_station": "No change after restarting the router and base station.",
             "reset_router_dns": "DNS is automatic; cloud reporting still fails."},
            ["S1"], "hard",
            "Base remains locally online, but cloud reporting persists after router and DNS checks.",
        ))

    # S2: application and gateway binding tables disagree.
    for i, (device_id, name, complaint) in enumerate([
        ("door_patio", "Patio Door", "The patio sensor is still in my app but missing from the base station."),
        ("motion_lobby", "Lobby Motion", "The app lists my lobby sensor, but the base says it is not bound."),
    ], start=36):
        devices = [
            _device(device_id, name, "SEN-D1" if "door" in device_id else "SEN-M1",
                    "1.3" if "door" in device_id else "1.4",
                    "offline", None, 72, False, True),
            *_supporting_devices(),
        ]
        cases.append(_case(
            f"C{i:03d}", complaint, "BINDING_TABLE_CORRUPT",
            _healthy_base(error_codes=["E-207"]), devices,
            [f"{device_id}: E-207 binding table write failed",
             f"{device_id} is listed in app but absent from base station table"],
            {"app_status": "The device is still shown in the app."},
            {"retry_pairing": "Pairing fails again with E-207."},
            ["S1", "S2"], "hard",
            "The app/base binding records disagree; retrying pairing repeats E-207.",
        ))

    # S5: isolated device still fails after a safe peripheral reset.
    for i, (device_id, name, model, fw, complaint) in enumerate([
        ("cam_study", "Study Cam", "CAM-I2", "2.0",
         "My study camera is still broken even beside the base after resetting the camera."),
        ("door_workshop", "Workshop Door", "SEN-D1", "1.3",
         "The workshop sensor will not report although it has good battery and was reset."),
        ("motion_entry", "Entry Motion", "SEN-M1", "1.4",
         "The entry sensor still fails next to the base after a reset; the other sensors work."),
    ], start=38):
        devices = [
            _device(device_id, name, model, fw, "offline", -60, 75),
            *_supporting_devices(),
        ]
        cases.append(_case(
            f"C{i:03d}", complaint, "HW_FAULT_SUSPECTED",
            _healthy_base(), devices,
            [f"{device_id} remains offline after peripheral reset", f"{device_id} RSSI -60 dBm"],
            {"device_location": "next to the base station",
             "reset_performed": "I reset the peripheral only; the base station was not reset.",
             "recent_changes": "none"},
            {"replace_battery": "The device remains offline after checking its power."},
            ["S1", "S3", "S4", "S5"], "hard",
            "One compatible, adequately powered device fails at close range after its own reset.",
        ))

    return [_enrich_case(case) for case in cases]


# ---------------------------------------------------------------------------
# Complexity pass: longer customer narratives with wrong self-diagnoses, a larger
# household, online "distractor" devices, noisy logs and more (mostly ineffective)
# customer-side actions. It never changes the label evidence the rules rely on:
# distractor devices stay `online`, so only the labelled devices are abnormal.
# ---------------------------------------------------------------------------
MAX_DEVICES = {"HB-100": 8, "HB-200": 16}

# id, name, model, protocol-v2 firmware, protocol-v3 firmware, rssi, battery
BACKGROUND_POOL = [
    ("cam_garden", "Garden Cam", "CAM-S1", "1.8", "2.1", -69, 63),
    ("win_kitchen", "Kitchen Window", "SEN-D1", "1.0", "1.3", -61, 48),
    ("motion_stairs", "Stairs Motion", "SEN-M1", "1.1", "1.4", -64, 57),
    ("cam_hall", "Hall Cam", "CAM-I2", "1.2", "2.0", -60, None),
]

GENERIC_OUTCOMES = {
    "BS_NETWORK_DOWN": {
        "restart_router_then_base_station": "After power-cycling the router, waiting two minutes and then restarting "
                                            "the base station, the light turns solid blue and every device returns.",
        "reinstall_app": "No change; the app still cannot reach the base station.",
        "restart_phone": "No change.",
    },
    "PAIR_TIMEOUT": {
        "hold_sync_button_3s_within_1m_and_retry": "Holding the SYNC button for 3 seconds until the LED blinks blue, "
                                                   "with the sensor within 1 m of the base, it pairs on the next try.",
        "replace_sensor_battery": "No change; pairing still times out.",
        "restart_base_station": "No change; pairing still times out.",
    },
    "CAPACITY_EXCEEDED": {
        "restart_base_station": "No change; the same capacity error appears.",
        "pair_with_other_phone": "The same error appears on the other phone.",
    },
    "WEAK_SIGNAL": {
        "install_repeater": "The device stays online after a repeater is installed halfway.",
        "replace_battery": "No change; it still drops offline.",
        "restart_base_station": "The device returns but drops again within a few hours.",
    },
    "BATTERY_LOW": {
        "recharge_device": "After a full charge the device works normally again.",
        "restart_base_station": "No change.",
        "reboot_router": "No change.",
    },
    "PERIPHERAL_FW_OUTDATED": {
        "restart_base_station": "No change; alerts still do not arrive.",
        "reboot_router": "No change.",
    },
    "STORAGE_FULL": {
        "delete_old_clips": "A little space is freed, but the warning returns the next day.",
        "restart_base_station": "No change; new clips are still not saved.",
    },
    "PROTOCOL_CONFLICT": {
        "restart_base_station": "The camera stays offline.",
        "re_pair": "Pairing fails with the same protocol error.",
        "move_device_closer": "Still offline even next to the base station.",
    },
    "BATCH_LINK_FAILURE": {
        "restart_base_station": "All affected devices stay offline.",
        "replace_battery": "No change.",
        "move_device_closer": "The device stays offline even next to the base station.",
    },
    "UPLINK_BLOCKED_PERSIST": {
        "relogin_app": "No change; notifications still do not arrive.",
        "reboot_router": "No change; cloud reporting still fails.",
    },
    "BINDING_TABLE_CORRUPT": {
        "restart_base_station": "After the restart pairing fails again with the same binding error.",
        "remove_and_readd_in_app": "Removal succeeds in the app, but re-adding fails with the same binding error.",
    },
    "HW_FAULT_SUSPECTED": {
        "restart_base_station": "No change.",
        "try_different_power_outlet": "No change.",
        "re_pair_device": "Pairing succeeds, but the device drops offline again within a minute.",
    },
}

# complaint, extra customer knowledge (red herrings included), difficulty, distractor note
RICH = {
    "C001": dict(
        complaint="My living room camera keeps going offline a few times a day, then comes back by itself. The other "
                  "devices seem fine. It started about a week ago, around when we rearranged the flat and I moved "
                  "the base station into the study to free up a socket in the hallway. I've restarted the camera "
                  "several times and checked that it is plugged in properly. My partner thinks the camera is faulty "
                  "and wants to return it, but I'd rather not buy anything new if I can avoid it.",
        knowledge={"camera_restarts": "Several; each restart only helps for an hour or two.",
                   "partner_theory": "My partner thinks the camera is faulty."}),
    "C002": dict(
        complaint="I bought a new door sensor last week but it just won't pair. I followed the instructions and held "
                  "the button. The app shows an error with a code, and I have tried both my phone and my partner's "
                  "phone with the same result. Our system has grown over the years and, honestly, I don't remember "
                  "how many devices we have. Do I need to return the sensor?",
        knowledge={"phones_tried": "Mine and my partner's, same error on both.",
                   "device_count": "I don't remember how many devices we have."}),
    "C003": dict(
        complaint="Since yesterday my hallway motion sensor doesn't send any alerts. It still shows in the app. The "
                  "LED blinks when I walk past it, so it seems to be working, and I changed its battery last month. "
                  "We never touch the base station settings, but I think it installs things at night by itself. "
                  "The front door sensor next to it is working fine.",
        knowledge={"battery_changed": "Last month, new battery.",
                   "other_sensors": "The front door sensor works fine."}),
    "C004": dict(
        complaint="My kitchen camera disappeared this morning. It says offline. I already unplugged it and plugged it "
                  "back in, tried a different power socket, and even restarted my Wi-Fi router because I assumed "
                  "that is what the camera uses. The garden camera and the door sensor are fine, which is why I'm "
                  "confused. The kitchen camera is the oldest one I own.",
        knowledge={"router_restarted": "Yes, no change.", "other_devices": "Garden camera and door sensor are fine."}),
    "C005": dict(
        complaint="The back door sensor went offline. Probably the signal, it's a bit far from the base. I got a "
                  "push notification around 2 pm but didn't think much of it, and only noticed in the evening that "
                  "the app showed it offline. I'm thinking of buying a signal repeater for that side of the house. "
                  "The front camera works as normal.",
        knowledge={"repeater_plan": "I want to buy a repeater for the back door.",
                   "front_camera": "Works as normal."}),
    "C006": dict(
        complaint="Hi, everything in my security app went grey around 7 this morning: all my cameras and sensors show "
                  "offline and I get no notifications at all. Yesterday afternoon our internet provider's technician "
                  "replaced the router, and since then the Wi-Fi on my laptop works fine. I tried opening the app on "
                  "mobile data and it says the base station is unreachable. I'm travelling next week, so I need this "
                  "working. I think the base station has died.",
        knowledge={"router_replaced": "ISP technician replaced it yesterday afternoon.",
                   "laptop_wifi": "Works fine.",
                   "cable_ports": "The technician plugged things back in; I don't know which port the cable is in.",
                   "hardware_belief": "I think the base station is dead."},
        difficulty="medium", distractor="Customer blames dead hardware; the cable is in the wrong router port."),
    "C007": dict(
        complaint="The red light on the base station has been on since I got home. The app shows no connection for "
                  "every device and the live view just spins. Last weekend we moved the TV cabinet and I may have "
                  "pulled some cables behind it. My son insists that all the camera batteries ran out at the same "
                  "time, but that seems unlikely to me. The smart TV also complains about something, I haven't "
                  "looked into it.",
        knowledge={"furniture_moved": "TV cabinet moved last weekend; cables behind it were disturbed.",
                   "son_theory": "My son thinks all camera batteries ran out.",
                   "smart_tv": "It says there is no internet connection."},
        difficulty="medium", distractor="Son blames batteries; the real clue is that the TV also lost internet."),
    "C008": dict(
        complaint="Every camera and sensor has shown offline since this morning, although they were all fine last "
                  "night. The base station has a red light. I rebooted my phone and reinstalled the app because I "
                  "thought that was the problem, but nothing changed. We had a thunderstorm last night and my "
                  "neighbour says the broadband is down on our street too.",
        knowledge={"phone_internet": "Home Wi-Fi shows connected but websites do not load.",
                   "storm": "Thunderstorm last night; the neighbour also lost internet.",
                   "app_reinstalled": "Yes, no change."},
        difficulty="easy", distractor="App reinstall is irrelevant; the home internet is down."),
    "C009": dict(
        complaint="I bought a new window sensor yesterday and followed the leaflet, but the app keeps counting down "
                  "120 seconds and then says pairing failed. I've tried five times now. I changed the sensor's "
                  "battery twice, just in case. Other sensors in the house work perfectly, so I don't think there is "
                  "a problem with the base station.",
        knowledge={"attempts": "Five times today.", "battery_swapped": "Twice, with fresh batteries.",
                   "other_sensors": "All work perfectly."},
        difficulty="medium", distractor="Battery swaps are irrelevant; the pairing procedure is the problem."),
    "C010": dict(
        complaint="The new hallway sensor times out every time I try to add it. The app says pairing expired. I'm "
                  "renting this flat, so I don't want to drill anything yet. I just wanted to put the sensor on the "
                  "shelf near the router first and test it. Last month a different sensor paired without any "
                  "problem, so I don't understand what changed.",
        knowledge={"temporary_position": "On the shelf next to the Wi-Fi router.",
                   "router_nearby": "The Wi-Fi router is about 30 cm from the base station.",
                   "earlier_pairing": "A different sensor paired fine last month."},
        difficulty="medium", distractor="Router proximity looks like interference; it is only a pairing timeout."),
    "C011": dict(
        complaint="I'm replacing a broken door sensor. I removed the old one from the app, but the replacement just "
                  "times out when I try to add it, and the app says pairing expired after two minutes. My brother is "
                  "an electrician and says the new sensor is probably defective, so I'm thinking of returning it. "
                  "Everything else in the system works.",
        knowledge={"old_sensor_removed": "Yes, removed in the app before adding the new one.",
                   "brother_theory": "He thinks the new sensor is defective."},
        difficulty="medium", distractor="Defective-device theory; the old sensor was already removed, so capacity is free."),
    "C012": dict(
        complaint="I want to add a sensor to the garage door, but the app refuses to register it. The screen shows "
                  "an error with a code and I'm not sure what it means. I held the button on the sensor until it "
                  "blinked, exactly like in the video. I've had this system for a few years and added things bit by "
                  "bit. Is the new sensor dead on arrival?",
        knowledge={"devices_added_over_time": "Added gradually over three years; I don't remember how many.",
                   "unused_devices": "A couple of devices I no longer use, never deleted from the app.",
                   "doa_belief": "I think the new sensor is dead on arrival."},
        difficulty="medium", distractor="Customer suspects a dead sensor; the base station is full."),
    "C013": dict(
        complaint="Since the weekend I can't add another door sensor. The app shows capacity reached, but I only see "
                  "about six devices on the home screen. I've reset my phone's Bluetooth and tried a different phone "
                  "as well, and nothing changes. I don't see why the system would be full.",
        knowledge={"devices_on_home_screen": "About six active ones; some greyed-out entries at the bottom I never look at.",
                   "phone_steps": "Reset Bluetooth and tried a second phone, same message."},
        difficulty="medium", distractor="Phone and Bluetooth steps are irrelevant; hidden greyed-out entries fill the slots."),
    "C014": dict(
        complaint="Pairing the new garage sensor fails immediately, within a second, with an error. It does not wait "
                  "for the 120 seconds. I tested the sensor on a friend's system and it paired fine there, so I'm "
                  "sure it isn't the sensor. I'm on the latest app version. What else can it be?",
        knowledge={"sensor_tested_elsewhere": "Yes, paired fine on a friend's system.",
                   "app_version": "Latest from the store."},
        difficulty="easy", distractor=""),
    "C015": dict(
        complaint="The camera in my detached garage keeps dropping off. It is offline maybe five times a day for "
                  "10 to 30 minutes and then comes back by itself, and notifications from it are delayed. I replaced "
                  "the camera battery and updated the app, but nothing changes. The camera is brand new, bought in "
                  "the spring, so it shouldn't be faulty.",
        knowledge={"battery_replaced": "Yes, new batteries two weeks ago.",
                   "garage_path": "About 20 m across the garden, through the garage's brick wall."},
        difficulty="medium", distractor="Battery replacement is irrelevant; RSSI is the evidence."),
    "C016": dict(
        complaint="My cellar motion sensor misses alerts. Twice last week I walked through the cellar to test it and "
                  "got nothing on my phone. The app sometimes shows it offline for a few minutes. I assume the "
                  "sensor is faulty because it is an older unit, but the hallway sensor of the same model works "
                  "perfectly.",
        knowledge={"same_model_elsewhere": "The hallway sensor of the same model works fine.",
                   "cellar_walls": "Thick concrete; the base station is on the second floor."},
        difficulty="medium", distractor="Faulty-unit theory; another sensor of the same model works, so signal is the cause."),
    "C017": dict(
        complaint="The shed door sensor keeps going offline and coming back. Honestly it only started after we put up "
                  "the new metal shed in October. The app notifies me about it at random times, including at night. "
                  "I tried moving the sensor to the other side of the door frame, but that made no difference.",
        knowledge={"new_metal_shed": "Installed three weeks ago.",
                   "sensor_moved_on_door": "Tried the other side of the frame, no change."},
        difficulty="medium", distractor="Moving the sensor within the frame is irrelevant; the shed blocks the radio path."),
    "C018": dict(
        complaint="The porch camera won't start live view; it just spins and then says camera unavailable. It started "
                  "a couple of days ago. I thought it was the Wi-Fi because our router was updated recently, so I "
                  "rebooted the router twice, but nothing changed. The other cameras are fine.",
        knowledge={"router_rebooted": "Twice, no change.",
                   "last_charged": "I can't remember when I last charged it, maybe two months ago.",
                   "battery_icon": "The camera card in the app shows a red battery icon."},
        difficulty="medium", distractor="Customer blames Wi-Fi; the camera battery is nearly empty."),
    "C019": dict(
        complaint="The side-door sensor shows offline and the app sends me an alert every few hours. I opened the door "
                  "to test it and nothing happened. We had the house repainted last week and the painter may have "
                  "bumped the sensor, so I think it is misaligned. I haven't touched it since.",
        knowledge={"painter": "House painted last week; the painter took the sensor off the frame and put it back.",
                   "battery_age": "Original battery from installation, about two years ago."},
        difficulty="medium", distractor="Misalignment theory after painting; the battery is almost empty."),
    "C020": dict(
        complaint="The attic motion detector misses events; its battery warning appeared today. But it also missed an "
                  "event last week, well before the warning, so I'm not sure the battery is the cause. It was boiling "
                  "up there all summer, so maybe the heat damaged it. Should I replace the whole sensor?",
        knowledge={"attic_temperature": "Very hot all summer, cooler now.",
                   "warning_time": "The low-battery notice appeared this morning."},
        difficulty="medium", distractor="Heat damage theory; the battery is below 10 percent."),
    "C021": dict(
        complaint="The entry motion sensor stopped sending alerts after the base station updated itself, at least "
                  "that is what I assume, because the sensor LED still blinks when I walk past and the app still "
                  "lists it as connected. It is the oldest sensor in the system. I'm worried because it covers the "
                  "front door.",
        knowledge={"sensor_age": "The oldest sensor, about four years.",
                   "led_behaviour": "The LED blinks normally when I walk past."},
        difficulty="medium", distractor="Sensor looks healthy (LED, 'connected'); the protocol is outdated."),
    "C022": dict(
        complaint="Events from the garage door sensor haven't come through for two days, although the app shows it as "
                  "connected. My husband thinks the garage Wi-Fi is bad, so he installed a Wi-Fi extender there, "
                  "which didn't help. The garage door opens and closes normally, so the sensor itself should be "
                  "fine.",
        knowledge={"wifi_extender": "Installed in the garage, no change.",
                   "sensor_physical": "Door opens and closes normally."},
        difficulty="medium", distractor="Wi-Fi extender is irrelevant to a sub-GHz sensor."),
    "C023": dict(
        complaint="The yard camera used to upload a clip every time somebody walked past. Since a night when the "
                  "system updated itself, the clips stopped, although live view still works. I checked the storage "
                  "page and there is plenty of space, so that is not it. My neighbour with the same system has no "
                  "problem.",
        knowledge={"storage_checked": "Plenty of space.", "live_view": "Still works.",
                   "neighbour": "Same system, no problem; I don't know her camera versions."},
        difficulty="medium", distractor="Customer rules out storage; live view working hides the outdated protocol."),
    "C024": dict(
        complaint="I went to look at the footage of a delivery from last week and the timeline stops at the end of "
                  "last month. There has been a purple light on the base station for a few days that I've been "
                  "ignoring. Live view and notifications still work, so I assumed the system was fine. I think the "
                  "cameras stopped recording after the last firmware update.",
        knowledge={"base_led": "Solid purple for a few days.",
                   "update_theory": "I think it broke after the last firmware update.",
                   "last_playback_date": "The timeline ends at the end of last month."},
        difficulty="easy", distractor="Customer blames a firmware update; the base station LED says storage is full."),
    "C025": dict(
        complaint="The system stopped saving event clips. A break-in attempt happened at a neighbour's house, so I "
                  "wanted to check my camera footage and there is nothing for the last three weeks! Did somebody "
                  "delete my recordings? Is my account hacked? I haven't received any password-change emails.",
        knowledge={"suspected_hack": "Worried someone deleted the recordings; no password-change emails.",
                   "loop_recording_setting": "I never touched storage settings and don't know what loop recording means."},
        difficulty="medium", distractor="Customer fears a hack; storage is simply full with loop recording off."),
    "C026": dict(
        complaint="The app shows a storage warning but I don't know what it wants me to do. I deleted some old clips "
                  "one by one, which frees a bit of space, but the warning comes back the next day. All cameras show "
                  "online and live view works. Is the base station's memory failing?",
        knowledge={"manual_deletions": "Deleted about ten clips; the warning returns the next day.",
                   "failing_memory_belief": "I think the memory is failing."},
        difficulty="medium", distractor="Failing-memory theory; loop recording is disabled."),
    "C027": dict(
        complaint="The guest room camera went offline overnight and won't come back. It is a wired indoor camera and "
                  "has power; the LED is orange. A friend who works in IT told me to factory reset the base station, "
                  "but I'd rather not lose all my settings. I looked in the app for a camera update and it says "
                  "none is available.",
        knowledge={"camera_led": "Orange, blinking slowly.", "camera_power": "Plugged in and the LED is on.",
                   "it_friend_advice": "Factory reset the base station."},
        difficulty="medium", distractor="Friend advises a base station factory reset, which frontline must never do."),
    "C028": dict(
        complaint="My office camera no longer connects since the overnight base station update. I've tried to re-add "
                  "it three times and each time it says it can't connect. It is the oldest camera I have, from the "
                  "first package three years ago. The rest of the system is fine, so I'm hesitant to blame the "
                  "update.",
        knowledge={"re_add_attempts": "Three times, same failure.", "camera_age": "About three years."},
        difficulty="medium", distractor="Customer doubts the update; the legacy camera cannot reach protocol v3."),
    "C029": dict(
        complaint="The den camera remains offline after the base station updated last night. I cannot find a firmware "
                  "update for it in the app. Support told me last time to just update the camera, but there is no "
                  "button. My neighbour has the same camera model and hers still works, so I suspect my unit is "
                  "broken.",
        knowledge={"neighbour_same_model": "Works for her; no idea which revision she has.",
                   "update_button": "There is no update button for this camera."},
        difficulty="hard", distractor="Same model works elsewhere, but only newer hardware revisions can reach v3."),
    "C030": dict(
        complaint="Three of my sensors went offline at the same time this afternoon. I got three offline notifications "
                  "within a few seconds of each other. The front camera is still fine. I assumed the batteries had run "
                  "low because they are the originals from 18 months ago, so I'm about to order a bunch of new ones. "
                  "Is that the right call?",
        knowledge={"battery_age": "About 18 months.", "push_notifications": "Three at once, around 2 pm.",
                   "front_camera": "Still fine."},
        difficulty="hard", distractor="Batteries are healthy; three devices dropped at the same moment."),
    "C031": dict(
        complaint="Several devices dropped at once although the base station is still online. Around breakfast the "
                  "app showed the garden door sensor, the living room motion sensor and the bedroom window sensor as "
                  "offline. I moved the Wi-Fi router about 2 m last week, so I assume the new position is causing "
                  "interference. Everything else is working.",
        knowledge={"router_moved": "Moved the Wi-Fi router about 2 m last week.",
                   "dropped_devices": "Garden door, living room motion, bedroom window."},
        difficulty="hard", distractor="Wi-Fi router move is a red herring; simultaneous drops with normal RSSI point to the radio."),
    "C032": dict(
        complaint="Three sensors stopped responding within seconds of each other yesterday evening. I restarted the "
                  "base station, hoping it would help, but they all stayed offline. The base station is at the far "
                  "end of the flat from some of them, so maybe the signal is the problem. The front camera, which is "
                  "farther away, is still online though.",
        knowledge={"restart_tried": "Yes, no change.", "base_location": "At the far end of the flat.",
                   "front_camera": "Still online."},
        difficulty="hard", distractor="Signal theory is contradicted by the farther camera staying online."),
    "C033": dict(
        complaint="Local live view works fine on my home Wi-Fi, but I haven't received a single push notification since "
                  "Tuesday, and when I'm out I can't see any clips. I rebooted the router, then the base station, and "
                  "even set my router's DNS to automatic like the help article said. Still nothing. I've been on hold "
                  "with my ISP and they insist the internet is fine.",
        knowledge={"isp_says": "The internet is fine.", "steps_done": "Rebooted router and base station; DNS set to automatic.",
                   "notifications_stopped": "Since Tuesday morning."},
        difficulty="hard", distractor="All standard frontline steps were already tried."),
    "C034": dict(
        complaint="The base station is online, but none of today's events appeared in the cloud, and the app timeline "
                  "has been empty since yesterday evening. I changed my account password last week; could that be the "
                  "problem? I already logged out and in again and removed and re-added the account on my phone.",
        knowledge={"password_changed": "Last week.", "relogin": "Logged out/in and re-added the account, no change."},
        difficulty="hard", distractor="Password change is a red herring; the cloud channel fails."),
    "C035": dict(
        complaint="My cameras work locally, but remote notifications have stopped. We just got a new mesh Wi-Fi system "
                  "and I wonder if it blocks something. I've disabled the firewall features in the mesh app and "
                  "rebooted all the nodes. Our old router is in a drawer if I should plug it back in.",
        knowledge={"new_mesh_wifi": "Installed two weeks ago.", "mesh_firewall": "Turned off, no change.",
                   "old_router": "Still available in a drawer."},
        difficulty="hard", distractor="New mesh Wi-Fi is suspected, but the old router makes no difference either."),
    "C036": dict(
        complaint="The patio sensor is still in my app and shows offline, but when I check the base station's device "
                  "list the patio sensor isn't there. I tried removing it from the app and adding it again, and it "
                  "gave an error code starting with E-2. We had a power cut while I was adding it last Thursday.",
        knowledge={"power_cut": "A power cut happened during pairing last Thursday.",
                   "readded": "Tried removing and re-adding it; error code again."},
        difficulty="hard", distractor="A power cut can cause a single write error, but the error repeats."),
    "C037": dict(
        complaint="The app lists my lobby sensor, but the base station says it is not bound. I'm confused: the app "
                  "says one thing and the base station another. I've deleted and re-added it twice. I wonder whether "
                  "my account is out of sync with my husband's account, since he also uses the app.",
        knowledge={"second_account": "My husband also uses the app and sees the same entry.",
                   "readd_attempts": "Twice."},
        difficulty="hard", distractor="Two-account sync theory is a red herring; the binding table is inconsistent."),
    "C038": dict(
        complaint="My study camera is still broken even beside the base station after resetting the camera. I carried it "
                  "into the same room as the base station, plugged it in and held the reset button for 10 seconds as "
                  "the manual says; the LED goes solid and then dark again. I also tried a different power outlet and "
                  "a different cable. Everything else in the system works.",
        knowledge={"other_outlet_cable": "Tried a different outlet and cable, no change.",
                   "reset_led": "Solid, then dark again."},
        difficulty="hard", distractor="Signal, power and firmware are all fine; only the unit itself fails."),
    "C039": dict(
        complaint="The workshop sensor will not report although it has good battery and was reset. I even put a brand "
                  "new battery in and held it right against the base station while resetting it. The app shows it "
                  "offline. The other sensors from the same box are perfect, so I don't think it is a setup problem.",
        knowledge={"new_battery": "Fresh battery fitted.", "other_sensors_same_box": "Perfect."},
        difficulty="hard", distractor="Battery replacement already ruled out; compatible firmware and strong RSSI."),
    "C040": dict(
        complaint="The entry sensor still fails next to the base station after a reset; the other sensors work. It "
                  "worked for a year, then died after I dropped it on the tiles while changing the battery. Could it "
                  "be signal? The entry is three walls away from the base in normal use, but I tested it right next to "
                  "the base.",
        knowledge={"dropped": "Dropped once on the tiles about a month ago.",
                   "tested_next_to_base": "Yes, still offline."},
        difficulty="hard", distractor="Signal theory is ruled out by the test beside the base station."),
}


def _background_devices(case):
    cause = case["gt_root_cause"]
    if cause == "CAPACITY_EXCEEDED":
        return []
    state = case["hidden_state"]
    base = state["base_station"]
    taken = {d["id"] for d in state["devices"]} | {d["name"] for d in state["devices"]}
    free_slots = MAX_DEVICES[base["model"]] - 1 - sum(d["bound_in_base"] for d in state["devices"])
    limit = min(4 if case["difficulty"] == "hard" else 3, free_slots)
    v2_only = base["model"] == "HB-100"
    status = "online" if base["online"] else "offline"
    extra = []
    for dev_id, name, model, fw_v2, fw_v3, rssi, battery in BACKGROUND_POOL:
        if len(extra) >= limit:
            break
        if dev_id in taken or name in taken:
            continue
        extra.append(_device(dev_id, name, model, fw_v2 if v2_only else fw_v3, status, rssi, battery))
    if base["online"] and extra:
        if cause == "WEAK_SIGNAL":
            extra[0]["rssi"] = -79       # borderline but online: must not be blamed
        else:
            for device in extra:
                if device["battery"] is not None:
                    device["battery"] = 17    # low but online: must not be blamed
                    break
    return extra


def _enrich_case(case):
    """Add narrative, household, log and action complexity. Idempotent."""
    rich = RICH.get(case["case_id"])
    if rich:
        case["complaint"] = rich["complaint"]
        case["user_knowledge"].update(rich["knowledge"])
        case["difficulty"] = rich.get("difficulty", case["difficulty"])
        note = rich.get("distractor", "")
        if note and note not in case["notes"]:
            case["notes"] = f"{case['notes']} Distractor: {note}".strip()

    state = case["hidden_state"]
    if any("housekeeping" in line for line in state["logs"]):
        return case
    background = _background_devices(case)
    state["devices"].extend(background)
    base = state["base_station"]
    before = ["02:00:03 scheduled housekeeping completed (event database vacuum 0.4 s)",
              "06:30:12 radio channel scan: channel 4 selected, utilisation 18%"]
    after = []
    if base["online"]:
        if case["gt_root_cause"] != "UPLINK_BLOCKED_PERSIST":
            before.insert(1, "04:10:48 cloud time sync ok (drift 1 s)")
            after.append("23:57:40 remote app session authenticated")
        after += [f"23:58:0{i} {d['id']} heartbeat ok" for i, d in enumerate(background[:2], 1)
                  if d["status"] == "online"]
        after.append("23:59:20 local app session opened from the home network")
    state["logs"] = before + state["logs"] + after

    for action, outcome in GENERIC_OUTCOMES[case["gt_root_cause"]].items():
        case["action_outcomes"].setdefault(action, outcome)
    return case


def _enrich_core_cases():
    """Apply the same complexity pass to the hand-authored C001-C005 files."""
    for case_id in ("C001", "C002", "C003", "C004", "C005"):
        path = CASES_DIR / f"{case_id}.json"
        case = _enrich_case(json.loads(path.read_text(encoding="utf-8")))
        path.write_text(json.dumps(case, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Enriched hand-authored cases C001-C005.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="Replace generated C006-C040 files if they already exist.")
    parser.add_argument("--enrich-core", action="store_true",
                        help="Only add the complexity pass to the hand-authored C001-C005 files (idempotent).")
    args = parser.parse_args()
    if args.enrich_core:
        _enrich_core_cases()
        return
    cases = _build_cases()
    expected_ids = [f"C{i:03d}" for i in range(6, 41)]
    actual_ids = [case["case_id"] for case in cases]
    if actual_ids != expected_ids:
        raise ValueError(f"Expected ordered ids C006-C040; got {actual_ids!r}")

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    paths = [CASES_DIR / f"{case['case_id']}.json" for case in cases]
    existing = [path for path in paths if path.exists()]
    if existing and not args.force:
        raise FileExistsError(
            f"{len(existing)} generated case(s) already exist; pass --force to regenerate."
        )
    for path, case in zip(paths, cases):
        path.write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Generated {len(cases)} synthetic cases ({expected_ids[0]}-{expected_ids[-1]}).")


if __name__ == "__main__":
    main()
