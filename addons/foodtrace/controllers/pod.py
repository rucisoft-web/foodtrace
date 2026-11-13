import base64

from markupsafe import escape

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>POD {name}</title>
<style>body{{font-family:sans-serif;margin:0;padding:16px;background:#f4f6f8;color:#1d2733}}
.card{{background:#fff;border-radius:10px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px #0002}}
h1{{font-size:20px;margin:0 0 4px}} label{{display:block;font-weight:600;margin:10px 0 4px}}
input,textarea{{width:100%;box-sizing:border-box;font-size:18px;padding:10px;border:1px solid #c5ccd3;border-radius:8px}}
table{{width:100%;border-collapse:collapse}} td{{padding:6px 4px;border-bottom:1px solid #eee;vertical-align:middle}}
td input{{font-size:16px;padding:6px}} button{{width:100%;font-size:20px;padding:14px;background:#0b6e4f;color:#fff;
border:0;border-radius:10px}} .ok{{background:#e3f5ec;color:#0b6e4f}} .err{{background:#fde8e8;color:#9b1c1c}}</style>
</head><body>{body}</body></html>"""


class WmsPodController(http.Controller):

    def _pod(self, token):
        return request.env["wms.pod"].sudo().search([("token", "=", token)], limit=1)

    def _render(self, pod, message="", cls="ok"):
        head = (f'<div class="card"><h1>Proof of Delivery {escape(pod.name)}</h1>'
                f'<div>{escape(pod.partner_id.display_name or "")}</div></div>')
        note = f'<div class="card {cls}">{escape(message)}</div>' if message else ""
        if pod.state == "done":
            body = head + note + (f'<div class="card ok">Sudah diterima oleh {escape(pod.received_by or "")} '
                                  f'pada {pod.received_at}.</div>')
        else:
            rows = "".join(
                f'<tr><td>{escape(l.product_id.display_name)}<br><small>dikirim {l.qty_sent:g} '
                f'{escape(l.uom_id.name or "")}</small></td>'
                f'<td style="width:90px"><input name="qty_{l.id}" type="number" step="any" value="{l.qty_received:g}"></td>'
                f'<td style="width:110px"><input name="remark_{l.id}" placeholder="catatan"></td></tr>'
                for l in pod.line_ids)
            body = head + note + (
                f'<form method="post" enctype="multipart/form-data">'
                f'<input type="hidden" name="csrf_token" value="{request.csrf_token()}">'
                f'<div class="card"><label>Diterima oleh *</label><input name="received_by" required></div>'
                f'<div class="card"><table>{rows}</table></div>'
                f'<div class="card"><label>Foto bukti terima</label>'
                f'<input name="photo" type="file" accept="image/*" capture="environment">'
                f'<label>Catatan</label><textarea name="remark" rows="2"></textarea></div>'
                f'<button type="submit">Kirim POD</button></form>')
        return request.make_response(PAGE.format(name=escape(pod.name), body=body),
                                     headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route("/wms/pod/<string:token>", type="http", auth="public", methods=["GET", "POST"], csrf=True)
    def pod(self, token, **post):
        pod = self._pod(token)
        if not pod:
            return request.not_found()
        if request.httprequest.method == "POST":
            lines = {str(l.id): {"qty": post.get(f"qty_{l.id}"), "remark": post.get(f"remark_{l.id}")}
                     for l in pod.line_ids}
            photo = post.get("photo")
            data = base64.b64encode(photo.read()) if photo and getattr(photo, "filename", "") else None
            try:
                pod.submit(post.get("received_by"), lines, photo=data,
                           remark=post.get("remark"))
            except UserError as e:
                return self._render(pod, str(e), "err")
            return self._render(pod, "Terima kasih, POD tersimpan.")
        return self._render(pod)
