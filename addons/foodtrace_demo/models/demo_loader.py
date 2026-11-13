from odoo import api, models


class FoodtraceDemoLoader(models.AbstractModel):
    """Melanjutkan pembuatan data demo bertahap bila modul dipasang dari menu Apps."""

    _name = "foodtrace.demo.loader"
    _description = "Pemuat data demo FoodTrace"

    @api.model
    def _cron_continue(self):
        from ..hooks import Demo

        demo = Demo.resume(self.sudo().env)
        if demo is not None:
            demo.continue_batch()
