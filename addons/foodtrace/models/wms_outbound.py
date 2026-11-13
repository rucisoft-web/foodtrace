import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

OUT_STAGES = [
    ("open", "Open"),
    ("picking", "Picking in progress"),
    ("staged", "Di staging"),
    ("checked", "Sudah dicek"),
    ("loading", "Loading"),
    ("shipped", "Terkirim (GI)"),
    ("delivered", "Diterima customer (POD)"),
]


class StockLot(models.Model):
    _inherit = "stock.lot"

    wms_grade = fields.Char("Grade")
    wms_brand = fields.Char("Brand")
    wms_cutting_type = fields.Char("Cutting type")
    wms_pack_date = fields.Date("Pack date")
    wms_mfg_date = fields.Date("Tanggal produksi")
    wms_est = fields.Char("EST / RPH", help="Nomor establishment / rumah potong di label pemasok, mis. ME 21")


class StockPickingBatch(models.Model):
    """Picking Job (wave) ala Largo: gabungan beberapa outbound document per shipping group/tujuan."""

    _inherit = "stock.picking.batch"

    wms_use_tote = fields.Boolean("Pakai tote/tray")
    wms_driver = fields.Char("Nama driver")
    wms_transporter = fields.Char("Transporter ID / plat")
    wms_ready_pct = fields.Float("Ready (%)", compute="_compute_wms_ready", digits=(5, 1))
    wms_total_weight = fields.Float("Total berat (kg)", compute="_compute_wms_ready")

    @api.depends("picking_ids.move_ids.quantity", "picking_ids.move_ids.product_uom_qty")
    def _compute_wms_ready(self):
        kg = self.env.ref("uom.product_uom_categ_kgm")
        for batch in self:
            demand = sum(batch.move_ids.mapped("product_uom_qty"))
            batch.wms_ready_pct = (sum(batch.move_ids.mapped("quantity")) / demand * 100) if demand else 0.0
            batch.wms_total_weight = sum(
                m.quantity if m.product_uom.category_id == kg else m.quantity * (m.product_id.weight or 0)
                for m in batch.move_ids)


class StockPickingOutbound(models.Model):
    _inherit = "stock.picking"

    wms_stage = fields.Selection(OUT_STAGES, "Tahap outbound", default="open", copy=False, index=True)
    wms_staging_location_id = fields.Many2one("stock.location", "Outbound staging", copy=False)
    wms_loading_id = fields.Many2one("wms.loading", "Loading job", copy=False, index=True)
    wms_pod_id = fields.Many2one("wms.pod", "POD", copy=False)

    @api.model
    def action_wms_create_picking_job(self):
        """Dari daftar outbound document yang dicentang: buat Picking Job (wave) dan reservasi FEFO."""
        pickings = self.browse(self.env.context.get("active_ids", [])) or self
        pickings = pickings.filtered(lambda p: p.picking_type_code == "outgoing" and p.state not in ("done", "cancel"))
        if not pickings:
            raise UserError(_("Pilih outbound document yang belum selesai."))
        to_assign = pickings.filtered(lambda p: p.state in ("confirmed", "waiting"))
        if to_assign:
            to_assign.action_assign()
        groups = sorted({p.wms_shipping_group for p in pickings if p.wms_shipping_group})
        batch = self.env["stock.picking.batch"].create({
            "picking_ids": [(6, 0, pickings.ids)],
            "description": ", ".join(groups) or _("Picking job"),
            "company_id": pickings.company_id[:1].id,
        })
        batch.action_confirm()
        pickings.write({"wms_stage": "open"})
        return {"type": "ir.actions.act_window", "res_model": "stock.picking.batch", "res_id": batch.id,
                "view_mode": "form"}

    def _wms_set_stage(self, stage):
        self.write({"wms_stage": stage})


class StockMoveLineOutbound(models.Model):
    _inherit = "stock.move.line"

    wms_checked = fields.Boolean("Dicek checker", copy=False)
    wms_loaded = fields.Boolean("Dimuat", copy=False)


class WmsLoading(models.Model):
    """Loading Job: daftar outbound yang dimuat ke satu kendaraan; mencetak manifest dan surat jalan."""

    _name = "wms.loading"
    _description = "Loading job"
    _order = "date desc, id desc"

    name = fields.Char("Nomor", required=True, copy=False, default=lambda self: _("Baru"))
    date = fields.Date("Tanggal muat", required=True, default=fields.Date.context_today)
    driver = fields.Char("Nama pengemudi")
    vehicle_plate = fields.Char("Plat nomor kendaraan")
    picking_ids = fields.One2many("stock.picking", "wms_loading_id", "Outbound document",
                                  domain=[("picking_type_code", "=", "outgoing")])
    state = fields.Selection([("open", "Open"), ("close", "Close"), ("cancel", "Cancel")], default="open", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    line_count = fields.Integer("LPN / baris", compute="_compute_progress")
    loaded_count = fields.Integer("Sudah dimuat", compute="_compute_progress")
    total_weight = fields.Float("Total berat (kg)", compute="_compute_progress")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Baru")) == _("Baru"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.loading") or _("Baru")
        return super().create(vals_list)

    @api.depends("picking_ids.move_line_ids.wms_loaded")
    def _compute_progress(self):
        kg = self.env.ref("uom.product_uom_categ_kgm")
        for job in self:
            lines = job.picking_ids.move_line_ids
            job.line_count = len(lines)
            job.loaded_count = len(lines.filtered("wms_loaded"))
            job.total_weight = sum(l.quantity for l in lines if l.product_uom_id.category_id == kg)

    def load_scan(self, code):
        """Scan LPN / lot / item di dock: tandai dimuat. Barang yang bukan untuk kendaraan ini ditolak."""
        self.ensure_one()
        code = (code or "").strip()
        lines = self.picking_ids.move_line_ids.filtered(
            lambda l: not l.wms_loaded and code in (l.result_package_id.name, l.package_id.name, l.lot_id.name,
                                                   l.product_id.default_code))
        if not lines:
            raise UserError(_("%s bukan muatan kendaraan ini atau sudah dimuat.", code))
        pack_lines = lines.filtered(lambda l: code in (l.result_package_id.name, l.package_id.name))
        target = pack_lines or lines[:1]
        target.write({"wms_loaded": True})
        target.picking_id._wms_set_stage("loading")
        return target

    def action_close(self):
        """Loading selesai: Goods Issue untuk semua outbound, buat POD per outbound."""
        for job in self:
            missing = job.picking_ids.move_line_ids.filtered(lambda l: not l.wms_loaded)
            if missing and not self.env.context.get("wms_force_close"):
                raise UserError(_("%s baris belum discan muat.", len(missing)))
            for picking in job.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
                picking.move_line_ids.write({"picked": True})
                picking.with_context(skip_backorder=True, wms_skip_checks=True).button_validate()
                picking._wms_set_stage("shipped")
            for picking in job.picking_ids.filtered(lambda p: not p.wms_pod_id):
                picking.wms_pod_id = self.env["wms.pod"].create_for_picking(picking)
            job.state = "close"
        return True

    def action_cancel(self):
        """Cancel loading: semua LPN kembali aktif di outbound staging."""
        for job in self:
            job.picking_ids.move_line_ids.write({"wms_loaded": False})
            job.picking_ids.filtered(lambda p: p.state != "done")._wms_set_stage("checked")
            job.picking_ids = [(5, 0, 0)]
            job.state = "cancel"
        return True

    def action_print_manifest(self):
        return self.env.ref("foodtrace.action_report_manifest").report_action(self)

    def action_print_surat_jalan(self):
        if any(j.state != "close" for j in self):
            raise UserError(_("Surat jalan dicetak setelah loading selesai (status Close)."))
        return self.env.ref("foodtrace.action_report_surat_jalan").report_action(self.picking_ids)


class WmsPod(models.Model):
    """Proof of Delivery: driver mengisi qty diterima, suhu (wajib) dan foto lewat tautan di surat jalan."""

    _name = "wms.pod"
    _description = "Proof of delivery"
    _order = "id desc"

    name = fields.Char(required=True)
    picking_id = fields.Many2one("stock.picking", "Outbound", required=True, ondelete="cascade")
    partner_id = fields.Many2one(related="picking_id.partner_id", string="Customer")
    loading_id = fields.Many2one(related="picking_id.wms_loading_id")
    token = fields.Char(required=True, copy=False, default=lambda self: uuid.uuid4().hex, index=True)
    state = fields.Selection([("open", "Dalam perjalanan"), ("done", "Diterima")], default="open", required=True)
    received_by = fields.Char("Diterima oleh")
    received_at = fields.Datetime("Waktu terima")
    photo = fields.Image("Foto bukti", max_width=1600, max_height=1600)
    remark = fields.Text("Catatan")
    line_ids = fields.One2many("wms.pod.line", "pod_id", "Barang")
    has_difference = fields.Boolean("Ada selisih", compute="_compute_difference", store=True)
    company_id = fields.Many2one(related="picking_id.company_id", store=True)

    @api.depends("line_ids.qty_received", "line_ids.qty_sent", "state")
    def _compute_difference(self):
        for pod in self:
            pod.has_difference = pod.state == "done" and any(
                abs(l.qty_received - l.qty_sent) > 1e-6 for l in pod.line_ids)

    @api.model
    def create_for_picking(self, picking):
        lines = []
        for move in picking.move_ids.filtered(lambda m: m.state == "done"):
            lines.append((0, 0, {"product_id": move.product_id.id, "qty_sent": move.quantity,
                                 "qty_received": move.quantity, "uom_id": move.product_uom.id}))
        return self.create({"name": picking.name, "picking_id": picking.id, "line_ids": lines})

    def get_url(self):
        self.ensure_one()
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base}/wms/pod/{self.token}"

    def submit(self, received_by, lines, photo=None, remark=None):
        self.ensure_one()
        if self.state == "done":
            raise UserError(_("POD ini sudah diisi."))
        if not (received_by or "").strip():
            raise UserError(_("Nama penerima wajib diisi."))
        for line in self.line_ids:
            if str(line.id) in lines:
                line.qty_received = float(lines[str(line.id)].get("qty") or 0)
                line.remark = lines[str(line.id)].get("remark")
        self.write({"received_by": received_by, "remark": remark,
                    "photo": photo or False, "state": "done", "received_at": fields.Datetime.now()})
        self.picking_id._wms_set_stage("delivered")
        return True


class WmsPodLine(models.Model):
    _name = "wms.pod.line"
    _description = "Baris POD"

    pod_id = fields.Many2one("wms.pod", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", "Item", required=True)
    uom_id = fields.Many2one("uom.uom", "Satuan")
    qty_sent = fields.Float("Qty dikirim")
    qty_received = fields.Float("Qty diterima")
    remark = fields.Char("Remark")
