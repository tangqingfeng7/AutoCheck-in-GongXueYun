import copy

from server.user_runtime import execution_status


def reconcile_results(results, day, checks):
    by_type = {c.get("target_type"): c for c in checks}
    changed = False

    def visit(item):
        nonlocal changed
        value = copy.deepcopy(item)
        details = value.get("details") or {}
        result_day = str(details.get("attendance_date") or details.get("createTime")
                         or details.get("打卡时间") or "")[:10]
        match = by_type.get(details.get("target_type"))
        eligible = value.get("status") == "pending" or (
            value.get("status") == "fail" and details.get("verification_type") in {"account", "face"})
        if match and match.get("record_confirmed") and result_day == day and eligible:
            value.update(status="success", message=f"{day} 考勤记录已由服务端确认")
            evidence = {k: v for k, v in match.items() if k in {
                "record_confirmed", "target_type", "attendance_date", "server_time"}}
            value["details"] = {**details, **evidence, "confirmation_state": "confirmed"}
            changed = True
        elif (match and result_day == day and eligible and match.get("verification_confirmed") is True
              and details.get("verification_type") in {"account", "face"}):
            value.update(status="pending", message="验证已确认，考勤记录待服务端确认")
            value["details"] = {**details, "verification_confirmed": True, "record_confirmed": False,
                                "confirmation_state": "record_query_failed" if match.get("confirmation_state") == "query_failed"
                                else "verified_pending_record"}
            changed = changed or value != item
        children = value.get("items")
        if isinstance(children, list):
            value["items"] = [visit(child) for child in children]
            if value["items"] != children and value.get("task_type") in {"打卡", "补卡"}:
                states = [child.get("status") for child in value["items"]]
                value["status"] = "fail" if "fail" in states else "pending" if "pending" in states else "success" if "success" in states else "skip"
                if value["status"] == "success":
                    value["message"] = "考勤结果已统一回查确认"
                counts = {"成功": states.count("success"), "失败": states.count("fail"),
                          "待确认": states.count("pending"), "跳过": states.count("skip")}
                value["details"] = {**details, **{k: v for k, v in counts.items() if k in details}}
        return value

    updated = [visit(item) for item in results or []]
    return updated, changed


def reconcile_user(session, user, day, checks):
    updated, changed = reconcile_results(user.last_execution_result or [], day, checks)
    if changed:
        user.last_execution_result = updated
        user.last_status = execution_status(updated)
        user.logs = [f"{item.get('task_type')}: {item.get('message')}" for item in updated if item.get("status") != "skip"]
        # Keep last_run_time: a read-only reconciliation is not a new attendance run.
        session.add(user)
    return changed
