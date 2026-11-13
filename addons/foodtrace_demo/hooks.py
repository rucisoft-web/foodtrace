"""Data demo WMS PT Sarana Kulina Intisejahtera.

Sumber: saldo akhir persediaan per 1 Januari 2025 (company 95, GENERAL WAREHOUSE), 615 item dengan zona usulan.
Saldo dipakai sebagai stok awal; di atasnya dibangun arus 30 hari terakhir, log suhu 14 hari, dokumen sinkron
SAP, antrean posting, picking job, loading, POD, inventory check dan butcher, sehingga dashboard dan semua menu
langsung berisi data yang masuk akal.
"""

import csv
import json
import logging
import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

_logger = logging.getLogger(__name__)

DATA = Path(__file__).parent / "data"

ZONE_CODE = {"frozen": "FZ", "chilled": "CH", "dry": "DR"}
ZONE_NAME = {"frozen": "Frozen", "chilled": "Chilled", "dry": "Dry"}
# Rak palet (baris × bay × level) per zona.
RACKS = {"frozen": (6, 6, 4), "chilled": (6, 8, 4), "dry": (8, 8, 4)}
SHELF_LIFE = {"frozen": 540, "chilled": 120, "dry": 365}

CUSTOMERS = [
    ("C-HTL001", "Hotel Nusantara Indah", "RUTE-01", 60),
    ("C-HTL002", "Hotel Pantai Losari Permai", "RUTE-01", 60),
    ("C-RST001", "Resto Pelangi Rasa", "RUTE-02", 0),
    ("C-RST002", "Resto Dapur Sulawesi", "RUTE-02", 0),
    ("C-CAF001", "Cafe Senja Kopi", "RUTE-03", 0),
    ("C-BAK001", "Bakery Mawar Sari", "RUTE-03", 40),
    ("C-CTR001", "Catering Sejahtera Bersama", "RUTE-04", 0),
    ("C-RTL001", "Swalayan Segar Jaya", "RUTE-04", 50),
    ("C-RST003", "Steakhouse Bara Api", "RUTE-02", 0),
    ("C-HTL003", "Hotel Bukit Karst", "RUTE-05", 60),
    ("C-RST004", "Pizzeria Nonna", "RUTE-05", 0),
    ("C-CAF002", "Kedai Teh Daun", "RUTE-03", 0),
]
SUPPLIERS = [
    ("VL0101", "PT Daging Impor Nusantara", 2),
    ("VL0102", "PT Seafood Samudra Timur", 0),
    ("VL0103", "CV Dairy Prima", 5),
    ("VL0104", "PT Bahan Kue Sentosa", 3),
    ("VL0105", "PT Frozen Food Makmur", 0),
]


def post_init_hook(env):
    Demo(env).run()


class Demo:
    def __init__(self, env):
        self.rnd = random.Random(95)
        self.now = datetime.now().replace(microsecond=0)
        self.base_env = env
        self.env = env

    # ------------------------------------------------------------------ main
    def run(self):
        _logger.info("FoodTrace demo: membuat data Sarana Kulina")
        self._company()
        self._settings()
        self._locations()
        self._partners()
        self._products()
        self._opening_stock()
        self._history()
        self._open_work()
        self._sync_documents()
        self._sap_queue()
        self._inventory_and_butcher()
        _logger.info("FoodTrace demo selesai")

    # ---------------------------------------------------------------- company
    def _company(self):
        env = self.base_env
        idr = env.ref("base.IDR")
        idr.active = True
        company = env["res.company"].create({
            "name": "PT Sarana Kulina Intisejahtera", "currency_id": idr.id,
            "wms_sap_company_db": "SBO_SARANA_KULINA", "city": "Makassar",
            "country_id": env.ref("base.id").id,
        })
        admin = env.ref("base.user_admin")
        admin.write({"company_ids": [(4, company.id)], "company_id": company.id})
        env.ref("base.user_root").write({"company_ids": [(4, company.id)]})
        self.company = company
        self.env = env(context=dict(env.context, allowed_company_ids=[company.id], tz="Asia/Makassar",
                                    tracking_disable=True, mail_create_nolog=True, mail_notrack=True))
        company = self.company = self.env["res.company"].browse(company.id)
        self.wh = self.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
        if self.wh:
            self.wh.write({"name": "GENERAL WAREHOUSE", "code": "SKI", "wms_sap_code": "95-SKI"})
        else:
            self.wh = self.env["stock.warehouse"].create({
                "name": "GENERAL WAREHOUSE", "code": "SKI", "company_id": company.id, "wms_sap_code": "95-SKI",
                "partner_id": company.partner_id.id})
        company.partner_id.write({"wms_owner_code": "95-SKI", "ref": "95-SKI"})
        # Picking Job dibuat sengaja oleh admin outbound, bukan batch otomatis per partner.
        self.env["stock.picking.type"].search([("company_id", "=", company.id)]).write({"auto_batch": False})
        self.env["ir.config_parameter"].sudo().set_param("foodtrace.sync_token", "demo-ski-token")

    def _settings(self):
        user_group = self.env.ref("base.group_user")
        for xmlid in ("stock.group_production_lot", "stock.group_stock_multi_locations",
                      "stock.group_tracking_lot", "stock.group_tracking_owner", "uom.group_uom"):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                user_group.write({"implied_ids": [(4, group.id)]})

    # -------------------------------------------------------------- locations
    def _locations(self):
        Loc = self.env["stock.location"]
        stock = self.wh.lot_stock_id
        stock.barcode = "SKI-STOCK"
        self.rooms, self.bins, self.qc, self.dmg, self.pck = {}, {}, {}, {}, {}
        for zone, code in ZONE_CODE.items():
            room = Loc.create({"name": code, "location_id": stock.id, "wms_zone": zone, "wms_area": "room",
                               "barcode": f"SKI-{code}"})
            self.rooms[zone] = room
            blk = Loc.create({"name": "BLK", "location_id": room.id, "wms_area": "blk", "barcode": f"SKI-{code}-BLK"})
            rows, bays, levels = RACKS[zone]
            vals = []
            for r in range(rows):
                for b in range(1, bays + 1):
                    for lv in range(1, levels + 1):
                        name = f"{chr(65 + r)}{b:02d}-{lv}"
                        vals.append({"name": name, "location_id": blk.id, "wms_area": "blk", "wms_max_pallets": 1,
                                     "wms_max_weight": 1000, "barcode": f"SKI-{code}-{name}"})
            self.bins[zone] = Loc.create(vals)
            self.pck[zone] = Loc.create({"name": "PCK", "location_id": room.id, "wms_area": "pck",
                                         "barcode": f"SKI-{code}-PCK"})
            self.qc[zone] = Loc.create({"name": "QC", "location_id": room.id, "wms_area": "qc", "wms_zone": zone,
                                        "barcode": f"SKI-{code}-QC"})
            self.dmg[zone] = Loc.create({"name": "DMG", "location_id": room.id, "wms_area": "dmg", "wms_zone": zone,
                                         "barcode": f"SKI-{code}-DMG"})
        self.docks = Loc.create([{"name": f"DOCK_{n:02d}", "location_id": stock.id, "wms_area": "rcv",
                                  "barcode": f"DOCK_{n:02d}"} for n in (1, 2, 3)])
        self.staging = Loc.create({"name": "OUT-STAGING", "location_id": stock.id, "wms_area": "out",
                                   "barcode": "SKI-OUT"})
        Loc.create({"name": "RTN", "location_id": stock.id, "wms_area": "rtn", "barcode": "SKI-RTN"})
        Loc.create({"name": "WASTE", "location_id": stock.id, "wms_area": "wst", "barcode": "SKI-WST"})
        Loc.create({"name": "BUTCHER-ROOM", "location_id": stock.id, "wms_area": "prd", "wms_zone": "chilled",
                    "barcode": "SKI-PRD"})
        # Bin yang terisi: ±85% posisi, sisanya kosong untuk saran put away.
        self.used_bins = {}
        for zone, bins in self.bins.items():
            ids = list(bins.ids)
            self.rnd.shuffle(ids)
            self.used_bins[zone] = self.env["stock.location"].browse(ids[: int(len(ids) * 0.85)])
        self._bin_cursor = defaultdict(int)

    def _next_bin(self, zone):
        bins = self.used_bins[zone]
        loc = bins[self._bin_cursor[zone] % len(bins)]
        self._bin_cursor[zone] += 1
        return loc

    # --------------------------------------------------------------- partners
    def _partners(self):
        Partner = self.env["res.partner"]
        self.customers = Partner
        self.route = {}
        for ref, name, group, life in CUSTOMERS:
            partner = Partner.create({
                "name": name, "ref": ref, "city": "Makassar", "is_company": True,
                "wms_min_shelf_life_pct": life})
            self.customers |= partner
            partner.wms_is_destination = True
            self.route[partner.id] = group
        self.suppliers = Partner
        for ref, name, tol in SUPPLIERS:
            self.suppliers |= Partner.create({"name": name, "ref": ref, "is_company": True,
                                              "wms_over_receive_pct": tol, "wms_is_source": True})

    # --------------------------------------------------------------- products
    def _products(self):
        env = self.env
        kg = env.ref("uom.product_uom_kgm")
        units = env.ref("uom.product_uom_unit")
        fefo = env.ref("product_expiry.removal_fefo")
        root = env["product.category"].create({"name": "Indoguna", "removal_strategy_id": fefo.id})
        categories = {}
        rows = list(csv.DictReader((DATA / "saldo_sarana_kulina_20250101.csv").open(encoding="utf-8")))
        vals = []
        for row in rows:
            group = row["item_group"] or "LAIN-LAIN"
            if group not in categories:
                categories[group] = env["product.category"].create({"name": group, "parent_id": root.id})
            zone = row["zone"]
            qty, value = float(row["qty"]), float(row["value"])
            catch = row["catch_weight"] == "1"
            life = SHELF_LIFE[zone]
            vals.append({
                "name": row["item_name"], "default_code": row["item_code"], "is_storable": True,
                "tracking": "lot", "use_expiration_date": True, "expiration_time": life,
                "use_time": max(1, life - 30), "removal_time": max(1, life - 7), "alert_time": 30,
                "uom_id": (kg if catch else units).id, "uom_po_id": (kg if catch else units).id,
                "categ_id": categories[group].id, "wms_zone": zone, "wms_catch_weight": catch,
                "wms_item_group": group, "wms_sub_group": row["sub_group"], "wms_country": row["country"],
                "standard_price": round(value / qty, 2) if qty else 0.0,
                "wms_min_receive_life_pct": {"frozen": 50, "chilled": 60, "dry": 40}[zone],
                "wms_units_per_pallet": 60 if not catch else 0, "weight": 1.0 if catch else 0.0,
                "wms_picking_strategy": "fefo",
            })
        templates = env["product.template"].with_company(self.company).create(vals)
        self.rows = {row["item_code"]: row for row in rows}
        self.products = {t.default_code: t.product_variant_id for t in templates}
        # Item yang wajib karantina saat terima (impor seafood/caviar) dan dilepas otomatis setelah 2 hari.
        quarantine = [t for t in templates if t.wms_sub_group in ("CAVIAR",)][:5]
        for t in quarantine:
            t.write({"wms_auto_quarantine": True, "wms_auto_release": True, "wms_quarantine_days": 2})
        # Format barcode karton GS1 untuk item berat aktual.
        catch_tmpls = templates.filtered("wms_catch_weight")
        env["wms.barcode.template"].create({
            "name": "GS1-128 berat kg (AI 3102)", "kind": "gs1", "product_tmpl_ids": [(6, 0, catch_tmpls.ids)]})
        env["wms.barcode.template"].create({
            "name": "Label US berat lbs (posisi tetap)", "kind": "regex", "weight_unit": "lb", "weight_decimals": 2,
            "pattern": r"^(?P<carton>\d{6})(?P<weight>\d{4})(?P<lot>[A-Z0-9]{5})$",
            "product_tmpl_ids": [(6, 0, catch_tmpls.filtered(lambda t: "US" in (t.wms_country or "")).ids)]})

    # ---------------------------------------------------------- opening stock
    def _lot_expiry(self, zone):
        """Sebaran umur: sebagian kecil sudah lewat atau mendekati expired, mayoritas aman."""
        r = self.rnd.random()
        if r < 0.03:
            days = -self.rnd.randint(3, 60)
        elif r < 0.10:
            days = self.rnd.randint(2, 30)
        elif r < 0.18:
            days = self.rnd.randint(31, 60)
        elif r < 0.25:
            days = self.rnd.randint(61, 90)
        elif r < 0.32:
            days = self.rnd.randint(91, 120)
        else:
            days = self.rnd.randint(121, max(150, SHELF_LIFE[zone]))
        return self.now + timedelta(days=days, hours=self.rnd.randint(0, 23))

    def _opening_stock(self):
        env = self.env
        Lot, Pack, Quant = env["stock.lot"], env["stock.quant.package"], env["stock.quant"]
        cartons = []
        seq = 0
        in_date = self.now - timedelta(days=40)
        for code, product in self.products.items():
            row = self.rows[code]
            qty = float(row["qty"])
            zone = row["zone"]
            if qty <= 0:
                continue
            n = 1 if qty < 20 else self.rnd.choice((1, 2, 2, 3))
            parts = [qty / n] * n
            if product.uom_id.category_id != env.ref("uom.product_uom_categ_kgm"):
                parts = [int(qty // n)] * n
                parts[-1] += qty - sum(parts)
            for i, part in enumerate(parts):
                if part <= 0:
                    continue
                seq += 1
                exp = self._lot_expiry(zone)
                lot = Lot.create({
                    "name": f"{code[-6:]}-{exp:%y%m}{i + 1}", "product_id": product.id, "company_id": self.company.id,
                    "expiration_date": exp, "wms_mfg_date": (exp - timedelta(days=SHELF_LIFE[zone])).date()})
                pack = Pack.create({"name": f"SKI{seq:07d}", "wms_closed": True, "company_id": self.company.id,
                                    "wms_pallet_no": f"P{seq:05d}", "wms_pack_date": in_date.date()})
                loc = self._next_bin(zone) if i == 0 or self.rnd.random() < 0.7 else self.pck[zone]
                Quant._update_available_quantity(product, loc, part, lot_id=lot, package_id=pack, in_date=in_date)
                if product.wms_catch_weight and zone != "dry":
                    remaining = part
                    for c in range(min(25, max(1, int(part // 8)))):
                        weight = round(min(remaining, self.rnd.uniform(4.5, 12.5)), 3)
                        if weight <= 0:
                            break
                        remaining -= weight
                        cartons.append({
                            "name": f"{lot.name}-{c + 1:03d}", "product_id": product.id, "lot_id": lot.id,
                            "package_id": pack.id, "location_id": loc.id, "weight_kg": weight,
                            "weight_lb": round(weight * 2.20462, 2), "state": "available",
                            "raw_barcode": f"(01)0{sum(map(ord, code)) * 7919:012d}(3102){int(weight * 100):06d}"
                                           f"(10){lot.name}(17){exp:%y%m%d}(21){c + 1:05d}",
                            "company_id": self.company.id})
        env["wms.carton"].create(cartons)
        # Item low: min stock di atas stok untuk sebagian item fast moving.
        codes = list(self.products)
        self.rnd.shuffle(codes)
        for code in codes[:28]:
            product = self.products[code]
            qty = float(self.rows[code]["qty"])
            product.product_tmpl_id.wms_min_stock = round(qty * self.rnd.uniform(1.2, 2.5) + 5)
        for code in codes[28:220]:
            product = self.products[code]
            qty = float(self.rows[code]["qty"])
            product.product_tmpl_id.wms_min_stock = round(qty * self.rnd.uniform(0.1, 0.4))

    # ---------------------------------------------------------------- history
    def _backdate(self, picking, date):
        cr = self.env.cr
        cr.execute("UPDATE stock_picking SET date_done = %s, scheduled_date = %s, date = %s, date_deadline = NULL "
                   "WHERE id = %s", (date, date, date, picking.id))
        cr.execute("UPDATE stock_move SET date = %s WHERE picking_id = %s", (date, picking.id))
        cr.execute("UPDATE stock_move_line SET date = %s WHERE picking_id = %s", (date, picking.id))
        cr.execute("UPDATE stock_quant SET in_date = %s WHERE in_date > %s AND lot_id IN "
                   "(SELECT lot_id FROM stock_move_line WHERE picking_id = %s)", (date, date, picking.id))
        picking.invalidate_recordset()
        picking.move_ids.invalidate_recordset()
        picking.move_line_ids.invalidate_recordset()

    def _make_picking(self, ptype, partner, src, dest, lines, origin=None, extra=None):
        vals = {
            "picking_type_id": ptype.id, "partner_id": partner.id, "location_id": src.id,
            "location_dest_id": dest.id, "origin": origin, "company_id": self.company.id,
            "move_ids": [(0, 0, {
                "name": p.name, "product_id": p.id, "product_uom_qty": q, "product_uom": p.uom_id.id,
                "location_id": src.id, "location_dest_id": dest.id, "company_id": self.company.id,
            }) for p, q in lines],
        }
        vals.update(extra or {})
        picking = self.env["stock.picking"].create(vals)
        picking.action_confirm()
        return picking

    def _receipt(self, date, zone, validate=True):
        supplier = self.rnd.choice(self.suppliers)
        candidates = [p for p in self.products.values() if p.wms_zone == zone]
        lines = []
        for p in self.rnd.sample(candidates, self.rnd.randint(1, 4)):
            q = round(self.rnd.uniform(40, 300), 2) if p.wms_catch_weight else self.rnd.randint(12, 240)
            lines.append((p, q))
        supplier_loc = self.env.ref("stock.stock_location_suppliers")
        picking = self._make_picking(
            self.wh.in_type_id, supplier, supplier_loc, self.rooms[zone], lines,
            origin=f"95-SKI-POR-{date:%y%m}{self.rnd.randint(100000, 999999)}",
            extra={"wms_inbound_type": "po", "wms_dock_id": self.rnd.choice(self.docks).id if validate else False,
                   "wms_container_no": f"{self.rnd.choice(['MSKU', 'TGHU', 'CMAU'])}{self.rnd.randint(1000000, 9999999)}"
                   if zone != "dry" else False,
                   "wms_vendor_ref": f"INV/{self.rnd.randint(1000, 9999)}/{date:%y}", "wms_vehicle_plate": f"DD {self.rnd.randint(1000, 9999)} "
                   f"{self.rnd.choice(['AB', 'XY', 'KL', 'MN'])}", "wms_driver": self.rnd.choice(
                       ["Andi", "Baso", "Rahman", "Iwan", "Sulaiman", "Yusuf"]),
                   "wms_delivery_note": f"SJ-{self.rnd.randint(10000, 99999)}"})
        if not validate:
            return picking
        for move in picking.move_ids:
            move.move_line_ids.unlink()
            exp = self.now + timedelta(days=int(SHELF_LIFE[zone] * self.rnd.uniform(0.75, 0.95)))
            lot = self.env["stock.lot"].create({
                "name": f"{move.product_id.default_code[-6:]}-R{date:%m%d}{move.id % 100:02d}",
                "product_id": move.product_id.id, "company_id": self.company.id, "expiration_date": exp})
            pack = self.env["stock.quant.package"].create({"wms_closed": True, "company_id": self.company.id})
            self.env["stock.move.line"].create({
                "move_id": move.id, "picking_id": picking.id, "product_id": move.product_id.id,
                "product_uom_id": move.product_uom.id, "quantity": move.product_uom_qty, "lot_id": lot.id,
                "location_id": supplier_loc.id, "location_dest_id": self._next_bin(zone).id,
                "result_package_id": pack.id, "picked": True})
        picking.with_context(skip_backorder=True).button_validate()
        self._backdate(picking, date)
        return picking

    def _pick_quants(self, product, qty, partner):
        """FEFO: lot non-expired dengan sisa umur memenuhi batas customer, dari rak (bukan QC/DMG)."""
        minimum = max(55, partner.wms_min_shelf_life_pct or 0)
        quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id), ("location_id", "child_of", self.wh.lot_stock_id.id),
            ("location_id.wms_area", "in", ("blk", "pck")), ("quantity", ">", 0)])
        quants = quants.filtered(lambda q: q.lot_id.expiration_date and q.lot_id.expiration_date > self.now
                                 and (q.lot_id.expiration_date - self.now).days / product.expiration_time * 100 >= minimum
                                 and q.quantity - q.reserved_quantity > 0)
        return quants.sorted(lambda q: q.lot_id.expiration_date)[:1]

    def _delivery(self, date, partner=None, validate=True, n_lines=None):
        partner = partner or self.rnd.choice(self.customers)
        chosen = []
        codes = list(self.products)
        tries = 0
        while len(chosen) < (n_lines or self.rnd.randint(1, 5)) and tries < 40:
            tries += 1
            product = self.products[self.rnd.choice(codes)]
            if any(p == product for p, _q, _qt in chosen):
                continue
            quant = self._pick_quants(product, 1, partner)
            if not quant:
                continue
            avail = quant.quantity - quant.reserved_quantity
            if product.wms_catch_weight:
                q = round(min(avail, self.rnd.uniform(2, 25)), 3)
            else:
                q = min(int(avail), self.rnd.randint(1, 24))
            if q <= 0:
                continue
            chosen.append((product, q, quant))
        if not chosen:
            return self.env["stock.picking"]
        customer_loc = self.env.ref("stock.stock_location_customers")
        picking = self._make_picking(
            self.wh.out_type_id, partner, self.wh.lot_stock_id, customer_loc, [(p, q) for p, q, _qt in chosen],
            origin=f"95-SKI-SOR-{date:%y%m}{self.rnd.randint(100000, 999999)}",
            extra={"wms_outbound_type": "so", "wms_shipping_group": self.route[partner.id],
                   "wms_priority": self.rnd.choice(["Normal", "Normal", "Normal", "High"]),
                   "scheduled_date": date})
        for move, (product, q, quant) in zip(picking.move_ids, chosen):
            move.move_line_ids.unlink()
            full = abs(q - quant.quantity) < 1e-6
            self.env["stock.move.line"].create({
                "move_id": move.id, "picking_id": picking.id, "product_id": product.id,
                "product_uom_id": product.uom_id.id, "quantity": q, "lot_id": quant.lot_id.id,
                "package_id": quant.package_id.id, "result_package_id": quant.package_id.id if full else False,
                "location_id": quant.location_id.id, "location_dest_id": customer_loc.id})
        if not validate:
            return picking
        picking.move_line_ids.write({"picked": True})
        picking.with_context(skip_backorder=True).button_validate()
        picking.wms_stage = "shipped"
        self._backdate(picking, date)
        return picking

    def _history(self):
        self.history_out = self.env["stock.picking"]
        for day in range(30, 0, -1):
            base = (self.now - timedelta(days=day)).replace(hour=1, minute=0, second=0)
            if self.rnd.random() < 0.8:
                zone = self.rnd.choice(["frozen", "frozen", "chilled", "dry", "dry"])
                self._receipt(base + timedelta(hours=self.rnd.randint(0, 3)), zone)
            for _i in range(self.rnd.randint(2, 6)):
                out = self._delivery(base + timedelta(hours=self.rnd.randint(2, 9), minutes=self.rnd.randint(0, 59)))
                self.history_out |= out
        # Rekap POD untuk 6 pengiriman terakhir lewat satu loading job yang sudah ditutup.
        last = self.history_out.sorted("date_done")[-6:]
        job = self.env["wms.loading"].create({
            "vehicle_plate": "DD 8812 KL", "driver": "Rahman", "date": (self.now - timedelta(days=1)).date(),
            "state": "close"})
        last.write({"wms_loading_id": job.id})
        last.move_line_ids.write({"wms_loaded": True, "wms_checked": True})
        for i, picking in enumerate(last):
            pod = self.env["wms.pod"].create_for_picking(picking)
            picking.wms_pod_id = pod
            if i < 4:
                lines = {str(l.id): {"qty": l.qty_sent - (1 if i == 1 and l.qty_sent > 1 else 0),
                                     "remark": "1 karton penyok" if i == 1 else ""} for l in pod.line_ids}
                pod.submit(self.rnd.choice(["Pak Hendra", "Ibu Sari", "Chef Anto"]), lines)

    # -------------------------------------------------------------- open work
    def _open_work(self):
        today = self.now.replace(hour=0, minute=0, second=0)
        # Receiving yang menunggu truk datang hari ini / besok.
        for zone in ("frozen", "chilled", "dry", "frozen", "dry"):
            self._receipt(today + timedelta(hours=self.rnd.randint(1, 30)), zone, validate=False)
        # Outbound hari ini: 3 dokumen dijadikan satu Picking Job (rute 02), 2 sudah di staging dan dicek,
        # sisanya menunggu.
        rute02 = self.customers.filtered(lambda c: self.route[c.id] == "RUTE-02")
        job_docs = self.env["stock.picking"]
        for partner in rute02[:3]:
            job_docs |= self._delivery(today + timedelta(hours=2), partner=partner, validate=False, n_lines=3)
        job_docs = job_docs.filtered(lambda p: p)
        if job_docs:
            batch = self.env["stock.picking.batch"].create({
                "picking_ids": [(6, 0, job_docs.ids)], "description": "RUTE-02", "company_id": self.company.id,
                "wms_driver": "Iwan", "wms_transporter": "DD 7781 AB"})
            batch.action_confirm()
            job_docs.write({"wms_stage": "picking"})
            job_docs[:1].move_line_ids.write({"picked": True})
        ready = self.env["stock.picking"]
        for partner in self.customers.filtered(lambda c: self.route[c.id] == "RUTE-01"):
            ready |= self._delivery(today + timedelta(hours=1), partner=partner, validate=False, n_lines=2)
        ready.move_line_ids.write({"picked": True, "wms_checked": True})
        ready.write({"wms_stage": "checked", "wms_staging_location_id": self.staging.id})
        if ready:
            self.env["wms.loading"].create({"vehicle_plate": "DD 9034 XY", "driver": "Baso",
                                            "picking_ids": [(6, 0, ready.ids)]})
            ready[:1].move_line_ids[:1].write({"wms_loaded": True})
            ready[:1].wms_stage = "loading"
        for _i in range(6):
            self._delivery(today + timedelta(hours=self.rnd.randint(3, 40)), validate=False)

    # ----------------------------------------------------------- sync & SAP
    def _sync_documents(self):
        Sync = self.env["wms.sync.document"]
        for name in ("POR-261000182.json", "SOR-261030260.json"):
            Sync.import_json((DATA / "sync" / name).read_text(encoding="utf-8"))
        broken = json.loads((DATA / "sync" / "SOR-261030260.json").read_text(encoding="utf-8"))
        broken[0]["number"] = "95-SKI-SOR-261030311"
        broken[0]["additional_information"][0]["web_trans_no"] = "SOR-261030311"
        broken[0]["items"] = [dict(broken[0]["items"][0], item_code="XNEW00TEST01",
                                   item_name="ITEM BARU BELUM ADA DI MASTER WMS", qty=5.0)]
        Sync.import_json(broken)

    def _sap_queue(self):
        docs = self.env["wms.sap.document"].search([("company_id", "=", self.company.id)], order="id")
        for doc in docs:
            date = doc.picking_id.date_done or self.now
            self.env.cr.execute("UPDATE wms_sap_document SET create_date = %s WHERE id = %s", (date, doc.id))
        docs.invalidate_recordset(["create_date"])
        posted = docs[:-7]
        posted.action_post()
        for doc in posted:
            doc.posted_at = (doc.picking_id.date_done or self.now) + timedelta(minutes=self.rnd.randint(2, 15))
        errors = ["Service Layer: (-5002) Quantity falls into negative inventory [OIGE.WhsCode][line: 1]",
                  "Service Layer: (-10) Batch number already exists for this item",
                  "Koneksi ke Service Layer timeout (30 dtk)"]
        for doc, err in zip(docs[-7:-4], errors):
            doc.write({"state": "failed", "error": err, "attempts": 3})

    # ------------------------------------------------ inventory check, butcher
    def _inventory_and_butcher(self):
        env = self.env
        packs = env["stock.quant"].search([
            ("location_id.wms_area", "=", "blk"), ("package_id", "!=", False), ("quantity", ">", 5),
            ("company_id", "=", self.company.id)], limit=40).package_id
        # Satu inventory check sudah disetujui, satu menunggu approval kepala gudang.
        approved = env["wms.inventory.check"].create({"mode": "lpn", "package_id": packs[0].id})
        approved.action_load()
        approved.line_ids[:1].qty_after = approved.line_ids[:1].qty_before - 1
        approved.action_submit()
        approved.action_approve()
        location = packs[1].location_id
        pending = env["wms.inventory.check"].create({"mode": "location", "location_id": location.id})
        pending.action_load()
        if pending.line_ids:
            line = pending.line_ids[0]
            line.write({"qty_after": line.qty_before + 2,
                        "expiry_after": (line.expiry_before or self.now) + timedelta(days=30)})
        pending.action_submit()
        # Butcher: daging chilled/frozen berat aktual dipotong jadi porsi resto, yield ±88%.
        meat = env["stock.quant"].search([
            ("product_id.wms_item_group", "=", "A-MEAT"), ("product_id.wms_catch_weight", "=", True),
            ("location_id.wms_area", "=", "blk"), ("quantity", ">", 10), ("package_id", "!=", False),
            ("lot_id.expiration_date", ">", self.now)], limit=1)
        if meat:
            qty = round(min(meat.quantity, 10.0), 3)
            out = env["wms.butcher"].create({"kind": "out", "ref": "SPK-BTC-0001", "line_ids": [(0, 0, {
                "package_id": meat.package_id.id, "product_id": meat.product_id.id, "lot_id": meat.lot_id.id,
                "location_id": meat.location_id.id, "qty": qty})]})
            out.action_done()
            zone = meat.product_id.wms_zone
            res = env["wms.butcher"].create({"kind": "in", "ref": "SPK-BTC-0001", "source_id": out.id, "line_ids": [
                (0, 0, {"process_type": "rebag", "product_id": meat.product_id.id, "qty": round(qty * 0.8, 3),
                        "location_id": self._next_bin(zone).id, "grade": "A", "brand": "INDOGUNA",
                        "cutting_type": "Steak 200 gr"}),
                (0, 0, {"process_type": "trimming", "product_id": meat.product_id.id, "qty": round(qty * 0.08, 3),
                        "location_id": self.pck[zone].id, "grade": "B", "cutting_type": "Trimming"}),
            ]})
            res.action_done()
