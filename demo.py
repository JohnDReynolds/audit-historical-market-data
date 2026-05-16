"""
Download Massive data and yFinance data.
Then audit Massive adjusted OHLCV, dividends, splits and returns.
"""

# Standard library imports
import subprocess
from pathlib import Path

# Project imports
from audit import Audit
import utilities as util


def main() -> None:
    """Demo"""

    # Perform audit
    audit = Audit(
        tickers=util.load_single_column_csv("inputs/tickers.csv"),
        from_date="2021-05-10",
        to_date="2026-05-10",
        # always_download=False,
    )

    # Print ohlcv audit results.  Squeaky clean, should always be empty.
    if not audit.audited_adjusted_ohlcv.is_empty():
        print(audit.audited_adjusted_ohlcv)

    for actionable in (False, True):
        # Set the output paths
        base_path = "outputs/_t_actionable" if actionable else "outputs/_t_non_actionable"
        csv_path = f"{base_path}.csv"
        html_path = f"{base_path}.html"

        # Write the audit results to csv and html
        content = audit.csv_audit_report(actionable=actionable)
        Path(csv_path).write_text(content, encoding=util.ENCODING)
        content = audit.html_audit_report(actionable=actionable)
        Path(html_path).write_text(content, encoding=util.ENCODING)

        # QA the output
        subprocess.run(["diff", csv_path, f"{csv_path}.good"], check=True)
        subprocess.run(["diff", html_path, f"{html_path}.good"], check=True)


if __name__ == "__main__":
    main()
