Multi Currency General Ledger
=============================

Generate general ledger reports with multiple currencies support for Odoo 18.

Features
--------

* View general ledger reports in multiple currencies
* Filter by account, date range, and journal
* Show initial balances
* Export to PDF and Excel
* Detailed view of transactions by currency
* Real-time currency conversion

Configuration
-------------

No additional configuration is required. The module adds a new menu item under 
Accounting > Reporting > Multi Currency General Ledger.

Usage
-----

1. Go to Accounting > Reporting > Multi Currency General Ledger
2. Select the date range
3. Choose accounts, journals, and currencies (leave empty for all)
4. Select account types to include
5. Click "Print PDF" or "Export to Excel"

Technical Information
---------------------

* Uses direct xlsxwriter for Excel export (no report_xlsx dependency)
* Supports company currency and foreign currencies
* Initial balance calculation for each currency

Credits
-------

* Digital Integrated Transformation Solutions (DigitsCode)
* Website: https://www.digitscode.com
* Email: info@digitscode.com

License
-------

OPL-1 (Odoo Proprietary License v1.0)

Demo Data
=========

Install ``digits_tools_demo_scenario`` or ``digits_tools_demo_core`` for historical
sale/purchase orders and posted invoices used by this module's reports and dashboards.
See ``DEMO_WALKTHROUGH.md`` at the repository root.

