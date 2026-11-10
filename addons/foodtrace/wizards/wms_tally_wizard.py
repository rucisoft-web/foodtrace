from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WmsTallyWizard(models.TransientModel):
    """Tally penerimaan per karton: scan barcode, sistem membaca berat, lot dan kedaluwarsa."""

    _name = "wms.tally.wizard"
    _description = "Tally karton penerimaan"

    picking_id = fields.Many2one("stock.picking", required=True)
    move_id = fields.Many2one(
        "stock.move", "Item", domain="[('picking_id', '=', picking_id)]", required=True)
    barcode = fields.Char("Scan barcode karton")
    manual_weight = fields.Float("Berat manual (kg)", help="Dipakai bila barcode gagal dibaca")
    manual_lot = fields.Char("Lot manual")
    manual_expiry = fields.Date("Kedaluwarsa manual")
    line_ids = fields.One2many("wms.tally.wizard.line", "wizard_id", "Karton")
    total_weight = fields.Float("Total berat (kg)", compute="_compute_totals", digits=(10, 3))
    carton_count = fields.Integer("Jumlah karton", compute="_compute_totals")
    message = fields.Char(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking = self.env["stock.picking"].browse(res.get("picking_id"))
        if picking and not res.get("move_id"):
            res["move_id"] = picking.move_ids[:1].id
        return res

    @api.depends("line_ids.weight_kg")
    def _compute_totals(self):
        for wiz in self:
            wiz.total_weight = sum(wiz.line_ids.mapped("weight_kg"))
            wiz.carton_count = len(wiz.line_ids)

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new", "name": _("Tally karton")}

    def action_scan(self):
        self.ensure_one()
        product = self.move_id.product_id
        raw = (self.barcode or "").strip()
        if not raw and not self.manual_weight:
            raise UserError(_("Scan barcode karton atau isi berat manual."))
        vals = {"wizard_id": self.id, "product_id": product.id, "raw_barcode": raw}
        try:
            if not raw:
                raise UserError(_("Tanpa barcode"))
            template, data = self.env["wms.barcode.template"].parse_for_product(product, raw)
            vals.update({
                "weight_kg": data["weight_kg"],
                "weight_lb": data.get("weight_lb") or 0.0,
                "lot_name": data.get("lot") or self.manual_lot,
                "expiry": data.get("expiry") or self.manual_expiry,
                "carton_no": data.get("carton") or raw[-12:],
                "template_id": template.id,
            })
        except UserError:
            if not self.manual_weight:
                raise
            vals.update({
                "weight_kg": self.manual_weight,
                "lot_name": self.manual_lot,
                "expiry": self.manual_expiry,
                "carton_no": raw[-12:] if raw else f"M{len(self.line_ids) + 1:04d}",
                "manual": True,
            })
        dup = self.line_ids.filtered(lambda l: l.carton_no == vals["carton_no"]) or self.env["wms.carton"].search_count(
            [("product_id", "=", product.id), ("name", "=", vals["carton_no"])])
        if dup:
            raise UserError(_("Karton %s sudah discan.", vals["carton_no"]))
        self.env["wms.tally.wizard.line"].create(vals)
        self.write({"barcode": False, "manual_weight": 0.0,
                    "message": _("Karton %(c)s: %(w).2f kg", c=vals["carton_no"], w=vals["weight_kg"])})
        return self._reopen()

    def action_confirm(self):
        """Buat lot, isi qty move line (kg untuk item berat aktual, karton untuk lainnya), simpan karton."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Belum ada karton yang discan."))
        move = self.move_id
        product = move.product_id
        Lot = self.env["stock.lot"]
        by_lot = defaultdict(lambda: self.env["wms.tally.wizard.line"])
        for line in self.line_ids:
            by_lot[line.lot_name or ""] |= line
        move.move_line_ids.unlink()
        is_weight = move.product_uom.category_id == self.env.ref("uom.product_uom_categ_kgm")
        for lot_name, lines in by_lot.items():
            expiry = next((e for e in lines.mapped("expiry") if e), False)
            lot = Lot.browse()
            if product.tracking != "none":
                lot_name = lot_name or f"{self.picking_id.name}-{product.default_code or product.id}"
                lot = Lot.search([("product_id", "=", product.id), ("name", "=", lot_name),
                                  ("company_id", "in", [False, self.picking_id.company_id.id])], limit=1)
                if not lot:
                    lot = Lot.create({"product_id": product.id, "name": lot_name,
                                      "company_id": self.picking_id.company_id.id,
                                      "expiration_date": fields.Datetime.to_datetime(expiry) if expiry else False})
            qty = sum(lines.mapped("weight_kg")) if is_weight else len(lines)
            self.env["stock.move.line"].create({
                "move_id": move.id,
                "picking_id": self.picking_id.id,
                "product_id": product.id,
                "product_uom_id": move.product_uom.id,
                "lot_id": lot.id,
                "quantity": qty,
                "location_id": move.location_id.id,
                "location_dest_id": move.location_dest_id.id,
                "owner_id": self.picking_id.owner_id.id,
            })
            for line in lines:
                self.env["wms.carton"].create({
                    "name": line.carton_no,
                    "raw_barcode": line.raw_barcode,
                    "product_id": product.id,
                    "lot_id": lot.id,
                    "weight_kg": line.weight_kg,
                    "weight_lb": line.weight_lb,
                    "owner_id": self.picking_id.owner_id.id,
                    "in_picking_id": self.picking_id.id,
                    "manual_weight": line.manual,
                    "company_id": self.picking_id.company_id.id,
                })
        move.picked = True
        return {"type": "ir.actions.act_window_close"}


class WmsTallyWizardLine(models.TransientModel):
    _name = "wms.tally.wizard.line"
    _description = "Baris tally karton"

    wizard_id = fields.Many2one("wms.tally.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product")
    raw_barcode = fields.Char("Barcode")
    carton_no = fields.Char("Nomor karton", required=True)
    weight_kg = fields.Float("Berat (kg)", digits=(10, 3))
    weight_lb = fields.Float("Berat label (lbs)", digits=(10, 3))
    lot_name = fields.Char("Lot")
    expiry = fields.Date("Kedaluwarsa")
    template_id = fields.Many2one("wms.barcode.template", "Template")
    manual = fields.Boolean("Manual")
