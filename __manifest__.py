# -*- coding: utf-8 -*-
# Part of DigitsCode. See LICENSE file for full copyright and licensing details.
# © 2025 DigitsCode (Digital Integrated Transformation Solutions)
# Developer: DigitsCode <info@digitscode.com>
# Website: https://www.digitscode.com
{
    'name': 'Multi Currency General Ledger',
    'summary': 'Generate general ledger reports with multiple currencies',
    'description': """
Multi Currency General Ledger
=============================
Generate general ledger reports with multiple currencies.

Key Features
------------
* View general ledger reports in multiple currencies
* Filter by account, date range, and journal
* Show initial balances
* Export to PDF and Excel
* Detailed view of transactions by currency
* Avoid currency exchange hassles

Technical Features
-----------------
* Advanced currency handling
* Real-time currency conversion
* Optimized report generation
* Enhanced data filtering
* Excel export with formatting (direct xlsxwriter, no report_xlsx dependency)
* PDF report with QWeb templates
* [2025-05-04] Direct Excel export and currency handling improvements. Removed report_xlsx dependency. Ensured Excel matches PDF structure and values are in selected currency.
    """,
    'version': '19.0.1.1.5',
    'author': 'Digital Integrated Transformation Solutions (DigitsCode)',
    'maintainer': 'Digital Integrated Transformation Solutions (DigitsCode)',
    'website': 'https://www.digitscode.com',
    'email': 'info@digitscode.com',
    'company': 'Digital Integrated Transformation Solutions (DigitsCode)',
    'license': 'OPL-1',
    'category': 'Accounting/Accounting',
    'depends': [
        'account',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/multi_currency_general_ledger_wizard_views.xml',
        'report/multi_currency_general_ledger_report.xml',
        'report/multi_currency_general_ledger_report_templates.xml',
        'views/menu_views.xml',
    ],
    'images': [
        'static/description/banner.png',
        'static/description/icon.png',
    ],
    'currency': 'EUR',
    'installable': True,
    'auto_install': False,
    'application': False,
    'demo': ['demo/demo.xml'],
}