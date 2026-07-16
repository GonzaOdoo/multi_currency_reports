# -*- coding: utf-8 -*-
# Part of DigitsCode. See LICENSE file for full copyright and licensing details.
# © 2025 DigitsCode (Digital Integrated Transformation Solutions)
# Developer: DigitsCode <info@digitscode.com>
# Website: https://www.digitscode.com
from odoo import api, models
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class MultiCurrencyGeneralLedgerReport(models.AbstractModel):
    _name = 'report.digits_multi_currency_general_ledger.mcgl_pdf'
    _description = 'Multi Currency General Ledger PDF Report'
    
    @api.model
    def _get_report_values(self, docids, data=None):
        """Get values for the report"""
        _logger.debug("PDF Report _get_report_values called with data: %s", data)
        
        if not data:
            _logger.warning("No data received for report")
            return {
                'doc_ids': docids,
                'doc_model': 'multi.currency.general.ledger.wizard',
                'docs': self.env['multi.currency.general.ledger.wizard'].browse(docids),
                'results': {},
                'currencies': [],
                'form': {},
            }
        
        # Process the report data directly
        form = data.get('form', {})
        
        # Get accounts
        account_ids = form.get('account_ids', [])
        if account_ids:
            accounts = self.env['account.account'].browse(account_ids)
        else:
            # Get accounts based on selected types
            company_id = form.get('company_id')
            
            # Build account type filters
            account_type_filters = []
            if form.get('account_type_asset'):
                account_type_filters.extend(['asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_fixed'])
            if form.get('account_type_liability'):
                account_type_filters.extend(['liability_payable', 'liability_current', 'liability_non_current'])
            if form.get('account_type_equity'):
                account_type_filters.append('equity')
            if form.get('account_type_income'):
                account_type_filters.append('income')
            if form.get('account_type_expense'):
                account_type_filters.append('expense')
            if form.get('account_type_other'):
                account_type_filters.append('off_balance')
            
            # Use helper method to get company accounts
            accounts = self.env['multi.currency.general.ledger']._get_company_accounts(
                company_id, account_type_filters if account_type_filters else None)
            
            _logger.debug("Found %s accounts for company %s", len(accounts), company_id)
        
        # Get currencies
        currency_ids = form.get('currency_ids', [])
        currencies = self.env['res.currency'].browse(currency_ids) if currency_ids else self.env['res.currency'].search([])
        
        # Get journals
        journal_ids = form.get('journal_ids', [])
        journals = self.env['account.journal'].browse(journal_ids) if journal_ids else self.env['account.journal']
        
        # Get other parameters
        company_id = form.get('company_id')
        date_from = form.get('date_from')
        date_to = form.get('date_to')
        target_move = form.get('target_move', 'posted')
        display_account = form.get('display_account', 'movement')
        show_init_balance = form.get('show_init_balance', True)
        
        # Convert string dates to datetime objects if needed
        if isinstance(date_from, str):
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except Exception as e:
                _logger.error("Error converting date_from: %s", e)
        
        if isinstance(date_to, str):
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except Exception as e:
                _logger.error("Error converting date_to: %s", e)
        
        # Process accounts and currencies
        results = {}
        for account in accounts:
            results[account.id] = {}
            for currency in currencies:
                # Get initial balance
                init_balance = 0.0
                if show_init_balance and date_from:
                    init_balance = self._get_initial_balance(account, currency, journals, date_from, target_move, company_id)
                
                # Get move lines
                lines = self._get_move_lines(account, currency, journals, date_from, date_to, target_move, company_id)
                
                # Calculate totals
                total_debit = sum(line.get('debit', 0.0) for line in lines)
                total_credit = sum(line.get('credit', 0.0) for line in lines)
                balance = init_balance + sum(line.get('balance', 0.0) for line in lines)
                
                # Skip accounts based on display_account setting
                if display_account == 'movement' and not lines and init_balance == 0.0:
                    continue
                if display_account == 'not_zero' and init_balance == 0.0 and not lines:
                    continue
                
                # Add to results
                results[account.id][currency.id] = {
                    'init_balance': init_balance,
                    'lines': lines,
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'balance': balance,
                }
        
        # Return report values
        return {
            'doc_ids': docids,
            'doc_model': 'multi.currency.general.ledger.wizard',
            'docs': accounts,
            'results': results,
            'currencies': currencies,
            'form': form,
        }
    
    def _get_initial_balance(self, account, currency, journals, date_from, target_move, company_id):
        """Calculate initial balance for an account in a specific currency"""
        company = self.env['res.company'].browse(company_id)
        company_currency = company.currency_id
        
        try:
            # For company currency use balance field
            # For foreign currency use amount_currency field with currency filter
            if currency.id == company_currency.id:
                query = """
                    SELECT COALESCE(SUM(aml.balance), 0) as initial_balance
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
                    SELECT COALESCE(SUM(aml.amount_currency), 0) as initial_balance
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
            if journals and journals.ids:
                query += " AND aml.journal_id IN %s"
                params.append(tuple(journals.ids))
            
            # Add target move filter
            if target_move == 'posted':
                query += " AND aml.parent_state = 'posted'"
            
            _logger.debug("Initial balance query: %s, params: %s", query, params)
            
            self.env.cr.execute(query, params)
            result = self.env.cr.dictfetchone()
            return result['initial_balance'] if result else 0.0
        except Exception as e:
            _logger.error("Error calculating initial balance: %s", e)
            return 0.0
    
    def _get_move_lines(self, account, currency, journals, date_from, date_to, target_move, company_id):
        """Get move lines for an account in a specific currency within date range"""
        company = self.env['res.company'].browse(company_id)
        company_currency = company.currency_id
        
        # Build domain for move lines search
        domain = [
            ('account_id', '=', account.id),
            ('move_id.company_id', '=', company_id),
        ]
        
        # Add journal filter if specified
        if journals and journals.ids:
            domain.append(('journal_id', 'in', journals.ids))
        
        # Add date filters
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
        
        _logger.debug("Move lines search domain: %s", domain)
        
        try:
            # Search for move lines
            move_lines = self.env['account.move.line'].search(domain, order='date, move_id, id')
            
            _logger.debug("Found %s move lines for account %s and currency %s", 
                        len(move_lines), account.name, currency.name)
            
            # Process move lines
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
                    'journal_name': line.journal_id.name,
                    'ref': line.move_id.ref or '',
                    'name': line.name or '',
                    'partner_id': line.partner_id.id if line.partner_id else False,
                    'partner_name': line.partner_id.name if line.partner_id else '',
                    'debit': debit,
                    'credit': credit,
                    'balance': balance,
                })
            
            return result
            
        except Exception as e:
            _logger.error("Error retrieving move lines: %s", e)
            return []
