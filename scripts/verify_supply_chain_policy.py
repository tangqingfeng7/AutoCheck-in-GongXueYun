from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
FULL_SHA = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
IMAGE_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}\b", re.IGNORECASE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _workflow_files() -> list[Path]:
    root = ROOT / ".github" / "workflows"
    if not root.exists():
        return []
    return [path for path in root.rglob("*.yml")] + [path for path in root.rglob("*.yaml")]


def check_github_actions_are_pinned() -> list[str]:
    failures: list[str] = []
    for path in _workflow_files():
        rel = path.relative_to(ROOT).as_posix()
        for line_no, line in enumerate(_read(path).splitlines(), start=1):
            match = re.search(r"\buses:\s*([^@\s]+)@([^\s#]+)", line)
            if not match:
                continue
            action, ref = match.groups()
            if action.startswith("./"):
                continue
            if not FULL_SHA.fullmatch(ref):
                failures.append(f"{rel}:{line_no} pins {action} with mutable ref {ref}")
    return failures


def check_docker_base_images_are_digest_pinned() -> list[str]:
    failures: list[str] = []
    dockerfile = ROOT / "Dockerfile"
    if not dockerfile.exists():
        return failures
    for line_no, line in enumerate(_read(dockerfile).splitlines(), start=1):
        stripped = line.strip()
        if not stripped.upper().startswith("FROM "):
            continue
        image = stripped.split()[1]
        if image.lower() == "scratch" or image.startswith("${"):
            continue
        if not IMAGE_DIGEST.search(image):
            failures.append(f"Dockerfile:{line_no} base image is not digest-pinned: {image}")
    return failures


def main() -> int:
    failures = []
    failures.extend(check_github_actions_are_pinned())
    failures.extend(check_docker_base_images_are_digest_pinned())
    if failures:
        print("Supply-chain policy failed:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("Supply-chain policy passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
