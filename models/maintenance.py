from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError, ValidationError


class StockMove(models.Model):
    _inherit = 'stock.move'

    maintenance_request_id = fields.Many2one('maintenance.request')


class MaintenanceTeam(models.Model):
    _inherit = 'maintenance.team'

    repair_location_id = fields.Many2one('stock.location', string='Fuente predeterminada para piezas de reparación')
    repair_location_dest_id = fields.Many2one('stock.location', string='Destino predeterminado para piezas de reparación')


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    maintenance_type = fields.Selection(selection_add=[('install', 'Instalacion'),('negligence', 'Negligencia')])
    repair_line_ids = fields.One2many('maintenance.request.repair.line', 'request_id', 'Partes', copy=True)
    repair_status = fields.Selection([
        ('repaired', 'Reparado'),
        ('to repair', 'Reparar'),
        ('no', 'Nada que reparar')
        ], string='Estado de reparación', compute='_get_repaired', store=True, readonly=True)
    repair_location_id = fields.Many2one('stock.location', string='Ubicación de origen')
    repair_location_dest_id = fields.Many2one('stock.location', string='Ubicación de destino')
    total_lst_price = fields.Float(string='Precio total', compute='_compute_repair_totals', stored=True)
    total_standard_price = fields.Float(string='Costo total estimado', compute='_compute_repair_totals', stored=True)
    total_cost = fields.Float(string='Coste total', compute='_compute_repair_totals', stored=True)

    @api.depends('repair_line_ids.lst_price', 'repair_line_ids.standard_price', 'repair_line_ids.cost')
    def _compute_repair_totals(self):
        for repair in self:
            repair.total_lst_price = sum(l.lst_price for l in repair.repair_line_ids)
            repair.total_standard_price = sum(l.standard_price for l in repair.repair_line_ids)
            repair.total_cost = sum(l.cost for l in repair.repair_line_ids)

    @api.depends('repair_line_ids.state')
    def _get_repaired(self):
        for request in self:
            if not request.repair_line_ids:
                request.repair_status = 'no'
            elif request.repair_line_ids.filtered(lambda l: l.state != 'done'):
                request.repair_status = 'to repair'
            else:
                request.repair_status = 'repaired'

    @api.onchange('maintenance_team_id')
    def _onchange_maintenance_team(self):
        for request in self:
            if request.maintenance_team_id:
                request.repair_location_id = request.maintenance_team_id.repair_location_id
                request.repair_location_dest_id = request.maintenance_team_id.repair_location_dest_id


    def action_complete_repair(self):
        for request in self.filtered(lambda r: r.repair_status == 'to repair'):
            request.repair_line_ids.action_complete()
        return True

class MaintenanceRequestRepairLine(models.Model):
    _name = 'maintenance.request.repair.line'

    request_id = fields.Many2one('maintenance.request', copy=False)
    product_id = fields.Many2one('product.product', 'Producto', required=True,
                                 states={'done': [('readonly', True)]})
    product_uom_qty = fields.Float('Cantidad', default=1.0,
                                   digits=dp.get_precision('Unidad de medida del producto'), required=True,
                                   states={'done': [('readonly', True)]})
    product_uom_id = fields.Many2one('uom.uom', 'Unidad de medida del producto', required=True,
                                     states={'done': [('readonly', True)]})
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Hecho'),
    ], string='State', copy=False, default='draft')
    move_id = fields.Many2one('stock.move', string='Movimiento de stock')
    lst_price = fields.Float(string='Precio de venta', states={'done': [('readonly', True)]})
    standard_price = fields.Float(string='Costo estimado', states={'done': [('readonly', True)]})
    cost = fields.Float(string='Costo', compute='_compute_actual_cost', stored=True)
    
    def unlink(self):
        if self.filtered(lambda l: l.state == 'done'):
            raise UserError(_('Solo se pueden eliminar líneas estando en borrador.'))
        return super(MaintenanceRequestRepairLine, self).unlink()

    @api.onchange('product_id', 'product_uom_qty')
    def onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
            self.lst_price = self.product_id.lst_price * self.product_uom_qty
            self.standard_price = self.product_id.standard_price * self.product_uom_qty

    @api.depends('product_id', 'move_id')
    def _compute_actual_cost(self):
        for line in self:
            if line.move_id:
                line.cost = sum(abs(m.amount) for m in line.move_id.account_move_ids)
            else:
                line.cost = 0.0

    def _repair_complete_stock_move_values(self):
        values = {
            'name': self.request_id.name,
            'product_id': self.product_id.id,
            'product_uom_qty': self.product_uom_qty,
            'product_uom': self.product_uom_id.id,
            'location_id': self.request_id.repair_location_id.id,
            'location_dest_id': self.request_id.repair_location_dest_id.id,
            'maintenance_request_id': self.request_id.id,
            'origin': self.request_id.name,
        }
        # Optional modules for linking maintenance requests to projects, and stock moves to analytic accounts
        if hasattr(self.request_id, 'project_id') and hasattr(self.env['stock.move'], 'analytic_account_id'):
            values['analytic_account_id'] = self.request_id.project_id.analytic_account_id.id
        return values

    def action_complete(self):
        # Create stock movements. - Inspired by mrp_repair
        stock_move_model = self.env['stock.move']
        for line in self.filtered(lambda l: not l.state == 'done'):
            move = stock_move_model.create(self._repair_complete_stock_move_values())
            move = move.sudo()
            move._action_confirm()
            move._action_assign()
            if move.state != 'assigned':
                raise ValidationError(_('No es posible reservar el inventario.'))

            move.quantity_done = line.product_uom_qty
            move._action_done()
            if move.state != 'done':
                raise ValidationError(_('No se ha podido mover el inventario.'))

            line.write({'move_id': move.id, 'state': 'done'})
        return True


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    def _create_new_request(self, date):
        # Added repair_location_id and repair_location_dest_id
        # Cannot call super() because it does not return the object
        self.ensure_one()
        return self.env['maintenance.request'].create({
            'name': _('Preventive Maintenance - %s') % self.name,
            'request_date': date,
            'schedule_date': date,
            'category_id': self.category_id.id,
            'equipment_id': self.id,
            'maintenance_type': 'preventive',
            'owner_user_id': self.owner_user_id.id,
            'user_id': self.technician_user_id.id,
            'maintenance_team_id': self.maintenance_team_id.id,
            'duration': self.maintenance_duration,
            'repair_location_id': self.maintenance_team_id.repair_location_id.id,
            'repair_location_dest_id': self.maintenance_team_id.repair_location_dest_id.id
        })
class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = "product.template"

    isParts = fields.Boolean('Puede ser una parte')
