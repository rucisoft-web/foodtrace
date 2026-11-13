from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    wms_min_shelf_life_pct = fields.Integer(
        "Min. sisa umur saat kirim (%)", default=0,
        help="Karton dengan sisa umur simpan di bawah angka ini tidak boleh dikirim ke pelanggan ini.")
    wms_over_receive_pct = fields.Float(
        "Toleransi over receiving (%)", default=0,
        help="Penerimaan di atas qty PO + toleransi ditolak. Importir boleh diberi toleransi.")
    wms_is_source = fields.Boolean(
        "Source (pemasok)", index=True,
        help="Tampil di Source Master. Terisi otomatis saat partner dipakai di dokumen inbound.")
    wms_is_destination = fields.Boolean(
        "Destination (pelanggan)", index=True,
        help="Tampil di Destination Master. Terisi otomatis saat partner dipakai di dokumen outbound.")
