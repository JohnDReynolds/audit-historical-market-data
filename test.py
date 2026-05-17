"""
Download Massive data and yFinance data.
Then audit Massive adjusted OHLCV, dividends, splits and returns.
"""

# Standard library imports
import subprocess

# Project imports
from audit import Audit
import utilities as util

# Constants
_DO_QA = False  # TODO: True
_FROM_DATE = "2021-05-16"
_TO_DATE = "2026-05-16"


def main() -> None:
    """Run the demo audit and compare generated reports to known-good files."""

    # Perform audit
    audit = Audit(
        tickers=util.load_single_column_csv("inputs/tickers.csv"),
        from_date=_FROM_DATE,
        to_date=_TO_DATE,
        # always_download=False, default
    )

    # Print ohlcv audit results.  Squeaky clean, probably always empty.
    if not audit.audited_adjusted_ohlcv.is_empty():
        print(audit.audited_adjusted_ohlcv)

    for actionable in (False, True):
        # Set the output paths
        base_path = "outputs/actionable" if actionable else "outputs/non_actionable"
        base_path = f"{base_path}.{_FROM_DATE}.{_TO_DATE}"
        csv_path = f"{base_path}.csv"
        html_path = f"{base_path}.html"
        pdf_path = f"{base_path}.pdf"

        # Write the audit results
        audit.csv_audit_report(actionable=actionable, output_path=csv_path)
        audit.html_audit_report(actionable=actionable, output_path=html_path)
        audit.pdf_audit_report(actionable=actionable, summary=True, output_path=pdf_path)

        # QA the output
        if _DO_QA:
            subprocess.run(["diff", csv_path, f"{csv_path}.good"], check=True)
            subprocess.run(["diff", html_path, f"{html_path}.good"], check=True)

    # Write the data dictionary PDF
    audit.pdf_data_dictionary("outputs/data_dictionary.pdf")


if __name__ == "__main__":
    main()
