from collections import defaultdict
from datetime import datetime, timedelta

from odoo import api, fields, models

from .wms_zone import STOCK_STATUS, ZONES

# Periode laporan expired mengikuti URS Largo: 1, 2, 3 (widget), 4 bulan.
EXPIRY_BUCKETS = [
    ("expired", "Kedaluwarsa", None, 0),
    ("m1", "≤ 1 bulan", 0, 30),
    ("m2", "1-2 bulan", 30, 60),
    ("m3", "2-3 bulan", 60, 90),
    ("m4", "3-4 bulan", 90, 120),
    ("m6", "4-6 bulan", 120, 180),
    ("long", "> 6 bulan", 180, None),
]


class WmsDashboard(models.AbstractModel):
    """Angka dashboard gudang untuk perusahaan aktif: stok per zona, kedaluwarsa, suhu, arus barang, SAP."""

    _name = "wms.dashboard"
    _description = "Dashboard WMS"

    @api.model
    def _bucket(self, days):
        for key, _label, low, high in EXPIRY_BUCKETS:
            if low is None and days < 0:
                return key
            if low is not None and days >= low and (high is None or days < high):
                return key
        return "long"

    @api.model
    def summary(self, warehouse_id=None):
        company = self.env.company
        now = datetime.now()
        Warehouse = self.env["stock.warehouse"]
        warehouses = Warehouse.search([("company_id", "=", company.id)])
        warehouse = Warehouse.browse(warehouse_id) if warehouse_id else warehouses[:1]
        root = warehouse.view_location_id
        standards = {s.zone: s for s in self.env["wms.zone.standard"].search([])}

        quants = self.env["stock.quant"].search([
            ("location_id", "child_of", root.id), ("location_id.usage", "=", "internal"), ("quantity", ">", 0)])
        zone_label = dict(ZONES)
        by_zone = defaultdict(lambda: {"value": 0.0, "items": set(), "lots": set()})
        by_group = defaultdict(float)
        by_item = defaultdict(lambda: {"value": 0.0, "qty": 0.0})
        buckets = defaultdict(float)
        bucket_by_zone = defaultdict(lambda: defaultdict(float))
        near = []
        total = quarantine = expired_value = near_value = 0.0
        occupied = defaultdict(set)
        by_status = defaultdict(float)
        m3_value = 0.0
        for q in quants:
            product = q.product_id
            value = q.quantity * product.standard_price
            zone = product.wms_zone or "dry"
            total += value
            by_status[q.wms_status or "available"] += value
            z = by_zone[zone]
            z["value"] += value
            z["items"].add(product.id)
            if q.lot_id:
                z["lots"].add(q.lot_id.id)
            by_group[product.wms_item_group or product.categ_id.name] += value
            item = by_item[product.id]
            item["value"] += value
            item["qty"] += q.quantity
            if q.location_id.wms_area == "qc":
                quarantine += value
            if q.location_id.wms_area == "blk":
                occupied[q.location_id._wms_effective_zone() or zone].add(q.location_id.id)
            exp = q.lot_id.expiration_date
            if exp:
                days = (exp - now).total_seconds() / 86400.0
                key = self._bucket(days)
                buckets[key] += value
                bucket_by_zone[key][zone] += value
                if days < 0:
                    expired_value += value
                elif days <= 30:
                    near_value += value
                if 0 <= days <= 90:
                    m3_value += value
                if days <= 30:
                    near.append({
                        "product": product.display_name, "lot": q.lot_id.name, "zone": zone,
                        "location": q.location_id.name, "days": int(days // 1) if days >= 0 else int(days),
                        "qty": round(q.quantity, 3), "uom": product.uom_id.name, "value": round(value),
                    })
        near.sort(key=lambda r: r["days"])

        # Okupansi rak palet utuh per zona.
        positions = self.env["stock.location"].search([
            ("location_id", "child_of", root.id), ("wms_area", "=", "blk"), ("child_ids", "=", False)])
        capacity = defaultdict(int)
        for loc in positions:
            capacity[loc._wms_effective_zone() or "dry"] += 1

        # Arus barang 30 hari (nilai) per hari.
        start = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        moves = self.env["stock.move"].search([
            ("state", "=", "done"), ("date", ">=", start), ("company_id", "=", company.id),
            ("picking_type_id.code", "in", ("incoming", "outgoing"))])
        flow = {(start + timedelta(days=i)).date().isoformat(): {"in": 0.0, "out": 0.0, "in_docs": set(), "out_docs": set()}
                for i in range(30)}
        for m in moves:
            day = fields.Datetime.context_timestamp(self, m.date).date().isoformat()
            if day not in flow:
                continue
            key = "in" if m.picking_type_id.code == "incoming" else "out"
            flow[day][key] += m.product_qty * m.product_id.standard_price
            flow[day][key + "_docs"].add(m.picking_id.id)

        # Pekerjaan hari ini dan status SAP.
        Picking = self.env["stock.picking"]
        open_domain = [("company_id", "=", company.id), ("state", "in", ("confirmed", "waiting", "assigned"))]
        sap = self.env["wms.sap.document"].read_group(
            [("company_id", "=", company.id)], ["state"], ["state"])
        sap_counts = {g["state"]: g["state_count"] for g in sap}
        stale = self.env["wms.sap.document"].search_count([
            ("company_id", "=", company.id), ("state", "!=", "posted"),
            ("create_date", "<", now - timedelta(days=1))])
        sync_err = self.env["wms.sync.document"].search_count(
            [("company_id", "=", company.id), ("state", "=", "error")])
        cartons = self.env["wms.carton"].search_count(
            [("company_id", "=", company.id), ("state", "in", ("available", "quarantine"))])

        low = self.env["product.product"].search([("wms_is_low", "=", True)], limit=10)

        top = sorted(by_item.items(), key=lambda kv: -kv[1]["value"])[:10]
        products = {p.id: p for p in self.env["product.product"].browse([k for k, _v in top])}

        def zone_row(zone):
            std = standards.get(zone)
            return {
                "zone": zone,
                "label": zone_label[zone],
                "color": std.color if std else "#64748b",
                "value": round(by_zone[zone]["value"]),
                "items": len(by_zone[zone]["items"]),
                "lots": len(by_zone[zone]["lots"]),
                "positions": capacity.get(zone, 0),
                "occupied": len(occupied.get(zone, ())),
            }

        return {
            "company": company.name,
            "warehouse": warehouse.name,
            "warehouses": [{"id": w.id, "name": w.name} for w in warehouses],
            "generated": fields.Datetime.to_string(fields.Datetime.now()),
            "kpi": {
                "value": round(total),
                "items": len(by_item),
                "lots": len({q.lot_id.id for q in quants if q.lot_id}),
                "cartons": cartons,
                "near_value": round(near_value),
                "near_count": len([n for n in near if n["days"] >= 0]),
                "m3_value": round(m3_value),
                "item_low": self.env["product.product"].search_count([("wms_is_low", "=", True)]),
                "expired_value": round(expired_value),
                "quarantine": round(quarantine),
                "receipts_open": Picking.search_count(open_domain + [("picking_type_code", "=", "incoming")]),
                "deliveries_open": Picking.search_count(open_domain + [("picking_type_code", "=", "outgoing")]),
                "sap_failed": sap_counts.get("failed", 0),
                "sap_queued": sap_counts.get("queued", 0),
                "sap_stale": stale,
                "sync_errors": sync_err,
            },
            "zones": [zone_row(z) for z, _l in ZONES],
            "expiry": {
                "labels": [b[1] for b in EXPIRY_BUCKETS],
                "keys": [b[0] for b in EXPIRY_BUCKETS],
                "by_zone": {z: [round(bucket_by_zone[b[0]][z]) for b in EXPIRY_BUCKETS] for z, _l in ZONES},
            },
            "groups": [{"name": k, "value": round(v)} for k, v in sorted(by_group.items(), key=lambda kv: -kv[1])],
            "top_items": [{
                "id": pid, "name": products[pid].name, "code": products[pid].default_code,
                "zone": products[pid].wms_zone, "qty": round(v["qty"], 2), "uom": products[pid].uom_id.name,
                "value": round(v["value"])} for pid, v in top],
            "flow": {
                "days": list(flow),
                "in": [round(v["in"]) for v in flow.values()],
                "out": [round(v["out"]) for v in flow.values()],
                "in_docs": [len(v["in_docs"]) for v in flow.values()],
                "out_docs": [len(v["out_docs"]) for v in flow.values()],
            },
            "status": [{"key": k, "label": label, "value": round(by_status.get(k, 0.0))} for k, label in STOCK_STATUS],
            "item_low": [{"id": p.id, "name": p.name, "code": p.default_code, "qty": round(p.qty_available, 2),
                          "min": p.wms_min_stock, "uom": p.uom_id.name} for p in low],
            "sap": {k: sap_counts.get(k, 0) for k in ("posted", "queued", "failed")},
            "near_expiry": near[:10],
        }
