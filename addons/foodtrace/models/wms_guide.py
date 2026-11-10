from odoo import api, models

from .wms_guide_data import CONCEPTS, MODEL_SCREENS, ROLES, SCREENS


class FoodtraceGuide(models.AbstractModel):
    """Panduan penggunaan: dipakai menu Panduan dan tombol bantuan (?) di setiap layar."""

    _name = "foodtrace.guide"
    _description = "Panduan penggunaan FoodTrace"

    @api.model
    def _render_screen(self, key):
        screen = SCREENS.get(key)
        if not screen:
            return None
        model = self.env.get(screen["model"]) if screen.get("model") else None
        model_fields = model._fields if model is not None else {}
        fields_out = []
        for name, desc in screen.get("fields", []):
            if name.startswith("#"):
                label = name[1:]
            elif name in model_fields:
                label = model_fields[name]._description_string(self.env)
            else:
                label = name
            fields_out.append({"label": label, "desc": desc})
        return {
            "key": key,
            "title": screen["title"],
            "purpose": screen.get("purpose", ""),
            "steps": screen.get("steps", []),
            "fields": fields_out,
            "tips": screen.get("tips", []),
            "roles": [r["name"] for r in ROLES if key in r["screens"]],
        }

    @api.model
    def get_guide(self):
        return {
            "concepts": CONCEPTS,
            "roles": [dict(role, screens=[self._render_screen(k) for k in role["screens"] if k in SCREENS])
                      for role in ROLES],
        }

    @api.model
    def _resolve_key(self, model=None, context=None, res_id=None, tag=None, key=None):
        context = context or {}
        if key and key in SCREENS:
            return key
        if context.get("foodtrace_guide") in SCREENS:
            return context["foodtrace_guide"]
        if tag == "foodtrace.dashboard":
            return "dashboard"
        if tag == "foodtrace_mobile.hht":
            return "hht.home"
        if model == "stock.picking":
            code = context.get("restricted_picking_type_code")
            if not code and res_id:
                code = self.env["stock.picking"].browse(res_id).exists().picking_type_code
            return {"incoming": "receipt", "outgoing": "delivery"}.get(code, "putaway")
        if model == "wms.butcher":
            kind = context.get("default_kind")
            if not kind and res_id:
                kind = self.env["wms.butcher"].browse(res_id).exists().kind
            return "butcher_in" if kind == "in" else "butcher_out"
        if model == "stock.quant.package" and context.get("search_default_need_reprint"):
            return "lpn"
        return MODEL_SCREENS.get(model)

    @api.model
    def get_screen(self, model=None, context=None, res_id=None, tag=None, key=None):
        """Keterangan layar aktif. Tanpa kecocokan: kembalikan daftar konsep agar tombol tetap berguna."""
        found = self._resolve_key(model=model, context=context, res_id=res_id, tag=tag, key=key)
        screen = self._render_screen(found) if found else None
        return {"screen": screen, "concepts": [{"key": c["key"], "title": c["title"]} for c in CONCEPTS]}
