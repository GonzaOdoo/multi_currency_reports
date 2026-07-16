# -*- coding: utf-8 -*-
# Part of DigitsCode. See LICENSE file for full copyright and licensing details.
# © 2025 DigitsCode (Digital Integrated Transformation Solutions)
# Developer: DigitsCode <info@digitscode.com>
# Website: https://www.digitscode.com
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime, date
import json
import logging

_logger = logging.getLogger(__name__)


class MultiCurrencyGeneralLedgerWizard(models.TransientModel):
    _name = 'multi.currency.general.ledger.wizard'
    _description = 'Multi Currency General Ledger Wizard'

    def _default_date_from(self):
        """Set default start date to beginning of current year"""
        today = date.today()
        return date(today.year, 1, 1)

    def _default_date_to(self):
        """Set default end date to today"""
        return date.today()

    company_id = fields.Many2one(
        'res.company', string='Company', 
        default=lambda self: self.env.company,
        required=True
    )
    date_from = fields.Date(string='Start Date', default=_default_date_from)
    date_to = fields.Date(string='End Date', default=_default_date_to)
    target_move = fields.Selection([
        ('posted', 'All Posted Entries'),
        ('all', 'All Entries'),
    ], string='Target Moves', required=True, default='posted')
    display_account = fields.Selection([
        ('all', 'All'),
        ('movement', 'With movements'),
        ('not_zero', 'With balance not equal to zero'),
    ], string='Display Accounts', required=True, default='movement')
    account_ids = fields.Many2many(
        'account.account', string='Accounts',
        help="Leave empty to get all accounts"
    )
    journal_ids = fields.Many2many(
        'account.journal', string='Journals',
        help="Leave empty to get all journals"
    )
    currency_ids = fields.Many2many(
        'res.currency', string='Currencies',
        help="Leave empty to get all currencies"
    )
    account_type_asset = fields.Boolean(string='Asset Accounts', default=True)
    account_type_liability = fields.Boolean(string='Liability Accounts', default=True)
    account_type_equity = fields.Boolean(string='Equity Accounts', default=True)
    account_type_income = fields.Boolean(string='Income Accounts', default=True)
    account_type_expense = fields.Boolean(string='Expense Accounts', default=True)
    account_type_other = fields.Boolean(string='Off-Balance Accounts', default=False)
    show_init_balance = fields.Boolean(
        string='Show Initial Balance', default=True
    )
    
    @api.onchange('account_type_asset', 'account_type_liability', 'account_type_equity',
                  'account_type_income', 'account_type_expense', 'account_type_other')
    def _onchange_account_types(self):
        """Ensure at least one account type is selected"""
        if not any([self.account_type_asset, self.account_type_liability, 
                   self.account_type_equity, self.account_type_income,
                   self.account_type_expense, self.account_type_other]):
            # If no type is selected, default to all types
            self.account_type_asset = True
            self.account_type_liability = True
            self.account_type_equity = True
            self.account_type_income = True
            self.account_type_expense = True
    
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Check if start date is before end date"""
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise UserError(_("Start date must be less than or equal to end date."))
    
    def action_print_pdf(self):
        """Print PDF report"""
        self.ensure_one()
        data = self._prepare_report_data()
        return self.env.ref('digits_multi_currency_general_ledger.action_report_multi_currency_general_ledger_pdf').report_action(self, data=data)
    
    def action_export_xlsx(self):
        """Export XLSX report directly using xlsxwriter - matching PDF report format"""
        import base64
        import io
        import logging
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_("The xlsxwriter library is not installed. Please install it using 'pip install xlsxwriter'."))
        
        self.ensure_one()
        _logger = logging.getLogger(__name__)
        _logger.info("Starting direct XLSX Export for Multi Currency General Ledger")
        
        # Prepare data using same method as PDF report
        form_data = self._prepare_report_data()['form']
        
        # Get the report model to use its data processing methods
        report_model = self.env['report.digits_multi_currency_general_ledger.mcgl_pdf']
        
        # Get accounts
        account_ids = form_data.get('account_ids', [])
        if account_ids:
            accounts = self.env['account.account'].browse(account_ids)
        else:
            # Get accounts based on selected types
            company_id = form_data.get('company_id')
            
            # Build account type filters
            account_type_filters = []
            if form_data.get('account_type_asset'):
                account_type_filters.extend(['asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_fixed'])
            if form_data.get('account_type_liability'):
                account_type_filters.extend(['liability_payable', 'liability_current', 'liability_non_current'])
            if form_data.get('account_type_equity'):
                account_type_filters.append('equity')
            if form_data.get('account_type_income'):
                account_type_filters.append('income')
            if form_data.get('account_type_expense'):
                account_type_filters.append('expense')
            if form_data.get('account_type_other'):
                account_type_filters.append('off_balance')
            
            # Use helper method to get company accounts
            accounts = self.env['multi.currency.general.ledger']._get_company_accounts(
                company_id, account_type_filters if account_type_filters else None)
        
        # Get currencies
        currency_ids = form_data.get('currency_ids', [])
        currencies = self.env['res.currency'].browse(currency_ids) if currency_ids else self.env['res.currency'].search([])
        
        # Get other parameters
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        target_move = form_data.get('target_move', 'posted')
        display_account = form_data.get('display_account', 'movement')
        show_init_balance = form_data.get('show_init_balance', True)
        
        # Process accounts and currencies to get data
        # This should mirror the logic in the PDF report
        results = {}
        for account in accounts:
            results[account.id] = {}
            for currency in currencies:
                # Get move lines for this account and currency
                move_lines, init_balance = self._get_account_move_lines(
                    account, currency, date_from, date_to, target_move, form_data.get('journal_ids', [])
                )
                
                # Skip if no data based on display_account setting
                if display_account == 'movement' and not move_lines:
                    continue
                if display_account == 'not_zero' and not move_lines and init_balance['balance'] == 0:
                    continue
                
                # Store data
                results[account.id][currency.id] = {
                    'move_lines': move_lines,
                    'init_balance': init_balance,
                }
        
        # Create in-memory Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        
        # Create formats
        formats = self._create_xlsx_formats(workbook)
        
        # Add worksheet
        sheet = workbook.add_worksheet('General Ledger')
        
        # Set column widths
        column_widths = {
            'A': 12,  # Date
            'B': 15,  # Journal
            'C': 20,  # Account
            'D': 40,  # Partner/Label
            'E': 15,  # Reference
            'F': 15,  # Debit
            'G': 15,  # Credit
            'H': 15,  # Balance
            'I': 15,  # Currency
            'J': 15,  # Amount Currency
        }
        for col, width in column_widths.items():
            col_idx = ord(col) - ord('A')
            sheet.set_column(col_idx, col_idx, width)
            
        # Add headers
        company = self.env.company
        sheet.merge_range('A1:J1', 'Multi Currency General Ledger', formats['title'])
        sheet.merge_range('A2:J2', company.name, formats['header_center'])
        date_str = f"From {self.date_from.strftime('%Y-%m-%d')} to {self.date_to.strftime('%Y-%m-%d')}"
        sheet.merge_range('A3:J3', date_str, formats['header_center'])
        
        # Add filter info
        row = 4
        sheet.merge_range(f'A{row}:J{row}', 'Filter Criteria', formats['subheader'])
        row += 1
        sheet.write(f'A{row}', 'Target Moves:', formats['filter_label'])
        sheet.write(f'B{row}', 'All Posted Entries' if self.target_move == 'posted' else 'All Entries', formats['filter_text'])
        row += 1
        sheet.write(f'A{row}', 'Display Accounts:', formats['filter_label'])
        display_account_map = {
            'all': 'All',
            'movement': 'With movements',
            'not_zero': 'With balance not equal to zero'
        }
        sheet.write(f'B{row}', display_account_map.get(self.display_account, ''), formats['filter_text'])
        row += 1
        sheet.write(f'A{row}', 'Initial Balance:', formats['filter_label'])
        sheet.write(f'B{row}', 'Yes' if self.show_init_balance else 'No', formats['filter_text'])
        row += 2
        
        # Process each account with data
        for account in accounts:
            account_id = account.id
            if account_id not in results:
                continue
            
            # Check if account has any data in any currency
            account_has_data = False
            account_total_balance = 0.0
            
            # First check if this account has any data worth showing based on display_account setting
            for currency in currencies:
                currency_id = currency.id
                if currency_id not in results[account_id]:
                    continue
                
                # Get data for this account and currency
                account_data = results[account_id][currency_id]
                move_lines = account_data.get('move_lines', [])
                init_balance = account_data.get('init_balance', {'balance': 0.0})
                
                # Check if this currency has any data
                if display_account == 'all':
                    account_has_data = True
                    break
                elif display_account == 'movement' and move_lines:
                    account_has_data = True
                    break
                elif display_account == 'not_zero' and (move_lines or init_balance['balance'] != 0):
                    account_has_data = True
                    break
                
                # Add to total balance (for not_zero check)
                account_total_balance += init_balance['balance']
            
            # Skip account completely if it has no data to show
            if not account_has_data:
                if display_account == 'not_zero' and account_total_balance == 0:
                    continue
                elif display_account == 'movement':
                    continue
            
            # Account header
            sheet.merge_range(f'A{row}:J{row}', f"{account.code} - {account.name}", formats['account_header'])
            row += 1
            
            # Process each currency for this account
            for currency in currencies:
                currency_id = currency.id
                if currency_id not in results[account_id]:
                    continue
                
                # Currency header
                sheet.merge_range(f'A{row}:J{row}', f"Currency: {currency.name}", formats['currency_header'])
                row += 1
                
                # Table Headers
                headers = ['Date', 'Journal', 'Partner/Label', 'Reference', 'Debit', 'Credit', 'Balance', 'Amount in Currency']
                for i, header in enumerate(headers):
                    sheet.write(row, i, header, formats['table_header'])
                row += 1
                
                # Get data for this account and currency
                account_data = results[account_id][currency_id]
                init_balance = account_data.get('init_balance', {'debit': 0, 'credit': 0, 'balance': 0, 'amount_currency': 0})
                move_lines = account_data.get('move_lines', [])

                # Net opening balance (used for display on debit/credit side)
                init_net_balance = init_balance.get('balance', 0.0)

                # Initial balance line if enabled (show on debit or credit side based on sign)
                if self.show_init_balance:
                    sheet.write(row, 0, "Initial Balance", formats['init_balance'])

                    opening_debit = init_net_balance if init_net_balance > 0 else 0.0
                    opening_credit = -init_net_balance if init_net_balance < 0 else 0.0

                    sheet.write(row, 4, opening_debit, formats['number'])
                    sheet.write(row, 5, opening_credit, formats['number'])
                    sheet.write(row, 6, init_net_balance, formats['number'])
                    sheet.write(row, 7, init_balance.get('amount_currency', 0.0), formats['number'])
                    row += 1

                # Process move lines
                running_balance = init_net_balance
                for line in move_lines:
                    sheet.write(row, 0, line.get('date', ''), formats['date'])
                    sheet.write(row, 1, line.get('journal', ''), formats['text'])
                    sheet.write(row, 2, line.get('partner_name', line.get('name', '')), formats['text'])
                    sheet.write(row, 3, line.get('ref', ''), formats['text'])
                    
                    debit = line.get('debit', 0.0)
                    credit = line.get('credit', 0.0)
                    
                    sheet.write(row, 4, debit, formats['number'])
                    sheet.write(row, 5, credit, formats['number'])
                    
                    running_balance += debit - credit
                    sheet.write(row, 6, running_balance, formats['number'])
                    sheet.write(row, 7, line.get('amount_currency', 0.0), formats['number'])
                    
                    row += 1
                
                # Currency total (include opening balance on correct side)
                opening_debit = init_net_balance if init_net_balance > 0 else 0.0
                opening_credit = -init_net_balance if init_net_balance < 0 else 0.0

                total_debit = opening_debit + sum(line.get('debit', 0.0) for line in move_lines)
                total_credit = opening_credit + sum(line.get('credit', 0.0) for line in move_lines)
                total_balance = total_debit - total_credit
                total_amount_currency = init_balance.get('amount_currency', 0.0) + sum(line.get('amount_currency', 0.0) for line in move_lines)
                
                sheet.write(row, 2, 'Total', formats['total_label'])
                sheet.write(row, 4, total_debit, formats['total_number'])
                sheet.write(row, 5, total_credit, formats['total_number'])
                sheet.write(row, 6, total_balance, formats['total_number'])
                sheet.write(row, 7, total_amount_currency, formats['total_number'])
                row += 2
            
            # Add a space between accounts
            row += 1
        
        # Finalize the workbook
        workbook.close()
        
        # Get the Excel data
        xlsx_data = output.getvalue()
        
        # Create attachment
        filename = f"Multi_Currency_General_Ledger_{self.date_from.strftime('%Y%m%d')}_to_{self.date_to.strftime('%Y%m%d')}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
        })
        
        # Return action to download the file
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
    
    def _get_account_move_lines(self, account, currency, date_from, date_to, target_move, journal_ids=None):
        """Get move lines for an account and currency"""
        company_id = self.company_id.id
        company = self.env['res.company'].browse(company_id)
        company_currency = company.currency_id
        
        # Build domain for move lines search
        domain = [
            ('account_id', '=', account.id),
            ('move_id.company_id', '=', company_id),
        ]
        
        # Add journal filter if specified
        if journal_ids:
            domain.append(('journal_id', 'in', journal_ids))
        
        # Add date filters for period lines
        # Date filter for initial balance is handled separately
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
            
        # Add target move filter
        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        
        # CRITICAL: The approach to currency filtering needs to be different
        # For company currency (base currency), remove currency filter OR check if it's NULL/company currency
        # For foreign currencies, only get lines with that specific currency
        if currency.id == company_currency.id:
            # For company currency, use a special filter that gets lines
            # with NO currency OR with company currency
            domain.extend(['|', ('currency_id', '=', False), ('currency_id', '=', company_currency.id)])
        else:
            # For foreign currency, only lines with this specific currency
            domain.append(('currency_id', '=', currency.id))
        
        _logger.info("Move lines search domain: %s", domain)
        
        try:
            # Get period move lines
            move_lines = self.env['account.move.line'].search(domain, order='date, move_id, id')
            
            # Process period move lines
            result = []
            for line in move_lines:
                # Determine debit/credit/balance based on currency
                if currency.id == company_currency.id:
                    # For company currency
                    debit = line.debit
                    credit = line.credit
                    balance = line.balance
                else:
                    # For foreign currency, use amount_currency with appropriate sign
                    amount_currency = line.amount_currency or 0.0
                    debit = abs(amount_currency) if amount_currency > 0 else 0.0
                    credit = abs(amount_currency) if amount_currency < 0 else 0.0
                    balance = amount_currency
                
                # Add line data
                result.append({
                    'id': line.id,
                    'date': line.date,
                    'move_id': line.move_id.id,
                    'move_name': line.move_id.name,
                    'journal_id': line.journal_id.id,
                    'journal': line.journal_id.code,
                    'journal_name': line.journal_id.name,
                    'ref': line.move_id.ref or '',
                    'name': line.name or '',
                    'partner_id': line.partner_id.id if line.partner_id else False,
                    'partner_name': line.partner_id.name if line.partner_id else '',
                    'debit': debit,
                    'credit': credit,
                    'balance': balance,
                    'amount_currency': balance,  # Using the computed balance as amount_currency
                })
            
            # Get initial balance using same method as PDF report
            init_balance = self._get_initial_balance(account, currency, journal_ids, date_from, target_move, company_id)
            
            return result, init_balance
            
        except Exception as e:
            _logger.error("Error retrieving move lines: %s", e)
            return [], {'debit': 0.0, 'credit': 0.0, 'balance': 0.0, 'amount_currency': 0.0}
            
    def _get_initial_balance(self, account, currency, journal_ids, date_from, target_move, company_id):
        """Calculate initial balance for an account in a specific currency - same method as PDF report"""
        company = self.env['res.company'].browse(company_id)
        company_currency = company.currency_id
        
        try:
            # For company currency use balance field
            # For foreign currency use amount_currency field with currency filter
            if currency.id == company_currency.id:
                query = """
                    SELECT 
                        COALESCE(SUM(aml.debit), 0) as debit,
                        COALESCE(SUM(aml.credit), 0) as credit,
                        COALESCE(SUM(aml.balance), 0) as balance,
                        COALESCE(SUM(aml.balance), 0) as amount_currency
                    FROM account_move_line aml
                    JOIN account_move am ON aml.move_id = am.id
                    WHERE aml.account_id = %s
                    AND am.company_id = %s
                    AND aml.date < %s
                """
                params = [
                    account.id,
                    company_id,
                    date_from,
                ]
            else:
                # For foreign currency, we need to filter by currency_id and use amount_currency
                query = """
                    SELECT 
                        COALESCE(SUM(CASE WHEN aml.amount_currency > 0 THEN ABS(aml.amount_currency) ELSE 0 END), 0) as debit,
                        COALESCE(SUM(CASE WHEN aml.amount_currency < 0 THEN ABS(aml.amount_currency) ELSE 0 END), 0) as credit,
                        COALESCE(SUM(aml.amount_currency), 0) as balance,
                        COALESCE(SUM(aml.amount_currency), 0) as amount_currency
                    FROM account_move_line aml
                    JOIN account_move am ON aml.move_id = am.id
                    WHERE aml.account_id = %s
                    AND aml.currency_id = %s
                    AND am.company_id = %s
                    AND aml.date < %s
                """
                params = [
                    account.id,
                    currency.id,
                    company_id,
                    date_from,
                ]
            
            # Add journal filter if specified
            if journal_ids:
                query += " AND aml.journal_id IN %s"
                params.append(tuple(journal_ids))
            
            # Add target move filter
            if target_move == 'posted':
                query += " AND aml.parent_state = 'posted'"
            
            _logger.info("Initial balance query: %s, params: %s", query, params)
            
            self.env.cr.execute(query, params)
            result = self.env.cr.dictfetchone()
            if result:
                return {
                    'debit': result['debit'],
                    'credit': result['credit'],
                    'balance': result['balance'],
                    'amount_currency': result['amount_currency']
                }
            else:
                return {'debit': 0.0, 'credit': 0.0, 'balance': 0.0, 'amount_currency': 0.0}
        except Exception as e:
            _logger.error("Error calculating initial balance: %s", e)
            return {'debit': 0.0, 'credit': 0.0, 'balance': 0.0, 'amount_currency': 0.0}
    
    def _create_xlsx_formats(self, workbook):
        """Create formats for the Excel report"""
        formats = {
            'title': workbook.add_format({
                'bold': True,
                'font_size': 14,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#EBF2F8',
                'border': 1,
            }),
            'header_center': workbook.add_format({
                'bold': True,
                'font_size': 12,
                'align': 'center',
                'valign': 'vcenter',
            }),
            'subheader': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#F2F2F2',
                'border': 1,
            }),
            'filter_label': workbook.add_format({
                'bold': True,
                'font_size': 10,
                'align': 'right',
            }),
            'filter_text': workbook.add_format({
                'font_size': 10,
                'align': 'left',
            }),
            'table_header': workbook.add_format({
                'bold': True,
                'font_size': 10,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#D9E1F2',
                'border': 1,
            }),
            'account_header': workbook.add_format({
                'bold': True,
                'font_size': 10,
                'align': 'left',
                'valign': 'vcenter',
                'bg_color': '#E6E6E6',
                'border': 1,
            }),
            'currency_header': workbook.add_format({
                'bold': True,
                'font_size': 10,
                'align': 'left',
                'valign': 'vcenter',
                'bg_color': '#E6E6E6',
                'border': 1,
            }),
            'init_balance': workbook.add_format({
                'italic': True,
                'font_size': 10,
                'align': 'left',
                'border': 1,
            }),
            'text': workbook.add_format({
                'font_size': 10,
                'align': 'left',
                'border': 1,
            }),
            'date': workbook.add_format({
                'font_size': 10,
                'align': 'center',
                'border': 1,
                'num_format': 'yyyy-mm-dd',
            }),
            'number': workbook.add_format({
                'font_size': 10,
                'align': 'right',
                'border': 1,
                'num_format': '#,##0.00',
            }),
            'total_label': workbook.add_format({
                'bold': True,
                'font_size': 10,
                'align': 'right',
                'border': 1,
                'bg_color': '#F2F2F2',
            }),
            'total_number': workbook.add_format({
                'bold': True,
                'font_size': 10,
                'align': 'right',
                'border': 1,
                'num_format': '#,##0.00',
                'bg_color': '#F2F2F2',
            }),
            'grand_total_label': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'align': 'right',
                'border': 1,
                'bg_color': '#E6E6E6',
            }),
            'grand_total_number': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'align': 'right',
                'border': 1,
                'num_format': '#,##0.00',
                'bg_color': '#E6E6E6',
            }),
        }
        return formats
    
    def _get_report_data_for_xlsx(self, form_data):
        """Get report data for XLSX export - similar to the PDF report data"""
        # This will mimic the data structure from the report_xlsx model
        report_data = []
        
        # Get accounts based on filter
        account_domain = []
        
        # Account types filter
        account_type_domains = []
        if form_data.get('account_type_asset'):
            account_type_domains.append(('account_type', '=', 'asset_receivable'))
            account_type_domains.append(('account_type', '=', 'asset_cash'))
            account_type_domains.append(('account_type', '=', 'asset_current'))
            account_type_domains.append(('account_type', '=', 'asset_non_current'))
        if form_data.get('account_type_liability'):
            account_type_domains.append(('account_type', '=', 'liability_payable'))
            account_type_domains.append(('account_type', '=', 'liability_current'))
            account_type_domains.append(('account_type', '=', 'liability_non_current'))
        if form_data.get('account_type_equity'):
            account_type_domains.append(('account_type', '=', 'equity'))
        if form_data.get('account_type_income'):
            account_type_domains.append(('account_type', '=', 'income'))
            account_type_domains.append(('account_type', '=', 'income_other'))
        if form_data.get('account_type_expense'):
            account_type_domains.append(('account_type', '=', 'expense'))
            account_type_domains.append(('account_type', '=', 'expense_direct_cost'))
            account_type_domains.append(('account_type', '=', 'expense_depreciation'))
        if form_data.get('account_type_other'):
            account_type_domains.append(('account_type', '=', 'off_balance'))
        
        if account_type_domains:
            # Add OR operators between account type conditions
            # We need to add len(account_type_domains) - 1 '|' operators
            for i in range(len(account_type_domains) - 1):
                account_domain.append('|')
            # Then add all the domain tuples
            account_domain.extend(account_type_domains)
            
        # Add company domain
        account_domain.append(('company_ids', 'in', form_data.get('company_id')))
        
        # Account selection
        if form_data.get('account_ids'):
            account_domain.append(('id', 'in', form_data.get('account_ids')))
        
        accounts = self.env['account.account'].search(account_domain)
        
        # Domain for move lines
        move_domain = [
            ('account_id', 'in', accounts.ids),
            ('date', '>=', form_data.get('date_from')),
            ('date', '<=', form_data.get('date_to'))
        ]
        
        # Target moves
        if form_data.get('target_move') == 'posted':
            move_domain.append(('move_id.state', '=', 'posted'))
        
        # Journal filter
        if form_data.get('journal_ids'):
            move_domain.append(('journal_id', 'in', form_data.get('journal_ids')))
        
        # Get all move lines
        move_lines = self.env['account.move.line'].search(move_domain)
        
        # Process each account
        for account in accounts:
            # Get move lines for this account
            account_lines = move_lines.filtered(lambda l: l.account_id.id == account.id)
            
            # Skip account based on display_account setting
            if form_data.get('display_account') == 'movement' and not account_lines:
                continue
                
            # Get account's initial balance
            init_balance = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
            if form_data.get('show_init_balance'):
                init_balance_domain = [
                    ('account_id', '=', account.id),
                    ('date', '<', form_data.get('date_from'))
                ]
                
                if form_data.get('target_move') == 'posted':
                    init_balance_domain.append(('move_id.state', '=', 'posted'))
                    
                init_balance_lines = self.env['account.move.line'].search(init_balance_domain)
                for line in init_balance_lines:
                    init_balance['debit'] += line.debit
                    init_balance['credit'] += line.credit
                    init_balance['balance'] = init_balance['debit'] - init_balance['credit']
            
            # Skip account based on display_account setting
            if form_data.get('display_account') == 'not_zero' and not account_lines and init_balance['balance'] == 0:
                continue
                
            # Format move lines
            formatted_lines = []
            total_debit = init_balance['debit']
            total_credit = init_balance['credit']
            
            for line in account_lines:
                formatted_line = {
                    'date': line.date,
                    'journal': line.journal_id.code,
                    'account': line.account_id.code,
                    'label': line.name or '',
                    'ref': line.ref or '',
                    'debit': line.debit,
                    'credit': line.credit,
                }
                
                # Partner info
                if line.partner_id:
                    formatted_line['label'] = line.partner_id.name + ': ' + formatted_line['label']
                
                # Currency info
                if line.currency_id and line.currency_id != line.company_currency_id:
                    formatted_line['currency'] = line.currency_id.name
                    formatted_line['amount_currency'] = line.amount_currency
                
                formatted_lines.append(formatted_line)
                total_debit += line.debit
                total_credit += line.credit
            
            # Add account data to report
            account_data = {
                'account_id': account.id,
                'init_balance': init_balance,
                'lines': formatted_lines,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'total_balance': total_debit - total_credit
            }
            
            report_data.append(account_data)
        
        return report_data
    
    def _prepare_report_data(self):
        """Prepare data for the report"""
        self.ensure_one()
        return {
            'ids': self.ids,
            'model': self._name,
            'form': {
                'company_id': self.company_id.id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'target_move': self.target_move,
                'display_account': self.display_account,
                'account_ids': self.account_ids.ids if self.account_ids else [],
                'journal_ids': self.journal_ids.ids if self.journal_ids else [],
                'currency_ids': self.currency_ids.ids if self.currency_ids else [],
                'account_type_asset': self.account_type_asset,
                'account_type_liability': self.account_type_liability,
                'account_type_equity': self.account_type_equity,
                'account_type_income': self.account_type_income,
                'account_type_expense': self.account_type_expense,
                'account_type_other': self.account_type_other,
                'show_init_balance': self.show_init_balance,
            }
        }
