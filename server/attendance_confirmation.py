import time

from server.clockin_backfill import normalize_clockin_records


def confirm_attendance(client, day, target_type, attempts=3, delay=2):
    state = {"record_confirmed": False, "attendance_date": day,
             "target_type": target_type, "confirmation_state": "missing"}
    for attempt in range(attempts):
        if attempt:
            time.sleep(delay)
        try:
            records = normalize_clockin_records(client.get_checkin_records(day, day))
            match = next((r for r in records if r["date"] == day and r["type"] == target_type), None)
            if match:
                return {**state, "record_confirmed": True, "confirmation_state": "confirmed",
                        "server_time": match["time"]}
            state["confirmation_state"] = "missing"
        except Exception:
            state["confirmation_state"] = "query_failed"
    return state
