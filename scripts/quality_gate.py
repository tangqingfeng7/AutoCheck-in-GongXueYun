from pathlib import Path
import ast
import re


ROOT = Path(__file__).resolve().parents[1]


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _python_files() -> list[Path]:
    ignored = {".git", ".pytest_cache", "web/node_modules"}
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if any(rel.startswith(prefix) for prefix in ignored):
            continue
        files.append(path)
    return files


def _source_files_for_product_surface() -> list[Path]:
    suffixes = {".py", ".js", ".ts", ".vue"}
    roots = [ROOT / "server", ROOT / "web" / "src"]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix in suffixes:
                files.append(path)
    return files


def check_no_utcnow() -> list[str]:
    failures: list[str] = []
    for path in _python_files():
        if path.as_posix().endswith("scripts/quality_gate.py"):
            continue
        if path.as_posix().endswith("server/time_utils.py"):
            continue
        text = _read(path)
        if "utcnow(" in text:
            failures.append(f"{path.relative_to(ROOT)} uses utcnow(); use server.time_utils.utc_now()")
    return failures


def check_no_frontend_token_storage() -> list[str]:
    failures: list[str] = []
    for path in (ROOT / "web" / "src").rglob("*"):
        if path.suffix not in {".js", ".vue", ".ts"}:
            continue
        for line_no, line in enumerate(_read(path).splitlines(), start=1):
            lowered = line.lower()
            if "localstorage" not in lowered:
                continue
            if "token" in lowered or "auth" in lowered or "authorization" in lowered:
                failures.append(f"{path.relative_to(ROOT)}:{line_no} may persist auth material in localStorage")
    return failures


def check_no_silent_exception_pass() -> list[str]:
    failures: list[str] = []
    for path in _python_files():
        rel = _rel(path)
        if rel == "scripts/quality_gate.py":
            continue
        lines = _read(path).splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not (stripped.startswith("except ") and stripped.endswith(":")):
                continue
            for next_index in range(index + 1, len(lines)):
                next_line = lines[next_index].strip()
                if not next_line or next_line.startswith("#"):
                    continue
                if next_line == "pass":
                    failures.append(f"{rel}:{index + 1} has bare except/pass")
                break
    return failures


def check_no_server_prints() -> list[str]:
    failures: list[str] = []
    for path in _python_files():
        rel = _rel(path)
        if not rel.startswith("server/") or rel == "server/backup_cli.py":
            continue
        for line_no, line in enumerate(_read(path).splitlines(), start=1):
            if "print(" in line:
                failures.append(f"{rel}:{line_no} uses server-side print; use logging")
    return failures


def check_no_unscoped_user_lookup() -> list[str]:
    failures: list[str] = []
    pattern = "_get_active_user_or_404(session, user_id)"
    for path in _python_files():
        rel = _rel(path)
        if rel != "server/api.py":
            continue
        for line_no, line in enumerate(_read(path).splitlines(), start=1):
            if pattern in line:
                failures.append(f"{rel}:{line_no} uses unscoped user lookup; pass tenant_id or payload")
    return failures


def check_api_audit_logs_are_tenant_scoped() -> list[str]:
    failures: list[str] = []
    path = ROOT / "server" / "api.py"
    if not path.exists():
        return failures
    try:
        tree = ast.parse(_read(path), filename=str(path))
    except SyntaxError as exc:
        return [f"{_rel(path)}:{exc.lineno or 1} cannot parse api.py"]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_audit_log = isinstance(func, ast.Name) and func.id == "AuditLog"
        if not is_audit_log:
            continue
        if not any(keyword.arg == "tenant_id" for keyword in node.keywords):
            failures.append(f"{_rel(path)}:{node.lineno} creates AuditLog without tenant_id")
    return failures


def check_no_user_invitation_surface() -> list[str]:
    failures: list[str] = []
    pattern = re.compile(r"\b(invite|invitation|invitations)\b|邀请", re.IGNORECASE)
    for path in _source_files_for_product_surface():
        rel = _rel(path)
        for line_no, line in enumerate(_read(path).splitlines(), start=1):
            if pattern.search(line):
                failures.append(f"{rel}:{line_no} introduces user invitation surface")
    return failures


def main() -> int:
    failures = []
    failures.extend(check_no_utcnow())
    failures.extend(check_no_frontend_token_storage())
    failures.extend(check_no_silent_exception_pass())
    failures.extend(check_no_server_prints())
    failures.extend(check_no_unscoped_user_lookup())
    failures.extend(check_api_audit_logs_are_tenant_scoped())
    failures.extend(check_no_user_invitation_surface())
    if failures:
        print("Quality gate failed:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("Quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
