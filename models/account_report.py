from odoo import models, fields, _, api
from odoo.tools import SQL
import datetime

NUMBER_FIGURE_TYPES = ('float', 'integer', 'monetary', 'percentage')


class AccountReport(models.Model):
    _inherit = 'account.report'

    def _init_options_currency_groups(self, options, previous_options=None):
        previous_options = previous_options or {}
        groups = self.env['account.report.currency.group'].search([])

        selected_id = previous_options.get('selected_currency_group_id')
        if selected_id not in groups.ids:
            selected_id = False

        options['currency_groups'] = [{'id': g.id, 'name': g.name} for g in groups]
        options['selected_currency_group_id'] = selected_id

        if selected_id:
            options['selected_currency_group_name'] = groups.browse(selected_id).name
        else:
            options['selected_currency_group_name'] = self.env.company.currency_id.name

        options['currency_self_handled_report'] = bool(selected_id)

    def _build_column_dict(self, col_value, col_data, options=None, currency=False, digits=1,
                           column_expression=None, has_sublines=False, report_line_id=None):
        if col_value is None and col_data is None:
            return {}
    
        options = options or {}
        col_data = col_data or {}
        expression_label = col_data.get('expression_label')
    
        group_id = options.get('selected_currency_group_id')
        if group_id and expression_label in ('balance', 'debit', 'credit'):
            currency = self.env['account.report.currency.group'].browse(group_id).reference_currency_id
    
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

        group_id = options.get('selected_currency_group_id')
        if group_id:
            currency_obj = self.env['account.report.currency.group'].browse(group_id).reference_currency_id
        else:
            currency_obj = self.env.company.currency_id
        options['rounding_unit_names'] = self._get_rounding_unit_names(currency_obj)

    def _get_rounding_unit_names(self, currency_obj):
        currency_symbol = currency_obj.symbol or self.env.company.currency_id.symbol
        return {
            'decimals': f'.{currency_symbol}',
            'units': f'U {currency_symbol}',
            'thousands': f'K{currency_symbol}',
            'millions': f'M{currency_symbol}',
        }

    def _compute_formula_batch(self, column_group_options, engine, date_scope, formulas_dict, current_groupby, next_groupby, offset=0, limit=None, warnings=None):
        group_id = column_group_options.get('selected_currency_group_id')
        if group_id and engine in ('domain', 'account_codes', 'tax_tags'):
            return super(AccountReport, self.with_context(currency_group_id=group_id))._compute_formula_batch(
                column_group_options, engine, date_scope, formulas_dict, current_groupby, next_groupby,
                offset=offset, limit=limit, warnings=warnings,
            )
        return super()._compute_formula_batch(
            column_group_options, engine, date_scope, formulas_dict, current_groupby, next_groupby,
            offset=offset, limit=limit, warnings=warnings,
        )

    def _currency_table_apply_rate(self, value: SQL) -> SQL:
        group_id = self.env.context.get('currency_group_id')
        if group_id:
            group = self.env['account.report.currency.group'].browse(group_id)
            currency_ids = tuple(group.currency_ids.ids) or (0,)
            ref_currency_id = group.reference_currency_id.id
            return SQL(
                """
                CASE
                    WHEN account_move_line.currency_id IN %(currency_ids)s THEN account_move_line.amount_currency
                    ELSE (%(value)s) * COALESCE((
                        SELECT r.rate FROM res_currency_rate r
                        WHERE r.currency_id = %(ref_currency)s AND r.name <= account_move_line.date
                        ORDER BY r.name DESC LIMIT 1
                    ), 0)
                END
                """,
                value=value,
                currency_ids=currency_ids,
                ref_currency=ref_currency_id,
            )
        return super()._currency_table_apply_rate(value)