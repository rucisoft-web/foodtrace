from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WmsQcReleaseWizard(models.TransientModel):
    """QC Release: stok Hold menjadi Good (kembali ke rak) dan/atau Damage, boleh sebagian."""

    _name = "wms.qc.release.wizard"
    _description = "QC release"

    quant_id = fields.Many2one("stock.quant", required=True, readonly=True)
    product_id = fields.Many2one(related="quant_id.product_id")
    lot_id = fields.Many2one(related="quant_id.lot_id")
    quantity = fields.Float(related="quant_id.quantity", string="Qty ditahan")
    qty_good = fields.Float("Qty GOOD")
    qty_damage = fields.Float("Qty DAMAGE")
    good_location_id = fields.Many2one("stock.location", "Lokasi GOOD", domain=[("usage", "=", "internal")])
    reason = fields.Char("Alasan / hasil QC")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        quant = self.env["stock.quant"].browse(res.get("quant_id"))
        if quant:
            res.setdefault("qty_good", quant.quantity)
            res.setdefault("good_location_id", quant.location_id.location_id.id)
        return res

    def action_confirm(self):
        self.ensure_one()
        quant = self.quant_id
        if self.qty_good < 0 or self.qty_damage < 0 or self.qty_good + self.qty_damage > quant.quantity + 1e-6:
            raise UserError(_("Qty GOOD + DAMAGE tidak boleh melebihi qty yang ditahan."))
        if not self.qty_good and not self.qty_damage:
            raise UserError(_("Isi qty GOOD atau DAMAGE."))
        reason = self.reason or _("QC release")
        if self.qty_damage:
            zone = quant.product_id.wms_zone or quant.location_id._wms_effective_zone()
            damage = self.env["stock.location"].search([
                ("wms_area", "=", "dmg"), ("warehouse_id", "=", quant.location_id.warehouse_id.id),
                "|", ("wms_zone", "=", zone), ("wms_zone", "=", False)], order="wms_zone", limit=1)
            if not damage:
                raise UserError(_("Lokasi Damage belum ada di gudang ini."))
            quant._wms_move_to(damage, self.qty_damage, _("%s (DAMAGE)", reason))
        if self.qty_good:
            quant._wms_move_to(self.good_location_id, self.qty_good, _("%s (GOOD)", reason))
        return {"type": "ir.actions.act_window_close"}
