import subprocess
import sys


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "automator.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "automator" in result.stdout
