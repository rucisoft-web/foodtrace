import re
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

LB_TO_KG = 0.45359237
GS = "\x1d"
# AI GS1 yang dipakai label karton daging/keju: panjang tetap atau variabel (None).
GS1_FIXED = {"00": 18, "01": 14, "02": 14, "11": 6, "13": 6, "15": 6, "17": 6}
GS1_VARIABLE = {"10", "21", "37"}


def _gs1_date(text):
    yy, mm, dd = int(text[:2]), int(text[2:4]), int(text[4:6])
    return date(2000 + yy, mm, dd or 28)


def parse_gs1(raw):
    """Urai GS1-128 dalam bentuk '(01)..(3102)..' atau string mentah dengan pemisah FNC1."""
    out = {}
    text = raw.strip()
    if text.startswith("("):
        for ai, value in re.findall(r"\((\d{2,4})\)([^(]*)", text):
            out[ai] = value
        return out
    text = text.replace("]C1", "")
    i = 0
    while i < len(text):
        if text[i] == GS:
            i += 1
            continue
        ai2 = text[i:i + 2]
        if ai2 in GS1_FIXED:
            out[ai2] = text[i + 2:i + 2 + GS1_FIXED[ai2]]
            i += 2 + GS1_FIXED[ai2]
        elif text[i:i + 3] in ("310", "320"):
            ai = text[i:i + 4]
            out[ai] = text[i + 4:i + 10]
            i += 10
        elif ai2 in GS1_VARIABLE:
            end = text.find(GS, i + 2)
            end = len(text) if end == -1 else end
            out[ai2] = text[i + 2:end]
            i = end
        else:
            raise ValueError(f"AI GS1 tidak dikenal di posisi {i}: {text[i:i + 4]}")
    return out


class WmsBarcodeTemplate(models.Model):
    """Format barcode karton per item: GS1-128 atau pola regex dengan grup bernama."""

    _name = "wms.barcode.template"
    _description = "Template barcode karton"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    kind = fields.Selection([("gs1", "GS1-128"), ("regex", "Pola regex")], required=True, default="gs1")
    pattern = fields.Char(
        "Pola regex",
        help="Grup bernama: weight, lot, expiry (YYMMDD), carton. Contoh: ^(?P<carton>\\d{8})(?P<weight>\\d{5})(?P<lot>\\w{6})$")
    weight_unit = fields.Selection([("kg", "Kg"), ("lb", "Lbs")], default="kg", required=True)
    weight_decimals = fields.Integer("Desimal berat (regex)", default=2)
    min_weight = fields.Float("Berat min. (kg)")
    max_weight = fields.Float("Berat maks. (kg)")
    sample = fields.Char("Contoh barcode")
    product_tmpl_ids = fields.Many2many("product.template", string="Item")
    active = fields.Boolean(default=True)

    def parse(self, raw):
        """Kembalikan dict weight_kg, lot, expiry, carton dari satu scan, atau raise UserError."""
        self.ensure_one()
        try:
            data = self._parse_gs1(raw) if self.kind == "gs1" else self._parse_regex(raw)
        except (ValueError, KeyError) as exc:
            raise UserError(_("Barcode %(raw)s tidak cocok dengan template %(name)s: %(err)s",
                              raw=raw, name=self.name, err=exc)) from exc
        weight = data.get("weight_kg") or 0.0
        if self.min_weight and weight < self.min_weight or self.max_weight and weight > self.max_weight:
            raise UserError(_("Berat %(w).2f kg di luar batas template %(name)s (salah baca?).",
                              w=weight, name=self.name))
        return data

    def _parse_gs1(self, raw):
        ais = parse_gs1(raw)
        weight = 0.0
        for ai, value in ais.items():
            if ai[:3] in ("310", "320"):
                weight = int(value) / (10 ** int(ai[3]))
                if ai.startswith("320"):
                    weight *= LB_TO_KG
        if not weight:
            raise ValueError("berat (AI 310x/320x) tidak ada")
        weight_lb = next((int(v) / (10 ** int(a[3])) for a, v in ais.items() if a.startswith("320")), 0.0)
        expiry = ais.get("17") or ais.get("15")
        return {
            "weight_kg": round(weight, 3),
            "weight_lb": weight_lb,
            "lot": ais.get("10"),
            "expiry": _gs1_date(expiry) if expiry else False,
            "carton": ais.get("21") or ais.get("00"),
            "gtin": ais.get("01"),
        }

    def _parse_regex(self, raw):
        match = re.match(self.pattern or "", raw.strip())
        if not match:
            raise ValueError("pola tidak cocok")
        groups = match.groupdict()
        weight = int(groups["weight"]) / (10 ** self.weight_decimals) if groups.get("weight") else 0.0
        weight_lb = weight if self.weight_unit == "lb" else 0.0
        if self.weight_unit == "lb":
            weight *= LB_TO_KG
        expiry = groups.get("expiry")
        return {
            "weight_kg": round(weight, 3),
            "weight_lb": weight_lb,
            "lot": groups.get("lot"),
            "expiry": _gs1_date(expiry) if expiry else False,
            "carton": groups.get("carton"),
        }

    @api.model
    def parse_for_product(self, product, raw):
        """Coba semua template milik item (berurutan). Template pertama yang cocok dipakai."""
        errors = []
        for template in product.product_tmpl_id.wms_barcode_template_ids:
            try:
                return template, template.parse(raw)
            except UserError as exc:
                errors.append(str(exc))
        raise UserError(_("Barcode tidak terbaca untuk %(p)s. Isi berat manual.\n%(e)s",
                          p=product.display_name, e="\n".join(errors) or _("Item belum punya template.")))

    def action_test_sample(self):
        self.ensure_one()
        data = self.parse(self.sample or "")
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Hasil uji"), "type": "success", "message": str(data)},
        }
