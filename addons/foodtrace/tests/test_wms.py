from datetime import datetime, timedelta
from pathlib import Path

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval

DATA = Path(__file__).parent / "data"


@tagged("post_install", "-at_install", "foodtrace")
class TestWms(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)
        cls.wh.wms_sap_code = "01-IGU"
        Loc = cls.env["stock.location"]
        stock = cls.wh.lot_stock_id
        cls.fz = Loc.create({"name": "FZ", "location_id": stock.id, "wms_zone": "frozen", "wms_area": "room"})
        cls.dr = Loc.create({"name": "DR", "location_id": stock.id, "wms_zone": "dry", "wms_area": "room"})
        cls.fz_rack = Loc.create({"name": "FZ-BLK-A01-1-1", "location_id": cls.fz.id, "wms_area": "blk"})
        cls.fz_qc = Loc.create({"name": "FZ-QC", "location_id": cls.fz.id, "wms_area": "qc", "wms_zone": "frozen"})
        cls.kg = cls.env.ref("uom.product_uom_kgm")
        cls.cheese = cls.env["product.product"].create({
            "name": "US FRZ LEPRINO MOZZARELLA CHEESE BLOCK 6 LBS", "default_code": "HUS2LEP002",
            "is_storable": True, "tracking": "lot", "use_expiration_date": True, "expiration_time": 360,
            "uom_id": cls.kg.id, "uom_po_id": cls.kg.id, "wms_zone": "frozen", "wms_catch_weight": True,
            "standard_price": 95000})
        cls.fries = cls.env["product.product"].create({
            "name": "SS-06C SNV COATING SHOESTRING FRIES 6 X 2KG", "default_code": "GCN2SNV001",
            "is_storable": True, "uom_id": cls.kg.id, "uom_po_id": cls.kg.id, "wms_zone": "frozen",
            "standard_price": 30000})
        cls.milk = cls.env["product.product"].create({
            "name": "CIMORY CHOCOLATE UHT MILK 750 ML @12 PCS", "default_code": "HID3CIM006",
            "is_storable": True, "wms_zone": "dry", "standard_price": 250000})
        cls.owner = cls.env["res.partner"].create({"name": "PT Sarana Kulina", "wms_owner_code": "01-IGU"})
        cls.gs1 = cls.env["wms.barcode.template"].create({
            "name": "GS1 berat kg", "kind": "gs1", "product_tmpl_ids": [(4, cls.cheese.product_tmpl_id.id)]})

    def _receipt(self, product, qty, dest, lot=None):
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.wh.in_type_id.id,
            "location_id": self.env.ref("stock.stock_location_suppliers").id,
            "location_dest_id": dest.id,
            "move_ids": [(0, 0, {"name": product.name, "product_id": product.id, "product_uom_qty": qty,
                                 "product_uom": product.uom_id.id,
                                 "location_id": self.env.ref("stock.stock_location_suppliers").id,
                                 "location_dest_id": dest.id})],
        })
        picking.action_confirm()
        picking.move_ids.quantity = qty
        if lot:
            picking.move_line_ids.lot_id = lot
        picking.move_ids.picked = True
        return picking

    def test_gs1_parse_weight_lot_expiry(self):
        data = self.gs1.parse("(01)10012345678902(3102)001234(10)LEP2611(17)270430(21)C0001")
        self.assertAlmostEqual(data["weight_kg"], 12.34)
        self.assertEqual(data["lot"], "LEP2611")
        self.assertEqual(str(data["expiry"]), "2027-04-30")
        raw = "0110012345678902320300612010LEP2611\x1d17270430"
        data = self.gs1.parse(raw)
        self.assertAlmostEqual(data["weight_kg"], 2.776, places=3)  # 6,120 lb

    def test_regex_template_lbs(self):
        tpl = self.env["wms.barcode.template"].create({
            "name": "Fixed", "kind": "regex", "weight_unit": "lb", "weight_decimals": 2,
            "pattern": r"^(?P<carton>\d{6})(?P<weight>\d{4})(?P<lot>[A-Z0-9]{5})$"})
        data = tpl.parse("1234560600AB123")
        self.assertAlmostEqual(data["weight_kg"], 2.722, places=3)
        with self.assertRaises(UserError):
            tpl.parse("xxx")

    def test_zone_mismatch_is_refused(self):
        picking = self._receipt(self.milk, 5, self.fz_rack)
        with self.assertRaisesRegex(UserError, "zona dry"):
            picking.button_validate()

    def test_receipt_needs_dock_and_auto_quarantine(self):
        dock = self.env["stock.location"].create({
            "name": "DOCK_01", "barcode": "DOCK_01", "location_id": self.wh.lot_stock_id.id, "wms_area": "rcv"})
        supplier = self.env["res.partner"].create({"name": "Leprino Foods"})
        self.cheese.wms_auto_quarantine = True
        lot = self.env["stock.lot"].create({
            "name": "LEP-1", "product_id": self.cheese.id, "expiration_date": datetime.now() + timedelta(days=300)})
        picking = self._receipt(self.cheese, 12.5, self.fz_rack, lot)
        picking.partner_id = supplier
        self.assertTrue(supplier.wms_is_source)
        with self.assertRaisesRegex(UserError, "Loading dock"):
            picking.button_validate()
        picking.wms_dock_id = dock
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.move_line_ids.location_dest_id, self.fz_qc)
        sap = picking.wms_sap_document_ids
        self.assertEqual(sap.doc_type, "grpo")
        sap.action_post()
        self.assertEqual(sap.state, "posted")
        sources = self.env["res.partner"].search(
            safe_eval(self.env.ref("foodtrace.action_source_master").domain))
        self.assertIn(supplier, sources)

    def test_receive_shelf_life_minimum(self):
        self.cheese.wms_min_receive_life_pct = 70
        lot = self.env["stock.lot"].create({
            "name": "LEP-OLD", "product_id": self.cheese.id, "expiration_date": datetime.now() + timedelta(days=60)})
        picking = self._receipt(self.cheese, 5, self.fz_rack, lot)
        with self.assertRaisesRegex(UserError, "umur simpan"):
            picking.button_validate()

    def test_tally_wizard_creates_cartons_and_lot(self):
        picking = self._receipt(self.cheese, 10, self.fz_rack)
        picking.move_line_ids.unlink()
        wiz = self.env["wms.tally.wizard"].with_context(default_picking_id=picking.id).create({})
        for raw in ("(01)10012345678902(3102)000512(10)L1(17)270430(21)C1",
                    "(01)10012345678902(3102)000488(10)L1(17)270430(21)C2"):
            wiz.barcode = raw
            wiz.action_scan()
        wiz.barcode = "(01)10012345678902(3102)000488(10)L1(17)270430(21)C2"
        with self.assertRaisesRegex(UserError, "sudah discan"):
            wiz.action_scan()
        wiz.barcode = False
        wiz.manual_weight = 4.75
        wiz.manual_lot = "L1"
        wiz.action_scan()
        self.assertAlmostEqual(wiz.total_weight, 14.75)
        wiz.action_confirm()
        self.assertAlmostEqual(picking.move_line_ids.quantity, 14.75)
        self.assertEqual(picking.move_line_ids.lot_id.name, "L1")
        self.assertEqual(picking.wms_carton_count, 3)

    def test_sync_por_and_sor_files(self):
        Sync = self.env["wms.sync.document"]
        por = Sync.import_json((DATA / "POR-261000182.json").read_text())
        self.assertEqual(por.state, "done", por.error)
        self.assertEqual(por.picking_id.picking_type_id, self.wh.in_type_id)
        self.assertEqual(por.picking_id.owner_id, self.owner)
        self.assertEqual(por.picking_id.move_ids.product_uom_qty, 3600)
        self.assertEqual(por.partner_code, "VL0193")
        self.assertEqual(por.picking_id.wms_vendor_ref, "IGU050/CMR/SC/2026 [A]")
        self.assertTrue(por.picking_id.partner_id.wms_is_source)
        inbound = self.env["stock.picking"].search(safe_eval(
            self.env.ref("foodtrace.action_inbound_document").domain) + [("origin", "=", "01-IGU-POR-261000182")])
        self.assertEqual(inbound, por.picking_id)
        sor = Sync.import_json((DATA / "SOR-261030260.json").read_text())
        self.assertEqual(sor.state, "done", sor.error)
        picking = sor.picking_id
        self.assertEqual(picking.picking_type_id, self.wh.out_type_id)
        self.assertEqual(picking.wms_shipping_group, "UTARA 1B")
        self.assertIn("SWISSOTEL", picking.partner_id.name)
        # Dua baris SO dengan item yang sama digabung menjadi satu move.
        self.assertEqual(len(picking.move_ids), 2)
        self.assertEqual(sum(picking.move_ids.mapped("product_uom_qty")), 11)
        # Kirim ulang file yang sama tidak membuat dokumen baru.
        again = Sync.import_json((DATA / "SOR-261030260.json").read_text())
        self.assertEqual(again, sor)

    def test_lpn_label_before_validation(self):
        """Label dicetak saat palet ditutup di receiving, sebelum stok ada: isinya diambil dari baris penerimaan."""
        lot = self.env["stock.lot"].create({
            "name": "LEP-L", "product_id": self.cheese.id, "expiration_date": datetime(2027, 4, 30), "wms_grade": "A",
            "wms_est": "ME 21"})
        picking = self._receipt(self.cheese, 38.34, self.fz_rack, lot)
        picking.wms_container_no = "MSKU1234567"
        pack = self.env["stock.quant.package"].create({"wms_pallet_no": "P-01", "wms_packaging": "Karton 20 kg"})
        picking.move_line_ids.result_package_id = pack
        data = pack._wms_label_data()
        self.assertEqual(data["code"], "HUS2LEP002")
        self.assertEqual(data["qty"], "38.34")
        self.assertEqual(data["exp"], "30-Apr-2027")
        self.assertEqual((data["est"], data["grade"], data["container"], data["pallet"]),
                         ("ME 21", "A", "MSKU1234567", "P-01"))
        self.assertEqual(data["printed_by"], self.env.user.name)
        html = self.env.ref("foodtrace.action_report_lpn_label")._render_qweb_html(
            "foodtrace.report_lpn_label", pack.ids)[0].decode()
        self.assertIn("Qty Tally/Karton", html)
        self.assertIn("ME 21", html)

    def test_sync_unknown_item_is_error(self):
        doc = self.env["wms.sync.document"].import_json([{
            "number": "X-1", "outbound_type": "Sales Order", "warehouse": "01-IGU", "owner": "01-IGU",
            "destination_code": "C1", "destination_outlet": "Hotel", "delivery_date": "10/26/2026",
            "items": [{"item_code": "NOPE", "qty": 1, "uom_id": "PCS"}]}])
        self.assertEqual(doc.state, "error")
        self.assertIn("NOPE", doc.error)

    def test_sync_sap_uom_ship_to_and_own_stock(self):
        """Data riil SARKUL: satuan SAP (JAR, GRAM), banyak outlet per pelanggan, owner = gudang sendiri."""
        jar = self.env.ref("foodtrace.uom_sap_jar")
        gram = self.env.ref("uom.product_uom_gram")
        capers = self.env["product.product"].create({
            "name": "FALLOT CAPERS 125GR", "default_code": "EFR03FAL0005", "is_storable": True,
            "uom_id": jar.id, "uom_po_id": jar.id, "wms_zone": "dry"})
        truffle = self.env["product.product"].create({
            "name": "GF SM TRUFFLE", "default_code": "EIT01GEO5004", "is_storable": True,
            "uom_id": gram.id, "uom_po_id": gram.id, "wms_zone": "chilled"})
        customer = self.env["res.partner"].create({"name": "PT SUPRA BOGA LESTARI Tbk", "ref": "SM0036"})
        self.env.company.partner_id.wms_owner_code = "95-SKI"
        self.wh.wms_sap_code = "95-SKI"

        def sor(number, outlet, items):
            return [{"number": number, "outbound_type": "Sales Order", "warehouse": "95-SKI", "owner": "95-SKI",
                     "destination_code": "SM0036", "destination_outlet": outlet, "delivery_date": "11/13/2026",
                     "items": items}]

        Sync = self.env["wms.sync.document"]
        doc = Sync.import_json(sor("95-SKI-SOR-261100001", "RANCH MARKET RM99 KEMANG", [
            {"item_code": "EFR03FAL0005", "uom_id": "JAR", "qty": 6},
            {"item_code": "EIT01GEO5004", "uom_id": "KG", "qty": 0.5},
            {"item_code": "HUS2LEP002", "uom_id": "PCK", "qty": 3}]))
        self.assertEqual(doc.state, "done", doc.error)
        picking = doc.picking_id
        self.assertFalse(picking.owner_id, "owner = perusahaan sendiri berarti stok sendiri")
        self.assertEqual(picking.partner_id.parent_id, customer)
        self.assertEqual(picking.partner_id.type, "delivery")
        self.assertEqual(picking.partner_id.name, "RANCH MARKET RM99 KEMANG")
        uoms = {m.product_id: m.product_uom for m in picking.move_ids}
        self.assertEqual(uoms[capers], jar)
        self.assertEqual(uoms[truffle], self.env.ref("uom.product_uom_kgm"), "KG ke item GRAM tetap satu kategori")
        self.assertEqual(uoms[self.cheese], self.kg, "satuan lain kategori tidak dikonversi")
        # Outlet yang sama dipakai ulang, outlet lain jadi alamat kirim baru di bawah pelanggan yang sama.
        again = Sync.import_json(sor("95-SKI-SOR-261100002", "ranch market rm99 kemang", [
            {"item_code": "EFR03FAL0005", "uom_id": "JAR", "qty": 1}]))
        self.assertEqual(again.picking_id.partner_id, picking.partner_id)
        other = Sync.import_json(sor("95-SKI-SOR-261100003", "RANCH MARKET P.I.", [
            {"item_code": "EFR03FAL0005", "uom_id": "JAR", "qty": 1}]))
        self.assertEqual(other.picking_id.partner_id.parent_id, customer)
        self.assertNotEqual(other.picking_id.partner_id, picking.partner_id)
        self.assertTrue(customer.wms_is_destination)

    def test_dashboard_summary(self):
        lot = self.env["stock.lot"].create({
            "name": "LEP-D", "product_id": self.cheese.id, "expiration_date": datetime.now() + timedelta(days=10)})
        self.env["stock.quant"]._update_available_quantity(self.cheese, self.fz_rack, 20, lot_id=lot)
        data = self.env["wms.dashboard"].summary()
        frozen = next(z for z in data["zones"] if z["zone"] == "frozen")
        self.assertEqual(frozen["value"], 20 * 95000)
        self.assertEqual(frozen["occupied"], 1)
        self.assertEqual(data["kpi"]["near_count"], 1)
        self.assertEqual(data["expiry"]["by_zone"]["frozen"][1], 20 * 95000)
        self.assertEqual(len(data["flow"]["days"]), 30)
