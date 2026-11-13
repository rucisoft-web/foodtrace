from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .wms_zone import INBOUND_TYPES, OUTBOUND_TYPES


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    wms_sap_code = fields.Char("Kode gudang SAP", help="Nilai 'warehouse' di file sinkron SAP, mis. 01-IGU")


class StockPicking(models.Model):
    _inherit = "stock.picking"

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
    wms_dock_id = fields.Many2one(
        "stock.location", "Loading dock", index=True,
        domain="[('wms_area', '=', 'rcv'), ('usage', '=', 'internal')]",
        help="Dock tempat truk dibongkar, mis. DOCK_01. Wajib diisi sebelum validasi penerimaan.")
    wms_container_no = fields.Char("No. container")
    wms_vendor_ref = fields.Char("No. referensi / DO vendor")
    wms_line_count = fields.Integer("Baris", compute="_compute_wms_line_count")

    def _compute_wms_line_count(self):
        for picking in self:
            picking.wms_line_count = len(picking.move_ids)

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        pickings._wms_flag_partners()
        return pickings

    def write(self, vals):
        res = super().write(vals)
        if "partner_id" in vals or "picking_type_id" in vals:
            self._wms_flag_partners()
        return res

    def _wms_flag_partners(self):
        """Partner di dokumen inbound masuk Source Master, di outbound masuk Destination Master."""
        for code, field in (("incoming", "wms_is_source"), ("outgoing", "wms_is_destination")):
            partners = self.filtered(lambda p, c=code: p.picking_type_code == c).partner_id.commercial_partner_id
            partners = partners.filtered(lambda r, f=field: not r[f])
            if partners:
                partners.sudo().write({field: True})

    def _wms_docks(self):
        self.ensure_one()
        wh = self.picking_type_id.warehouse_id
        domain = [("wms_area", "=", "rcv"), ("usage", "=", "internal")]
        if wh:
            domain.append(("warehouse_id", "=", wh.id))
        return self.env["stock.location"].search(domain, order="name")

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
                if picking.picking_type_code == "incoming":
                    if not picking.wms_dock_id and picking._wms_docks():
                        raise UserError(_("%s: isi Loading dock (mis. DOCK_01) sebelum validasi penerimaan.",
                                          picking.name))
                    picking._wms_check_over_receiving()
                    picking._wms_route_to_quarantine()
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

    def _wms_route_to_quarantine(self):
        """Item bertanda auto karantina langsung ke area Karantina & QC zonanya saat diterima."""
        for ml in self.move_line_ids:
            zone = ml.product_id.wms_zone
            if not zone or not ml.product_id.wms_auto_quarantine:
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
