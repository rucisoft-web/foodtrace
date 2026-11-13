from odoo import _, api, fields, models
from odoo.exceptions import UserError

BUTCHER_TYPES = [
    ("rebag", "Rebag"),
    ("nonrebag", "Non rebag"),
    ("trimming", "Trimming"),
    ("sisa_potong", "Sisa potong"),
    ("repack", "Repack"),
]


class WmsButcher(models.Model):
    """Butcher ala Largo.

    Butcher Out: bahan (LPN) dikeluarkan dari gudang ke ruang potong (lokasi produksi).
    Butcher In: hasil potong/repack masuk kembali sebagai lot dan LPN baru, lengkap dengan grade, brand,
    cutting type dan expiry. Yield = berat hasil / berat bahan.
    """

    _name = "wms.butcher"
    _description = "Butcher / repack"
    _order = "id desc"

    name = fields.Char("Nomor", required=True, copy=False, default=lambda self: _("Baru"))
    kind = fields.Selection([("out", "Butcher Out (bahan keluar)"), ("in", "Butcher In (hasil masuk)")],
                            "Jenis", required=True, default="out")
    ref = fields.Char("Ref. dokumen / SPK")
    source_id = fields.Many2one("wms.butcher", "Butcher Out asal", domain=[("kind", "=", "out")])
    date = fields.Datetime("Tanggal", default=fields.Datetime.now, required=True)
    user_id = fields.Many2one("res.users", "Petugas", default=lambda self: self.env.user)
    state = fields.Selection([("draft", "Draft"), ("done", "Selesai"), ("cancel", "Batal")],
                             default="draft", required=True)
    line_ids = fields.One2many("wms.butcher.line", "butcher_id", "Baris")
    move_ids = fields.Many2many("stock.move", string="Pergerakan stok", readonly=True, copy=False)
    total_kg = fields.Float("Total berat (kg)", compute="_compute_totals", store=True)
    yield_pct = fields.Float("Yield (%)", compute="_compute_yield", digits=(5, 1))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Baru")) == _("Baru"):
                code = "wms.butcher.in" if vals.get("kind") == "in" else "wms.butcher.out"
                vals["name"] = self.env["ir.sequence"].next_by_code(code) or _("Baru")
        return super().create(vals_list)

    @api.depends("line_ids.qty_kg")
    def _compute_totals(self):
        for doc in self:
            doc.total_kg = sum(doc.line_ids.mapped("qty_kg"))

    def _compute_yield(self):
        for doc in self:
            out = doc if doc.kind == "out" else doc.source_id
            ins = self.search([("source_id", "=", out.id), ("state", "=", "done")]) if out else doc
            base = out.total_kg if out else 0.0
            doc.yield_pct = sum(ins.mapped("total_kg")) / base * 100 if base else 0.0

    def _production_location(self, product):
        loc = product.with_company(self.company_id).property_stock_production
        if not loc:
            loc = self.env["stock.location"].search(
                [("usage", "=", "production"), ("company_id", "in", [self.company_id.id, False])], limit=1)
        if not loc:
            raise UserError(_("Lokasi produksi (ruang potong) belum ada."))
        return loc

    def _make_move(self, line, src, dest, lot, package_src=False, package_dest=False):
        product = line.product_id
        move = self.env["stock.move"].create({
            "name": f"{self.name}: {product.display_name}", "product_id": product.id,
            "product_uom_qty": line.qty, "product_uom": product.uom_id.id,
            "location_id": src.id, "location_dest_id": dest.id, "company_id": self.company_id.id,
            "origin": self.ref or self.name, "is_inventory": False,
        })
        move._action_confirm()
        move.move_line_ids.unlink()
        self.env["stock.move.line"].create({
            "move_id": move.id, "product_id": product.id, "product_uom_id": product.uom_id.id,
            "quantity": line.qty, "lot_id": lot.id if lot else False, "location_id": src.id,
            "location_dest_id": dest.id, "package_id": package_src.id if package_src else False,
            "result_package_id": package_dest.id if package_dest else False,
        })
        move.picked = True
        move._action_done()
        return move

    def action_done(self):
        for doc in self:
            if doc.state != "draft":
                continue
            if not doc.line_ids:
                raise UserError(_("Isi baris dulu."))
            moves = self.env["stock.move"]
            for line in doc.line_ids:
                if line.qty <= 0:
                    raise UserError(_("Qty %s harus lebih dari 0.", line.product_id.display_name))
                prod = doc._production_location(line.product_id)
                if doc.kind == "out":
                    src = line.package_id.location_id or line.location_id
                    if not src:
                        raise UserError(_("Scan LPN atau isi lokasi asal untuk %s.", line.product_id.display_name))
                    moves |= doc._make_move(line, src, prod, line.lot_id or line.package_id.wms_lot_id,
                                            package_src=line.package_id)
                else:
                    if not line.location_id:
                        raise UserError(_("Isi lokasi simpan untuk hasil %s.", line.product_id.display_name))
                    lot = line._create_result_lot()
                    pack = self.env["stock.quant.package"].create({
                        "wms_pack_date": fields.Date.context_today(self), "wms_closed": True,
                        "wms_remark": dict(BUTCHER_TYPES).get(line.process_type)})
                    moves |= doc._make_move(line, prod, line.location_id, lot, package_dest=pack)
                    line.write({"lot_id": lot.id, "package_id": pack.id})
            doc.write({"state": "done", "move_ids": [(4, m) for m in moves.ids]})
        return True

    def action_cancel(self):
        if any(d.state == "done" for d in self):
            raise UserError(_("Dokumen yang sudah selesai tidak bisa dibatalkan; buat dokumen koreksi."))
        self.write({"state": "cancel"})
        return True

    def action_print_labels(self):
        packs = self.line_ids.package_id
        return self.env.ref("foodtrace.action_report_lpn_label").report_action(packs)


class WmsButcherLine(models.Model):
    _name = "wms.butcher.line"
    _description = "Baris butcher"

    butcher_id = fields.Many2one("wms.butcher", required=True, ondelete="cascade")
    kind = fields.Selection(related="butcher_id.kind")
    process_type = fields.Selection(BUTCHER_TYPES, "Proses", default="rebag")
    package_id = fields.Many2one("stock.quant.package", "LPN")
    product_id = fields.Many2one("product.product", "Item", required=True)
    lot_id = fields.Many2one("stock.lot", "Lot")
    location_id = fields.Many2one("stock.location", "Lokasi", domain=[("usage", "=", "internal")])
    qty = fields.Float("Qty", required=True, default=1.0)
    uom_id = fields.Many2one(related="product_id.uom_id", string="Satuan")
    qty_kg = fields.Float("Berat (kg)", compute="_compute_qty_kg", store=True)
    grade = fields.Char("Grade")
    brand = fields.Char("Brand")
    cutting_type = fields.Char("Cutting type")
    lot_name = fields.Char("Lot hasil", help="Kosong = dibuat otomatis dari nomor dokumen.")
    expiration_date = fields.Datetime("Expiry hasil")

    @api.depends("qty", "product_id.uom_id", "product_id.weight")
    def _compute_qty_kg(self):
        kg = self.env.ref("uom.product_uom_categ_kgm")
        for line in self:
            uom = line.product_id.uom_id
            line.qty_kg = uom._compute_quantity(line.qty, self.env.ref("uom.product_uom_kgm")) \
                if uom.category_id == kg else line.qty * (line.product_id.weight or 0.0)

    @api.onchange("package_id")
    def _onchange_package(self):
        if self.package_id:
            self.product_id = self.package_id.wms_product_id
            self.lot_id = self.package_id.wms_lot_id
            self.location_id = self.package_id.location_id
            self.qty = self.package_id.wms_qty

    def _create_result_lot(self):
        self.ensure_one()
        doc = self.butcher_id
        name = self.lot_name or f"{doc.name}-{self.id}"
        expiry = self.expiration_date
        if not expiry and self.product_id.expiration_time:
            expiry = fields.Datetime.add(fields.Datetime.now(), days=self.product_id.expiration_time)
        return self.env["stock.lot"].create({
            "name": name, "product_id": self.product_id.id, "company_id": doc.company_id.id,
            "expiration_date": expiry, "wms_grade": self.grade, "wms_brand": self.brand,
            "wms_cutting_type": self.cutting_type, "wms_pack_date": fields.Date.context_today(self),
        })
