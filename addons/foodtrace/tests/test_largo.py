from datetime import datetime, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_wms import TestWms


@tagged("post_install", "-at_install", "foodtrace")
class TestLargoFlows(TestWms):
    """Alur dari user guide Largo: QC, LPN, picking job → loading → POD, inventory check, butcher."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Loc = cls.env["stock.location"]
        stock = cls.wh.lot_stock_id
        cls.dr_rack = Loc.create({"name": "DR-BLK-A01-1-1", "location_id": cls.dr.id, "wms_area": "blk"})
        cls.fz_dmg = Loc.create({"name": "FZ-DMG", "location_id": cls.fz.id, "wms_area": "dmg", "wms_zone": "frozen"})
        cls.staging = Loc.create({"name": "OUT-STAGING", "location_id": stock.id, "wms_area": "out"})
        cls.customer = cls.env["res.partner"].create({"name": "Resto Makassar"})

    def _stock(self, product, qty, location, lot_name=None, days=200, package=None):
        lot = False
        if lot_name:
            lot = self.env["stock.lot"].create({
                "name": lot_name, "product_id": product.id,
                "expiration_date": datetime.now() + timedelta(days=days)})
        self.env["stock.quant"]._update_available_quantity(
            product, location, qty, lot_id=lot or None, package_id=package)
        return lot

    def _delivery(self, product, qty):
        out = self.env["stock.picking"].create({
            "picking_type_id": self.wh.out_type_id.id, "partner_id": self.customer.id,
            "location_id": self.wh.lot_stock_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "wms_shipping_group": "RUTE-01",
            "move_ids": [(0, 0, {"name": product.name, "product_id": product.id, "product_uom_qty": qty,
                                 "product_uom": product.uom_id.id, "location_id": self.wh.lot_stock_id.id,
                                 "location_dest_id": self.env.ref("stock.stock_location_customers").id})],
        })
        out.action_confirm()
        return out

    def test_over_receiving_tolerance(self):
        self.owner.wms_over_receive_pct = 5
        picking = self._receipt(self.milk, 10, self.dr_rack)
        picking.partner_id = self.owner
        picking.move_ids.quantity = 11
        with self.assertRaisesRegex(UserError, "Over receiving"):
            picking.button_validate()
        picking.move_ids.quantity = 10.5
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_auto_quarantine_and_qc_release_split(self):
        self.fries.wms_auto_quarantine = True
        picking = self._receipt(self.fries, 20, self.fz_rack)
        picking.wms_temperature_ids = [(0, 0, {"zone": "frozen", "temperature": -20, "source": "receipt"})]
        picking.button_validate()
        quant = self.env["stock.quant"].search([("product_id", "=", self.fries.id), ("location_id", "=", self.fz_qc.id)])
        self.assertEqual(quant.wms_status, "hold")
        wiz = self.env["wms.qc.release.wizard"].with_context(default_quant_id=quant.id).create({
            "qty_good": 18, "qty_damage": 2})
        wiz.action_confirm()
        qty = lambda loc: sum(self.env["stock.quant"].search(
            [("product_id", "=", self.fries.id), ("location_id", "=", loc.id)]).mapped("quantity"))
        self.assertEqual(qty(self.fz), 18)
        self.assertEqual(qty(self.fz_dmg), 2)

    def test_lpn_single_sku(self):
        pack = self.env["stock.quant.package"].create({})
        self._stock(self.milk, 5, self.dr_rack, package=pack)
        picking = self._receipt(self.milk, 3, self.dr_rack)
        picking.move_line_ids.result_package_id = pack
        picking.button_validate()
        other = self.env["product.product"].create({"name": "Dry lain", "is_storable": True, "wms_zone": "dry"})
        picking = self._receipt(other, 3, self.dr_rack)
        picking.move_line_ids.result_package_id = pack
        with self.assertRaisesRegex(UserError, "1 SKU"):
            picking.button_validate()

    def test_picking_job_loading_and_pod(self):
        self._stock(self.milk, 50, self.dr_rack)
        out1, out2 = self._delivery(self.milk, 10), self._delivery(self.milk, 5)
        action = self.env["stock.picking"].with_context(active_ids=(out1 | out2).ids).action_wms_create_picking_job()
        batch = self.env["stock.picking.batch"].browse(action["res_id"])
        self.assertEqual(batch.picking_ids, out1 | out2)
        self.assertEqual(batch.description, "RUTE-01")
        self.assertAlmostEqual(batch.wms_ready_pct, 100.0)
        job = self.env["wms.loading"].create({"vehicle_plate": "DD 1234 XY", "driver": "Budi",
                                              "picking_ids": [(6, 0, (out1 | out2).ids)]})
        self.assertTrue(job.name.startswith("LD/"))
        with self.assertRaisesRegex(UserError, "bukan muatan"):
            job.load_scan("TIDAK-ADA")
        with self.assertRaisesRegex(UserError, "belum discan"):
            job.action_close()
        job.load_scan("HID3CIM006")
        job.load_scan("HID3CIM006")
        self.assertEqual(job.loaded_count, 2)
        job.action_close()
        self.assertEqual(job.state, "close")
        self.assertEqual(set((out1 | out2).mapped("state")), {"done"})
        pod = out1.wms_pod_id
        self.assertTrue(pod.get_url().endswith(pod.token))
        with self.assertRaisesRegex(UserError, "Suhu"):
            pod.submit("", "Andi", {})
        pod.submit("4.5", "Andi", {str(pod.line_ids.id): {"qty": 9, "remark": "1 penyok"}})
        self.assertTrue(pod.has_difference)
        self.assertEqual(out1.wms_stage, "delivered")
        self.env.ref("foodtrace.action_report_manifest")._render_qweb_html(
            "foodtrace.report_manifest", job.ids)
        self.env.ref("foodtrace.action_report_surat_jalan")._render_qweb_html(
            "foodtrace.report_surat_jalan", out1.ids)

    def test_inventory_check_with_approval(self):
        pack = self.env["stock.quant.package"].create({})
        lot = self._stock(self.cheese, 12, self.fz_rack, "IC-1", package=pack)
        check = self.env["wms.inventory.check"].create({"mode": "lpn", "package_id": pack.id})
        check.action_load()
        self.assertEqual(len(check.line_ids), 1)
        new_expiry = datetime.now().replace(microsecond=0) + timedelta(days=100)
        check.line_ids.write({"qty_after": 11.2, "expiry_after": new_expiry})
        self.assertTrue(check.line_ids.need_reprint)
        check.action_submit()
        check.action_approve()
        self.assertEqual(check.state, "approved")
        self.assertAlmostEqual(pack.wms_qty, 11.2)
        self.assertEqual(lot.expiration_date, new_expiry)
        self.assertTrue(pack.wms_need_reprint)
        self.env.ref("foodtrace.action_report_lpn_label")._render_qweb_html(
            "foodtrace.report_lpn_label", pack.ids)

    def test_butcher_out_in_yield(self):
        pack = self.env["stock.quant.package"].create({})
        lot = self._stock(self.cheese, 20, self.fz_rack, "BO-1", package=pack)
        out = self.env["wms.butcher"].create({"kind": "out", "ref": "SPK-01", "line_ids": [(0, 0, {
            "package_id": pack.id, "product_id": self.cheese.id, "lot_id": lot.id, "qty": 20})]})
        self.assertTrue(out.name.startswith("BO/"))
        out.action_done()
        self.assertAlmostEqual(pack.wms_qty, 0)
        result = self.env["wms.butcher"].create({"kind": "in", "source_id": out.id, "line_ids": [(0, 0, {
            "process_type": "rebag", "product_id": self.cheese.id, "qty": 18, "location_id": self.fz_rack.id,
            "grade": "A", "brand": "LEPRINO", "cutting_type": "Shredded"})]})
        result.action_done()
        line = result.line_ids
        self.assertEqual(line.lot_id.wms_grade, "A")
        self.assertTrue(line.lot_id.expiration_date)
        self.assertAlmostEqual(line.package_id.wms_qty, 18)
        self.assertAlmostEqual(out.yield_pct, 90.0)
        with self.assertRaisesRegex(UserError, "zona"):
            self.env["wms.butcher"].create({"kind": "in", "line_ids": [(0, 0, {
                "product_id": self.cheese.id, "qty": 1, "location_id": self.dr_rack.id})]}).action_done()
