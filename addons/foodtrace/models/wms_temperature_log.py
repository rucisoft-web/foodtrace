from odoo import api, fields, models

from .wms_zone import ZONES


class WmsTemperatureLog(models.Model):
    """Catatan suhu ruang, produk, dan truk. Manual di handheld sampai sensor terpasang."""

    _name = "wms.temperature.log"
    _description = "Log suhu"
    _order = "date desc, id desc"

    date = fields.Datetime("Waktu", required=True, default=fields.Datetime.now, index=True)
    zone = fields.Selection(ZONES, "Zona", required=True, index=True)
    location_id = fields.Many2one("stock.location", "Ruang / lokasi", domain=[("usage", "=", "internal")])
    temperature = fields.Float("Suhu (°C)", required=True, digits=(4, 1))
    humidity = fields.Float("Kelembapan (%)", digits=(4, 1))
    source = fields.Selection(
        [("manual", "Manual ruang"), ("receipt", "Produk saat terima"), ("truck", "Truk"),
         ("delivery", "Produk saat kirim"), ("sensor", "Sensor")],
        "Sumber", required=True, default="manual")
    picking_id = fields.Many2one("stock.picking", "Dokumen", index=True)
    user_id = fields.Many2one("res.users", "Petugas", default=lambda self: self.env.user)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    standard_id = fields.Many2one("wms.zone.standard", compute="_compute_alarm", store=True)
    target_temp = fields.Float("Standar (°C)", related="standard_id.target_temp")
    alarm_temp = fields.Float("Batas alarm (°C)", related="standard_id.alarm_temp")
    is_alarm = fields.Boolean("Alarm", compute="_compute_alarm", store=True, index=True)
    deviation = fields.Float("Selisih dari batas (°C)", compute="_compute_alarm", store=True, digits=(4, 1))
    note = fields.Char("Catatan")
    state = fields.Selection(
        [("open", "Perlu tindak lanjut"), ("done", "Selesai")], default="done", required=True)

    @api.depends("zone", "temperature", "humidity")
    def _compute_alarm(self):
        standards = {s.zone: s for s in self.env["wms.zone.standard"].search([])}
        for log in self:
            std = standards.get(log.zone)
            log.standard_id = std
            if not std:
                log.is_alarm, log.deviation = False, 0.0
                continue
            hot = log.temperature > std.alarm_temp
            humid = bool(std.max_humidity and log.humidity and log.humidity > std.max_humidity)
            log.is_alarm = hot or humid
            log.deviation = log.temperature - std.alarm_temp if hot else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        logs = super().create(vals_list)
        for log in logs.filtered("is_alarm"):
            log.state = "open"
        return logs

    def action_close(self):
        self.write({"state": "done"})
