from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    wms_min_shelf_life_pct = fields.Integer(
        "Min. sisa umur saat kirim (%)", default=0,
        help="Karton dengan sisa umur simpan di bawah angka ini tidak boleh dikirim ke pelanggan ini.")
    wms_over_receive_pct = fields.Float(
        "Toleransi over receiving (%)", default=0,
        help="Penerimaan di atas qty PO + toleransi ditolak. Importir boleh diberi toleransi.")
