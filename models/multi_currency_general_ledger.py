# -*- coding: utf-8 -*-
# Part of DigitsCode. See LICENSE file for full copyright and licensing details.
# © 2025 DigitsCode (Digital Integrated Transformation Solutions)
# Developer: DigitsCode <info@digitscode.com>
# Website: https://www.digitscode.com
from odoo import models, api, _
from datetime import datetime
import json
import logging

_logger = logging.getLogger(__name__)


class MultiCurrencyGeneralLedger(models.AbstractModel):
    _name = 'multi.currency.general.ledger'
    _description = 'Multi Currency General Ledger Report'

    def _get_company_accounts(self, company_id, account_type_filters=None):
        """Get accounts for a specific company without direct company_id filtering"""
        # Get all accounts first
        domain = []
        
        # Add account type filters if provided
        if account_type_filters:
            domain.append(('account_type', 'in', account_type_filters))
            
        all_accounts = self.env['account.account'].search(domain)
        
        # Now filter the accounts that belong to this company
        # This is done in Python to avoid ORM issues with company_id field
        company = self.env['res.company'].browse(company_id)
        company_accounts = self.env['account.account']
        
        for account in all_accounts:
            # Check if account belongs to company using various possible fields
            belongs_to_company = False
            
            # Try different ways to check company association
            if hasattr(account, 'company_id') and account.company_id and account.company_id.id == company_id:
                belongs_to_company = True
            elif hasattr(account, 'company_ids') and company_id in account.company_ids.ids:
                belongs_to_company = True
            
            if belongs_to_company:
                company_accounts += account
                
        return company_accounts

    @api.model
    def debug_account_fields(self):
        """Debug method to check account.account fields"""
        # Get a sample account
        account = self.env['account.account'].search([], limit=1)
        if account:
            _logger.debug("Account fields: %s", account.fields_get().keys())
            # Check if company_id exists
            if hasattr(account, 'company_id'):
                _logger.debug("account.company_id exists: %s", account.company_id.name)
            # Check if company_ids exists
            if hasattr(account, 'company_ids'):
                _logger.debug("account.company_ids exists: %s", account.company_ids.mapped('name'))
        return True

    @api.model
    def _get_report_values(self, docids, data=None):
        # Debug account fields
        self.debug_account_fields()

        """Prepare the data for rendering the report template"""
        _logger.debug("Report data received: %s", data)

        
        if not data:
            _logger.warning("No data received for report")
            return {}
        
        form = data.get('form', {})
        _logger.debug("Report form data: %s", form)
        
        # Get selected accounts or all accounts if none selected
        if form.get('account_ids'):
            account_ids = form['account_ids']
            accounts = self.env['account.account'].browse(account_ids)
        else:
            # Get accounts based on account types selected
            domain = []
            
            account_type_asset = form.get('account_type_asset', False)
            account_type_liability = form.get('account_type_liability', False)
            account_type_equity = form.get('account_type_equity', False)
            account_type_income = form.get('account_type_income', False)
            account_type_expense = form.get('account_type_expense', False)
            account_type_other = form.get('account_type_other', False)
            
            # If no type is selected, default to all types
            if not any([account_type_asset, account_type_liability, account_type_equity,
                       account_type_income, account_type_expense, account_type_other]):
                account_type_asset = True
                account_type_liability = True
                account_type_equity = True
                account_type_income = True
                account_type_expense = True
            
            # Count selected types to determine number of OR operators needed
            selected_types = []
            if account_type_asset:
                selected_types.append(('account_type', 'like', 'asset'))
            if account_type_liability:
                selected_types.append(('account_type', 'like', 'liability'))
            if account_type_equity:
                selected_types.append(('account_type', 'like', 'equity'))
            if account_type_income:
                selected_types.append(('account_type', 'like', 'income'))
            if account_type_expense:
                selected_types.append(('account_type', 'like', 'expense'))
            if account_type_other:
                selected_types.append(('account_type', 'like', 'off_balance'))
            
            # Construct domain with proper OR operators
            if len(selected_types) > 1:
                # Add n-1 OR operators for n conditions
                domain.extend(['|'] * (len(selected_types) - 1))
                # Add all conditions
                domain.extend(selected_types)
            elif len(selected_types) == 1:
                domain.extend(selected_types)
            
            _logger.debug("Account search domain: %s", domain)
            accounts = self.env['account.account'].search(domain)
            
        _logger.info("Selected accounts: %s", accounts)
        
        # Get selected journals or all journals if none selected
        if form.get('journal_ids'):
            journal_ids = form['journal_ids']
            journals = self.env['account.journal'].browse(journal_ids)
        else:
            journals = self.env['account.journal'].search([])
            
        _logger.info("Selected journals: %s", journals)
        
        # Get selected currencies or all currencies if none selected
        if form.get('currency_ids'):
            currency_ids = form['currency_ids']
            currencies = self.env['res.currency'].browse(currency_ids)
        else:
            currencies = self.env['res.currency'].search([])
            
        _logger.info("Selected currencies: %s", currencies)
        
        # Prepare report data
        results = {}
        company_id = form.get('company_id', self.env.company.id)
        company = self.env['res.company'].browse(company_id)
        
        # Get parameters
        date_from = form.get('date_from', False)
        date_to = form.get('date_to', datetime.now().date())
        target_move = form.get('target_move', 'posted')
        display_account = form.get('display_account', 'movement')
        show_init_balance = form.get('show_init_balance', True)
        
        _logger.info("Report parameters: from=%s, to=%s, target_move=%s, display_account=%s", 
                    date_from, date_to, target_move, display_account)
        
        for account in accounts:
            results[account.id] = {}
            for currency in currencies:
                results[account.id][currency.id] = {
                    'debit': 0.0,
                    'credit': 0.0,
                    'balance': 0.0,
                    'init_balance': 0.0,
                    'lines': []
                }
                
                # Compute initial balance if needed
                if date_from and show_init_balance:
                    init_balance = self._get_initial_balance(
                        account, currency, journals, date_from, target_move, company_id
                    )
                    results[account.id][currency.id]['init_balance'] = init_balance
                
                # Get move lines
                move_lines = self._get_move_lines(
                    account, currency, journals, date_from, date_to, 
                    target_move, company_id
                )
                
                _logger.info("Account %s, Currency %s: found %s move lines", 
                           account.name, currency.name, len(move_lines))
                
                # Process move lines
                for line in move_lines:
                    results[account.id][currency.id]['lines'].append(line)
                    results[account.id][currency.id]['debit'] += line['debit']
                    results[account.id][currency.id]['credit'] += line['credit']
                    results[account.id][currency.id]['balance'] += line['balance']
        
        return {
            'doc_ids': accounts.ids,
            'doc_model': 'account.account',
            'docs': accounts,
            'company': company,
            'currencies': currencies,
            'journals': journals,
            'form': form,
            'results': results,
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
                    AND aml.company_id = %s
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
            ('company_id', 'in', [company_id]),
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
            
            # If we found any move lines, log the first one as sample
            if move_lines:
                sample = move_lines[0]
                _logger.debug("Sample move line - ID: %s, Date: %s, Debit: %s, Credit: %s, Amount Currency: %s, Currency: %s", 
                           sample.id, sample.date, sample.debit, sample.credit, 
                           sample.amount_currency, sample.currency_id.name if sample.currency_id else "None")
            
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
                    debit = abs(line.amount_currency) if line.amount_currency > 0 else 0.0
                    credit = abs(line.amount_currency) if line.amount_currency < 0 else 0.0
                    balance = line.amount_currency
                
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
