from datetime import datetime

from odoo import _, models
from odoo.exceptions import UserError


def remaining_life_pct(lot, product, today=None):
    """Sisa umur simpan dalam persen dari umur simpan total item, atau None bila tidak bisa dihitung."""
    if not lot or not lot.expiration_date or not product.expiration_time:
        return None
    today = today or datetime.now()
    left = (lot.expiration_date - today).total_seconds() / 86400.0
    return max(0.0, left) / product.expiration_time * 100.0


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _action_done(self):
        if not self.env.context.get("wms_skip_checks"):
            self._wms_check_zone()
            self._wms_check_shelf_life()
            self._wms_check_lpn_single_sku()
        return super()._action_done()

    def _wms_check_lpn_single_sku(self):
        """Satu LPN hanya untuk 1 SKU dan 1 lot (aturan Largo)."""
        for ml in self.filtered("result_package_id"):
            pack = ml.result_package_id
            others = pack.quant_ids.filtered(
                lambda q, m=ml: q.quantity > 0 and (q.product_id != m.product_id or q.lot_id != m.lot_id))
            same_batch = self.filtered(
                lambda m, p=pack: m.result_package_id == p and m != ml
                and (m.product_id != ml.product_id or m.lot_id != ml.lot_id))
            if others or same_batch:
                raise UserError(_("LPN %(lpn)s hanya boleh berisi 1 SKU dan 1 lot.", lpn=pack.name))

    def _wms_check_zone(self):
        for ml in self:
            zone = ml.product_id.wms_zone
            dest = ml.location_dest_id
            if not zone or dest.usage != "internal":
                continue
            dest_zone = dest._wms_effective_zone()
            if dest_zone and dest_zone != zone:
                raise UserError(_(
                    "%(item)s wajib di zona %(zone)s, tetapi lokasi tujuan %(loc)s ada di zona %(dest)s.",
                    item=ml.product_id.display_name, zone=zone, loc=dest.complete_name, dest=dest_zone))

    def _wms_check_shelf_life(self):
        for ml in self:
            code = ml.picking_id.picking_type_code
            if code == "incoming":
                minimum = ml.product_id.wms_min_receive_life_pct
                who = _("batas terima item")
            elif code == "outgoing":
                minimum = ml.picking_id.partner_id.commercial_partner_id.wms_min_shelf_life_pct
                who = _("batas pelanggan %s", ml.picking_id.partner_id.display_name)
                if ml.lot_id.expiration_date and ml.lot_id.expiration_date < datetime.now():
                    raise UserError(_("Lot %(lot)s (%(item)s) sudah kedaluwarsa dan diblokir.",
                                      lot=ml.lot_id.name, item=ml.product_id.display_name))
            else:
                continue
            if not minimum:
                continue
            pct = remaining_life_pct(ml.lot_id, ml.product_id)
            if pct is not None and pct < minimum:
                raise UserError(_(
                    "Lot %(lot)s (%(item)s) tinggal %(pct).0f%% umur simpan, di bawah %(who)s %(min)s%%.",
                    lot=ml.lot_id.name, item=ml.product_id.display_name, pct=pct, who=who, min=minimum))
