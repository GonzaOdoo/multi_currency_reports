# -*- coding: utf-8 -*-
{
    'name': "Multiple currency in reports",

    'summary': """
       
        """,

    'description': """
        Este módulo permite visualizar y trabajar con múltiples monedas en los informes contables.
    """,

    'author': "GonzaOdoo",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['project_purchase','project_hr_expense','project_stock_account','sale_project','account_budget_purchase','project_account_budget','account_reports','account_budget','analytic'],

    # always loaded
    "data": ["views/project_views.xml",
             "views/account_analytic.xml",
             "views/currency_group.xml",
             "security/ir.model.access.csv",
             #'data/general_ledger.xml',
             #'data/partner_ledger.xml',
            ],

    'assets': {
        'web.assets_backend': [
            (
                'after',
                'project_account_budget/static/src/components/**/*',
                'multi_currency_reports/static/src/xml/project_right_side_panel_budget_lines.xml',
            ),
            'multi_currency_reports/static/src/*',  # tu patch de formatMonetary, si sigue viviendo ahí
        ],
    },
}
