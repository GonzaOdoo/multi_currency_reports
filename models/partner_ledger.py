from odoo import fields, models


class AccountPartnerLedgerReportHandler(models.AbstractModel):
    _inherit = "account.partner.ledger.report.handler"

    def _compute_usd_values(self, values):
        """
        Agrega:
        - balance_current: balance convertido a moneda compañía usando tasa actual
        - balance_usd_current: balance convertido a USD usando tasa actual
        """

        company_currency = self.env.company.currency_id
        usd_currency = self.env.ref("base.USD")

        balance = values.get("balance", 0.0)
        amount_currency = values.get("amount_currency")
        currency_id = values.get("currency_id")

        values["balance_current"] = balance
        values["balance_current_currency_id"] = company_currency.id

        values["balance_usd_current"] = 0.0
        values["balance_usd_currency_id"] = usd_currency.id

        if not usd_currency:
            return values

        # La línea está expresada en USD
        if currency_id == usd_currency.id and amount_currency is not None:

            values["balance_current"] = usd_currency._convert(
                amount_currency,
                company_currency,
                self.env.company,
                fields.Date.today(),
            )

            values["balance_usd_current"] = amount_currency

        else:
            values["balance_usd_current"] = company_currency._convert(
                balance,
                usd_currency,
                self.env.company,
                fields.Date.today(),
            )

        return values


    def _build_partner_lines(self, report, options, level_shift=0):
        """
        Extiende el método original para agregar columnas USD
        """

        lines = []

        totals_by_column_group = {
            column_group_key: {
                total: 0.0
                for total in [
                    "debit",
                    "credit",
                    "amount",
                    "balance",
                    "balance_current",
                    "balance_usd_current",
                ]
            }
            for column_group_key in options["column_groups"]
        }

        partners_results = self._query_partners(report, options)

        search_filter = options.get("filter_search_bar", "")
        accept_unknown_in_filter = (
            search_filter.lower()
            in self._get_no_partner_line_label().lower()
        )

        for partner, results in partners_results:

            if (
                options["export_mode"] == "print"
                and search_filter
                and not partner
                and not accept_unknown_in_filter
            ):
                continue

            partner_values = {}

            for column_group_key in options["column_groups"]:

                partner_sum = results.get(column_group_key, {})

                values = {
                    "debit": partner_sum.get("debit", 0.0),
                    "credit": partner_sum.get("credit", 0.0),
                    "amount": partner_sum.get("amount", 0.0),
                    "balance": partner_sum.get("balance", 0.0),
                    "amount_currency": partner_sum.get(
                        "amount_currency"
                    ),
                    "currency_id": partner_sum.get(
                        "currency_id"
                    ),
                }

                values = self._compute_usd_values(values)

                partner_values[column_group_key] = values


                for field in [
                    "debit",
                    "credit",
                    "amount",
                    "balance",
                    "balance_current",
                    "balance_usd_current",
                ]:
                    totals_by_column_group[column_group_key][field] += (
                        values.get(field, 0.0)
                    )

            lines.append(
                self._get_report_line_partners(
                    options,
                    partner,
                    partner_values,
                    level_shift=level_shift,
                )
            )

        return lines, totals_by_column_group



    def _get_aml_values(
        self,
        options,
        partner_ids,
        offset=0,
        limit=None,
    ):
        """
        Agrega valores USD a cada account.move.line
        """

        result = super()._get_aml_values(
            options,
            partner_ids,
            offset=offset,
            limit=limit,
        )

        for partner_id, lines in result.items():

            for line in lines:
                self._compute_usd_values(line)

        return result



    def _get_report_line_move_line(
        self,
        options,
        aml_query_result,
        partner_line_id,
        init_bal_by_col_group,
        level_shift=0,
    ):

        return super()._get_report_line_move_line(
            options,
            aml_query_result,
            partner_line_id,
            init_bal_by_col_group,
            level_shift=level_shift,
        )


    ####################################################
    # COLUMNS/LINES
    ####################################################
    def _get_report_line_partners(self, options, partner, partner_values, level_shift=0):
        company_currency = self.env.company.currency_id
        usd_currency = self.env.ref("base.USD")
    
        partner_data = next(iter(partner_values.values()))
    
        unfoldable = not company_currency.is_zero(
            partner_data.get('debit', 0) or partner_data.get('credit', 0)
        )
    
        column_values = []
        report = self.env['account.report'].browse(options['report_id'])
    
        for column in options['columns']:
            col_expr_label = column['expression_label']
    
            value = (
                None
                if options.get('hide_partner_totals')
                else partner_values[column['column_group_key']].get(col_expr_label)
            )
    
            unfoldable = unfoldable or (
                col_expr_label in ('debit', 'credit', 'amount')
                and value
                and not company_currency.is_zero(value)
            )
    
            currency_id = partner_values[column['column_group_key']].get(
                'currency_id'
            )
    
            currency = False
    
            # Moneda original del importe
            if col_expr_label == 'amount_currency' and currency_id:
                currency = self.env['res.currency'].browse(currency_id)
    
            # Tu nueva columna: Valor Actual (moneda compañía)
            elif col_expr_label == 'balance_current':
                currency = company_currency
    
            # Tu nueva columna: Valorización USD Actual
            elif col_expr_label == 'balance_usd_current':
                currency = usd_currency
    
            column_values.append(
                report._build_column_dict(
                    value,
                    column,
                    options=options,
                    currency=currency,
                )
            )
    
        line_id = (
            report._get_generic_line_id('res.partner', partner.id)
            if partner
            else report._get_generic_line_id(
                'res.partner',
                None,
                markup='no_partner'
            )
        )
    
        return {
            'id': line_id,
            'name': partner is not None and (partner.name or '')[:128]
                or self._get_no_partner_line_label(),
            'columns': column_values,
            'level': 1 + level_shift,
            'trust': partner.trust if partner else None,
            'unfoldable': unfoldable,
            'unfolded': (
                line_id in options['unfolded_lines']
                or options['unfold_all']
            ),
            'expand_function': '_report_expand_unfoldable_line_partner_ledger',
        }


    def _get_report_line_move_line(
        self,
        options,
        aml_query_result,
        partner_line_id,
        init_bal_by_col_group,
        level_shift=0,
    ):
        if aml_query_result['payment_id']:
            caret_type = 'account.payment'
        else:
            caret_type = 'account.move.line'
    
        columns = []
        report = self.env['account.report'].browse(options['report_id'])
    
        company_currency = self.env.company.currency_id
        usd_currency = self.env.ref("base.USD")
    
        for column in options['columns']:
            col_expr_label = column['expression_label']
    
            if col_expr_label not in aml_query_result:
                raise UserError(
                    _("The column '%s' is not available for this report.", col_expr_label)
                )
    
            col_value = (
                aml_query_result[col_expr_label]
                if column['column_group_key'] == aml_query_result['column_group_key']
                else None
            )
    
            if col_value is None:
                columns.append(report._build_column_dict(None, None))
    
            else:
                currency = False
    
                if col_expr_label == 'balance':
                    col_value += init_bal_by_col_group[
                        column['column_group_key']
                    ]
    
                if col_expr_label == 'amount_currency':
                    currency = self.env['res.currency'].browse(
                        aml_query_result['currency_id']
                    )
    
                    if currency == company_currency:
                        col_value = ''
    
                # Valor actual en moneda compañía
                elif col_expr_label == 'balance_current':
                    currency = company_currency
    
                # Valorización USD actual
                elif col_expr_label == 'balance_usd_current':
                    currency = usd_currency
    
                columns.append(
                    report._build_column_dict(
                        col_value,
                        column,
                        options=options,
                        currency=currency,
                    )
                )
    
        return {
            'id': report._get_generic_line_id(
                'account.move.line',
                aml_query_result['id'],
                parent_line_id=partner_line_id,
                markup=aml_query_result['partial_id'],
            ),
            'parent_id': partner_line_id,
            'name': self._format_aml_name(
                aml_query_result['name'],
                aml_query_result['ref'],
                aml_query_result['move_name'],
            ),
            'columns': columns,
            'caret_options': caret_type,
            'level': 3 + level_shift,
            'is_draft': aml_query_result['parent_state'] == 'draft',
            'no_followup': aml_query_result['no_followup'],
        }