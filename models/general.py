from collections import defaultdict
from odoo import fields, models


class AccountGeneralLedgerReportHandler(models.AbstractModel):
    _inherit = "account.general.ledger.report.handler"

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(
            report, options, previous_options=previous_options,
        )
        # El grupo de monedas y el flag "currency_self_handled_report" ya los
        # arma el _init_options_currency_groups central; acá no hace falta nada más.

    def _get_currency_group(self, options):
        group_id = options.get("selected_currency_group_id")
        return self.env["account.report.currency.group"].browse(group_id) if group_id else None

    def _group_value(self, group, balance, amount_currency, currency_id, conv_date):
        company_currency = self.env.company.currency_id
        conv_date = conv_date or fields.Date.context_today(self)

        if currency_id in group.currency_ids.ids and amount_currency is not None:
            # Ya está en una moneda del grupo: se muestra tal cual, sin convertir.
            return amount_currency

        return company_currency._convert(
            balance or 0.0, group.reference_currency_id, self.env.company, conv_date,
        )

    def _overwrite_group_value(self, values, new_value, group, currency_id):
        # Solo tocamos balance/debit/credit (moneda de referencia o valor propio).
        # amount_currency y currency_id se dejan tal cual los calculó el motor
        # original, para que "Importe en moneda" siga mostrando la moneda real
        # de cada apunte, sin convertir.
        values["balance"] = new_value
        values["debit"] = new_value if new_value > 0 else 0.0
        values["credit"] = -new_value if new_value < 0 else 0.0

    def _get_group_line_values(self, group, expressions, options, date_scope, offset, limit, warnings):
        """Trae los apuntes individuales (sin pasar por nuestro override) y los
        resuelve contra el grupo de monedas una sola vez, cacheando por
        date_scope/offset/limit para no repetir la consulta cuando account_id
        y el total la piden por separado."""
        cache = options.setdefault("_gl_currency_group_cache", {})
        cache_key = (group.id, date_scope, offset, limit)
        if cache_key in cache:
            return cache[cache_key]

        raw_lines = super(AccountGeneralLedgerReportHandler, self)._report_custom_engine_general_ledger(
            expressions, options, date_scope, "id_with_accumulated_balance", None,
            offset=offset, limit=limit, warnings=warnings,
        )

        date_from = fields.Date.from_string(options["date"]["date_from"])

        for key, values in raw_lines:
            if isinstance(key, str) and key.startswith("balance_line_"):
                # Saldo inicial: se convierte con la tasa de la fecha "desde" del reporte
                conv_date = date_from
            else:
                conv_date = values.get("date") or date_from
            currency_id = values.get("currency_id")
            new_value = self._group_value(
                group, values.get("balance"), values.get("amount_currency"),
                currency_id, conv_date,
            )
            self._overwrite_group_value(values, new_value, group, currency_id)

        cache[cache_key] = raw_lines
        return raw_lines

    def _report_custom_engine_general_ledger(
        self, expressions, options, date_scope, current_groupby, next_groupby,
        offset=0, limit=None, warnings=None,
    ):
        group = self._get_currency_group(options)
        if not group:
            return super()._report_custom_engine_general_ledger(
                expressions, options, date_scope, current_groupby, next_groupby,
                offset=offset, limit=limit, warnings=warnings,
            )

        if current_groupby == "id_with_accumulated_balance":
            return self._get_group_line_values(group, expressions, options, date_scope, offset, limit, warnings)

        # Cuenta o total: sumamos los valores de línea ya resueltos (posiblemente cacheados)
        line_level = self._get_group_line_values(group, expressions, options, date_scope, 0, None, warnings)

        totals_by_account = defaultdict(float)
        grand_total = 0.0
        for key, values in line_level:
            account_id = values.get("account_id")
            value = values.get("balance") or 0.0
            totals_by_account[account_id] += value
            grand_total += value

        result = super()._report_custom_engine_general_ledger(
            expressions, options, date_scope, current_groupby, next_groupby,
            offset=offset, limit=limit, warnings=warnings,
        )

        # A nivel cuenta/total pueden mezclarse líneas en distintas monedas del
        # grupo (o fuera de él); mostramos siempre la moneda de referencia acá,
        # porque un subtotal no puede tener "su propia" moneda de línea.
        if current_groupby == "account_id":
            for account_id, values in result:
                self._overwrite_group_value(
                    values, totals_by_account.get(account_id, 0.0), group, group.reference_currency_id.id,
                )
            return result

        if not current_groupby:
            self._overwrite_group_value(result, grand_total, group, group.reference_currency_id.id)
            return result

        return result