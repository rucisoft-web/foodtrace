from odoo import _, api, fields, models

DOC_TYPES = [
    ("grpo", "Goods Receipt PO"),
    ("delivery", "Delivery"),
    ("transfer", "Inventory Transfer"),
    ("adjustment", "Inventory Adjustment"),
    ("return", "Return"),
]


class WmsSapDocument(models.Model):
    """Antrean posting ke SAP B1 (Service Layer). Mode simulasi sampai konektor rasentra_sap_b1 dipasang."""

    _name = "wms.sap.document"
    _description = "Antrean posting SAP B1"
    _order = "create_date desc, id desc"

    name = fields.Char("Referensi unik", required=True, index=True, copy=False)
    picking_id = fields.Many2one("stock.picking", "Dokumen WMS", index=True)
    doc_type = fields.Selection(DOC_TYPES, "Jenis dokumen SAP", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    sap_company_db = fields.Char("Company DB SAP")
    state = fields.Selection(
        [("queued", "Antre"), ("posted", "Terkirim"), ("failed", "Gagal")],
        default="queued", required=True, index=True)
    sap_doc_num = fields.Char("DocNum SAP")
    error = fields.Text("Pesan gagal")
    attempts = fields.Integer("Percobaan")
    posted_at = fields.Datetime("Waktu terkirim")
    total_qty = fields.Float("Qty")
    total_weight = fields.Float("Berat (kg)")

    _sql_constraints = [("name_unique", "unique(name)", "Referensi posting SAP harus unik (cegah dobel posting).")]

    @api.model
    def _doc_type_for(self, picking):
        code = picking.picking_type_id.code
        if code == "incoming":
            return "return" if picking.origin and picking.origin.startswith("Return") else "grpo"
        if code == "outgoing":
            return "delivery"
        return "transfer"

    @api.model
    def enqueue_picking(self, picking):
        ref = f"WMS-{picking.company_id.id}-{picking.name}"
        if self.search_count([("name", "=", ref)]):
            return self.browse()
        lines = picking.move_ids.filtered(lambda m: m.state == "done")
        return self.create({
            "name": ref,
            "picking_id": picking.id,
            "doc_type": self._doc_type_for(picking),
            "company_id": picking.company_id.id,
            "sap_company_db": picking.company_id.wms_sap_company_db or picking.company_id.name,
            "total_qty": sum(lines.mapped("quantity")),
            "total_weight": sum(
                m.quantity for m in lines if m.product_uom.category_id == self.env.ref("uom.product_uom_categ_kgm")),
        })

    def action_post(self):
        """Simulasi Service Layer: tandai terkirim dan beri DocNum. Gagal bila item belum dipetakan."""
        for doc in self.filtered(lambda d: d.state != "posted"):
            doc.attempts += 1
            missing = doc.picking_id.move_ids.product_id.filtered(lambda p: not p.default_code)
            if missing:
                doc.write({"state": "failed", "error": _("Item tanpa ItemCode SAP: %s", ", ".join(missing.mapped("name")))})
                continue
            doc.write({
                "state": "posted",
                "error": False,
                "posted_at": fields.Datetime.now(),
                "sap_doc_num": str(100000 + doc.id),
            })
        return True

    @api.model
    def _cron_post_queue(self):
        self.search([("state", "=", "queued")], limit=200).action_post()


class ResCompany(models.Model):
    _inherit = "res.company"

    wms_sap_company_db = fields.Char("Company DB SAP B1")
