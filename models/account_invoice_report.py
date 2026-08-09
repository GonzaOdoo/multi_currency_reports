from odoo import models, fields, api
from odoo.tools import SQL


class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"

    price_subtotal_usd_current = fields.Monetary(
        string="Subtotal USD",
        currency_field="usd_currency_id",
        readonly=True,
    )

    price_total_usd_current = fields.Monetary(
        string="Total USD",
        currency_field="usd_currency_id",
        readonly=True,
    )

    usd_currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.ref("base.USD"),
        readonly=True,
    )

    @api.model
    def _select(self) -> SQL:
        return SQL(
            """
            %(select)s,

            %(usd_currency_id)s AS usd_currency_id,

            (
                -line.balance * account_currency_table.rate
            ) * usd_rate.rate AS price_subtotal_usd_current,

            (
                line.price_total *
                (CASE 
                    WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') 
                    THEN -1 
                    ELSE 1 
                END)
                / move.invoice_currency_rate
            ) * usd_rate.rate AS price_total_usd_current

            """,
            select=super()._select(),
            usd_currency_id=self.env.ref("base.USD").id,
        )

    
    @api.model
    def _from(self) -> SQL:
        return SQL(
            """
            %(base_from)s
    
            LEFT JOIN LATERAL (
                SELECT rate
                FROM res_currency_rate
                WHERE currency_id = %(usd_currency_id)s
                AND name <= move.date
                ORDER BY name DESC
                LIMIT 1
            ) usd_rate ON TRUE
    
            """,
            base_from=super()._from(),
            usd_currency_id=self.env.ref("base.USD").id,
        )