"""Record build facts without paths or credentials; not an attestation."""

import argparse
import json
import platform
import subprocess
from pathlib import Path

from slidetransit import __version__
from slidetransit.pdf import versions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = {
        "version": __version__,
        "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "environment": {
            "os": platform.system(),
            "osVersion": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
        "tools": versions(),
        "uv": subprocess.check_output(["uv", "--version"], text=True).strip(),
        "origin": "GitHub Actions build; consumer-tested artifacts",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
