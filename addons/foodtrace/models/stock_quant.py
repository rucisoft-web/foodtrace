from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .wms_zone import AREA_STATUS, STOCK_STATUS


class StockQuant(models.Model):
    _inherit = "stock.quant"

    wms_status = fields.Selection(
        STOCK_STATUS, "Status stok", compute="_compute_wms_status", store=True, index=True,
        help="Status ala Largo, dari area lokasi: Receiving, Available, Picked, Hold, Damage.")
    wms_zone = fields.Selection(related="product_id.wms_zone", store=True, string="Zona")
    wms_expiration_date = fields.Datetime(related="lot_id.expiration_date", store=True, string="Kedaluwarsa")

    @api.depends("location_id.wms_area")
    def _compute_wms_status(self):
        for quant in self:
            quant.wms_status = AREA_STATUS.get(quant.location_id.wms_area, "available")

    def action_wms_qc_release(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("QC release"), "res_model": "wms.qc.release.wizard",
            "view_mode": "form", "target": "new", "context": {"default_quant_id": self.id},
        }

    def action_wms_qc_hold(self):
        """QC Hold: pindahkan stok ke lokasi karantina zonanya."""
        for quant in self:
            zone = quant.product_id.wms_zone or quant.location_id._wms_effective_zone()
            qc = quant.location_id._wms_qc_location(zone)
            if not qc:
                raise UserError(_("Lokasi karantina zona %s belum ada.", zone))
            quant._wms_move_to(qc, quant.quantity, _("QC Hold"))
        return True

    def _wms_move_to(self, dest, qty, reason):
        """Pemindahan internal satu quant (bin transfer) dengan dokumen, langsung selesai."""
        self.ensure_one()
        warehouse = self.location_id.warehouse_id
        picking = self.env["stock.picking"].create({
            "picking_type_id": warehouse.int_type_id.id,
            "location_id": self.location_id.id,
            "location_dest_id": dest.id,
            "origin": reason,
            "owner_id": self.owner_id.id,
            "move_ids": [(0, 0, {
                "name": reason, "product_id": self.product_id.id, "product_uom_qty": qty,
                "product_uom": self.product_id.uom_id.id, "location_id": self.location_id.id,
                "location_dest_id": dest.id, "restrict_partner_id": self.owner_id.id,
            })],
        })
        picking.action_confirm()
        move = picking.move_ids
        move.move_line_ids.unlink()
        self.env["stock.move.line"].create({
            "move_id": move.id, "picking_id": picking.id, "product_id": self.product_id.id,
            "product_uom_id": self.product_id.uom_id.id, "quantity": qty, "lot_id": self.lot_id.id,
            "package_id": self.package_id.id, "result_package_id": self.package_id.id if qty == self.quantity else False,
            "owner_id": self.owner_id.id, "location_id": self.location_id.id, "location_dest_id": dest.id,
        })
        move.picked = True
        picking.button_validate()
        return picking

    @api.model
    def _cron_auto_release(self):
        """Lepas karantina otomatis untuk item ber-Auto release setelah durasi karantina habis."""
        now = fields.Datetime.now()
        quants = self.search([("wms_status", "=", "hold"), ("quantity", ">", 0),
                              ("product_id.wms_auto_release", "=", True)])
        for quant in quants:
            days = quant.product_id.wms_quarantine_days or 0
            if quant.in_date and quant.in_date + timedelta(days=days) <= now:
                dest = quant.location_id.location_id
                quant._wms_move_to(dest, quant.quantity, _("Auto release karantina"))


class StockQuantPackage(models.Model):
    """LPN palet: 1 SKU dan 1 lot per LPN, dengan info tally."""

    _inherit = "stock.quant.package"

    wms_mfg_date = fields.Date("Tanggal produksi")
    wms_pack_date = fields.Date("Pack date")
    wms_pallet_no = fields.Char("No. palet")
    wms_remark = fields.Char("Remark")
    wms_product_id = fields.Many2one("product.product", "SKU", compute="_compute_wms_content")
    wms_lot_id = fields.Many2one("stock.lot", "Lot", compute="_compute_wms_content")
    wms_qty = fields.Float("Qty", compute="_compute_wms_content")
    wms_expiration_date = fields.Datetime("Kedaluwarsa", compute="_compute_wms_content")
    wms_status = fields.Selection(STOCK_STATUS, "Status", compute="_compute_wms_content")

    @api.depends("quant_ids.quantity", "quant_ids.lot_id", "quant_ids.location_id")
    def _compute_wms_content(self):
        for pack in self:
            quants = pack.quant_ids.filtered(lambda q: q.quantity > 0)
            pack.wms_product_id = quants.product_id[:1]
            pack.wms_lot_id = quants.lot_id[:1]
            pack.wms_qty = sum(quants.mapped("quantity"))
            pack.wms_expiration_date = quants.lot_id[:1].expiration_date
            pack.wms_status = quants[:1].wms_status or False
