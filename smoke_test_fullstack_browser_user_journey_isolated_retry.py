from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import smoke_test_fullstack_browser_user_journey as base


ROOT = Path(__file__).resolve().parent


def run_once(width: int, height: int) -> None:
    chrome = base.chrome_binary()
    with tempfile.TemporaryDirectory(prefix="jj-fullstack-isolated-retry-") as td:
        work = Path(td)
        port = base.free_port()
        env = os.environ.copy()
        env.pop("DATABASE_URL", None)
        env.pop("RENDER", None)
        env["JJ_DB_PATH"] = str(work / "journey.sqlite3")
        env["JJ_ENABLE_DEMO_MEMBER"] = "0"
        env["JJ_ADMIN_NAME"] = "E2E_ADMIN"
        env.pop("JJ_ADMIN_PIN", None)

        process = subprocess.Popen(
            [sys.executable, str(ROOT / "smoke_test_fullstack_browser_user_journey.py"), "--serve", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            base.wait_server(port, process)
            proc = subprocess.run(
                [
                    chrome,
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=30000",
                    f"--window-size={width},{height}",
                    "--dump-dom",
                    f"http://127.0.0.1:{port}/",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=70,
            )
            assert 'data-fullstack-journey-ok="1"' in proc.stdout, proc.stdout[-6000:]
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.returncode not in (0, -15):
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"journey server failed: {process.returncode}\n{output[-3000:]}")


def run_viewport(width: int, height: int) -> None:
    failures: list[str] = []
    for attempt in range(1, 3):
        try:
            run_once(width, height)
            return
        except Exception as exc:
            failures.append(f"attempt {attempt}: {exc}")
    raise AssertionError("fresh-state browser retries failed\n" + "\n".join(failures))


def main() -> None:
    run_viewport(1440, 900)
    run_viewport(390, 844)
    print("JJ_FULLSTACK_BROWSER_USER_JOURNEY_ISOLATED_RETRY_OK desktop=1 mobile=1")


if __name__ == "__main__":
    main()
