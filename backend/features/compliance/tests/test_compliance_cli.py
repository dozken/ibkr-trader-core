import sys
import argparse
import unittest
from pathlib import Path
from unittest.mock import patch
import io
from contextlib import redirect_stdout
from backend.features.compliance.cli import main

_CLI_PATH = Path(__file__).resolve().parents[1] / "cli.py"

class TestComplianceCLI(unittest.TestCase):
    def test_cli_halal_symbol(self):
        # TEST: CLI output for a compliant symbol
        # Citing AGENT.md Section 1: Ironclad engineering & Traceability
        test_args = [
            "cli.py",
            "--symbol", "AAPL",
            "--debt", "10",
            "--cash", "5",
            "--revenue", "100",
            "--prohibited-income", "2",
            "--mkt-cap", "1000",
            "--sector", "Technology"
        ]
        with patch("sys.argv", test_args):
            f = io.StringIO()
            with redirect_stdout(f):
                main()
            output = f.getvalue()
            self.assertIn("AAPL SHARIAH STATUS", output)
            self.assertIn("COMPLIANT", output)

    def test_cli_haram_symbol(self):
        # TEST: CLI output for a non-compliant symbol (High Debt)
        test_args = [
            "cli.py",
            "--symbol", "DEBTCO",
            "--debt", "400",
            "--cash", "50",
            "--revenue", "1000",
            "--prohibited-income", "10",
            "--mkt-cap", "1000",
            "--sector", "Technology"
        ]
        with patch("sys.argv", test_args):
            f = io.StringIO()
            with redirect_stdout(f):
                main()
            output = f.getvalue()
            self.assertIn("DEBTCO SHARIAH STATUS", output)
            self.assertIn("NON-COMPLIANT", output)
            self.assertIn("Debt ratio", output)

    def test_cli_prohibited_sector(self):
        # TEST: CLI output for a prohibited sector
        test_args = [
            "cli.py",
            "--symbol", "WINERY",
            "--debt", "0",
            "--cash", "0",
            "--revenue", "100",
            "--prohibited-income", "0",
            "--mkt-cap", "1000",
            "--sector", "Alcohol"
        ]
        with patch("sys.argv", test_args):
            f = io.StringIO()
            with redirect_stdout(f):
                main()
            output = f.getvalue()
            self.assertIn("WINERY SHARIAH STATUS", output)
            self.assertIn("NON-COMPLIANT", output)
            self.assertIn("Prohibited sector: Alcohol", output)

    def test_cli_main_block(self):
        # TEST: Execute the cli.py file as a script to hit the __main__ block
        # Using exec() to run the file with __name__ == "__main__" to capture absolute 100% coverage
        test_args = [
            "cli.py",
            "--symbol", "AAPL",
            "--debt", "10",
            "--cash", "5",
            "--revenue", "100",
            "--prohibited-income", "2",
            "--mkt-cap", "1000",
            "--sector", "Technology"
        ]
        with patch("sys.argv", test_args):
            f = io.StringIO()
            with redirect_stdout(f):
                with open(_CLI_PATH, "r") as cli_file:
                    exec_globals = {
                        "__name__": "__main__",
                        "__file__": str(_CLI_PATH),
                        "sys": sys,
                        "argparse": argparse,
                    }
                    # We need to make sure the imports inside the file work
                    # Since it uses 'from backend.features.compliance.screening import ...'
                    # we need to ensure the parent packages are in sys.modules or reachable
                    exec(cli_file.read(), exec_globals)
            self.assertIn("SHARIAH STATUS: COMPLIANT", f.getvalue())

if __name__ == "__main__":
    unittest.main()
