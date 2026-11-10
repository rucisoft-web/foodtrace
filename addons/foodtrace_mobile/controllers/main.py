from odoo import http
from odoo.http import request


class WmsHht(http.Controller):
    @http.route("/wms/hht", type="http", auth="user")
    def hht(self, **_kw):
        """Alamat pendek untuk shortcut di handheld."""
        return request.redirect("/odoo/action-foodtrace_mobile.action_hht")
