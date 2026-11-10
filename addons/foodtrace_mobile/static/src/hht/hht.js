import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ZONE = { frozen: "Frozen", chilled: "Chilled", dry: "Dry" };

/** Input scan: scanner handheld mengirim Enter di akhir barcode. */
class ScanInput extends Component {
    static template = "foodtrace_mobile.ScanInput";
    static props = { placeholder: { type: String, optional: true }, onScan: Function, type: { type: String, optional: true } };

    setup() {
        this.input = useRef("input");
        onMounted(() => this.input.el?.focus());
    }

    onKey(ev) {
        if (ev.key === "Enter") {
            const value = ev.target.value.trim();
            ev.target.value = "";
            if (value) {
                this.props.onScan(value);
            }
        }
    }
}

/** Aplikasi mobile terminal: satu layar per tugas, tombol besar, selalu siap scan. */
export class WmsHht extends Component {
    static template = "foodtrace_mobile.Hht";
    static components = { ScanInput };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.zone = ZONE;
        this.state = useState({
            screen: "home", home: null, list: [], receipt: null, delivery: null, lpn: null, count: null,
            lookup: null, msg: null, ok: true, busy: false, activeMove: null, activeTask: null,
            pickLocationOk: false, form: { plate: "", driver: "", note: "", qty: "", weight: "", lot: "", expiry: "" },
            tempZone: "frozen", counts: {}, lpns: [], jobs: [], check: null, loading: null, ic: null,
            icRows: {}, pallet: { no: "", mfg: "", remark: "" }, labelUrl: null,
        });
        onWillStart(() => this.goHome());
    }

    async call(method, args = [], kwargs = {}) {
        this.state.busy = true;
        try {
            return await this.orm.call("wms.mobile", method, args, kwargs);
        } catch (e) {
            this.feedback(e.data?.message || e.message || String(e), false);
            throw e;
        } finally {
            this.state.busy = false;
        }
    }

    feedback(msg, ok = true) {
        this.state.msg = msg;
        this.state.ok = ok;
        if (navigator.vibrate) {
            navigator.vibrate(ok ? 40 : [80, 60, 80]);
        }
    }

    async goHome() {
        this.state.screen = "home";
        this.state.msg = null;
        this.state.home = await this.orm.call("wms.mobile", "home", []);
    }

    async open(screen) {
        this.state.msg = null;
        this.state.screen = screen;
        if (screen === "receipts") {
            this.state.list = await this.call("receipt_list");
        } else if (screen === "deliveries") {
            this.state.list = await this.call("delivery_list");
            this.state.jobs = await this.call("job_list");
        } else if (screen === "loadings") {
            this.state.list = await this.call("loading_list");
        }
        this.state.lpn = null;
        this.state.lpns = [];
        this.state.count = null;
        this.state.lookup = null;
        this.state.check = null;
        this.state.ic = null;
        this.state.labelUrl = null;
    }

    // ---------- receiving
    async openReceipt(id, code) {
        this.state.receipt = await this.call("receipt_open", [], { picking_id: id || null, code: code || null });
        this.state.activeMove = this.state.receipt.lines[0]?.move_id || null;
        this.state.screen = "receipt";
    }

    get activeLine() {
        return this.state.receipt?.lines.find((l) => l.move_id === this.state.activeMove);
    }

    async scanCarton(barcode) {
        const f = this.state.form;
        try {
            const res = await this.call("receipt_scan", [this.state.receipt.id, this.state.activeMove], {
                barcode, manual_weight: Number(f.weight) || 0, lot: f.lot || null, expiry: f.expiry || null,
            });
            this.state.receipt = res.receipt;
            f.weight = "";
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    async addQty() {
        const f = this.state.form;
        try {
            const res = await this.call("receipt_scan", [this.state.receipt.id, this.state.activeMove], {
                qty: Number(f.qty) || 0, manual_weight: Number(f.weight) || 0, lot: f.lot || null, expiry: f.expiry || null,
            });
            this.state.receipt = res.receipt;
            f.qty = "";
            f.weight = "";
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    get openPallet() {
        return this.state.receipt?.pallets.find((p) => !p.closed && p.move_id === this.state.activeMove);
    }

    async closePallet() {
        const pallet = this.openPallet;
        if (!pallet) {
            return;
        }
        const p = this.state.pallet;
        try {
            const res = await this.call("receipt_close_pallet", [this.state.receipt.id, pallet.id], {
                pallet_no: p.no || null, mfg_date: p.mfg || null, remark: p.remark || null,
            });
            this.state.receipt = res.receipt;
            this.state.labelUrl = res.label_url;
            Object.assign(p, { no: "", mfg: "", remark: "" });
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    async logTemp(source, pickingId, value) {
        if (value === "" || value === undefined) {
            return;
        }
        try {
            const res = await this.call("log_temperature", [this.state.tempZone, Number(value)], {
                source, picking_id: pickingId || null,
            });
            this.feedback(res.message, !res.alarm);
            if (this.state.receipt && pickingId === this.state.receipt.id) {
                this.state.receipt = await this.call("receipt_open", [], { picking_id: pickingId });
            }
            if (this.state.delivery && pickingId === this.state.delivery.id) {
                this.state.delivery = await this.call("delivery_open", [], { picking_id: pickingId });
            }
        } catch {
            // pesan sudah ditampilkan
        }
    }

    onTempInput(ev, source, pickingId) {
        const value = ev.target.value;
        ev.target.value = "";
        this.logTemp(source, pickingId, value);
    }

    async validateReceipt() {
        const f = this.state.form;
        try {
            const res = await this.call("receipt_validate", [this.state.receipt.id], {
                plate: f.plate, driver: f.driver, note: f.note,
            });
            this.feedback(res.message);
            this.state.receipt = null;
            await this.open("putaway");
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    // ---------- put away / transfer / hold
    /** Scan berikutnya: LPN lain ditambahkan ke daftar, lokasi = put away semua LPN di daftar. */
    async scanPutaway(code) {
        if (this.state.lpns.length) {
            try {
                const info = await this.orm.call("wms.mobile", "lpn_info", [code]);
                if (this.state.lpns.some((l) => l.lpn === info.lpn)) {
                    this.feedback(`${info.lpn} sudah ada di daftar`, false);
                } else {
                    this.state.lpns.push(info);
                    this.feedback(`${this.state.lpns.length} LPN. Scan LPN lain atau lokasi tujuan.`);
                }
                return;
            } catch {
                // bukan LPN: anggap lokasi
            }
            try {
                const res = await this.call("move_lpns", [this.state.lpns.map((l) => l.lpn), code]);
                this.feedback(res.message);
                this.state.lpns = [];
            } catch {
                // pesan sudah ditampilkan
            }
            return;
        }
        try {
            const info = await this.call("lpn_info", [code]);
            this.state.lpns = [info];
            this.feedback(`LPN ${info.lpn}: scan LPN lain atau lokasi tujuan`);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    removeLpn(lpn) {
        this.state.lpns = this.state.lpns.filter((l) => l.lpn !== lpn);
    }

    async holdLpn(code) {
        try {
            const res = await this.call("qc_hold", [code]);
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    // ---------- picking
    async openDelivery(id, code, batchId) {
        this.state.delivery = await this.call("delivery_open", [], {
            picking_id: id || null, code: code || null, batch_id: batchId || null,
        });
        this.nextTask();
        this.state.screen = "delivery";
    }

    nextTask() {
        const next = this.state.delivery.tasks.find((t) => !t.picked);
        this.state.activeTask = next ? next.id : null;
        this.state.pickLocationOk = false;
        this.state.form.qty = "";
    }

    selectTask(x) {
        if (!x.picked) {
            this.state.activeTask = x.id;
            this.state.pickLocationOk = false;
        }
    }

    get task() {
        return this.state.delivery?.tasks.find((t) => t.id === this.state.activeTask);
    }

    scanPickLocation(code) {
        const t = this.task;
        if (code === t.location_barcode || code === t.location) {
            this.state.pickLocationOk = true;
            this.feedback("Lokasi benar. Scan LPN / lot / item.");
        } else {
            this.feedback(`Lokasi salah. Ambil dari ${t.location}`, false);
        }
    }

    async scanPickItem(code) {
        const t = this.task;
        try {
            const res = await this.call("delivery_pick", [t.id, t.location_barcode || t.location, code], {
                qty: this.state.form.qty || null, batch_id: this.state.delivery.batch_id || null,
            });
            this.state.delivery = res.delivery;
            this.feedback(res.message);
            this.nextTask();
        } catch {
            // pesan sudah ditampilkan
        }
    }

    async validateDelivery() {
        try {
            const res = await this.call("delivery_validate", [this.state.delivery.id]);
            this.feedback(res.message);
            this.state.delivery = null;
            await this.open("deliveries");
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    get allPicked() {
        return this.state.delivery && this.state.delivery.tasks.every((t) => t.picked);
    }

    async scanStaging(code) {
        try {
            const res = await this.call("delivery_stage", [this.state.delivery.picking_ids, code]);
            this.state.delivery = null;
            await this.open("deliveries");
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    // ---------- checker
    async scanCheck(code) {
        try {
            if (!this.state.check) {
                this.state.check = await this.call("check_open", [code]);
                this.feedback(`${this.state.check.name}: scan LPN / lot / item`);
                return;
            }
            const res = await this.call("check_scan", [this.state.check.id, code]);
            this.state.check = res.check;
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    // ---------- loading
    openLoading(job) {
        this.state.loading = job;
        this.state.screen = "loading";
        this.state.msg = null;
    }

    async scanLoad(code) {
        try {
            const res = await this.call("loading_scan", [this.state.loading.id, code]);
            this.state.loading = res.job;
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    async closeLoading() {
        try {
            const res = await this.call("loading_close", [this.state.loading.id]);
            this.state.loading = null;
            await this.open("loadings");
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    // ---------- inventory check
    async scanIc(code) {
        try {
            this.state.ic = await this.call("ic_open", [code]);
            this.state.icRows = {};
            for (const l of this.state.ic.lines) {
                this.state.icRows[l.id] = { qty: l.qty, expiry: l.expiry, reprint: false };
            }
        } catch {
            this.state.ic = null;
        }
    }

    async submitIc() {
        const rows = Object.entries(this.state.icRows).map(([id, r]) => ({
            id: Number(id), qty: Number(r.qty), expiry: r.expiry || null, reprint: r.reprint,
        }));
        try {
            const res = await this.call("ic_submit", [this.state.ic.id, rows]);
            this.state.ic = null;
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    // ---------- butcher out
    async scanButcher(code) {
        try {
            const res = await this.call("butcher_out", [code], {
                qty: this.state.form.qty || null, ref: this.state.form.note || null,
            });
            this.state.form.qty = "";
            this.feedback(res.message);
        } catch {
            // pesan sudah ditampilkan
        }
    }

    // ---------- cycle count
    async scanCountLocation(code) {
        try {
            this.state.count = await this.call("count_location", [code]);
            this.state.counts = {};
            for (const l of this.state.count.lines) {
                this.state.counts[l.id] = l.counted ?? "";
            }
        } catch {
            this.state.count = null;
        }
    }

    async submitCount() {
        const rows = Object.entries(this.state.counts)
            .filter(([, v]) => v !== "" && v !== null)
            .map(([id, qty]) => ({ id: Number(id), qty: Number(qty) }));
        try {
            const res = await this.call("count_submit", [this.state.count.location_id, rows]);
            this.feedback(res.message);
            this.state.count = null;
        } catch {
            // pesan sudah ditampilkan
        }
    }

    // ---------- suhu ruang, cek stok
    async scanLookup(code) {
        try {
            this.state.lookup = await this.call("lookup", [code]);
        } catch {
            this.state.lookup = null;
        }
    }
}

registry.category("actions").add("foodtrace_mobile.hht", WmsHht);
