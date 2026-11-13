from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.foodtrace.tests.test_largo import TestLargoFlows


@tagged("post_install", "-at_install", "foodtrace")
class TestMobile(TestLargoFlows):
    """Alur handheld end to end: receiving per palet → put away → picking job → staging → checker → loading."""

    def test_hht_full_flow(self):
        M = self.env["wms.mobile"]
        self.assertIn("receipts", M.home())
        receipt = self._receipt(self.milk, 0, self.dr_rack)
        receipt.move_ids.write({"product_uom_qty": 20, "quantity": 0})
        receipt.move_line_ids.unlink()
        move = receipt.move_ids
        dock = self.env["stock.location"].create({
            "name": "DOCK_01", "barcode": "DOCK_01", "location_id": self.wh.lot_stock_id.id, "wms_area": "rcv"})
        M.receipt_scan(receipt.id, move.id, qty=12)
        opened = M.receipt_open(receipt.id)
        self.assertIn({"id": dock.id, "name": "DOCK_01"}, opened["docks"])
        pallet = opened["pallets"][0]
        res = M.receipt_close_pallet(receipt.id, pallet["id"], pallet_no="P1", packaging="Karton", grade="A")
        self.assertIn("/report/pdf/foodtrace.report_lpn_label/", res["label_url"])
        pack = self.env["stock.quant.package"].browse(pallet["id"])
        self.assertEqual(pack._wms_label_data()["qty"], "12")
        self.assertEqual(pack._wms_label_data()["packaging"], "Karton")
        M.receipt_scan(receipt.id, move.id, qty=8)
        pallets = M.receipt_open(receipt.id)["pallets"]
        self.assertEqual(len(pallets), 2)
        with self.assertRaisesRegex(UserError, "Loading dock"):
            M.receipt_validate(receipt.id, plate="DD 1", driver="Ali")
        M.receipt_validate(receipt.id, plate="DD 1", driver="Ali", dock_id=dock.id)
        self.assertEqual(receipt.state, "done")
        self.assertEqual(receipt.wms_dock_id, dock)
        lpns = [p["lpn"] for p in pallets]
        rack2 = self.env["stock.location"].create({"name": "DR-BLK-A02-1-1", "location_id": self.dr.id,
                                                   "wms_area": "blk", "barcode": "SKI-DR-A02"})
        M.move_lpns(lpns, "SKI-DR-A02")
        self.assertEqual(sum(self.env["stock.quant"].search(
            [("location_id", "=", rack2.id), ("product_id", "=", self.milk.id)]).mapped("quantity")), 20)

        out1, out2 = self._delivery(self.milk, 6), self._delivery(self.milk, 4)
        action = self.env["stock.picking"].with_context(active_ids=(out1 | out2).ids).action_wms_create_picking_job()
        batch_id = action["res_id"]
        self.assertTrue(M.job_list())
        job = M.delivery_open(batch_id=batch_id)
        self.assertEqual(set(job["picking_ids"]), set((out1 | out2).ids))
        for task in job["tasks"]:
            with self.assertRaisesRegex(UserError, "Lokasi salah"):
                M.delivery_pick(task["id"], self.fz_rack.name, "HID3CIM006", batch_id=batch_id)
            M.delivery_pick(task["id"], task["location"], "HID3CIM006", batch_id=batch_id)
        with self.assertRaisesRegex(UserError, "bukan lokasi outbound staging"):
            M.delivery_stage(job["picking_ids"], self.dr_rack.name)
        M.delivery_stage(job["picking_ids"], self.staging.name)
        self.assertEqual(out1.wms_stage, "staged")
        check = M.check_open(out1.name)
        with self.assertRaisesRegex(UserError, "tidak ada"):
            M.check_scan(check["id"], "SALAH")
        for _line in check["lines"]:
            res = M.check_scan(check["id"], "HID3CIM006")
        self.assertEqual(out1.wms_stage, "checked")
        loading = self.env["wms.loading"].create({"vehicle_plate": "DD 2", "picking_ids": [(6, 0, out1.ids)]})
        self.assertTrue(M.loading_list())
        for _line in out1.move_line_ids:
            M.loading_scan(loading.id, "HID3CIM006")
        M.loading_close(loading.id)
        self.assertEqual(out1.state, "done")
        self.assertTrue(out1.wms_pod_id)

    def test_hht_inventory_check_and_butcher(self):
        M = self.env["wms.mobile"]
        pack = self.env["stock.quant.package"].create({})
        self._stock(self.cheese, 10, self.fz_rack, "HHT-1", package=pack)
        ic = M.ic_open(pack.name)
        M.ic_submit(ic["id"], [{"id": ic["lines"][0]["id"], "qty": 9.5}])
        check = self.env["wms.inventory.check"].browse(ic["id"])
        self.assertEqual(check.state, "submitted")
        self.assertEqual(check.difference_count, 1)
        M.butcher_out(pack.name, qty=4, ref="SPK-9")
        self.assertAlmostEqual(pack.wms_qty, 6)
