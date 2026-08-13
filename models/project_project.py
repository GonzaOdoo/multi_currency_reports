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
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
        tracking=True,
        help="Currency used to display financial figures (profitability, budget) on this project's dashboard. "
             "Amounts are converted from their original currency using the exchange rate on each transaction date.",
    )
    purchase_orders_count = fields.Integer('# Purchase Orders', compute='_compute_purchase_orders_count', groups='purchase.group_purchase_user', export_string_translation=False)

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

    def _compute_purchase_orders_count(self):
        purchase_orders_per_project = dict(
            self.env['purchase.order']._read_group(
                domain=[
                    ('project_id', 'in', self.ids),
                    ('order_line', '!=', False),
                ],
                groupby=['project_id'],
                aggregates=['id:array_agg'],
            )
        )
        purchase_orders_count_per_project_from_lines = dict(
            self.env['purchase.order.line']._read_group(
                domain=[
                    ('order_id', 'not in', [order_id for values in purchase_orders_per_project.values() for order_id in values]),
                    ('analytic_distribution', 'in', self.account_id.ids),
                ],
                groupby=['analytic_distribution'],
                aggregates=['__count'],
            )
        )

        projects_no_account = self.filtered(lambda project: not project.account_id)
        for project in projects_no_account:
            project.purchase_orders_count = len(purchase_orders_per_project.get(project, []))

        purchase_orders_per_project = {project.account_id.id: len(orders) for project, orders in purchase_orders_per_project.items()}
        for project in (self - projects_no_account):
            project.purchase_orders_count = purchase_orders_per_project.get(project.account_id.id, 0) + purchase_orders_count_per_project_from_lines.get(project.account_id.id, 0)

    # ----------------------------
    #  Actions
    # ----------------------------

    def action_open_project_purchase_orders(self):
        purchase_orders = self.env['purchase.order.line'].search([
            '|',
                ('analytic_distribution', 'in', self.account_id.ids),
                ('order_id.project_id', '=', self.id),
        ]).order_id
        action_window = {
            'name': self.env._('Purchase Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'views': [
                [False, 'list'], [self.env.ref('purchase.purchase_order_view_kanban_without_dashboard').id, 'kanban'],
                [False, 'form'], [False, 'calendar'], [False, 'pivot'], [False, 'graph'], [False, 'activity'],
            ],
            'domain': [('id', 'in', purchase_orders.ids)],
            'context': {
                'default_project_id': self.id,
            },
            'help': "<p class='o_view_nocontent_smiling_face'>%s</p><p>%s</p>" % (
                _("No purchase order found. Let's create one."),
                _("Once you ordered your products from your supplier, confirm your request for quotation and it will turn "
                    "into a purchase order."),
            ),
        }
        if len(purchase_orders) == 1 and not self.env.context.get('from_embedded_action'):
            action_window['views'] = [[False, 'form']]
            action_window['res_id'] = purchase_orders.id
        return action_window

    def action_profitability_items(self, section_name, domain=None, res_id=False):
        if section_name == 'purchase_order':
            action = {
                'name': self.env._('Purchase Orders'),
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.order',
                'views': [[False, 'list'], [False, 'form']],
                'domain': domain,
                'context': {
                    'create': False,
                    'edit': False,
                },
            }
            if res_id:
                action['res_id'] = res_id
                if 'views' in action:
                    action['views'] = [
                        (view_id, view_type)
                        for view_id, view_type in action['views']
                        if view_type == 'form'
                    ] or [False, 'form']
                action['view_mode'] = 'form'
            return action
        return super().action_profitability_items(section_name, domain, res_id)

    # ----------------------------
    #  Project Updates
    # ----------------------------

    def _get_stat_buttons(self):
        buttons = super()._get_stat_buttons()
        if self.env.user.has_group('purchase.group_purchase_user'):
            buttons.append({
                'icon': 'credit-card',
                'text': self.env._('Purchase Orders'),
                'number': self.purchase_orders_count,
                'action_type': 'object',
                'action': 'action_open_project_purchase_orders',
                'show': self.purchase_orders_count > 0,
                'sequence': 36,
            })
        return buttons

    def _get_profitability_aal_domain(self):
        return Domain.AND([
            super()._get_profitability_aal_domain(),
            ['|', ('move_line_id', '=', False), ('move_line_id.purchase_line_id', '=', False)],
        ])

    def _add_purchase_items(self, profitability_items, with_action=True):
        return False

    def _get_profitability_labels(self):
        labels = super()._get_profitability_labels()
        labels['purchase_order'] = self.env._('Purchase Orders')
        return labels

    def _get_profitability_sequence_per_invoice_type(self):
        sequence_per_invoice_type = super()._get_profitability_sequence_per_invoice_type()
        sequence_per_invoice_type['purchase_order'] = 10
        return sequence_per_invoice_type

    def _get_profitability_items(self, with_action=True):
        profitability_items = super()._get_profitability_items(with_action)
        # Defensa: si por instalación duplicada hay más de una entrada
        # 'expenses' en costs o revenues, nos quedamos solo con la primera
        # y sumamos el resto en ella, para evitar keys repetidas en el t-foreach.
        for section_key, amount_fields in (
            ('costs', ('billed', 'to_bill')),
            ('revenues', ('invoiced', 'to_invoice')),
        ):
            section = profitability_items.get(section_key)
            if not section:
                continue
            seen = {}
            deduped_data = []
            for item in section['data']:
                item_id = item.get('id')
                if item_id == 'expenses' and item_id in seen:
                    # ya vimos una entrada 'expenses': sumamos montos y descartamos duplicado
                    first = seen[item_id]
                    for fname in amount_fields:
                        first[fname] = first.get(fname, 0.0) + item.get(fname, 0.0)
                    continue
                deduped_data.append(item)
                if item_id == 'expenses':
                    seen[item_id] = item
            section['data'] = deduped_data
            _logger.info(deduped_data)
        if self.account_id:
            company = self.company_id or self.env.company
            today = fields.Date.context_today(self)
    
            # Idempotencia: si alguna otra clase en la cadena de herencia
            # ya agregó una sección 'purchase_order', la sacamos antes de
            # recalcular la nuestra, para no duplicar sin importar cuántas
            # fuentes contribuyan a este método.
            costs = profitability_items['costs']
            section_id = 'purchase_order'
            existing = next((item for item in costs['data'] if item.get('id') == section_id), None)
            if existing:
                costs['data'].remove(existing)
                costs['total']['billed'] -= existing.get('billed', 0.0)
                costs['total']['to_bill'] -= existing.get('to_bill', 0.0)
    
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
                        total_invoiced_amount = 0.0
                        for line in invoice_lines:
                            line_date = line.date or today
                            price_subtotal = line.currency_id._convert(
                                line.price_subtotal, self.currency_id, company, line_date)
                            if not line.analytic_distribution:
                                continue
                            analytic_contribution = sum(
                                percentage for ids, percentage in line.analytic_distribution.items()
                                if str(self.account_id.id) in ids.split(',')
                            ) / 100.
                            cost = price_subtotal * analytic_contribution * (-1 if line.is_refund else 1)
                            if not line.is_refund:
                                total_invoiced_amount += cost
                            if line.parent_state == 'posted':
                                amount_invoiced -= cost
                            else:
                                amount_to_invoice -= cost
                        amount_to_invoice -= purchase_line_amount_to_invoice - total_invoiced_amount
                    else:
                        amount_to_invoice -= purchase_line_amount_to_invoice
    
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
            
            #self._get_costs_items_from_purchase(
            #    domain,
            #    profitability_items,
            #    with_action=with_action,
            #)
            

        _logger.info(profitability_items)
        return profitability_items


    def _get_items_from_invoices(self, excluded_move_line_ids=None, with_action=True):
        if excluded_move_line_ids is None:
            excluded_move_line_ids = []
        aml_fetch_fields = [
            'balance', 'parent_state', 'company_currency_id', 'currency_id', 'amount_currency',
            'analytic_distribution', 'move_id', 'display_type', 'date',
        ]
        invoices_move_lines = self.env['account.move.line'].sudo().search_fetch(
            Domain.AND([
                self._get_items_from_invoices_domain([('id', 'not in', excluded_move_line_ids)]),
                [('analytic_distribution', 'in', self.account_id.ids)]
            ]),
            aml_fetch_fields,
        )
        res = {
            'revenues': {
                'data': [], 'total': {'invoiced': 0.0, 'to_invoice': 0.0}
            },
            'costs': {
                'data': [], 'total': {'billed': 0.0, 'to_bill': 0.0}
            },
        }
        if invoices_move_lines:
            revenues_lines = []
            cogs_lines = []
            for move_line in invoices_move_lines:
                if move_line['display_type'] == 'cogs':
                    cogs_lines.append(move_line)
                else:
                    revenues_lines.append(move_line)
            for move_lines, ml_type in ((revenues_lines, 'revenues'), (cogs_lines, 'costs')):
                amount_invoiced = amount_to_invoice = 0.0
                for move_line in move_lines:
                    # Si la línea ya está en la moneda que queremos mostrar,
                    # usamos el monto original exacto (amount_currency) en vez de
                    # reconvertir desde balance (moneda de compañía), lo que
                    # introducía diferencias de tasa/redondeo innecesarias.
                    if move_line.currency_id and move_line.currency_id == self.currency_id:
                        line_balance = move_line.amount_currency
                    else:
                        currency = move_line.company_currency_id
                        line_balance = currency._convert(move_line.balance, self.currency_id, self.company_id, move_line.date)
                    # an analytic account can appear several time in an analytic distribution with different repartition percentage
                    analytic_contribution = sum(
                        percentage for ids, percentage in move_line.analytic_distribution.items()
                        if str(self.account_id.id) in ids.split(',')
                    ) / 100.
                    if move_line.parent_state == 'draft':
                        amount_to_invoice -= line_balance * analytic_contribution
                    else:  # move_line.parent_state == 'posted'
                        amount_invoiced -= line_balance * analytic_contribution
                # don't display the section if the final values are both 0 (invoice -> credit note)
                if amount_invoiced != 0 or amount_to_invoice != 0:
                    section_id = 'other_invoice_revenues' if ml_type == 'revenues' else 'cost_of_goods_sold'
                    invoices_items = {
                        'id': section_id,
                        'sequence': self._get_profitability_sequence_per_invoice_type()[section_id],
                        'invoiced' if ml_type == 'revenues' else 'billed': amount_invoiced,
                        'to_invoice' if ml_type == 'revenues' else 'to_bill': amount_to_invoice,
                    }
                    if with_action and (
                        self.env.user.has_group('sales_team.group_sale_salesman_all_leads')
                        or self.env.user.has_group('account.group_account_invoice')
                        or self.env.user.has_group('account.group_account_readonly')
                    ):
                        invoices_items['action'] = self._get_action_for_profitability_section(invoices_move_lines.move_id.ids, section_id)
                    res[ml_type] = {
                        'data': [invoices_items],
                        'total': {
                            'invoiced' if ml_type == 'revenues' else 'billed': amount_invoiced,
                            'to_invoice' if ml_type == 'revenues' else 'to_bill': amount_to_invoice,
                        },
                    }
        return res