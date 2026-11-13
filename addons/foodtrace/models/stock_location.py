from odoo import fields, models

from .wms_zone import AREAS, ZONES


class StockLocation(models.Model):
    _inherit = "stock.location"

    wms_zone = fields.Selection(ZONES, "Zona suhu", help="Kosong = ikut lokasi induk.")
    wms_area = fields.Selection(AREAS, "Area WMS")
    wms_max_pallets = fields.Integer("Kapasitas palet")
    wms_max_weight = fields.Float("Berat maks. (kg)")

    def _wms_effective_zone(self):
        self.ensure_one()
        loc = self
        while loc:
            if loc.wms_zone:
                return loc.wms_zone
            loc = loc.location_id
        return False

    def _wms_qc_location(self, zone):
        """Lokasi karantina untuk zona tertentu di gudang yang sama."""
        self.ensure_one()
        warehouse = self.warehouse_id
        domain = [("wms_area", "=", "qc"), ("wms_zone", "=", zone), ("usage", "=", "internal")]
        if warehouse:
            domain.append(("warehouse_id", "=", warehouse.id))
        return self.search(domain, limit=1)
