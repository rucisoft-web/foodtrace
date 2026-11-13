from odoo.tests import TransactionCase, tagged

from ..models.wms_guide_data import CONCEPTS, MODEL_SCREENS, ROLES, SCREENS


@tagged("post_install", "-at_install", "foodtrace")
class TestGuide(TransactionCase):

    def test_every_field_exists_and_every_screen_is_reachable(self):
        for key, screen in SCREENS.items():
            self.assertTrue(screen.get("purpose"), key)
            model = screen.get("model")
            if model:
                self.assertIn(model, self.env, key)
            for name, desc in screen.get("fields", []):
                self.assertTrue(desc, f"{key}.{name}")
                if not name.startswith("#"):
                    self.assertTrue(model, f"{key}: field {name} butuh model")
                    self.assertIn(name, self.env[model]._fields, f"{key}: {model}.{name}")
        in_roles = {k for r in ROLES for k in r["screens"]}
        self.assertEqual(in_roles, set(SCREENS), "setiap layar harus masuk minimal satu kelompok pengguna")
        self.assertTrue(set(MODEL_SCREENS.values()) <= set(SCREENS))
        self.assertGreaterEqual(len(CONCEPTS), 8)

    def test_screen_resolution(self):
        Guide = self.env["foodtrace.guide"]
        get = lambda **kw: (Guide.get_screen(**kw)["screen"] or {}).get("key")
        self.assertEqual(get(model="stock.picking", context={"restricted_picking_type_code": "incoming"}), "receipt")
        self.assertEqual(get(model="stock.picking", context={"restricted_picking_type_code": "outgoing"}), "delivery")
        self.assertEqual(get(model="wms.butcher", context={"default_kind": "in"}), "butcher_in")
        self.assertEqual(get(model="wms.loading"), "loading")
        self.assertEqual(get(tag="foodtrace.dashboard"), "dashboard")
        self.assertEqual(get(key="hht.receipt"), "hht.receipt")
        self.assertEqual(get(model="stock.quant", context={"foodtrace_guide": "report_by_location"}), "report_by_location")
        self.assertEqual(get(model="stock.quant", context={"foodtrace_guide": "report_by_item"}), "report_by_item")
        for xmlid in ("foodtrace.action_report_by_location", "foodtrace.action_report_by_item"):
            action = self.env.ref(xmlid)
            self.assertEqual(action.res_model, "stock.quant")
        self.assertIsNone(Guide.get_screen(model="res.users")["screen"])
        screen = Guide.get_screen(model="wms.loading")["screen"]
        labels = [f["label"] for f in screen["fields"]]
        self.assertIn("Plat nomor kendaraan", labels)
        guide = Guide.get_guide()
        self.assertEqual(len(guide["roles"]), len(ROLES))
