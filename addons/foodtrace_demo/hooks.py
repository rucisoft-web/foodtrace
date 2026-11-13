"""Data demo WMS PT Sarana Kulina Intisejahtera dari tarikan riil SAP B1 (DB SARKUL, 13 Nov 2026).

Sumber (dibuat dengan scripts/sap_xlsx_to_demo.py dari tiga file xlsx SAP):
  data/sarkul/master_item.csv  842 item aktif 2025-2026: group, sub group, brand, satuan SAP, OnHand, ItemCost
  data/sarkul/po.csv           69 PO (239 baris) 1 Sep - 13 Nov 2026
  data/sarkul/so.csv           SO Closed 7 hari terakhir + semua SO Open

Alur demo memakai jalur yang sama dengan produksi: setiap PO dan SO masuk sebagai dokumen sinkron SAP
(POR/SOR) lalu diproses jadi picking. PO Closed diterima (lot, LPN, dock, container), SO Closed 7 hari
terakhir dikirim FEFO, PO dan SO Open menjadi pekerjaan terbuka. Stok awal dihitung mundur supaya stok
akhir sama dengan OnHand SAP: awal = OnHand - PO diterima + SO terkirim (tidak pernah negatif).

Tanggal digeser: tanggal tarik (13 Nov 2026) = hari demo dipasang, sehingga dashboard selalu segar.
Lot, kedaluwarsa, bin, palet, kendaraan dan pengemudi tidak ada di SAP dan dibangkitkan.
"""

import csv
import logging
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

_logger = logging.getLogger(__name__)

DATA = Path(__file__).parent / "data" / "sarkul"
DATA_DAY = date(2026, 11, 13)
HISTORY_DAYS = 7

ZONE_CODE = {"frozen": "FZ", "chilled": "CH", "dry": "DR"}
ZONE_NAME = {"frozen": "Frozen", "chilled": "Chilled", "dry": "Dry"}
# Rak palet (baris × bay × level) per zona.
RACKS = {"frozen": (6, 6, 4), "chilled": (6, 8, 4), "dry": (8, 8, 4)}
SHELF_LIFE = {"frozen": 540, "chilled": 120, "dry": 365}

# Kelompok kirim dari prefix CardCode SAP (data SAP tidak membawa rute).
SHIPPING_GROUP = {"GR": "CABANG", "EC": "E-COMMERCE", "SM": "RITEL MODERN", "HT": "HOTEL", "RS": "RESTO",
                  "CT": "KATERING"}
# Min. sisa umur saat kirim (%) per jenis pelanggan; angka sementara sampai ada ketentuan resmi.
MIN_LIFE = {"SM": 50, "HT": 60}
PLATES = ["B 9123 KXT", "B 9561 TRS", "B 9802 UAK", "B 9017 NDP", "B 9442 SKI"]
DRIVERS = ["Agus", "Bambang", "Dedi", "Hendra", "Rizal", "Slamet"]


# Dokumen riwayat per giliran cron saat demo dipasang dari menu Apps (muat dalam batas waktu worker).
BATCH = 80
PARAM = "foodtrace_demo.progress"


def post_init_hook(env):
    """Dengan --stop-after-init: semua data dibuat langsung. Selain itu (menu Apps, worker dibatasi
    limit_time_cpu/real): master, stok awal dan dokumen dibuat sekarang, riwayat PO/SO diputar ulang
    bertahap oleh cron "FoodTrace demo: lanjutkan data" lalu cron mematikan dirinya sendiri."""
    from odoo.tools import config

    demo = Demo(env)
    if config.get("stop_after_init"):
        demo.run()
    else:
        demo.run_deferred()


def _cron_continue(env):
    Demo.resume(env).continue_batch()


def _rows(name):
    return list(csv.DictReader((DATA / name).open(encoding="utf-8")))


def _sap_date(day):
    return day.strftime("%m/%d/%Y")


class Demo:
    def __init__(self, env, shift_days=None):
        self.rnd = random.Random(95)
        self.now = datetime.now().replace(microsecond=0)
        self.shift = timedelta(days=shift_days) if shift_days is not None else self.now.date() - DATA_DAY
        self.base_env = env
        self.env = env
        self.master = _rows("master_item.csv")
        self.po = _rows("po.csv")
        self.so = _rows("so.csv")
        self.window_start = DATA_DAY - timedelta(days=HISTORY_DAYS - 1)

    def day(self, text):
        """Tanggal SAP (YYYY-MM-DD) digeser ke kalender demo."""
        return datetime.strptime(text, "%Y-%m-%d").date() + self.shift

    # ------------------------------------------------------------------ main
    def run(self):
        _logger.info("FoodTrace demo: membuat data Sarana Kulina dari tarikan SAP")
        self._setup()
        events = self._events()
        self._replay(events, 0, len(events))
        self._finish()

    def _setup(self):
        self._company()
        self._settings()
        self._locations()
        self._partners()
        self._products()
        self._opening_stock()

    def _finish(self):
        self._after_history()
        self._open_work()
        self._sap_queue()
        self._inventory_and_butcher()
        _logger.info("FoodTrace demo selesai")

    # ------------------------------------------------- bertahap lewat cron
    def run_deferred(self):
        self._setup()
        self.env["ir.config_parameter"].sudo().set_param(
            PARAM, f"0|{self.shift.days}|{self.company.id}")
        cron = self.env.ref("foodtrace_demo.ir_cron_demo_continue").sudo()
        cron.write({"active": True, "nextcall": datetime.now()})
        _logger.info("FoodTrace demo: riwayat %s dokumen dilanjutkan oleh cron", len(self._events()))

    @classmethod
    def resume(cls, env):
        value = env["ir.config_parameter"].sudo().get_param(PARAM)
        if not value:
            return None
        done, shift, company_id = (int(x) for x in value.split("|"))
        demo = cls(env, shift_days=shift)
        demo.done = done
        company = env["res.company"].browse(company_id)
        demo.company = company
        demo.env = env(context=dict(env.context, allowed_company_ids=[company.id], tz="Asia/Jakarta",
                                    tracking_disable=True, mail_create_nolog=True, mail_notrack=True))
        demo.rnd = random.Random(95 + done)
        demo._load_context()
        return demo

    def _load_context(self):
        env = self.env
        Loc = env["stock.location"]
        self.wh = env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        stock = self.wh.lot_stock_id
        self.rooms, self.used_bins, self.pck = {}, {}, {}
        for zone in ZONE_CODE:
            room = Loc.search([("location_id", "=", stock.id), ("wms_area", "=", "room"), ("wms_zone", "=", zone)],
                              limit=1)
            self.rooms[zone] = room
            self.used_bins[zone] = Loc.search([("location_id.location_id", "=", room.id), ("wms_area", "=", "blk"),
                                               ("location_id.wms_area", "=", "blk")])
            self.pck[zone] = Loc.search([("location_id", "=", room.id), ("wms_area", "=", "pck")], limit=1)
        self._bin_cursor = defaultdict(lambda: self.rnd.randint(0, 200))
        self.docks = Loc.search([("location_id", "=", stock.id), ("wms_area", "=", "rcv")])
        self.staging = Loc.search([("location_id", "=", stock.id), ("wms_area", "=", "out")], limit=1)
        products = env["product.product"].search([("default_code", "!=", False),
                                                  ("company_id", "in", [self.company.id, False])])
        self.rows = {row["item_code"]: row for row in self.master}
        self.products = {p.default_code: p for p in products if p.default_code in self.rows}
        partners = env["res.partner"].search([("ref", "!=", False), ("parent_id", "=", False)])
        self.customers = {p.ref: p for p in partners if p.wms_is_destination}
        self.suppliers = {p.ref: p for p in partners if p.wms_is_source}

    def continue_batch(self):
        events = self._events()
        end = min(self.done + BATCH, len(events))
        self._replay(events, self.done, end)
        Param = self.env["ir.config_parameter"].sudo()
        if end < len(events):
            Param.set_param(PARAM, f"{end}|{self.shift.days}|{self.company.id}")
            return
        self._finish()
        # Cron tidak bisa menonaktifkan dirinya sendiri selagi berjalan; tanpa progress ia tidak berbuat apa-apa.
        Param.set_param(PARAM, False)

    # ---------------------------------------------------------------- company
    def _company(self):
        env = self.base_env
        idr = env.ref("base.IDR")
        idr.active = True
        company = env["res.company"].create({
            "name": "PT Sarana Kulina Intisejahtera", "currency_id": idr.id,
            "wms_sap_company_db": "SARKUL", "city": "Jakarta",
            "country_id": env.ref("base.id").id,
        })
        admin = env.ref("base.user_admin")
        admin.write({"company_ids": [(4, company.id)], "company_id": company.id})
        env.ref("base.user_root").write({"company_ids": [(4, company.id)]})
        self.company = company
        self.env = env(context=dict(env.context, allowed_company_ids=[company.id], tz="Asia/Jakarta",
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
        customers, suppliers = {}, {}
        for row in self.so:
            customers.setdefault(row["card_code"], row["card_name"])
        for row in self.po:
            suppliers.setdefault(row["card_code"], row["card_name"])
        created = Partner.create([{
            "name": name, "ref": code, "is_company": True, "wms_is_destination": True,
        } for code, name in sorted(customers.items())])
        self.customers = {p.ref: p for p in created}
        created = Partner.create([{
            "name": name, "ref": code, "is_company": True, "wms_is_source": True,
            # Pemasok impor (VI*) mengirim keju/daging berat aktual: toleransi lebih terima 2%.
            "wms_over_receive_pct": 2 if code.startswith("VI") else 0,
        } for code, name in sorted(suppliers.items())])
        self.suppliers = {p.ref: p for p in created}

    def _apply_customer_shelf_life(self):
        """Batas sisa umur pelanggan dipasang setelah riwayat dibangun (riwayat = fakta yang sudah terjadi)."""
        for code, partner in self.customers.items():
            life = MIN_LIFE.get(code[:2])
            if life:
                partner.wms_min_shelf_life_pct = life

    # --------------------------------------------------------------- products
    def _uoms(self):
        env = self.env
        uoms = {"KG": env.ref("uom.product_uom_kgm"), "GRAM": env.ref("uom.product_uom_gram")}
        for code in {row["uom"] for row in self.master}:
            if code not in uoms:
                uoms[code] = env.ref(f"foodtrace.uom_sap_{code.lower()}", raise_if_not_found=False) \
                    or env.ref("foodtrace.uom_sap_pce")
        return uoms

    def _products(self):
        env = self.env
        uoms = self._uoms()
        fefo = env.ref("product_expiry.removal_fefo")
        root = env["product.category"].create({"name": "Sarana Kulina", "removal_strategy_id": fefo.id})
        categories = {}
        vals = []
        for row in self.master:
            group = row["item_group"] or "LAIN-LAIN"
            if group not in categories:
                categories[group] = env["product.category"].create({"name": group, "parent_id": root.id})
            zone = row["zone"]
            catch = row["catch_weight"] == "1"
            life = SHELF_LIFE[zone]
            uom = uoms[row["uom"]]
            vals.append({
                "name": row["item_name"], "default_code": row["item_code"], "is_storable": True,
                "tracking": "lot", "use_expiration_date": True, "expiration_time": life,
                "use_time": max(1, life - 30), "removal_time": max(1, life - 7), "alert_time": 30,
                "uom_id": uom.id, "uom_po_id": uom.id,
                "categ_id": categories[group].id, "wms_zone": zone, "wms_catch_weight": catch,
                "wms_item_group": group, "wms_sub_group": row["sub_group"], "wms_country": row["country"],
                "wms_brand": row["brand"],
                "standard_price": float(row["item_cost"]) or float(row["last_price"]),
                "wms_units_per_pallet": 0 if catch else 60, "weight": 1.0 if catch else 0.0,
                "wms_picking_strategy": "fefo",
            })
        templates = env["product.template"].with_company(self.company).create(vals)
        self.rows = {row["item_code"]: row for row in self.master}
        self.products = {t.default_code: t.product_variant_id for t in templates}
        # Caviar impor wajib karantina saat terima dan dilepas otomatis setelah 2 hari.
        for t in templates.filtered(lambda t: t.wms_sub_group == "CAVIAR"):
            t.write({"wms_auto_quarantine": True, "wms_auto_release": True, "wms_quarantine_days": 2})
        # Format barcode karton GS1 untuk item berat aktual.
        catch_tmpls = templates.filtered("wms_catch_weight")
        env["wms.barcode.template"].create({
            "name": "GS1-128 berat kg (AI 3102)", "kind": "gs1", "product_tmpl_ids": [(6, 0, catch_tmpls.ids)]})
        env["wms.barcode.template"].create({
            "name": "Label US berat lbs (posisi tetap)", "kind": "regex", "weight_unit": "lb", "weight_decimals": 2,
            "pattern": r"^(?P<carton>\d{6})(?P<weight>\d{4})(?P<lot>[A-Z0-9]{5})$",
            "product_tmpl_ids": [(6, 0, catch_tmpls.filtered(lambda t: "US" in (t.wms_country or "")).ids)]})

    def _apply_receive_life(self):
        for product in self.products.values():
            product.product_tmpl_id.wms_min_receive_life_pct = {"frozen": 50, "chilled": 60, "dry": 40}[
                product.wms_zone]

    # ---------------------------------------------------------- opening stock
    def _closed_po(self):
        return [r for r in self.po if r["status"] == "Closed" and r["item_code"] in self.products]

    def _closed_so(self):
        return [r for r in self.so if r["status"] == "Closed" and r["item_code"] in self.products
                and self.window_start <= datetime.strptime(r["date"], "%Y-%m-%d").date() <= DATA_DAY]

    def _lot_expiry(self, zone, allow_expired=True):
        """Sebaran umur: sebagian kecil sudah lewat atau mendekati expired, mayoritas aman."""
        r = self.rnd.random()
        if r < 0.03 and allow_expired:
            days = -self.rnd.randint(3, 60)
        elif r < 0.10:
            days = self.rnd.randint(15, 30)
        elif r < 0.18:
            days = self.rnd.randint(31, 60)
        elif r < 0.25:
            days = self.rnd.randint(61, 90)
        elif r < 0.32:
            days = self.rnd.randint(91, 120)
        else:
            days = self.rnd.randint(121, max(150, SHELF_LIFE[zone]))
        return self.now + timedelta(days=days, hours=self.rnd.randint(0, 23))

    def _opening_qty(self):
        """Stok awal per item supaya stok akhir = OnHand SAP dan saldo tidak pernah minus di tengah jalan."""
        events = defaultdict(list)
        for r in self._closed_po():
            events[r["item_code"]].append((r["date"], 0, float(r["qty"])))
        for r in self._closed_so():
            events[r["item_code"]].append((r["date"], 1, -float(r["qty"])))
        opening = {}
        for code, row in self.rows.items():
            balance = low = 0.0
            for _d, _k, qty in sorted(events[code]):
                balance += qty
                low = min(low, balance)
            opening[code] = round(max(float(row["onhand"]) - balance, -low, 0.0), 3)
        return opening

    def _opening_stock(self):
        env = self.env
        Lot, Pack, Quant = env["stock.lot"], env["stock.quant.package"], env["stock.quant"]
        weight = env.ref("uom.product_uom_categ_kgm")
        shipped = {r["item_code"] for r in self._closed_so()}
        self.opening = self._opening_qty()
        cartons = []
        seq = 0
        in_date = datetime.combine(date(2026, 8, 25) + self.shift, datetime.min.time())
        for code, product in self.products.items():
            qty = self.opening[code]
            zone = self.rows[code]["zone"]
            if qty <= 0:
                continue
            n = 1 if qty < 20 else self.rnd.choice((1, 2, 2, 3))
            parts = [round(qty / n, 3)] * n
            if product.uom_id.category_id != weight:
                parts = [int(qty // n)] * n
            parts[-1] = round(qty - sum(parts[:-1]), 3)
            for i, part in enumerate(parts):
                if part <= 0:
                    continue
                seq += 1
                exp = self._lot_expiry(zone, allow_expired=code not in shipped)
                lot = Lot.create({
                    "name": f"{code[-6:]}-{exp:%y%m}{i + 1}", "product_id": product.id, "company_id": self.company.id,
                    "expiration_date": exp, "wms_mfg_date": (exp - timedelta(days=SHELF_LIFE[zone])).date(),
                    "wms_brand": self.rows[code]["brand"]})
                pack = Pack.create({"name": f"SKI{seq:07d}", "wms_closed": True, "company_id": self.company.id,
                                    "wms_pallet_no": f"P{seq:05d}", "wms_pack_date": in_date.date()})
                loc = self._next_bin(zone) if i == 0 or self.rnd.random() < 0.7 else self.pck[zone]
                Quant._update_available_quantity(product, loc, part, lot_id=lot, package_id=pack, in_date=in_date)
                if product.wms_catch_weight and zone != "dry":
                    cartons += self._cartons(product, lot, pack, loc, part, exp)
        env["wms.carton"].create(cartons)

    def _cartons(self, product, lot, pack, loc, qty, exp):
        cartons = []
        remaining = qty
        code = product.default_code
        for c in range(min(25, max(1, int(qty // 8)))):
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
        return cartons

    def _min_stock(self):
        """Stok minimum = rata-rata SO harian 7 hari terakhir x 5 hari kerja."""
        sold = defaultdict(float)
        for r in self._closed_so():
            sold[r["item_code"]] += float(r["qty"])
        for code, qty in sold.items():
            self.products[code].product_tmpl_id.wms_min_stock = round(qty / HISTORY_DAYS * 5, 2)

    # ---------------------------------------------------------- SAP payloads
    def _sap_uom(self, row):
        return row["uom"] or self.rows.get(row["item_code"], {}).get("uom") or "PCE"

    def _por_payload(self, lines, container=""):
        head = lines[0]
        doc_date = self.day(head["date"])
        return {
            "additional_information": [{
                "doc_entry": head["doc_num"], "vendor_ref_no": head["ref"], "vendor_do_no": head["ref"],
                "container": container, "remarks": "", "web_trans_no": f"POR-{head['doc_num']}"}],
            "items": [{"po_line_no": str(i), "item_code": r["item_code"], "item_name": r["item_name"],
                       "uom_id": self._sap_uom(r), "qty": float(r["qty"]), "remark": "", "is_free": "NO",
                       "brand_desc": self.rows.get(r["item_code"], {}).get("brand")} for i, r in enumerate(lines)],
            "number": f"95-SKI-POR-{head['doc_num']}", "inbound_type": "Purchase Order",
            "source": head["card_code"], "warehouse": "95-SKI", "owner": "95-SKI", "user": "indogunasap",
            "date": _sap_date(doc_date), "status": head["status"], "obj_type": "22",
        }

    def _sor_payload(self, lines):
        head = lines[0]
        return {
            "additional_information": [{
                "doc_entry": head["doc_num"], "vendor_ref_no": head["ref"], "remarks": "",
                "web_trans_no": f"SOR-{head['doc_num']}"}],
            "items": [{"so_line_no": str(i), "item_code": r["item_code"], "item_name": r["item_name"],
                       "uom_id": self._sap_uom(r), "qty": float(r["qty"]), "remark": "",
                       "brand_desc": self.rows.get(r["item_code"], {}).get("brand"), "grade": "-"}
                      for i, r in enumerate(lines)],
            "number": f"95-SKI-SOR-{head['doc_num']}", "outbound_type": "Sales Order",
            "warehouse": "95-SKI", "owner": "95-SKI", "user": "indogunasap",
            "destination_code": head["card_code"], "destination_outlet": head["ship_to"] or head["card_name"],
            "po_date": _sap_date(self.day(head["date"])), "delivery_date": _sap_date(self.day(head["due_date"])),
            "shipping_group": SHIPPING_GROUP.get(head["card_code"][:2], "UMUM"),
            "status": head["status"], "priority": "Normal", "obj_type": "17",
        }

    @staticmethod
    def _docs(rows):
        docs = defaultdict(list)
        for r in rows:
            docs[r["doc_num"]].append(r)
        return docs

    # ---------------------------------------------------------------- history
    def _backdate(self, picking, when):
        self.env.flush_all()
        cr = self.env.cr
        cr.execute("UPDATE stock_picking SET date_done = %s, scheduled_date = %s, date = %s, date_deadline = NULL "
                   "WHERE id = %s", (when, when, when, picking.id))
        cr.execute("UPDATE stock_move SET date = %s WHERE picking_id = %s", (when, picking.id))
        cr.execute("UPDATE stock_move_line SET date = %s WHERE picking_id = %s", (when, picking.id))
        cr.execute("UPDATE stock_quant SET in_date = %s WHERE in_date > %s AND lot_id IN "
                   "(SELECT lot_id FROM stock_move_line WHERE picking_id = %s)", (when, when, picking.id))
        cr.execute("UPDATE wms_sync_document SET create_date = %s WHERE picking_id = %s", (when, picking.id))
        picking.invalidate_recordset()
        picking.move_ids.invalidate_recordset()
        picking.move_line_ids.invalidate_recordset()

    def _validate(self, picking):
        picking.with_context(skip_backorder=True, picking_ids_not_to_backorder=picking.ids).button_validate()

    def _receive(self, lines):
        head = lines[0]
        zones = {self.products[r["item_code"]].wms_zone for r in lines}
        imported = head["card_code"].startswith("VI")
        container = (f"{self.rnd.choice(['MSKU', 'TGHU', 'CMAU', 'MEDU'])}{self.rnd.randint(1000000, 9999999)}"
                     if imported and zones - {"dry"} else "")
        doc = self.env["wms.sync.document"].import_json([self._por_payload(lines, container)])
        picking = doc.picking_id
        if not picking:
            _logger.warning("PO %s gagal: %s", head["doc_num"], doc.error)
            return picking
        when = datetime.combine(self.day(head["date"]), datetime.min.time()) + timedelta(
            hours=self.rnd.randint(1, 4), minutes=self.rnd.randint(0, 59))
        picking.write({
            "wms_dock_id": self.rnd.choice(self.docks).id, "wms_vehicle_plate": self.rnd.choice(PLATES),
            "wms_driver": self.rnd.choice(DRIVERS), "wms_delivery_note": head["ref"] or f"SJ-{head['doc_num']}"})
        supplier_loc = self.env.ref("stock.stock_location_suppliers")
        for move in picking.move_ids:
            move.move_line_ids.unlink()
            product = move.product_id
            zone = product.wms_zone
            exp = when + timedelta(days=int(SHELF_LIFE[zone] * self.rnd.uniform(0.75, 0.95)))
            lot = self.env["stock.lot"].create({
                "name": f"{product.default_code[-6:]}-R{when:%m%d}{move.id % 100:02d}", "product_id": product.id,
                "company_id": self.company.id, "expiration_date": exp, "wms_brand": product.wms_brand})
            pack = self.env["stock.quant.package"].create({
                "wms_closed": True, "company_id": self.company.id, "wms_pack_date": when.date()})
            dest = self._next_bin(zone)
            self.env["stock.move.line"].create({
                "move_id": move.id, "picking_id": picking.id, "product_id": product.id,
                "product_uom_id": move.product_uom.id, "quantity": move.product_uom_qty, "lot_id": lot.id,
                "location_id": supplier_loc.id, "location_dest_id": dest.id,
                "result_package_id": pack.id, "picked": True})
        self._validate(picking)
        self._backdate(picking, when)
        return picking

    def _fefo_quants(self, product, partner=None):
        quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id), ("location_id", "child_of", self.wh.lot_stock_id.id),
            ("location_id.wms_area", "in", ("blk", "pck")), ("quantity", ">", 0)])
        minimum = (partner.commercial_partner_id.wms_min_shelf_life_pct or 0) if partner else 0
        quants = quants.filtered(
            lambda q: q.lot_id.expiration_date and q.lot_id.expiration_date > self.now
            and q.quantity - q.reserved_quantity > 0
            and (not minimum or (q.lot_id.expiration_date - self.now).days / product.expiration_time * 100 >= minimum))
        return quants.sorted(lambda q: q.lot_id.expiration_date)

    def _ship(self, lines):
        head = lines[0]
        doc = self.env["wms.sync.document"].import_json([self._sor_payload(lines)])
        picking = doc.picking_id
        if not picking:
            _logger.warning("SO %s gagal: %s", head["doc_num"], doc.error)
            return picking
        customer_loc = self.env.ref("stock.stock_location_customers")
        for move in picking.move_ids:
            move.move_line_ids.unlink()
            need = move.product_uom_qty
            for quant in self._fefo_quants(move.product_id):
                if need <= 1e-6:
                    break
                take = round(min(need, quant.quantity - quant.reserved_quantity), 3)
                if take <= 0:
                    continue
                self.env["stock.move.line"].create({
                    "move_id": move.id, "picking_id": picking.id, "product_id": move.product_id.id,
                    "product_uom_id": move.product_id.uom_id.id, "quantity": take, "lot_id": quant.lot_id.id,
                    "package_id": quant.package_id.id, "location_id": quant.location_id.id,
                    "location_dest_id": customer_loc.id, "picked": True})
                need -= take
        if not picking.move_line_ids:
            return self.env["stock.picking"]
        self._validate(picking)
        picking.wms_stage = "shipped"
        when = datetime.combine(self.day(head["date"]), datetime.min.time()) + timedelta(
            hours=self.rnd.randint(2, 9), minutes=self.rnd.randint(0, 59))
        self._backdate(picking, when)
        return picking

    def _events(self):
        """PO Closed diterima dan SO Closed 7 hari terakhir dikirim, urut tanggal (terima dulu, lalu kirim)."""
        events = [(lines[0]["date"], 0, num, lines) for num, lines in self._docs(self._closed_po()).items()]
        events += [(lines[0]["date"], 1, num, lines) for num, lines in self._docs(self._closed_so()).items()]
        return sorted(events)

    def _replay(self, events, start, end):
        for i in range(start, end):
            _d, kind, _num, lines = events[i]
            if kind == 0:
                self._receive(lines)
            else:
                self._ship(lines)
            if i % 200 == 0:
                _logger.info("FoodTrace demo: riwayat %s/%s dokumen", i, len(events))

    def _after_history(self):
        self._reconcile_onhand()
        self._apply_receive_life()
        self._apply_customer_shelf_life()
        self._min_stock()
        # Rekap POD untuk 6 pengiriman terakhir lewat satu loading job yang sudah ditutup.
        last = self.env["stock.picking"].search([
            ("company_id", "=", self.company.id), ("picking_type_code", "=", "outgoing"), ("state", "=", "done")],
            order="date_done desc", limit=6).sorted("date_done")
        job = self.env["wms.loading"].create({
            "vehicle_plate": PLATES[0], "driver": DRIVERS[0], "date": (self.now - timedelta(days=1)).date(),
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

    def _reconcile_onhand(self):
        """Samakan stok dengan OnHand SAP 13 Nov.

        Sebagian PO Sep-Okt sudah habis terjual oleh SO sebelum jendela 7 hari yang tidak diputar ulang;
        selisih itu dikeluarkan lewat penyesuaian stok bertanggal awal jendela, seperti stock opname
        rekonsiliasi saat go-live.
        """
        self.env.invalidate_all()
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        when = datetime.combine(self.window_start + self.shift, datetime.min.time()) - timedelta(hours=2)
        adjusted = Quant
        for code, product in self.products.items():
            quants = Quant.search([("product_id", "=", product.id), ("location_id.usage", "=", "internal"),
                                   ("company_id", "=", self.company.id)])
            excess = round(sum(quants.mapped("quantity")) - float(self.rows[code]["onhand"]), 3)
            for quant in quants.filtered(lambda q: q.quantity > 0).sorted(lambda q: (q.in_date, q.id)):
                if excess <= 1e-6:
                    break
                take = min(excess, quant.quantity - quant.reserved_quantity)
                if take <= 0:
                    continue
                quant.inventory_quantity = round(quant.quantity - take, 3)
                adjusted |= quant
                excess -= take
        if adjusted:
            adjusted.with_context(inventory_name="Rekonsiliasi OnHand SAP 13 Nov 2026").action_apply_inventory()
            self.env.flush_all()
            self.env.cr.execute(
                "UPDATE stock_move SET date = %s WHERE reference LIKE %s AND company_id = %s",
                (when, "Rekonsiliasi OnHand SAP%", self.company.id))
            self.env.cr.execute(
                "UPDATE stock_move_line SET date = %s WHERE reference LIKE %s AND company_id = %s",
                (when, "Rekonsiliasi OnHand SAP%", self.company.id))
        _logger.info("FoodTrace demo: %s quant disesuaikan ke OnHand SAP", len(adjusted))

    # -------------------------------------------------------------- open work
    def _open_work(self):
        Sync = self.env["wms.sync.document"]
        # PO Open: truk belum datang, tampil di Inbound Document "Belum diterima".
        for lines in self._docs([r for r in self.po if r["status"] == "Open"]).values():
            Sync.import_json([self._por_payload(lines)])
        # SO Open: masuk lewat sinkron SAP. Dokumen dengan ItemCode yang belum ada di master WMS gagal
        # dan menunggu master item dilengkapi (kasus nyata di data SARKUL).
        docs = Sync.browse()
        for lines in self._docs([r for r in self.so if r["status"] == "Open"]).values():
            docs |= Sync.import_json([self._sor_payload(lines)])
        out = docs.picking_id
        out.action_assign()
        today = self.now.date()
        todays = out.filtered(lambda p: p.state == "assigned" and p.scheduled_date.date() == today)
        groups = defaultdict(lambda: self.env["stock.picking"])
        for picking in todays:
            groups[picking.wms_shipping_group] |= picking
        ranked = sorted(groups.values(), key=len, reverse=True) + [self.env["stock.picking"]] * 2
        # Picking Job: kelompok kirim terbanyak hari ini.
        job_docs = ranked[0][:4]
        if job_docs:
            batch = self.env["stock.picking.batch"].create({
                "picking_ids": [(6, 0, job_docs.ids)], "description": job_docs[0].wms_shipping_group,
                "company_id": self.company.id, "wms_driver": DRIVERS[3], "wms_transporter": PLATES[1]})
            batch.action_confirm()
            job_docs.write({"wms_stage": "picking"})
            job_docs[:1].move_line_ids.write({"picked": True})
        # Sudah dicek di staging dan mulai dimuat: kelompok kirim kedua.
        ready = ranked[1][:3]
        if ready:
            ready.move_line_ids.write({"picked": True, "wms_checked": True})
            ready.write({"wms_stage": "checked", "wms_staging_location_id": self.staging.id})
            self.env["wms.loading"].create({"vehicle_plate": PLATES[2], "driver": DRIVERS[1],
                                            "picking_ids": [(6, 0, ready.ids)]})
            ready[:1].move_line_ids[:1].write({"wms_loaded": True})
            ready[:1].wms_stage = "loading"

    # ----------------------------------------------------------- SAP queue
    def _sap_queue(self):
        docs = self.env["wms.sap.document"].search([("company_id", "=", self.company.id)], order="id")
        for doc in docs:
            when = doc.picking_id.date_done or self.now
            self.env.cr.execute("UPDATE wms_sap_document SET create_date = %s WHERE id = %s", (when, doc.id))
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
