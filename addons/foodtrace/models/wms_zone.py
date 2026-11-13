from odoo import api, fields, models

ZONES = [("frozen", "Frozen"), ("chilled", "Chilled"), ("dry", "Dry")]
AREAS = [
    ("rcv", "Dock penerimaan"),
    ("in", "Staging masuk"),
    ("blk", "Palet utuh"),
    ("pck", "Pecah palet"),
    ("qc", "Karantina & QC"),
    ("rtn", "Retur"),
    ("dmg", "Damage"),
    ("wst", "Waste"),
    ("out", "Staging keluar"),
    ("prd", "Produksi Pack ID"),
    ("room", "Ruang (induk zona)"),
]
# Enam status stok ala Largo, diturunkan dari area lokasi quant.
STOCK_STATUS = [
    ("receiving", "Receiving"),
    ("available", "Available"),
    ("picked", "Picked"),
    ("hold", "Hold"),
    ("damage", "Damage"),
]
AREA_STATUS = {"rcv": "receiving", "in": "receiving", "out": "picked", "qc": "hold", "rtn": "hold",
               "dmg": "damage", "wst": "damage"}
INBOUND_TYPES = [
    ("po", "Purchase Order"), ("titipan", "Titipan"), ("transfer", "Warehouse Transfer"),
    ("retur", "Retur"), ("butcher", "Hasil/sisa potong"), ("sampling", "Sampling"),
]
OUTBOUND_TYPES = [
    ("so", "Sales Order"), ("butcher", "Butcher/Produksi"), ("dispose", "Pemusnahan"),
    ("transfer", "Warehouse Transfer"), ("rtv", "Return to Vendor"), ("chill_frozen", "Chill to Frozen"),
    ("others", "Lainnya"),
]


class WmsZoneStandard(models.Model):
    """Standar per zona penyimpanan (Frozen, Chilled, Dry): kode lokasi, umur simpan bawaan, warna."""

    _name = "wms.zone.standard"
    _description = "Standar zona"
    _order = "sequence, id"
    _rec_name = "name"

    sequence = fields.Integer(default=10)
    zone = fields.Selection(ZONES, required=True)
    name = fields.Char(required=True)
    code = fields.Char(required=True, help="Kode zona di kode lokasi, mis. FZ")
    shelf_life_days = fields.Integer("Umur simpan bawaan (hari)", default=365)
    color = fields.Char(default="#2563eb")

    _sql_constraints = [("zone_unique", "unique(zone)", "Setiap zona hanya punya satu standar.")]

    @api.model
    def for_zone(self, zone):
        return self.search([("zone", "=", zone)], limit=1)
