from collections import defaultdict
from odoo import fields, models


class AccountGeneralLedgerReportHandler(models.AbstractModel):
    _inherit = "account.general.ledger.report.handler"

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(
            report, options, previous_options=previous_options,
        )
        previous_options = previous_options or {}
        historical = previous_options.get("historical_currency", False)
        selected_currency_id = previous_options.get("selected_currencies_id")
        if selected_currency_id and selected_currency_id != self.env.company.currency_id.id:
            historical = False
        options["historical_currency"] = historical
        options["historical_currency_id"] = self.env.ref("base.USD").id if historical else False
        options["currency_self_handled_report"] = historical

    def _usd_value(self, balance, amount_currency, currency_id, conv_date):
        company = self.env.company
        company_currency = company.currency_id
        usd = self.env.ref("base.USD")
        conv_date = conv_date or fields.Date.context_today(self)

        if currency_id == usd.id and amount_currency is not None:
            return usd._convert(amount_currency, company_currency, company, conv_date)
        return company_currency._convert(balance or 0.0, usd, company, conv_date)

    def _overwrite_usd(self, values, new_value, usd):
        values["balance"] = new_value
        values["amount_currency"] = new_value
        values["currency_id"] = usd.id
        values["debit"] = new_value if new_value > 0 else 0.0
        values["credit"] = -new_value if new_value < 0 else 0.0

    def _get_usd_line_values(self, expressions, options, date_scope, offset, limit, warnings):
        """Trae los apuntes individuales (sin pasar por nuestro override) y los
        convierte a USD histórico una sola vez, cacheando por date_scope/offset/limit
        para no repetir la consulta cuando account_id y el total la piden por separado."""
        cache = options.setdefault("_gl_usd_historical_cache", {})
        cache_key = (date_scope, offset, limit)
        if cache_key in cache:
            return cache[cache_key]

        raw_lines = super(AccountGeneralLedgerReportHandler, self)._report_custom_engine_general_ledger(
            expressions, options, date_scope, "id_with_accumulated_balance", None,
            offset=offset, limit=limit, warnings=warnings,
        )

        usd = self.env.ref("base.USD")
        date_from = fields.Date.from_string(options["date"]["date_from"])

        for key, values in raw_lines:
            if isinstance(key, str) and key.startswith("balance_line_"):
                # Saldo inicial: se convierte con la tasa de la fecha "desde" del reporte
                conv_date = date_from
            else:
                conv_date = values.get("date") or date_from
            new_value = self._usd_value(
                values.get("balance"), values.get("amount_currency"),
                values.get("currency_id"), conv_date,
            )
            self._overwrite_usd(values, new_value, usd)

        cache[cache_key] = raw_lines
        return raw_lines

    def _report_custom_engine_general_ledger(
        self, expressions, options, date_scope, current_groupby, next_groupby,
        offset=0, limit=None, warnings=None,
    ):
        if not options.get("historical_currency"):
            return super()._report_custom_engine_general_ledger(
                expressions, options, date_scope, current_groupby, next_groupby,
                offset=offset, limit=limit, warnings=warnings,
            )

        usd = self.env.ref("base.USD")
        company_currency = self.env.company.currency_id
        if not usd or usd == company_currency:
            return super()._report_custom_engine_general_ledger(
                expressions, options, date_scope, current_groupby, next_groupby,
                offset=offset, limit=limit, warnings=warnings,
            )

        if current_groupby == "id_with_accumulated_balance":
            return self._get_usd_line_values(expressions, options, date_scope, offset, limit, warnings)

        # Cuenta o total: sumamos los valores de línea ya convertidos (posiblemente cacheados)
        line_level = self._get_usd_line_values(expressions, options, date_scope, 0, None, warnings)

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

        if current_groupby == "account_id":
            for account_id, values in result:
                self._overwrite_usd(values, totals_by_account.get(account_id, 0.0), usd)
            return result

        if not current_groupby:
            self._overwrite_usd(result, grand_total, usd)
            return result

        return result