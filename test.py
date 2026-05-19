"""
Download or reuse cached Massive data and yFinance data.
Then audit Massive adjusted OHLCV, dividends, splits and returns.
"""

# Standard library imports
import subprocess

# Project imports
from audit import Audit
import forensic_docs_validation
import utilities as util

# Constants
_FROM_DATE = "2021-05-16"
_TO_DATE = "2026-05-16"

# Columns to exclude from the test CSV output, which may contain non-deterministic content that
# would cause false positives in diff-based QA.  These columns are still included in the full CSV
# output for human review.
_NON_DETERMINISTIC_COLUMNS = (
    "evidence summary",
    "primary source url",
    "real world event",
    "secondary source url",
)


def _main() -> None:
    """Run the demo audit and compare generated reports to known-good verified files."""
    forensic_docs_validation.validate_forensic_docs()

    # Perform audit
    audit = Audit(
        tickers=util.load_single_column("inputs/tickers"),
        from_date=_FROM_DATE,
        to_date=_TO_DATE,
        always_download=False,
    )

    # Print ohlcv audit results.  Squeaky clean, probably always empty.
    if audit.audited_adjusted_ohlcv.is_empty():
        print("No adjusted OHLCV mismatches detected.")
    else:
        print(audit.audited_adjusted_ohlcv)

    for actionable in (True, False):
        # Set the output paths
        base_path = "outputs/actionable" if actionable else "outputs/non_actionable"
        base_path = f"{base_path}.{_FROM_DATE}.{_TO_DATE}"
        csv_path = f"{base_path}.csv"
        html_path = f"{base_path}.html"
        pdf_path = f"{base_path}.pdf"

        # Write the audit results
        audit.csv_audit_report(actionable=actionable, output_path=csv_path, verbose=True)
        audit.html_audit_report(actionable=actionable, output_path=html_path, verbose=True)
        audit.pdf_audit_report(
            actionable=actionable, output_path=pdf_path, summary=True, verbose=True
        )

        # # QA the output
        csv_test_path = f"{csv_path}.test"
        audit.csv_audit_report(
            actionable=actionable,
            output_path=csv_test_path,
            exclude_columns=_NON_DETERMINISTIC_COLUMNS,
        )
        subprocess.run(["diff", csv_test_path, f"{csv_path}.verified"], check=True)

    # Write the data dictionary PDF
    audit.pdf_data_dictionary("outputs/data_dictionary.pdf")


if __name__ == "__main__":
    _main()
