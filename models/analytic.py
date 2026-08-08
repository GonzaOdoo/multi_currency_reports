from odoo import models, fields, api


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    usd_currency_id = fields.Many2one(
        "res.currency",
        string="USD Currency",
        default=lambda self: self.env.ref("base.USD"),
        readonly=True,
    )

    amount_usd_current = fields.Monetary(
        string="Amount USD Actual",
        currency_field="usd_currency_id",
        compute="_compute_amount_usd_current",
        store=True,
    )

    @api.depends(
        "amount",
        "date",
        "company_id.currency_id",
    )
    def _compute_amount_usd_current(self):
        usd_currency = self.env.ref("base.USD")

        for line in self:
            if not line.amount:
                line.amount_usd_current = 0.0
                continue

            line.amount_usd_current = line.company_id.currency_id._convert(
                line.amount,
                usd_currency,
                line.company_id,
                fields.Date.today(),
            )