import time

from server.clockin_backfill import normalize_clockin_records


# Observed official v6/304 response: a human-readable instruction, not an ID
# or encrypted object. Only this known variant permits registration-only
# continuation; arbitrary opaque strings must still fail closed.
OFFICIAL_ACCOUNT_VERIFICATION_NOTICE = (
    "平台监测到您的账户存在风险操作。请确保后续由本人使用，点击【确定】前往支付宝进行安全验证后再继续签到。"
)


def continuation_context_supported(snapshot):
    if (not isinstance(snapshot, dict) or snapshot.get("version") != 1
            or snapshot.get("path") != "attendence/clock/v6/save"
            or not isinstance(snapshot.get("body"), dict)):
        return False
    return bool(snapshot.get("attendanceId")) or snapshot.get("response_data") == OFFICIAL_ACCOUNT_VERIFICATION_NOTICE


def verification_query_succeeded(response):
    """queryAxdj is a void business operation (200 + null is valid).

    APK's successful query callback clears its pending registration and refreshes
    attendance; it does not require a boolean response body. This ONLY confirms
    the verification query, never the existence of a clock-in record.
    """
    if not isinstance(response, dict) or response.get("code") != 200:
        return False
    data = response.get("data")
    return data is None or data is True


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
