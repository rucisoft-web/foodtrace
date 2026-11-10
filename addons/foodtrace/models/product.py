from odoo import api, fields, models

from .wms_zone import ZONES


class ProductTemplate(models.Model):
    _inherit = "product.template"

    wms_zone = fields.Selection(ZONES, "Zona suhu", help="Zona wajib. Putaway ke zona lain ditolak.")
    wms_catch_weight = fields.Boolean(
        "Berat aktual per karton", help="Stok dikelola per karton dengan berat berbeda; satuan nilai kg.")
    wms_min_receive_life_pct = fields.Integer(
        "Min. sisa umur saat terima (%)", default=0,
        help="Karton dengan sisa umur simpan di bawah angka ini ditolak saat penerimaan. 0 = tidak dicek.")
    wms_barcode_template_ids = fields.Many2many(
        "wms.barcode.template", string="Template barcode karton")
    wms_auto_quarantine = fields.Boolean(
        "Auto karantina", help="Semua penerimaan item ini langsung berstatus Hold (karantina).")
    wms_quarantine_days = fields.Integer("Durasi karantina (hari)", default=7)
    wms_auto_release = fields.Boolean("Auto release", help="Lepas otomatis dari karantina setelah durasinya habis.")
    wms_units_per_pallet = fields.Float("Qty per palet (UPP)")
    wms_multi_qty = fields.Boolean("Multi qty (boleh ambil eceran)")
    wms_picking_strategy = fields.Selection([("fefo", "FEFO"), ("fifo", "FIFO")], "Strategi picking", default="fefo")
    wms_min_stock = fields.Float("Stok minimum (item low)")
    wms_item_group = fields.Char("Item group SAP")
    wms_sub_group = fields.Char("Sub group SAP")
    wms_country = fields.Char("Negara asal")


class ProductProduct(models.Model):
    _inherit = "product.product"

    wms_is_low = fields.Boolean("Item low", compute="_compute_wms_is_low", search="_search_wms_is_low")

    @api.depends("qty_available", "wms_min_stock")
    def _compute_wms_is_low(self):
        for product in self:
            product.wms_is_low = bool(product.wms_min_stock) and product.qty_available < product.wms_min_stock

    def _search_wms_is_low(self, operator, value):
        candidates = self.search([("wms_min_stock", ">", 0)])
        ids = candidates.filtered("wms_is_low").ids
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", ids)]
