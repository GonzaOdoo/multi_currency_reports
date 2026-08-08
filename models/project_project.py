from collections import defaultdict
import json

from odoo import fields, models, _, api
from odoo.fields import Domain
import logging

_logger = logging.getLogger(__name__)
class ProjectProject(models.Model):
    _inherit = "project.project"

    total_budget_amount = fields.Monetary('Total planned amount', compute='_compute_budget', default=0, export_string_translation=False)
    total_budget_progress = fields.Float("Budget Spent", compute="_compute_budget", export_string_translation=False)
    display_currency_id = fields.Many2one(
        'res.currency',
        string='Display Currency',
        default=lambda self: self.env.company.currency_id,
        tracking=True,
        help="Currency used to display financial figures (profitability, budget) on this project's dashboard. "
             "Amounts are converted from their original currency using the exchange rate on each transaction date.",
    )

    @api.depends('display_currency_id')
    @api.depends_context('company')
    @api.depends('company_id')
    def _compute_currency_id(self):
        super()._compute_currency_id()
        for project in self:
            if project.display_currency_id:
                project.currency_id = project.display_currency_id
                
    def _get_budget_analytic_account_domain(self):
        return Domain.OR([
            [(account.plan_id._column_name(), '=', account.id)] for account in self.account_id
        ])

    def _compute_budget(self):
        budget_items = self.env['budget.line'].sudo()._read_group(
            Domain.AND([
                self._get_budget_analytic_account_domain(),
                [('budget_analytic_id.state', 'in', ['confirmed', 'done'])],
            ]),
            groupby=['account_id', 'budget_analytic_id'],
            aggregates=['budget_amount:sum', 'achieved_amount:sum'],
        )
        budget_items_by_account_analytic = defaultdict(lambda: {
            'budget_amount': 0,
            'budget_amount_for_progress': 0,
            'achieved_amount_for_progress': 0,
        })
        today = fields.Date.context_today(self)
        # Convertimos por proyecto, porque cada uno puede tener su propia display_currency_id
        for project in self:
            project_currency = project.currency_id
            company = project.company_id or self.env.company
            for analytic_account, budget_analytic_id, budget_amount_sum, achieved_amount_sum in budget_items:
                if analytic_account.id != project.account_id.id:
                    continue
                budget_currency = budget_analytic_id.currency_id
                if budget_currency != project_currency:
                    budget_amount_sum = budget_currency._convert(budget_amount_sum, project_currency, company, today)
                    achieved_amount_sum = budget_currency._convert(achieved_amount_sum, project_currency, company, today)
                type_factor = -1 if budget_analytic_id.budget_type == 'expense' else 1
                budget_items_by_account_analytic[analytic_account.id]["budget_amount"] += budget_amount_sum
                budget_items_by_account_analytic[analytic_account.id]["budget_amount_for_progress"] += budget_amount_sum * type_factor
                budget_items_by_account_analytic[analytic_account.id]["achieved_amount_for_progress"] += achieved_amount_sum * type_factor
    
        for project in self:
            total_budget_amount = budget_items_by_account_analytic[project.account_id.id]['budget_amount']
            total_budget_amount_fp = budget_items_by_account_analytic[project.account_id.id]['budget_amount_for_progress']
            total_achieved_amount_fp = budget_items_by_account_analytic[project.account_id.id]['achieved_amount_for_progress']
            project.total_budget_progress = total_budget_amount_fp and (total_achieved_amount_fp - total_budget_amount_fp) / abs(total_budget_amount_fp)
            project.total_budget_amount = total_budget_amount

    def action_view_budget_lines(self, domain=None):
        self.ensure_one()
        budget_lines = self.env['budget.line'].search(Domain.AND([
            [(self.account_id.plan_id._column_name(), '=', self.account_id.id), ('budget_analytic_id.state', 'in', ['confirmed', 'done'])],
            domain or [],
        ]))
        return {
            "type": "ir.actions.act_window",
            "res_model": "budget.analytic",
            "res_id": budget_lines.budget_analytic_id.id,
            'context': {'create': False},
            "name": _("Budget Items"),
            'view_mode': 'form',
        }

    def get_panel_data(self):
        panel_data = super().get_panel_data()
        panel_data['account_id'] = self.account_id.id
        panel_data['budget_items'] = self._get_budget_items()
        panel_data['show_budget_items'] = bool(self.account_id)
        return panel_data

    def _get_budget_items(self, with_action=True):
        self.ensure_one()
        if not self.account_id:
            return
        budget_items_domain = self._get_budget_items_domain()
        budget_lines = self.env['budget.line'].sudo()._read_group(
            budget_items_domain,
            ['budget_analytic_id', 'company_id'],
            ['budget_amount:sum', 'achieved_amount:sum', 'id:array_agg'],
        )
        has_company_access = False
        for line in budget_lines:
            if line[1].id in self.env.context.get('allowed_company_ids', []):
                has_company_access = True
                break
    
        company = self.company_id or self.env.company
        display_currency = self.currency_id  # moneda de visualización del proyecto
        today = fields.Date.context_today(self)
    
        total_allocated = total_spent = 0.0
        total_allocated_for_progress = total_spent_for_progress = 0.0
        can_see_budget_items = with_action and has_company_access and (
            self.env.user.has_group('account.group_account_readonly')
            or self.env.user.has_group('analytic.group_analytic_accounting')
        )
        budget_data_per_budget = defaultdict(
            lambda: {
                'allocated': 0,
                'spent': 0,
                'budget_type': False,
                **({
                    'ids': [],
                    'budgets': [],
                } if can_see_budget_items else {})
            }
        )
    
        for budget_analytic, _dummy, allocated, spent, ids in budget_lines:
            budget_currency = budget_analytic.currency_id
            # Convertimos a la moneda de visualización del proyecto, sea cual sea
            # la moneda propia en la que se cargó este presupuesto
            if budget_currency != display_currency:
                allocated_dc = budget_currency._convert(allocated, display_currency, company, today)
                spent_dc = budget_currency._convert(spent, display_currency, company, today)
            else:
                allocated_dc = allocated
                spent_dc = spent
    
            budget_data = budget_data_per_budget[budget_analytic]
            budget_data['id'] = budget_analytic.id
            budget_data['name'] = budget_analytic.display_name
            budget_data['currency_id'] = display_currency.id
            budget_data['allocated'] += allocated_dc
            budget_data['spent'] += spent_dc
            budget_data['budget_type'] = budget_analytic.budget_type
    
            total_allocated += -allocated_dc if budget_analytic.budget_type == 'expense' else allocated_dc
            total_spent += -spent_dc if budget_analytic.budget_type == 'expense' else spent_dc
            total_allocated_for_progress += allocated_dc * -1 if budget_analytic.budget_type == 'expense' else allocated_dc
            total_spent_for_progress += spent_dc * -1 if budget_analytic.budget_type == 'expense' else spent_dc
    
            if can_see_budget_items:
                budget_item = {
                    'id': budget_analytic.id,
                    'name': budget_analytic.display_name,
                    'currency_id': display_currency.id,
                    'allocated': allocated_dc,
                    'spent': spent_dc,
                    'budget_type': budget_analytic.budget_type,
                    'progress': allocated_dc and (spent_dc - allocated_dc) / abs(allocated_dc) * (-1 if budget_analytic.budget_type == 'expense' else 1),
                }
                budget_data['budgets'].append(budget_item)
                budget_data['ids'] += ids
            else:
                budget_data['budgets'] = []
    
        for budget_data in budget_data_per_budget.values():
            budget_data['progress'] = budget_data['allocated'] and (budget_data['spent'] - budget_data['allocated']) / abs(budget_data['allocated']) \
                * (-1 if budget_data['budget_type'] == 'expense' else 1)
    
        budget_data_per_budget = list(budget_data_per_budget.values())
        if can_see_budget_items:
            for budget_data in budget_data_per_budget:
                if len(budget_data['budgets']) == 1:
                    budget_data['budgets'].clear()
                budget_data['action'] = {
                    'name': 'action_view_budget_lines',
                    'type': 'object',
                    'args': json.dumps([[('id', 'in', budget_data.pop('ids'))]]),
                }
    
        can_add_budget = with_action and self.env.user.has_group('account.group_account_user')
        budget_items = {
            'data': budget_data_per_budget,
            'currency_id': display_currency.id,
            'total': {
                'allocated': total_allocated,
                'spent': total_spent,
                'progress': (total_spent_for_progress - total_allocated_for_progress) / abs(total_allocated_for_progress) if total_allocated_for_progress else 0,
            },
            'can_add_budget': can_add_budget,
        }
        if can_add_budget:
            budget_items['form_view_id'] = self.env.ref('project_account_budget.view_budget_analytic_form_dialog').id
            budget_items['company_id'] = self.company_id.id or self.env.company.id
        return budget_items
        
    def _get_budget_items_domain(self):
        self.ensure_one()
        return [
            (self.account_id.plan_id._column_name(), '=', self.account_id.id),
            ('budget_analytic_id', '!=', False),
            ('budget_analytic_id.state', 'in', ['confirmed', 'done']),
        ]


    def _get_revenues_items_from_sol(self, domain=None, with_action=True):
        company = self.company_id or self.env.company
        project_currency = self.currency_id
        today = fields.Date.context_today(self)
    
        sale_line_read_group = self.env['sale.order.line'].sudo()._read_group(
            self._get_profitability_sale_order_items_domain(domain),
            ['currency_id', 'product_id', 'is_downpayment', 'order_id'],
            ['id:array_agg', 'untaxed_amount_to_invoice:sum', 'untaxed_amount_invoiced:sum'],
        )
        display_sol_action = with_action and len(self) == 1 and self.env.user.has_group('sales_team.group_sale_salesman')
        revenues_dict = {}
        total_to_invoice = total_invoiced = 0.0
        data = []
        sequence_per_invoice_type = self._get_profitability_sequence_per_invoice_type()
        if sale_line_read_group:
            sols_per_product = defaultdict(lambda: [0.0, 0.0, []])
            downpayment_amount_invoiced = 0
            downpayment_sol_ids = []
            for currency, product, is_downpayment, order, sol_ids, untaxed_amount_to_invoice, untaxed_amount_invoiced in sale_line_read_group:
                conv_date = order.date_order.date() if order.date_order else today
                if is_downpayment:
                    downpayment_amount_invoiced += currency._convert(
                        untaxed_amount_invoiced, project_currency, company, conv_date, round=False)
                    downpayment_sol_ids += sol_ids
                else:
                    sols_per_product[product.id][0] += currency._convert(
                        untaxed_amount_to_invoice, project_currency, company, conv_date)
                    sols_per_product[product.id][1] += currency._convert(
                        untaxed_amount_invoiced, project_currency, company, conv_date)
                    sols_per_product[product.id][2] += sol_ids
    
            if downpayment_amount_invoiced:
                downpayments_data = {
                    'id': 'downpayments',
                    'sequence': sequence_per_invoice_type['downpayments'],
                    'invoiced': downpayment_amount_invoiced,
                    'to_invoice': -downpayment_amount_invoiced,
                }
                if with_action and (
                    self.env.user.has_group('sales_team.group_sale_salesman_all_leads,')
                    or self.env.user.has_group('account.group_account_invoice,')
                    or self.env.user.has_group('account.group_account_readonly')
                ):
                    invoices = self.env['account.move'].search([('line_ids.sale_line_ids', 'in', downpayment_sol_ids)])
                    args = ['downpayments', [('id', 'in', invoices.ids)]]
                    if len(invoices) == 1:
                        args.append(invoices.id)
                    downpayments_data['action'] = {
                        'name': 'action_profitability_items',
                        'type': 'object',
                        'args': json.dumps(args),
                    }
                data += [downpayments_data]
                total_invoiced += downpayment_amount_invoiced
                total_to_invoice -= downpayment_amount_invoiced
    
            product_read_group = self.env['product.product'].sudo()._read_group(
                [('id', 'in', list(sols_per_product))],
                ['invoice_policy', 'service_type', 'type'],
                ['id:array_agg'],
            )
            service_policy_to_invoice_type = self._get_service_policy_to_invoice_type()
            general_to_service_map = self.env['product.template']._get_general_to_service_map()
            for invoice_policy, service_type, type_, product_ids in product_read_group:
                service_policy = None
                if type_ == 'service':
                    service_policy = general_to_service_map.get(
                        (invoice_policy, service_type),
                        'ordered_prepaid')
                for product_id, (amount_to_invoice, amount_invoiced, sol_ids) in sols_per_product.items():
                    if product_id in product_ids:
                        invoice_type = service_policy_to_invoice_type.get(service_policy, 'materials')
                        revenue = revenues_dict.setdefault(invoice_type, {'invoiced': 0.0, 'to_invoice': 0.0})
                        revenue['to_invoice'] += amount_to_invoice
                        total_to_invoice += amount_to_invoice
                        revenue['invoiced'] += amount_invoiced
                        total_invoiced += amount_invoiced
                        if display_sol_action and invoice_type in ['service_revenues', 'materials']:
                            revenue.setdefault('record_ids', []).extend(sol_ids)
    
            if display_sol_action:
                section_name = 'materials'
                materials = revenues_dict.get(section_name, {})
                sale_order_items = self.env['sale.order.line'] \
                    .browse(materials.pop('record_ids', [])) \
                    ._filtered_access('read')
                if sale_order_items:
                    args = [section_name, [('id', 'in', sale_order_items.ids)]]
                    if len(sale_order_items) == 1:
                        args.append(sale_order_items.id)
                    action_params = {
                        'name': 'action_profitability_items',
                        'type': 'object',
                        'args': json.dumps(args),
                    }
                    if len(sale_order_items) == 1:
                        action_params['res_id'] = sale_order_items.id
                    materials['action'] = action_params
        sequence_per_invoice_type = self._get_profitability_sequence_per_invoice_type()
        data += [{
            'id': invoice_type,
            'sequence': sequence_per_invoice_type[invoice_type],
            **vals,
        } for invoice_type, vals in revenues_dict.items()]
        return {
            'data': data,
            'total': {'to_invoice': total_to_invoice, 'invoiced': total_invoiced},
        }

    def _get_expenses_profitability_items(self, with_action=True):
        if not self.account_id:
            return {}
        can_see_expense = with_action and self.env.user.has_group('hr_expense.group_hr_expense_team_approver')
    
        company = self.company_id or self.env.company
        project_currency = self.currency_id
        today = fields.Date.context_today(self)
    
        expenses_read_group = self.env['hr.expense']._read_group(
            [
                ('state', 'in', ['posted', 'in_payment', 'paid']),
                ('analytic_distribution', 'in', self.account_id.ids),
            ],
            groupby=['currency_id', 'date'],
            aggregates=['id:array_agg', 'untaxed_amount_currency:sum'],
        )
        if not expenses_read_group:
            return {}
        expense_ids = []
        amount_billed = 0.0
        for currency, date, ids, untaxed_amount_currency_sum in expenses_read_group:
            if can_see_expense:
                expense_ids.extend(ids)
            amount_billed += currency._convert(
                from_amount=untaxed_amount_currency_sum,
                to_currency=project_currency,
                company=company,
                date=date or today,
            )
    
        section_id = 'expenses'
        expense_profitability_items = {
            'costs': {'id': section_id, 'sequence': self._get_profitability_sequence_per_invoice_type()[section_id], 'billed': -amount_billed, 'to_bill': 0.0},
        }
        if can_see_expense:
            args = [section_id, [('id', 'in', expense_ids)]]
            if len(expense_ids) == 1:
                args.append(expense_ids[0])
            action = {'name': 'action_profitability_items', 'type': 'object', 'args': json.dumps(args)}
            expense_profitability_items['costs']['action'] = action
        return expense_profitability_items

    def _get_profitability_items(self, with_action=True):
        profitability_items = super()._get_profitability_items(with_action)
        if self.account_id:
            company = self.company_id or self.env.company
            today = fields.Date.context_today(self)

            purchase_lines = self.env['purchase.order.line'].sudo().search([
                ('analytic_distribution', 'in', self.account_id.ids),
                ('state', 'in', 'purchase')
            ])
            purchase_order_line_invoice_line_ids = self._get_already_included_profitability_invoice_line_ids()
            with_action = with_action and (
                self.env.user.has_group('purchase.group_purchase_user')
                or self.env.user.has_group('account.group_account_invoice')
                or self.env.user.has_group('account.group_account_readonly')
            )
            if purchase_lines:
                amount_invoiced = amount_to_invoice = 0.0
                purchase_order_line_invoice_line_ids.extend(purchase_lines.invoice_lines.ids)
                for purchase_line in purchase_lines:
                    po_date = purchase_line.order_id.date_approve or purchase_line.order_id.date_order
                    po_date = po_date.date() if po_date else today
                    price_subtotal = purchase_line.currency_id._convert(
                        purchase_line.price_subtotal, self.currency_id, company, po_date)
                    # an analytic account can appear several time in an analytic distribution with different repartition percentage
                    analytic_contribution = sum(
                        percentage for ids, percentage in purchase_line.analytic_distribution.items()
                        if str(self.account_id.id) in ids.split(',')
                    ) / 100.
                    purchase_line_amount_to_invoice = price_subtotal * analytic_contribution
                    invoice_lines = purchase_line.invoice_lines.filtered(
                        lambda l:
                        l.parent_state != 'cancel'
                        and l.analytic_distribution
                        and any(
                            str(self.account_id.id) in key.split(',')
                            for key in l.analytic_distribution
                        )
                    )
                    if invoice_lines:
                        # Calculate total invoiced amount (posted + draft, excluding refunds for unbilled calculation)
                        total_invoiced_amount = 0.0
                        for line in invoice_lines:
                            line_date = line.date or today
                            price_subtotal = line.currency_id._convert(
                                line.price_subtotal, self.currency_id, company, line_date)
                            if not line.analytic_distribution:
                                continue
                            # an analytic account can appear several time in an analytic distribution with different repartition percentage
                            analytic_contribution = sum(
                                percentage for ids, percentage in line.analytic_distribution.items()
                                if str(self.account_id.id) in ids.split(',')
                            ) / 100.
                            cost = price_subtotal * analytic_contribution * (-1 if line.is_refund else 1)
                            # Only count non-refund invoices for unbilled calculation
                            if not line.is_refund:
                                total_invoiced_amount += cost
                            if line.parent_state == 'posted':
                                amount_invoiced -= cost
                            else:
                                amount_to_invoice -= cost
                        # Calculate the unbilled portion: PO amount - total invoiced amount (non-refunds only)
                        amount_to_invoice -= purchase_line_amount_to_invoice - total_invoiced_amount
                    else:
                        amount_to_invoice -= purchase_line_amount_to_invoice

                costs = profitability_items['costs']
                section_id = 'purchase_order'
                purchase_order_costs = {'id': section_id, 'sequence': self._get_profitability_sequence_per_invoice_type()[section_id], 'billed': amount_invoiced, 'to_bill': amount_to_invoice}
                if with_action:
                    purchase_order = purchase_lines.order_id
                    args = [section_id, [('id', 'in', purchase_order.ids)]]
                    if len(purchase_order) == 1:
                        args.append(purchase_order.id)
                    action = {'name': 'action_profitability_items', 'type': 'object', 'args': json.dumps(args)}
                    purchase_order_costs['action'] = action
                costs['data'].append(purchase_order_costs)
                costs['total']['billed'] += amount_invoiced
                costs['total']['to_bill'] += amount_to_invoice
            domain = [
                ('move_id.move_type', 'in', ['in_invoice', 'in_refund']),
                ('parent_state', 'in', ['draft', 'posted']),
                ('price_subtotal', '!=', 0),
                ('id', 'not in', purchase_order_line_invoice_line_ids),
            ]
            self._get_costs_items_from_purchase(domain, profitability_items, with_action=with_action)
        return profitability_items