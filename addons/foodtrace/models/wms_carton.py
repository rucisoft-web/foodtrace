from odoo import api, fields, models


class WmsCarton(models.Model):
    """Satu karton fisik: berat aktual, lot, kedaluwarsa, owner, dan LPN palet tempatnya."""

    _name = "wms.carton"
    _description = "Karton"
    _order = "expiration_date, id"

    name = fields.Char("Nomor karton", required=True, index=True)
    raw_barcode = fields.Char("Barcode mentah")
    product_id = fields.Many2one("product.product", "Item", required=True, index=True)
    lot_id = fields.Many2one("stock.lot", "Lot", index=True)
    expiration_date = fields.Datetime(related="lot_id.expiration_date", store=True, string="Kedaluwarsa")
    package_id = fields.Many2one("stock.quant.package", "LPN palet", index=True)
    location_id = fields.Many2one("stock.location", "Lokasi", index=True)
    owner_id = fields.Many2one("res.partner", "Owner")
    weight_kg = fields.Float("Berat (kg)", digits=(10, 3))
    weight_lb = fields.Float("Berat label (lbs)", digits=(10, 3), help="Berat asli di label untuk klaim selisih Lbs-Kg")
    zone = fields.Selection(related="product_id.wms_zone", store=True)
    state = fields.Selection(
        [("available", "Tersedia"), ("quarantine", "Karantina"), ("shipped", "Terkirim"), ("waste", "Waste")],
        default="available", required=True, index=True)
    in_picking_id = fields.Many2one("stock.picking", "Penerimaan")
    out_picking_id = fields.Many2one("stock.picking", "Pengiriman")
    manual_weight = fields.Boolean("Berat diisi manual")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    _sql_constraints = [
        ("carton_unique", "unique(company_id, product_id, name)", "Nomor karton sudah pernah diterima untuk item ini."),
    ]

    @api.depends("name", "weight_kg")
    def _compute_display_name(self):
        for carton in self:
            carton.display_name = f"{carton.name} · {carton.weight_kg:.2f} kg"
