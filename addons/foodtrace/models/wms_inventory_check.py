from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockQuantPackageCheck(models.Model):
    _inherit = "stock.quant.package"

    wms_closed = fields.Boolean("Palet ditutup", help="LPN sudah 'Simpan palet' di receiving dan siap put away.")
    wms_need_reprint = fields.Boolean("Perlu cetak ulang label", copy=False)

    def action_wms_print_label(self):
        self.write({"wms_need_reprint": False})
        return self.env.ref("foodtrace.action_report_lpn_label").report_action(self)


class WmsInventoryCheck(models.Model):
    """Inventory Check ala Largo: cek fisik per LPN atau per lokasi, selisih disetujui kepala gudang."""

    _name = "wms.inventory.check"
    _description = "Inventory check"
    _order = "id desc"

    name = fields.Char("Nomor", required=True, copy=False, default=lambda self: _("Baru"))
    mode = fields.Selection([("lpn", "Per LPN"), ("location", "Per lokasi")], "Cek berdasarkan",
                            required=True, default="location")
    location_id = fields.Many2one("stock.location", "Lokasi", domain=[("usage", "=", "internal")])
    package_id = fields.Many2one("stock.quant.package", "LPN")
    date = fields.Datetime("Tanggal", default=fields.Datetime.now, required=True)
    user_id = fields.Many2one("res.users", "Checker", default=lambda self: self.env.user)
    approved_by = fields.Many2one("res.users", "Disetujui oleh", readonly=True)
    state = fields.Selection([("draft", "Draft"), ("submitted", "Menunggu approval"),
                              ("approved", "Approved"), ("rejected", "Rejected")],
                             default="draft", required=True, index=True)
    line_ids = fields.One2many("wms.inventory.check.line", "check_id", "Hasil cek")
    difference_count = fields.Integer("Baris selisih", compute="_compute_summary", store=True)
    reprint_count = fields.Integer("Perlu cetak ulang", compute="_compute_summary", store=True)
    remark = fields.Text("Catatan")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Baru")) == _("Baru"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.inventory.check") or _("Baru")
        return super().create(vals_list)

    @api.depends("line_ids.is_difference", "line_ids.need_reprint")
    def _compute_summary(self):
        for check in self:
            check.difference_count = len(check.line_ids.filtered("is_difference"))
            check.reprint_count = len(check.line_ids.filtered("need_reprint"))

    def _quant_domain(self):
        self.ensure_one()
        if self.mode == "lpn":
            if not self.package_id:
                raise UserError(_("Pilih / scan LPN."))
            return [("package_id", "=", self.package_id.id)]
        if not self.location_id:
            raise UserError(_("Pilih / scan lokasi."))
        return [("location_id", "child_of", self.location_id.id)]

    def action_load(self):
        """Isi baris dari stok sistem. Qty fisik dibiarkan sama dengan sistem sampai checker mengubahnya."""
        for check in self:
            if check.state != "draft":
                continue
            check.line_ids.unlink()
            quants = self.env["stock.quant"].search(check._quant_domain() + [("quantity", ">", 0)])
            check.line_ids = [(0, 0, {
                "quant_id": q.id, "product_id": q.product_id.id, "lot_id": q.lot_id.id,
                "package_id": q.package_id.id, "location_id": q.location_id.id,
                "qty_before": q.quantity, "qty_after": q.quantity,
                "expiry_before": q.lot_id.expiration_date, "expiry_after": q.lot_id.expiration_date,
            }) for q in quants]
        return True

    def action_submit(self):
        for check in self:
            if not check.line_ids:
                raise UserError(_("Belum ada baris hasil cek."))
            check.state = "submitted"
        return True

    def action_reject(self):
        self.write({"state": "rejected"})
        return True

    def action_reset(self):
        self.write({"state": "draft", "approved_by": False})
        return True

    def action_approve(self):
        """Terapkan selisih qty sebagai adjustment, ubah expiry lot, tandai LPN perlu cetak ulang."""
        for check in self:
            if check.state != "submitted":
                raise UserError(_("Hanya dokumen yang menunggu approval yang bisa disetujui."))
            for line in check.line_ids:
                if line.expiry_after and line.expiry_after != line.expiry_before and line.lot_id:
                    line.lot_id.expiration_date = line.expiry_after
                if abs(line.qty_after - line.qty_before) > 1e-6:
                    quant = line.quant_id or self.env["stock.quant"].search([
                        ("product_id", "=", line.product_id.id), ("lot_id", "=", line.lot_id.id),
                        ("package_id", "=", line.package_id.id), ("location_id", "=", line.location_id.id)],
                        limit=1)
                    if not quant:
                        quant = self.env["stock.quant"].create({
                            "product_id": line.product_id.id, "lot_id": line.lot_id.id,
                            "package_id": line.package_id.id, "location_id": line.location_id.id})
                    quant.with_context(inventory_mode=True).write({"inventory_quantity": line.qty_after})
                    quant.with_context(inventory_name=check.name, wms_skip_checks=True).action_apply_inventory()
                if line.need_reprint and line.package_id:
                    line.package_id.wms_need_reprint = True
            check.write({"state": "approved", "approved_by": self.env.user.id})
        return True


class WmsInventoryCheckLine(models.Model):
    _name = "wms.inventory.check.line"
    _description = "Baris inventory check"

    check_id = fields.Many2one("wms.inventory.check", required=True, ondelete="cascade")
    quant_id = fields.Many2one("stock.quant")
    product_id = fields.Many2one("product.product", "Item", required=True)
    lot_id = fields.Many2one("stock.lot", "Lot")
    package_id = fields.Many2one("stock.quant.package", "LPN")
    location_id = fields.Many2one("stock.location", "Lokasi", required=True)
    qty_before = fields.Float("Qty sistem", readonly=True)
    qty_after = fields.Float("Qty fisik")
    expiry_before = fields.Datetime("Expiry sistem", readonly=True)
    expiry_after = fields.Datetime("Expiry fisik")
    difference = fields.Float("Selisih", compute="_compute_difference", store=True)
    is_difference = fields.Boolean(compute="_compute_difference", store=True)
    need_reprint = fields.Boolean("Perlu cetak ulang", compute="_compute_difference", store=True, readonly=False,
                                  help="Otomatis bila qty atau expiry LPN berubah; bisa dicentang manual "
                                       "bila label rusak.")
    remark = fields.Char("Remark")

    @api.depends("qty_before", "qty_after", "expiry_before", "expiry_after")
    def _compute_difference(self):
        for line in self:
            line.difference = line.qty_after - line.qty_before
            expiry_changed = bool(line.expiry_after) and line.expiry_after != line.expiry_before
            line.is_difference = abs(line.difference) > 1e-6 or expiry_changed
            line.need_reprint = bool(line.package_id) and line.is_difference
