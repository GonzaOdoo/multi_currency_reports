from odoo import models, _, api
from odoo.exceptions import AccessError

from odoo.tools import SQL
from odoo.tools.misc import format_date

from dateutil.relativedelta import relativedelta
from itertools import chain
import logging
import datetime
import pprint
NUMBER_FIGURE_TYPES = ('float', 'integer', 'monetary', 'percentage')
import logging

_logger = logging.getLogger(__name__)
class AccountReport(models.Model):
    _inherit = 'account.report'

    def _init_options_currencies(self, options, previous_options=None):
        previous_options = previous_options or {}
        currencies = self.env['res.currency'].search([])

        historical = previous_options.get('historical_currency', False)
        selected_currency_id = previous_options.get('selected_currencies_id')

        if selected_currency_id and selected_currency_id != self.env.company.currency_id.id:
            historical = False
        if historical:
            selected_currency_id = False

        options['currencies'] = [
            {'id': c.id, 'name': _(c.name), 'selected': c.id == selected_currency_id}
            for c in currencies
        ]
        options['selected_currencies_id'] = selected_currency_id

        if selected_currency_id:
            options['selected_currencies'] = self.env['res.currency'].browse(selected_currency_id).name
        else:
            options['selected_currencies'] = self.env.company.currency_id.name

        # Histórico USD: aplica a cualquier reporte que use este filtro de moneda.
        options['historical_currency'] = historical
        options['historical_currency_id'] = self.env.ref('base.USD').id if historical else False
        options['currency_self_handled_report'] = historical
        
    def _build_column_dict(self, col_value, col_data, options=None, currency=False, digits=1,
                           column_expression=None, has_sublines=False, report_line_id=None):
        if col_value is None and col_data is None:
            return {}
    
        options = options or {}
        col_data = col_data or {}
        expression_label = col_data.get('expression_label')
    
        target_currency_id = options.get('selected_currencies_id') or options.get('historical_currency_id')
        self_handled_columns = options.get('currency_self_handled_columns') or set()
        skip_value_conversion = (
            options.get('currency_self_handled_report', False)
            or expression_label in self_handled_columns
        )
    
        if target_currency_id:
            to_currency = self.env['res.currency'].browse(target_currency_id)
            if to_currency:
                currency = to_currency
                if isinstance(col_value, (int, float)) and not skip_value_conversion:
                    date_obj = datetime.datetime.strptime(options['date']['date_to'], '%Y-%m-%d').date()
                    col_value = self.env.company.currency_id._convert(col_value, to_currency, date=date_obj)
    
        column_expression = column_expression or self.env['account.report.expression']
    
        figure_type = column_expression.figure_type or col_data.get('figure_type', 'string')
        format_params = {'currency_id': currency.id} if figure_type == 'monetary' and currency else {}
        if figure_type in ('float', 'percentage'):
            format_params['digits'] = digits
    
        col_group_key = col_data.get('column_group_key')
        return {
            'auditable': col_value is not None and column_expression.auditable
                         and not options['column_groups'][col_group_key]['forced_options'].get('compute_budget'),
            'blank_if_zero': column_expression.blank_if_zero or col_data.get('blank_if_zero', False),
            'column_group_key': col_group_key,
            'currency': currency or None,
            'currency_symbol': self.env.company.currency_id.symbol if options.get('multi_currency') else None,
            'digits': digits,
            'expression_label': expression_label,
            'figure_type': figure_type,
            'green_on_positive': column_expression.green_on_positive,
            'has_sublines': has_sublines,
            'is_zero': col_value is None or (isinstance(col_value, (int, float)) and figure_type in NUMBER_FIGURE_TYPES
                                             and self._is_value_zero(col_value, figure_type, format_params)),
            'no_format': col_value,
            'format_params': format_params,
            'report_line_id': report_line_id,
            'sortable': col_data.get('sortable', False),
            'comparison_mode': col_data.get('comparison_mode'),
        }

    def _init_options_rounding_unit(self, options, previous_options=None):
        options['rounding_unit'] = previous_options.get('rounding_unit', 'decimals') if previous_options else 'decimals'

        currency_name = previous_options.get('selected_currencies') or self.env.company.currency_id.name
        currency_obj = self.env['res.currency'].search([('name', '=', currency_name)],
                                                       limit=1) or self.env.company.currency_id
        options['rounding_unit_names'] = self._get_rounding_unit_names(currency_obj)

    def _get_rounding_unit_names(self, currency_obj):
        currency_symbol = currency_obj.symbol or self.env.company.currency_id.symbol
        return {
            'decimals': f'.{currency_symbol}',
            'units': f'U {currency_symbol}',  # Ensures length >= 2
            'thousands': f'K{currency_symbol}',
            'millions': f'M{currency_symbol}',
        }



    
    def _compute_formula_batch(self, column_group_options, engine, date_scope, formulas_dict, current_groupby, next_groupby, offset=0, limit=None, warnings=None):
        if column_group_options.get('historical_currency') and engine in ('domain', 'account_codes', 'tax_tags'):
            return super(AccountReport, self.with_context(historical_currency_usd=True))._compute_formula_batch(
                column_group_options, engine, date_scope, formulas_dict, current_groupby, next_groupby,
                offset=offset, limit=limit, warnings=warnings,
            )
        return super()._compute_formula_batch(
            column_group_options, engine, date_scope, formulas_dict, current_groupby, next_groupby,
            offset=offset, limit=limit, warnings=warnings,
        )

    def _currency_table_apply_rate(self, value: SQL) -> SQL:
        if self.env.context.get('historical_currency_usd'):
            usd = self.env.ref('base.USD')
            return SQL(
                """
                (%(value)s) * COALESCE((
                    SELECT r.rate FROM res_currency_rate r
                    WHERE r.currency_id = %(usd)s AND r.name <= account_move_line.date
                    ORDER BY r.name DESC LIMIT 1
                ), 0)
                """,
                value=value,
                usd=usd.id,
            )
        return super()._currency_table_apply_rate(value)