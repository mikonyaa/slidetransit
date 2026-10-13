import json
import os
import signal
import subprocess
import time


def test_interrupt_kills_owned_worker_and_preserves_other_output(real, tmp_path):
    other = tmp_path / (".slidetransit-" + "f" * 32 + "-other")
    other.mkdir()
    (other / "sentinel").write_text("other invocation")
    process = subprocess.Popen(
        [
            "slidetransit",
            "compare",
            "--manifest",
            str(real / "repeat.json"),
            "--out",
            str(tmp_path / "report"),
            "--no-open",
            "--json",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(os.environ, CI="1"),
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            owned = [p for p in tmp_path.glob(".slidetransit-*") if p != other]
            if any((p / "assets").is_dir() for p in owned):
                break
            assert process.poll() is None
            time.sleep(0.005)
        else:
            raise AssertionError("worker never reached owned staging")
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 130
        assert json.loads(stdout)["exitCode"] == 130
        assert "Traceback" not in stderr
        assert not (tmp_path / "report").exists()
        assert list(tmp_path.glob(".slidetransit-*")) == [other]
        assert (other / "sentinel").read_text() == "other invocation"
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
