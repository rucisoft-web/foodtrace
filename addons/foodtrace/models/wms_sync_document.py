import json
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Satuan di file sinkron SAP yang berarti berat.
WEIGHT_UOMS = {"KG", "KGS"}


def _sap_date(text):
    """Tanggal SAP format MM/DD/YYYY."""
    if not text:
        return False
    return datetime.strptime(text.strip(), "%m/%d/%Y")


class WmsSyncDocument(models.Model):
    """Inbox dokumen dari SAP B1 (POR = PO inbound, SOR = SO outbound) sebelum dijadikan picking."""

    _name = "wms.sync.document"
    _description = "Dokumen sinkron SAP"
    _order = "create_date desc, id desc"

    name = fields.Char("Nomor", required=True, index=True)
    direction = fields.Selection([("inbound", "Inbound"), ("outbound", "Outbound")], required=True)
    doc_type = fields.Char("Jenis")
    obj_type = fields.Char("ObjType SAP")
    web_trans_no = fields.Char("Web trans no")
    doc_entry = fields.Char("DocEntry SAP")
    partner_code = fields.Char("Kode pemasok / tujuan")
    partner_name = fields.Char("Nama tujuan")
    warehouse_code = fields.Char("Gudang SAP")
    owner_code = fields.Char("Owner")
    shipping_group = fields.Char("Shipping group")
    vendor_ref = fields.Char("Ref. vendor / PO pelanggan")
    container_no = fields.Char("No. container")
    doc_date = fields.Date("Tanggal dokumen")
    delivery_date = fields.Date("Tanggal kirim")
    priority = fields.Char("Prioritas")
    sap_status = fields.Char("Status SAP")
    line_count = fields.Integer("Baris")
    payload = fields.Text("JSON", required=True)
    state = fields.Selection(
        [("new", "Baru"), ("done", "Jadi picking"), ("error", "Gagal")], default="new", required=True, index=True)
    error = fields.Text("Pesan gagal")
    picking_id = fields.Many2one("stock.picking", "Picking", readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    _sql_constraints = [("name_unique", "unique(company_id, name)", "Dokumen SAP ini sudah pernah diterima.")]

    @api.model
    def import_json(self, text, process=True):
        """Terima isi file sinkron (list JSON). Dokumen yang sudah ada dilewati (idempoten)."""
        data = json.loads(text) if isinstance(text, str) else text
        if isinstance(data, dict):
            data = [data]
        docs = self.browse()
        for doc in data:
            existing = self.search([("name", "=", doc["number"]), ("company_id", "=", self.env.company.id)], limit=1)
            if existing:
                docs |= existing
                continue
            docs |= self.create(self._vals_from_payload(doc))
        if process:
            docs.filtered(lambda d: d.state != "done").action_process()
        return docs

    @api.model
    def _vals_from_payload(self, doc):
        info = (doc.get("additional_information") or [{}])[0]
        outbound = "outbound_type" in doc
        return {
            "name": doc["number"],
            "direction": "outbound" if outbound else "inbound",
            "doc_type": doc.get("outbound_type") or doc.get("inbound_type"),
            "obj_type": doc.get("obj_type"),
            "web_trans_no": info.get("web_trans_no"),
            "doc_entry": info.get("doc_entry"),
            "partner_code": doc.get("destination_code") if outbound else doc.get("source"),
            "partner_name": doc.get("destination_outlet"),
            "warehouse_code": doc.get("warehouse"),
            "owner_code": doc.get("owner"),
            "shipping_group": doc.get("shipping_group"),
            "vendor_ref": info.get("vendor_ref_no") or info.get("vendor_do_no"),
            "container_no": info.get("container"),
            "doc_date": _sap_date(doc.get("po_date") or doc.get("date")),
            "delivery_date": _sap_date(doc.get("delivery_date") or doc.get("date")),
            "priority": doc.get("priority"),
            "sap_status": doc.get("status"),
            "line_count": len(doc.get("items") or []),
            "payload": json.dumps(doc, ensure_ascii=False, indent=2),
        }

    def _warehouse(self):
        Warehouse = self.env["stock.warehouse"]
        wh = Warehouse.search([("wms_sap_code", "=", self.warehouse_code), ("company_id", "=", self.company_id.id)],
                              limit=1)
        return wh or Warehouse.search([("company_id", "=", self.company_id.id)], limit=1)

    def _partner(self):
        Partner = self.env["res.partner"]
        partner = Partner.search([("ref", "=", self.partner_code)], limit=1) if self.partner_code else Partner
        if not partner and self.partner_code:
            partner = Partner.create({
                "name": self.partner_name or self.partner_code,
                "ref": self.partner_code,
                "is_company": True,
            })
        return partner

    def _owner(self):
        if not self.owner_code:
            return self.env["res.partner"]
        return self.env["res.partner"].search([("wms_owner_code", "=", self.owner_code)], limit=1)

    def action_process(self):
        Product = self.env["product.product"]
        for doc in self:
            try:
                with self.env.cr.savepoint():
                    payload = json.loads(doc.payload)
                    codes = [line["item_code"] for line in payload.get("items") or []]
                    products = {p.default_code: p for p in Product.search([("default_code", "in", codes)])}
                    missing = sorted({c for c in codes if c not in products})
                    if missing:
                        raise UserError(_("ItemCode belum ada di WMS: %s", ", ".join(missing)))
                    warehouse = doc._warehouse()
                    if not warehouse:
                        raise UserError(_("Gudang %s tidak ditemukan.", doc.warehouse_code))
                    ptype = warehouse.in_type_id if doc.direction == "inbound" else warehouse.out_type_id
                    partner = doc._partner()
                    src = ptype.default_location_src_id or self.env.ref("stock.stock_location_suppliers")
                    dst = ptype.default_location_dest_id or self.env.ref("stock.stock_location_customers")
                    if doc.direction == "inbound":
                        src = self.env.ref("stock.stock_location_suppliers")
                    else:
                        dst = self.env.ref("stock.stock_location_customers")
                    moves = []
                    for line in payload["items"]:
                        product = products[line["item_code"]]
                        uom = product.uom_id
                        if (line.get("uom_id") or "").upper() in WEIGHT_UOMS:
                            uom = self.env.ref("uom.product_uom_kgm")
                            if uom.category_id != product.uom_id.category_id:
                                uom = product.uom_id
                        moves.append((0, 0, {
                            "name": line.get("item_name") or product.display_name,
                            "product_id": product.id,
                            "product_uom": uom.id,
                            "product_uom_qty": float(line["qty"]),
                            "location_id": src.id,
                            "location_dest_id": dst.id,
                            "description_picking": (line.get("remark") or "").strip(),
                        }))
                    picking = self.env["stock.picking"].create({
                        "picking_type_id": ptype.id,
                        "partner_id": partner.id,
                        "owner_id": doc._owner().id,
                        "origin": doc.name,
                        "location_id": src.id,
                        "location_dest_id": dst.id,
                        "scheduled_date": doc.delivery_date or fields.Datetime.now(),
                        "wms_sync_id": doc.id,
                        "wms_shipping_group": doc.shipping_group,
                        "wms_priority": doc.priority,
                        "wms_vendor_ref": doc.vendor_ref,
                        "wms_container_no": doc.container_no,
                        "wms_inbound_type": doc._map_type("inbound"),
                        "wms_outbound_type": doc._map_type("outbound"),
                        "move_ids": moves,
                    })
                    picking.action_confirm()
                    doc.write({"state": "done", "picking_id": picking.id, "error": False})
            except UserError as exc:
                doc.write({"state": "error", "error": str(exc)})
        return True

    def _map_type(self, direction):
        if self.direction != direction:
            return False
        text = (self.doc_type or "").lower()
        table = {
            "inbound": [("purchase", "po"), ("titip", "titipan"), ("transfer", "transfer"), ("retur", "retur"),
                        ("return", "retur"), ("butcher", "butcher"), ("potong", "butcher"), ("sampl", "sampling")],
            "outbound": [("sales", "so"), ("butcher", "butcher"), ("produksi", "butcher"), ("musnah", "dispose"),
                         ("dispose", "dispose"), ("transfer", "transfer"), ("vendor", "rtv"), ("chill", "chill_frozen")],
        }[direction]
        return next((code for key, code in table if key in text), "po" if direction == "inbound" else "others")

    def action_open_picking(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "stock.picking", "res_id": self.picking_id.id,
                "view_mode": "form"}


class ResPartnerOwner(models.Model):
    _inherit = "res.partner"

    wms_owner_code = fields.Char("Kode owner WMS", help="Nilai 'owner' di file sinkron SAP, mis. 01-IGU", index=True)
