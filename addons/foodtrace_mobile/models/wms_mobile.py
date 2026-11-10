from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

ZONE_LABEL = {"frozen": "Frozen", "chilled": "Chilled", "dry": "Dry"}


class WmsMobile(models.AbstractModel):
    """API untuk aplikasi handheld. Setiap langkah = satu scan, hasil dikembalikan sebagai dict sederhana."""

    _name = "wms.mobile"
    _description = "API mobile terminal WMS"

    # ------------------------------------------------------------------ util
    @api.model
    def _warehouse(self):
        return self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)

    @api.model
    def _find_location(self, code):
        code = (code or "").strip()
        if not code:
            raise UserError(_("Scan barcode lokasi."))
        Loc = self.env["stock.location"]
        loc = Loc.search([("barcode", "=", code), ("company_id", "in", [False, self.env.company.id])], limit=1)
        loc = loc or Loc.search([("complete_name", "=ilike", code), ("usage", "=", "internal")], limit=1)
        loc = loc or Loc.search([("name", "=ilike", code), ("usage", "=", "internal"),
                                 ("company_id", "=", self.env.company.id)], limit=1)
        if not loc:
            raise UserError(_("Lokasi %s tidak dikenal.", code))
        return loc

    @api.model
    def _find_package(self, code):
        pack = self.env["stock.quant.package"].search([("name", "=", (code or "").strip())], limit=1)
        if not pack:
            raise UserError(_("LPN %s tidak dikenal.", code))
        return pack

    @api.model
    def _find_product(self, code):
        code = (code or "").strip()
        Product = self.env["product.product"]
        return Product.search(["|", ("barcode", "=", code), ("default_code", "=", code)], limit=1)

    @api.model
    def _quant_dict(self, q):
        return {
            "id": q.id, "product": q.product_id.display_name, "code": q.product_id.default_code,
            "lot": q.lot_id.name or "", "expiry": fields.Date.to_string(q.lot_id.expiration_date) if q.lot_id.expiration_date else "",
            "qty": round(q.quantity, 3), "uom": q.product_uom_id.name, "location": q.location_id.complete_name,
            "lpn": q.package_id.name or "", "status": q.wms_status, "zone": q.product_id.wms_zone or "",
        }

    @api.model
    def _picking_head(self, p):
        return {
            "id": p.id, "name": p.name, "origin": p.origin or "", "partner": p.partner_id.display_name or "",
            "date": fields.Date.to_string(p.scheduled_date) if p.scheduled_date else "",
            "state": p.state, "group": p.wms_shipping_group or "", "priority": p.wms_priority or "",
            "needs_temp": p.wms_needs_temp, "temp_logged": p.wms_temp_logged, "temp_alarm": p.wms_temp_alarm,
            "lines": len(p.move_ids),
        }

    # ------------------------------------------------------------------ home
    @api.model
    def home(self):
        Picking = self.env["stock.picking"]
        base = [("company_id", "=", self.env.company.id), ("state", "in", ("confirmed", "assigned", "waiting"))]
        return {
            "user": self.env.user.name,
            "company": self.env.company.name,
            "warehouse": self._warehouse().name,
            "receipts": Picking.search_count(base + [("picking_type_code", "=", "incoming")]),
            "deliveries": Picking.search_count(base + [("picking_type_code", "=", "outgoing")]),
            "hold": self.env["stock.quant"].search_count([("wms_status", "=", "hold"), ("quantity", ">", 0)]),
            "alarms": self.env["wms.temperature.log"].search_count([("state", "=", "open")]),
            "jobs": self.env["stock.picking.batch"].search_count([
                ("state", "=", "in_progress"), ("picking_ids.picking_type_code", "=", "outgoing")]),
            "staged": Picking.search_count([("picking_type_code", "=", "outgoing"), ("wms_stage", "=", "staged")]),
            "loadings": self.env["wms.loading"].search_count([("state", "=", "open")]),
        }

    # ------------------------------------------------------------- receiving
    @api.model
    def receipt_list(self):
        pickings = self.env["stock.picking"].search([
            ("company_id", "=", self.env.company.id), ("picking_type_code", "=", "incoming"),
            ("state", "in", ("confirmed", "assigned", "waiting"))], order="scheduled_date, id")
        return [self._picking_head(p) for p in pickings]

    @api.model
    def _find_picking(self, code, kind):
        code = (code or "").strip()
        picking = self.env["stock.picking"].search([
            ("picking_type_code", "=", kind), ("state", "not in", ("done", "cancel")),
            "|", ("name", "=", code), ("origin", "=", code)], limit=1)
        if not picking:
            raise UserError(_("Dokumen %s tidak ditemukan atau sudah selesai.", code))
        return picking

    @api.model
    def receipt_open(self, picking_id=None, code=None):
        picking = self.env["stock.picking"].browse(picking_id) if picking_id else self._find_picking(code, "incoming")
        Carton = self.env["wms.carton"]
        lines = []
        for move in picking.move_ids:
            cartons = Carton.search([("in_picking_id", "=", picking.id), ("product_id", "=", move.product_id.id)])
            lines.append({
                "move_id": move.id, "product": move.product_id.display_name, "code": move.product_id.default_code,
                "zone": move.product_id.wms_zone or "", "demand": move.product_uom_qty,
                "done": round(sum(move.move_line_ids.mapped("quantity")), 3), "uom": move.product_uom.name,
                "catch_weight": move.product_id.wms_catch_weight, "cartons": len(cartons),
                "tracking": move.product_id.tracking != "none",
                "has_template": bool(move.product_id.wms_barcode_template_ids),
            })
        head = self._picking_head(picking)
        head.update({
            "lines": lines, "plate": picking.wms_vehicle_plate or "", "driver": picking.wms_driver or "",
            "note": picking.wms_delivery_note or "",
            "zones": sorted(picking._wms_cold_zones()),
            "pallets": [{
                "lpn": ml.result_package_id.name, "id": ml.result_package_id.id, "product": ml.product_id.display_name,
                "lot": ml.lot_id.name or "", "qty": round(ml.quantity, 3), "uom": ml.product_uom_id.name,
                "closed": ml.result_package_id.wms_closed, "move_id": ml.move_id.id,
            } for ml in picking.move_line_ids.filtered("result_package_id")],
        })
        return head

    @api.model
    def receipt_close_pallet(self, picking_id, package_id, pallet_no=None, mfg_date=None, remark=None):
        """'Simpan palet': tutup LPN (scan berikutnya membuka LPN baru) dan kembalikan URL label."""
        picking = self.env["stock.picking"].browse(picking_id)
        pack = picking.move_line_ids.result_package_id.filtered(lambda p: p.id == package_id)
        if not pack:
            raise UserError(_("LPN bukan bagian dokumen ini."))
        pack.write({"wms_closed": True, "wms_pallet_no": pallet_no or False, "wms_remark": remark or False,
                    "wms_mfg_date": mfg_date or False, "wms_pack_date": fields.Date.context_today(self)})
        return {"message": _("Palet %s disimpan. Tempel label lalu lanjut palet berikutnya.", pack.name),
                "label_url": f"/report/pdf/foodtrace.report_lpn_label/{pack.id}",
                "receipt": self.receipt_open(picking.id)}

    @api.model
    def receipt_scan(self, picking_id, move_id, barcode=None, manual_weight=0.0, lot=None, expiry=None, qty=0.0):
        """Satu scan karton (item berat aktual) atau input qty (item biasa). Mengisi LPN per lot."""
        picking = self.env["stock.picking"].browse(picking_id)
        move = self.env["stock.move"].browse(move_id)
        product = move.product_id
        carton_no = weight = weight_lb = None
        if product.wms_catch_weight or barcode:
            data = {}
            if barcode:
                try:
                    _tpl, data = self.env["wms.barcode.template"].parse_for_product(product, barcode)
                except UserError:
                    if not manual_weight:
                        raise
            weight = data.get("weight_kg") or manual_weight
            weight_lb = data.get("weight_lb") or 0.0
            lot = data.get("lot") or lot
            expiry = data.get("expiry") or expiry
            carton_no = data.get("carton") or (barcode or "")[-12:] or f"M{self.env['wms.carton'].search_count([]) + 1:06d}"
            if self.env["wms.carton"].search_count([("product_id", "=", product.id), ("name", "=", carton_no)]):
                raise UserError(_("Karton %s sudah discan.", carton_no))
            add = weight if move.product_uom.category_id == self.env.ref("uom.product_uom_categ_kgm") else 1
        else:
            add = float(qty or 0)
            if add <= 0:
                raise UserError(_("Isi qty yang diterima."))
        lot_rec = self.env["stock.lot"]
        if product.tracking != "none":
            lot = lot or f"{picking.name}-{product.default_code or product.id}"
            lot_rec = lot_rec.search([("product_id", "=", product.id), ("name", "=", lot),
                                      ("company_id", "in", [False, picking.company_id.id])], limit=1)
            if not lot_rec:
                exp = fields.Datetime.to_datetime(expiry) if expiry else False
                lot_rec = lot_rec.create({"product_id": product.id, "name": lot, "expiration_date": exp,
                                          "company_id": picking.company_id.id})
        ml = move.move_line_ids.filtered(
            lambda m: m.lot_id == lot_rec and m.result_package_id and not m.result_package_id.wms_closed)[:1]
        if not ml:
            # Mulai LPN baru: 1 SKU + 1 lot per LPN.
            move.move_line_ids.filtered(lambda m: not m.result_package_id and not m.picked).unlink()
            package = self.env["stock.quant.package"].create({})
            ml = self.env["stock.move.line"].create({
                "move_id": move.id, "picking_id": picking.id, "product_id": product.id,
                "product_uom_id": move.product_uom.id, "lot_id": lot_rec.id, "quantity": 0,
                "location_id": move.location_id.id, "location_dest_id": move.location_dest_id.id,
                "result_package_id": package.id, "owner_id": picking.owner_id.id,
            })
        ml.quantity += add
        ml.picked = True
        if carton_no:
            self.env["wms.carton"].create({
                "name": carton_no, "raw_barcode": barcode, "product_id": product.id, "lot_id": lot_rec.id,
                "weight_kg": weight, "weight_lb": weight_lb, "owner_id": picking.owner_id.id,
                "in_picking_id": picking.id, "package_id": ml.result_package_id.id,
                "manual_weight": not bool(barcode) or bool(manual_weight), "company_id": picking.company_id.id,
            })
        msg = _("%(c)s · %(w).2f kg → %(lpn)s", c=carton_no, w=weight, lpn=ml.result_package_id.name) if carton_no \
            else _("+%(q)s %(u)s → %(lpn)s", q=add, u=move.product_uom.name, lpn=ml.result_package_id.name)
        return {"message": msg, "receipt": self.receipt_open(picking.id)}

    @api.model
    def log_temperature(self, zone, temperature, source="manual", picking_id=None, location_code=None, humidity=0.0):
        vals = {"zone": zone, "temperature": float(temperature), "source": source, "humidity": float(humidity or 0)}
        if picking_id:
            vals["picking_id"] = picking_id
        if location_code:
            vals["location_id"] = self._find_location(location_code).id
        log = self.env["wms.temperature.log"].create(vals)
        return {"alarm": log.is_alarm, "message": _("%(z)s %(t)s °C %(s)s", z=ZONE_LABEL.get(zone, zone),
                                                     t=log.temperature, s=_("ALARM") if log.is_alarm else _("OK"))}

    @api.model
    def receipt_validate(self, picking_id, plate=None, driver=None, note=None):
        picking = self.env["stock.picking"].browse(picking_id)
        picking.write({"wms_vehicle_plate": plate, "wms_driver": driver, "wms_delivery_note": note})
        # Kurang terima = backorder otomatis (partial receiving).
        res = picking.with_context(skip_backorder=True).button_validate()
        if isinstance(res, dict) and res.get("res_model"):
            raise UserError(_("Validasi butuh konfirmasi di web: %s", res.get("name") or res["res_model"]))
        held = picking.move_line_ids.filtered(lambda m: m.location_dest_id.wms_area == "qc")
        return {"message": _("%(p)s selesai. %(n)s LPN siap put away%(h)s.", p=picking.name,
                             n=len(picking.move_line_ids.result_package_id),
                             h=_(", %s ke karantina", len(held)) if held else "")}

    # --------------------------------------------------------------- putaway
    @api.model
    def lpn_info(self, code):
        pack = self._find_package(code)
        quants = pack.quant_ids.filtered(lambda q: q.quantity > 0)
        if not quants:
            raise UserError(_("LPN %s kosong.", pack.name))
        product = quants.product_id[:1]
        zone = product.wms_zone
        return {
            "lpn": pack.name, "quants": [self._quant_dict(q) for q in quants],
            "zone": zone or "", "suggestion": self._suggest_bin(zone, quants.location_id[:1]),
        }

    @api.model
    def _suggest_bin(self, zone, current):
        """Saran put away: posisi palet utuh kosong di zona item (operator boleh pilih bin lain di zona sama)."""
        Loc = self.env["stock.location"]
        warehouse = current.warehouse_id or self._warehouse()
        bins = Loc.search([("warehouse_id", "=", warehouse.id), ("wms_area", "=", "blk"),
                           ("child_ids", "=", False), ("usage", "=", "internal")], order="complete_name")
        bins = bins.filtered(lambda b: b._wms_effective_zone() == zone) if zone else bins
        used = set(self.env["stock.quant"].search([("location_id", "in", bins.ids), ("quantity", ">", 0)])
                   .mapped("location_id").ids)
        free = bins.filtered(lambda b: b.id not in used)
        target = free[:1] or bins[:1]
        return {"barcode": target.barcode or target.complete_name, "name": target.complete_name} if target else None

    @api.model
    def move_lpn(self, code, location_code):
        """Put away / bin transfer satu LPN utuh ke lokasi yang discan."""
        pack = self._find_package(code)
        dest = self._find_location(location_code)
        quants = pack.quant_ids.filtered(lambda q: q.quantity > 0)
        if not quants:
            raise UserError(_("LPN %s kosong.", pack.name))
        for quant in quants:
            if quant.location_id == dest:
                continue
            quant._wms_move_to(dest, quant.quantity, _("Bin transfer HHT"))
        self.env["wms.carton"].search([("package_id", "=", pack.id)]).write({"location_id": dest.id})
        return {"message": _("%(lpn)s → %(loc)s", lpn=pack.name, loc=dest.complete_name)}

    @api.model
    def move_lpns(self, codes, location_code):
        """Put away beberapa LPN sekaligus: scan semua LPN, lalu satu kali scan lokasi."""
        dest = self._find_location(location_code)
        moved = [self.move_lpn(code, dest.barcode or dest.complete_name) and code for code in codes]
        return {"message": _("%(n)s LPN → %(loc)s", n=len(moved), loc=dest.complete_name)}

    @api.model
    def qc_hold(self, code):
        pack = self._find_package(code)
        pack.quant_ids.filtered(lambda q: q.quantity > 0).action_wms_qc_hold()
        return {"message": _("%s ditahan (QC Hold).", pack.name)}

    # ---------------------------------------------------------------- picking
    @api.model
    def delivery_list(self):
        pickings = self.env["stock.picking"].search([
            ("company_id", "=", self.env.company.id), ("picking_type_code", "=", "outgoing"),
            ("state", "in", ("confirmed", "assigned", "waiting"))])
        # Urutan kerja: prioritas tinggi dulu, lalu tanggal kirim, lalu shipping group.
        pickings = pickings.sorted(lambda p: (0 if (p.wms_priority or "").lower().startswith("high") or p.priority == "1" else 1,
                                              p.scheduled_date or datetime.max, p.wms_shipping_group or ""))
        return [self._picking_head(p) for p in pickings]

    @api.model
    def job_list(self):
        """Picking Job (wave) yang masih berjalan."""
        batches = self.env["stock.picking.batch"].search([
            ("company_id", "=", self.env.company.id), ("state", "=", "in_progress"),
            ("picking_ids.picking_type_code", "=", "outgoing")], order="id")
        return [{"id": b.id, "name": b.name, "description": b.description or "", "docs": len(b.picking_ids),
                 "ready": round(b.wms_ready_pct, 1)} for b in batches]

    @api.model
    def delivery_open(self, picking_id=None, code=None, batch_id=None):
        """Buka satu outbound document atau satu Picking Job (semua dokumennya digabung jadi satu rute ambil)."""
        Batch = self.env["stock.picking.batch"]
        batch = Batch.browse(batch_id) if batch_id else Batch
        if not batch and code:
            batch = Batch.search([("name", "=", code.strip()), ("state", "=", "in_progress")], limit=1)
        if batch:
            pickings = batch.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            picking = pickings[:1]
        else:
            picking = self.env["stock.picking"].browse(picking_id) if picking_id else self._find_picking(code, "outgoing")
            pickings = picking
        to_assign = pickings.filtered(lambda p: p.state in ("confirmed", "waiting"))
        if to_assign:
            to_assign.action_assign()
        pickings.filtered(lambda p: p.wms_stage == "open")._wms_set_stage("picking")
        tasks = []
        lines = pickings.move_line_ids.sorted(lambda m: (m.location_id.complete_name, m.lot_id.expiration_date or datetime.max))
        for ml in lines:
            tasks.append({
                "id": ml.id, "doc": ml.picking_id.name, "customer": ml.picking_id.partner_id.display_name or "",
                "product": ml.product_id.display_name, "code": ml.product_id.default_code,
                "zone": ml.product_id.wms_zone or "", "location": ml.location_id.complete_name,
                "location_barcode": ml.location_id.barcode or "", "lot": ml.lot_id.name or "",
                "expiry": fields.Date.to_string(ml.lot_id.expiration_date) if ml.lot_id.expiration_date else "",
                "lpn": ml.package_id.name or "", "qty": round(ml.quantity, 3), "uom": ml.product_uom_id.name,
                "picked": ml.picked, "catch_weight": ml.product_id.wms_catch_weight,
            })
        head = self._picking_head(picking)
        zones = set()
        for p in pickings:
            zones |= p._wms_cold_zones()
        head.update({
            "batch_id": batch.id or False, "batch": batch.name or "", "picking_ids": pickings.ids,
            "docs": [p.name for p in pickings], "tasks": tasks,
            "short": [{"product": m.product_id.display_name, "missing": round(m.product_uom_qty - m.quantity, 3),
                       "uom": m.product_uom.name} for m in pickings.move_ids if m.quantity < m.product_uom_qty - 1e-6],
            "zones": sorted(zones),
        })
        if batch:
            head["name"] = batch.name
            head["partner"] = batch.description or ""
        return head

    @api.model
    def delivery_pick(self, move_line_id, location_code, item_code, qty=None, batch_id=None):
        """Assisted picking: scan lokasi saran (FEFO) lalu scan LPN/lot/item. Salah lokasi atau lot ditolak."""
        ml = self.env["stock.move.line"].browse(move_line_id)
        loc = self._find_location(location_code)
        if loc != ml.location_id:
            raise UserError(_("Lokasi salah. Ambil dari %s (FEFO).", ml.location_id.complete_name))
        code = (item_code or "").strip()
        ok = code in (ml.package_id.name, ml.lot_id.name, ml.product_id.default_code, ml.product_id.barcode)
        if not ok:
            raise UserError(_("Barang yang discan bukan %(p)s lot %(l)s.", p=ml.product_id.display_name, l=ml.lot_id.name))
        if qty not in (None, "", False):
            qty = float(qty)
            if qty <= 0 or qty > ml.quantity + 1e-6:
                raise UserError(_("Qty ambil harus antara 0 dan %s.", ml.quantity))
            if qty < ml.quantity:
                # Ambil sebagian (loose picking): LPN dipecah, sisa tetap di rak.
                ml.quantity = qty
                ml.result_package_id = False
        ml.picked = True
        return {"message": _("Diambil %(q)s %(u)s %(p)s", q=ml.quantity, u=ml.product_uom_id.name, p=ml.product_id.name),
                "delivery": self.delivery_open(ml.picking_id.id, batch_id=batch_id)}

    @api.model
    def delivery_validate(self, picking_id):
        picking = self.env["stock.picking"].browse(picking_id)
        if not all(picking.move_line_ids.mapped("picked")):
            raise UserError(_("Masih ada baris yang belum diambil."))
        res = picking.with_context(skip_backorder=True).button_validate()
        if isinstance(res, dict) and res.get("res_model"):
            raise UserError(_("Validasi butuh konfirmasi di web: %s", res.get("name") or res["res_model"]))
        return {"message": _("%s selesai, Goods Issue masuk antrean SAP.", picking.name)}

    @api.model
    def delivery_stage(self, picking_ids, location_code):
        """Finish trip: semua barang diambil lalu diletakkan di outbound staging (scan lokasi staging)."""
        pickings = self.env["stock.picking"].browse(picking_ids)
        loc = self._find_location(location_code)
        if loc.wms_area != "out":
            raise UserError(_("%s bukan lokasi outbound staging.", loc.complete_name))
        if not all(pickings.move_line_ids.mapped("picked")):
            raise UserError(_("Masih ada baris yang belum diambil."))
        pickings.write({"wms_stage": "staged", "wms_staging_location_id": loc.id})
        return {"message": _("%(n)s dokumen di staging %(loc)s, siap dicek checker.", n=len(pickings),
                             loc=loc.name)}

    @api.model
    def check_open(self, code):
        """Checker: scan nomor outbound document di staging."""
        picking = self._find_picking(code, "outgoing")
        if picking.wms_stage not in ("staged", "checked", "picking"):
            raise UserError(_("%s belum di staging.", picking.name))
        return self._check_dict(picking)

    @api.model
    def _check_dict(self, picking):
        return {"id": picking.id, "name": picking.name, "partner": picking.partner_id.display_name or "",
                "stage": picking.wms_stage, "lines": [{
                    "id": ml.id, "product": ml.product_id.display_name, "code": ml.product_id.default_code,
                    "lot": ml.lot_id.name or "", "lpn": (ml.result_package_id or ml.package_id).name or "",
                    "qty": round(ml.quantity, 3), "uom": ml.product_uom_id.name, "checked": ml.wms_checked,
                } for ml in picking.move_line_ids]}

    @api.model
    def check_scan(self, picking_id, code):
        """Checker scan LPN / lot / item: cocokkan dengan hasil picking. Barang salah ditolak."""
        picking = self.env["stock.picking"].browse(picking_id)
        code = (code or "").strip()
        lines = picking.move_line_ids.filtered(lambda l: not l.wms_checked and code in (
            l.result_package_id.name, l.package_id.name, l.lot_id.name, l.product_id.default_code,
            l.product_id.barcode))
        if not lines:
            raise UserError(_("%s tidak ada di dokumen ini atau sudah dicek.", code))
        lines[:1].wms_checked = True
        if all(picking.move_line_ids.mapped("wms_checked")):
            picking._wms_set_stage("checked")
            msg = _("%s lengkap, siap dimuat.", picking.name)
        else:
            msg = _("OK %s", lines[:1].product_id.display_name)
        return {"message": msg, "check": self._check_dict(picking)}

    @api.model
    def loading_list(self):
        jobs = self.env["wms.loading"].search([("state", "=", "open"), ("company_id", "=", self.env.company.id)])
        return [self._loading_dict(j) for j in jobs]

    @api.model
    def _loading_dict(self, job):
        return {"id": job.id, "name": job.name, "plate": job.vehicle_plate or "", "driver": job.driver or "",
                "lines": job.line_count, "loaded": job.loaded_count, "docs": job.picking_ids.mapped("name")}

    @api.model
    def loading_scan(self, loading_id, code):
        job = self.env["wms.loading"].browse(loading_id)
        lines = job.load_scan(code)
        return {"message": _("Dimuat: %s", ", ".join(lines.mapped("product_id.display_name"))),
                "job": self._loading_dict(job)}

    @api.model
    def loading_close(self, loading_id):
        job = self.env["wms.loading"].browse(loading_id)
        job.action_close()
        return {"message": _("%s ditutup. Goods Issue terkirim ke antrean SAP, surat jalan siap dicetak.", job.name)}

    # -------------------------------------------------------- inventory check
    @api.model
    def ic_open(self, code):
        """Inventory Check: scan LPN atau lokasi, tampilkan qty dan expiry sistem untuk dicek."""
        code = (code or "").strip()
        pack = self.env["stock.quant.package"].search([("name", "=", code)], limit=1)
        vals = {"mode": "lpn", "package_id": pack.id} if pack else \
            {"mode": "location", "location_id": self._find_location(code).id}
        check = self.env["wms.inventory.check"].create(vals)
        check.action_load()
        return {"id": check.id, "name": check.name, "title": pack.name if pack else check.location_id.complete_name,
                "lines": [{"id": l.id, "product": l.product_id.display_name, "lot": l.lot_id.name or "",
                           "lpn": l.package_id.name or "", "qty": l.qty_before, "uom": l.product_id.uom_id.name,
                           "expiry": fields.Date.to_string(l.expiry_before) if l.expiry_before else ""}
                          for l in check.line_ids]}

    @api.model
    def ic_submit(self, check_id, rows):
        check = self.env["wms.inventory.check"].browse(check_id)
        for row in rows:
            line = check.line_ids.filtered(lambda l, r=row: l.id == int(r["id"]))
            if not line:
                continue
            vals = {"qty_after": float(row["qty"])}
            if row.get("expiry"):
                vals["expiry_after"] = fields.Datetime.to_datetime(row["expiry"])
            line.write(vals)
            if row.get("reprint"):
                line.need_reprint = True
        check.action_submit()
        return {"message": _("%(c)s dikirim: %(d)s baris selisih menunggu approval.", c=check.name,
                             d=check.difference_count)}

    # ----------------------------------------------------------------- butcher
    @api.model
    def butcher_out(self, lpn_code, qty=None, ref=None):
        """Butcher Out: scan LPN bahan, qty (kosong = satu LPN), langsung keluar ke ruang potong."""
        pack = self._find_package(lpn_code)
        avail = pack.wms_qty
        qty = float(qty) if qty not in (None, "", False) else avail
        if qty <= 0 or qty > avail + 1e-6:
            raise UserError(_("Qty harus antara 0 dan %s.", avail))
        doc = self.env["wms.butcher"].create({"kind": "out", "ref": ref, "line_ids": [(0, 0, {
            "package_id": pack.id, "product_id": pack.wms_product_id.id, "lot_id": pack.wms_lot_id.id,
            "location_id": pack.location_id.id, "qty": qty})]})
        doc.action_done()
        return {"message": _("%(d)s: %(q)s %(u)s %(p)s ke ruang potong.", d=doc.name, q=qty,
                             u=pack.wms_product_id.uom_id.name, p=pack.wms_product_id.display_name)}

    # ------------------------------------------------------------ cycle count
    @api.model
    def count_location(self, location_code):
        """Hitung buta: operator hanya melihat item & lot di bin, tanpa qty sistem."""
        loc = self._find_location(location_code)
        quants = self.env["stock.quant"].search([("location_id", "=", loc.id), ("quantity", ">", 0)])
        return {
            "location": loc.complete_name, "location_id": loc.id,
            "lines": [{"id": q.id, "product": q.product_id.display_name, "code": q.product_id.default_code,
                       "lot": q.lot_id.name or "", "lpn": q.package_id.name or "", "uom": q.product_uom_id.name,
                       "counted": q.inventory_quantity if q.inventory_quantity_set else None} for q in quants],
        }

    @api.model
    def count_submit(self, location_id, counts):
        """Simpan hasil hitung sebagai 'counted quantity'. Selisih disetujui kepala gudang di web."""
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        diff = 0
        for row in counts:
            quant = Quant.browse(int(row["id"]))
            if quant.location_id.id != location_id:
                continue
            quant.inventory_quantity = float(row["qty"])
            quant.user_id = self.env.user
            if abs(quant.inventory_quantity - quant.quantity) > 1e-6:
                diff += 1
        return {"message": _("Hitungan tersimpan. %s baris selisih menunggu persetujuan.", diff)}

    # ----------------------------------------------------------------- lookup
    @api.model
    def lookup(self, code):
        code = (code or "").strip()
        Quant = self.env["stock.quant"]
        domain = [("quantity", ">", 0), ("location_id.usage", "=", "internal")]
        pack = self.env["stock.quant.package"].search([("name", "=", code)], limit=1)
        if pack:
            quants, title = Quant.search(domain + [("package_id", "=", pack.id)]), _("LPN %s", pack.name)
        else:
            loc = self.env["stock.location"].search(["|", ("barcode", "=", code), ("complete_name", "=ilike", code)], limit=1)
            if loc:
                quants, title = Quant.search(domain + [("location_id", "child_of", loc.id)]), loc.complete_name
            else:
                product = self._find_product(code)
                if product:
                    quants, title = Quant.search(domain + [("product_id", "=", product.id)]), product.display_name
                else:
                    lots = self.env["stock.lot"].search([("name", "=", code)])
                    if not lots:
                        raise UserError(_("%s tidak dikenal (bukan LPN, lokasi, item, atau lot).", code))
                    quants, title = Quant.search(domain + [("lot_id", "in", lots.ids)]), _("Lot %s", code)
        quants = quants.sorted(lambda q: q.lot_id.expiration_date or datetime.max)
        return {"title": title, "quants": [self._quant_dict(q) for q in quants[:60]],
                "total": round(sum(quants.mapped("quantity")), 3)}
