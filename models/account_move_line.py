# -*- coding: utf-8 -*-
# Part of DigitsCode. See LICENSE file for full copyright and licensing details.
# © 2025 DigitsCode (Digital Integrated Transformation Solutions)
# Developer: DigitsCode <info@digitscode.com>
# Website: https://www.digitscode.com
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def get_currency_balance(self, currency_id):
        """Get the balance in a specific currency"""
        self.ensure_one()
        if self.currency_id.id == currency_id:
            return self.amount_currency
        elif self.company_currency_id.id == currency_id:
            return self.balance
        else:
            # Convert from company currency to target currency
            currency = self.env['res.currency'].browse(currency_id)
            company_currency = self.company_currency_id
            date = self.date or fields.Date.context_today(self)
            return company_currency._convert(
                self.balance, currency, self.company_id, date
            )
