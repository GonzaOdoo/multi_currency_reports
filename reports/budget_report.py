from odoo import fields, models
from odoo.tools import SQL


class BudgetReport(models.Model):
    _inherit = 'budget.report'

    currency_id = fields.Many2one('res.currency', 'Currency', readonly=True)

    @property
    def _table_query(self):
        base_query = super()._table_query
        return SQL(
            """
            SELECT
                sub.*,
                COALESCE(ba.currency_id, rc.currency_id) AS currency_id
              FROM (%(base_query)s) sub
         LEFT JOIN budget_analytic ba ON ba.id = sub.budget_analytic_id
         LEFT JOIN res_company rc ON rc.id = sub.company_id
            """,
            base_query=base_query,
        )

    def _convert_achieved_committed(self, records):
        for fname in ('achieved', 'committed'):
            if fname not in records._fields:
                continue
            for record in records:
                value = record[fname]
                if value and record.currency_id and record.currency_id != record.company_id.currency_id:
                    yield fname, record, record.company_id.currency_id._convert(
                        from_amount=value,
                        to_currency=record.currency_id,
                        company=record.company_id,
                        date=record.date or fields.Date.context_today(self),
                    )
                else:
                    yield fname, record, value

    def _read_format(self, fnames, load='_classic_read'):
        result = super()._read_format(fnames, load=load)
        if 'achieved' in fnames or 'committed' in fnames:
            records_by_id = {r.id: r for r in self}
            for vals in result:
                record = records_by_id.get(vals['id'])
                if not record or not record.currency_id or record.currency_id == record.company_id.currency_id:
                    continue
                for fname in ('achieved', 'committed'):
                    if fname in vals and vals[fname]:
                        vals[fname] = record.company_id.currency_id._convert(
                            from_amount=vals[fname],
                            to_currency=record.currency_id,
                            company=record.company_id,
                            date=record.date or fields.Date.context_today(self),
                        )
        return result

    def _read_group_select(self, aggregate_spec, query):
        if aggregate_spec in ('achieved:sum', 'committed:sum'):
            return super()._read_group_select('id:recordset', query)
        return super()._read_group_select(aggregate_spec, query)

    def _read_group_postprocess_aggregate(self, aggregate_spec, raw_values):
        if aggregate_spec in ('achieved:sum', 'committed:sum'):
            field_name, _op = aggregate_spec.split(':')
            column = super()._read_group_postprocess_aggregate('id:recordset', raw_values)

            def convert_sum(records):
                total = 0
                for record in records:
                    value = record[field_name]
                    if value and record.currency_id and record.currency_id != record.company_id.currency_id:
                        value = record.company_id.currency_id._convert(
                            from_amount=value,
                            to_currency=record.currency_id,
                            company=record.company_id,
                            date=record.date or fields.Date.context_today(self),
                        )
                    total += value
                return total

            return (convert_sum(records) for records in column)
        return super()._read_group_postprocess_aggregate(aggregate_spec, raw_values)