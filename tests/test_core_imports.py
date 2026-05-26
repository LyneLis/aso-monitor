import subprocess
import sys
import textwrap


def test_importing_core_compare_does_not_load_optional_clients():
    code = textwrap.dedent(
        """
        import sys

        import core.compare

        assert "core.gemini" not in sys.modules
        assert "google.generativeai" not in sys.modules
        assert "google.genai" not in sys.modules
        assert "core.parsing" not in sys.modules
        assert "bs4" not in sys.modules
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
