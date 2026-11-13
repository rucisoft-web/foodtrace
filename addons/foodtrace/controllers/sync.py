import hmac

from odoo import http
from odoo.http import request


class WmsSyncController(http.Controller):
    """Endpoint sinkron SAP → WMS. Body = isi file POR/SOR (list JSON); header X-WMS-Token."""

    @http.route("/wms/api/v1/sync", type="http", auth="none", methods=["POST"], csrf=False)
    def sync(self, **_kw):
        env = request.env(su=True)
        token = env["ir.config_parameter"].get_param("foodtrace.sync_token") or ""
        sent = request.httprequest.headers.get("X-WMS-Token", "")
        if not token or not hmac.compare_digest(token, sent):
            return request.make_json_response({"error": "token tidak valid"}, status=401)
        try:
            docs = env["wms.sync.document"].import_json(request.httprequest.get_data(as_text=True))
        except (ValueError, KeyError) as exc:
            return request.make_json_response({"error": f"format tidak valid: {exc}"}, status=400)
        return request.make_json_response({
            "results": [{"number": d.name, "state": d.state, "picking": d.picking_id.name or None,
                         "error": d.error or None} for d in docs],
        })
