from odoo import fields, models, api


class AccountPartnerLedgerReportHandler(models.AbstractModel):
    _inherit = "res.currency.rate"


    sort_key = fields.Integer(index=True,compute="_compute_sort_key",store=True)

    @api.depends('name')
    def _compute_sort_key(self):
        for record in self:
            record.sort_key = -int(fields.Date.to_date(record.name).strftime("%Y%m%d"))
    
