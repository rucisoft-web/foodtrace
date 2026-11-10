from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .wms_zone import INBOUND_TYPES, OUTBOUND_TYPES


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    wms_sap_code = fields.Char("Kode gudang SAP", help="Nilai 'warehouse' di file sinkron SAP, mis. 01-IGU")


class StockPicking(models.Model):
    _inherit = "stock.picking"

    wms_temperature_ids = fields.One2many("wms.temperature.log", "picking_id", "Catatan suhu")
    wms_temp_alarm = fields.Boolean("Ada alarm suhu", compute="_compute_wms_temp", store=True)
    wms_temp_logged = fields.Boolean("Suhu sudah dicatat", compute="_compute_wms_temp", store=True)
    wms_needs_temp = fields.Boolean(compute="_compute_wms_needs_temp")
    wms_carton_count = fields.Integer("Karton", compute="_compute_wms_carton_count")
    wms_sap_document_ids = fields.One2many("wms.sap.document", "picking_id", "Posting SAP")
    wms_sap_state = fields.Selection(
        [("none", "Belum"), ("queued", "Antre"), ("posted", "Terkirim"), ("failed", "Gagal")],
        "Status SAP", compute="_compute_wms_sap_state")
    wms_sync_id = fields.Many2one("wms.sync.document", "Dokumen sinkron SAP", readonly=True)
    wms_shipping_group = fields.Char("Shipping group / rute")
    wms_priority = fields.Char("Prioritas SAP")
    wms_inbound_type = fields.Selection(INBOUND_TYPES, "Jenis inbound")
    wms_outbound_type = fields.Selection(OUTBOUND_TYPES, "Jenis outbound")
    wms_vehicle_plate = fields.Char("No. plat kendaraan")
    wms_driver = fields.Char("Nama driver")
    wms_delivery_note = fields.Char("No. surat jalan")

    @api.depends("wms_temperature_ids.is_alarm")
    def _compute_wms_temp(self):
        for picking in self:
            picking.wms_temp_logged = bool(picking.wms_temperature_ids)
            picking.wms_temp_alarm = any(picking.wms_temperature_ids.mapped("is_alarm"))

    def _wms_cold_zones(self):
        self.ensure_one()
        return {z for z in self.move_ids.product_id.mapped("wms_zone") if z in ("frozen", "chilled")}

    def _compute_wms_needs_temp(self):
        for picking in self:
            picking.wms_needs_temp = (
                picking.picking_type_code in ("incoming", "outgoing") and bool(picking._wms_cold_zones()))

    def _compute_wms_carton_count(self):
        Carton = self.env["wms.carton"]
        for picking in self:
            picking.wms_carton_count = Carton.search_count(
                ["|", ("in_picking_id", "=", picking.id), ("out_picking_id", "=", picking.id)])

    def _compute_wms_sap_state(self):
        for picking in self:
            docs = picking.wms_sap_document_ids
            picking.wms_sap_state = docs[:1].state if docs else "none"

    def button_validate(self):
        if not self.env.context.get("wms_skip_checks"):
            for picking in self:
                if picking.wms_needs_temp and not picking.wms_temp_logged:
                    raise UserError(_(
                        "%s berisi barang frozen/chilled. Catat suhu produk dan truk dulu (tombol Catat suhu).",
                        picking.name))
                if picking.picking_type_code == "incoming":
                    picking._wms_check_over_receiving()
                    picking._wms_route_to_quarantine(all_cold=picking.wms_temp_alarm)
        return super().button_validate()

    def _wms_check_over_receiving(self):
        tolerance = self.partner_id.commercial_partner_id.wms_over_receive_pct
        for move in self.move_ids:
            limit = move.product_uom_qty * (1 + tolerance / 100.0)
            if move.product_uom_qty and move.quantity > limit + 1e-6:
                raise UserError(_(
                    "Over receiving %(item)s: diterima %(qty)s, PO %(po)s (toleransi %(tol)s%%). "
                    "Buat inbound document (PO) terpisah untuk kelebihannya.",
                    item=move.product_id.display_name, qty=move.quantity, po=move.product_uom_qty, tol=tolerance))

    def _wms_route_to_quarantine(self, all_cold=False):
        """Ke karantina: item ber-auto karantina, dan semua barang dingin bila suhu saat terima menyimpang."""
        for ml in self.move_line_ids:
            zone = ml.product_id.wms_zone
            hold = ml.product_id.wms_auto_quarantine or (all_cold and zone in ("frozen", "chilled"))
            if not zone or not hold:
                continue
            qc = ml.location_dest_id._wms_qc_location(zone)
            if qc:
                ml.location_dest_id = qc

    def _action_done(self):
        res = super()._action_done()
        Sap = self.env["wms.sap.document"]
        Carton = self.env["wms.carton"]
        for picking in self.filtered(lambda p: p.state == "done"):
            Sap.enqueue_picking(picking)
            if picking.picking_type_code == "incoming":
                cartons = Carton.search([("in_picking_id", "=", picking.id)])
                for carton in cartons:
                    ml = picking.move_line_ids.filtered(
                        lambda m, c=carton: m.product_id == c.product_id and m.lot_id == c.lot_id)[:1]
                    if ml:
                        is_qc = ml.location_dest_id.wms_area == "qc"
                        carton.write({
                            "location_id": ml.location_dest_id.id,
                            "package_id": ml.result_package_id.id,
                            "state": "quarantine" if is_qc else "available",
                        })
        return res

    def action_wms_log_temperature(self):
        self.ensure_one()
        zones = sorted(self._wms_cold_zones()) or ["chilled"]
        return {
            "type": "ir.actions.act_window",
            "name": _("Catat suhu"),
            "res_model": "wms.temperature.log",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_picking_id": self.id,
                "default_zone": zones[0],
                "default_source": "receipt" if self.picking_type_code == "incoming" else "delivery",
            },
        }

    def action_wms_tally(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Tally karton"),
            "res_model": "wms.tally.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_picking_id": self.id},
        }

    def action_wms_cartons(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Karton"),
            "res_model": "wms.carton",
            "view_mode": "list,form",
            "domain": ["|", ("in_picking_id", "=", self.id), ("out_picking_id", "=", self.id)],
        }
