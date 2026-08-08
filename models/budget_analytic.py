from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from  odoo.tools import SQL

class BudgetAnalytic(models.Model):
    _inherit = 'budget.analytic'

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )

    @api.constrains('currency_id')
    def _check_currency_change(self):
        for budget in self:
            if budget.state != 'draft' and budget.budget_line_ids:
                raise ValidationError(_(
                    "You cannot change the currency of a budget once it has "
                    "lines and is no longer in Draft."
                ))


class BudgetLine(models.Model):
    _inherit = 'budget.line'

    currency_id = fields.Many2one(related='budget_analytic_id.currency_id', store=True, readonly=True)

    def _compute_all(self):
        super()._compute_all()
        today = fields.Date.context_today(self)
        has_committed = 'committed_amount' in self._fields
        for line in self:
            company_currency = line.company_id.currency_id
            if line.currency_id == company_currency:
                continue
            if line.achieved_amount:
                line.achieved_amount = company_currency._convert(
                    from_amount=line.achieved_amount,
                    to_currency=line.currency_id,
                    company=line.company_id,
                    date=today,
                )
            line.achieved_percentage = line.budget_amount and (line.achieved_amount / line.budget_amount)

            if has_committed and line.committed_amount:
                line.committed_amount = company_currency._convert(
                    from_amount=line.committed_amount,
                    to_currency=line.currency_id,
                    company=line.company_id,
                    date=today,
                )
                line.committed_percentage = line.budget_amount and (line.committed_amount / line.budget_amount)

    def _field_to_sql(self, alias, field_expr, query=None):
        # currency_id ahora es una columna real (related+store), así que
        # ignoramos la resolución especial del padre para este campo y
        # dejamos que se lea directo de la tabla.
        if field_expr == 'currency_id':
            return SQL("%s.currency_id", SQL.identifier(alias))
        return super()._field_to_sql(alias, field_expr, query)