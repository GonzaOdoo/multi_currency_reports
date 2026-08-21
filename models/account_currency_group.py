from odoo import fields, models


class AccountReportCurrencyGroup(models.Model):
    _name = 'account.report.currency.group'
    _description = 'Grupo de monedas para reportes contables'
    _order = 'sequence, id'

    name = fields.Char(required=True, help="Nombre mostrado en el filtro del reporte, ej. 'USD'.")
    sequence = fields.Integer(default=10)
    currency_ids = fields.Many2many(
        'res.currency', string="Monedas del grupo",
        help="Asientos hechos en cualquiera de estas monedas se muestran sin convertir.",
    )
    reference_currency_id = fields.Many2one(
        'res.currency', string="Moneda de referencia", required=True,
        help="Moneda usada para convertir asientos que no están en ninguna moneda del grupo.",
    )