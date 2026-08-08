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
    'depends': ['account_budget_purchase','project_account_budget','project_purchase','account_reports','account_budget','analytic'],

    # always loaded
    "data": ["security/ir.model.access.csv",
             "views/delivery_carrier.xml",
             #'data/general_ledger.xml',
             'data/partner_ledger.xml',
            ],

    'assets': {
        'web.assets_backend': [
            (
                'after',
                'project_account_budget/static/src/components/**/*',
                'multi_currency_reports/static/src/*',
            ),
        ],
    },
}
