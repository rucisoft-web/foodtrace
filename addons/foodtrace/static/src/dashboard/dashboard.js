import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ZONE_LABEL = { frozen: "Frozen", chilled: "Chilled", dry: "Dry" };
const ZONE_COLOR = { frozen: "#2563eb", chilled: "#0d9488", dry: "#d97706" };

export function rupiah(value, compact = false) {
    const n = Number(value || 0);
    if (compact) {
        if (Math.abs(n) >= 1e9) {
            return "Rp " + (n / 1e9).toLocaleString("id-ID", { maximumFractionDigits: 2 }) + " M";
        }
        if (Math.abs(n) >= 1e6) {
            return "Rp " + (n / 1e6).toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " jt";
        }
    }
    return "Rp " + Math.round(n).toLocaleString("id-ID");
}

function shortDay(iso) {
    const d = new Date(iso + "T00:00:00");
    return `${d.getDate()}/${d.getMonth() + 1}`;
}

/** Dashboard gudang cold chain: stok per zona, kedaluwarsa, suhu, arus barang dan status SAP. */
export class WmsDashboard extends Component {
    static template = "foodtrace.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, warehouseId: null });
        this.rupiah = rupiah;
        this.zoneLabel = ZONE_LABEL;
        this.zoneColor = ZONE_COLOR;
        this.charts = [];
        this.refs = {
            zone: useRef("zoneChart"),
            expiry: useRef("expiryChart"),
            flow: useRef("flowChart"),
            groups: useRef("groupChart"),
            occupancy: useRef("occupancyChart"),
            sap: useRef("sapChart"),
            status: useRef("statusChart"),
        };
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        onMounted(() => this.renderCharts());
        onWillUnmount(() => this.destroyCharts());
    }

    async load() {
        this.state.data = await this.orm.call("wms.dashboard", "summary", [], {
            warehouse_id: this.state.warehouseId,
        });
    }

    async onWarehouse(ev) {
        this.state.warehouseId = Number(ev.target.value) || null;
        await this.reload();
    }

    async reload() {
        await this.load();
        this.destroyCharts();
        // Tunggu OWL merender ulang kanvas sebelum menggambar.
        await new Promise((resolve) => requestAnimationFrame(resolve));
        this.renderCharts();
    }

    destroyCharts() {
        for (const chart of this.charts) {
            chart.destroy();
        }
        this.charts = [];
    }

    chart(ref, config) {
        if (!ref.el) {
            return;
        }
        config.options = Object.assign({ responsive: true, maintainAspectRatio: false, animation: false }, config.options);
        this.charts.push(new window.Chart(ref.el, config));
    }

    renderCharts() {
        const d = this.state.data;
        if (!d) {
            return;
        }
        const money = (v) => rupiah(v, true);
        const tooltipMoney = { callbacks: { label: (ctx) => `${ctx.dataset.label || ctx.label}: ${rupiah(ctx.raw)}` } };

        this.chart(this.refs.zone, {
            type: "doughnut",
            data: {
                labels: d.zones.map((z) => z.label),
                datasets: [{ data: d.zones.map((z) => z.value), backgroundColor: d.zones.map((z) => z.color), borderWidth: 2 }],
            },
            options: {
                cutout: "62%",
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${rupiah(ctx.raw)}` } },
                },
            },
        });

        this.chart(this.refs.expiry, {
            type: "bar",
            data: {
                labels: d.expiry.labels,
                datasets: Object.keys(ZONE_LABEL).map((z) => ({
                    label: ZONE_LABEL[z],
                    data: d.expiry.by_zone[z],
                    backgroundColor: ZONE_COLOR[z],
                    stack: "s",
                })),
            },
            options: {
                plugins: { legend: { position: "bottom" }, tooltip: tooltipMoney },
                scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: money } } },
            },
        });

        this.chart(this.refs.flow, {
            type: "bar",
            data: {
                labels: d.flow.days.map(shortDay),
                datasets: [
                    { label: "Masuk", data: d.flow.in, backgroundColor: "#16a34a", borderRadius: 3 },
                    { label: "Keluar", data: d.flow.out, backgroundColor: "#475569", borderRadius: 3 },
                ],
            },
            options: {
                plugins: { legend: { position: "bottom" }, tooltip: tooltipMoney },
                scales: { y: { ticks: { callback: money } } },
            },
        });

        const groups = d.groups.slice(0, 10);
        this.chart(this.refs.groups, {
            type: "bar",
            data: {
                labels: groups.map((g) => g.name),
                datasets: [{ label: "Nilai stok", data: groups.map((g) => g.value), backgroundColor: "#1f5a40", borderRadius: 3 }],
            },
            options: {
                indexAxis: "y",
                plugins: { legend: { display: false }, tooltip: tooltipMoney },
                scales: { x: { ticks: { callback: money } } },
            },
        });

        this.chart(this.refs.occupancy, {
            type: "bar",
            data: {
                labels: d.zones.map((z) => z.label),
                datasets: [
                    { label: "Terisi", data: d.zones.map((z) => z.occupied), backgroundColor: d.zones.map((z) => z.color), stack: "o" },
                    {
                        label: "Kosong", data: d.zones.map((z) => Math.max(0, z.positions - z.occupied)),
                        backgroundColor: "#e2e8f0", stack: "o",
                    },
                ],
            },
            options: {
                plugins: { legend: { position: "bottom" } },
                scales: { x: { stacked: true }, y: { stacked: true, title: { display: true, text: "Posisi palet" } } },
            },
        });

        const STATUS_COLOR = { receiving: "#0ea5e9", available: "#16a34a", picked: "#6366f1", hold: "#d97706", damage: "#dc2626" };
        this.chart(this.refs.status, {
            type: "bar",
            data: {
                labels: d.status.map((s) => s.label),
                datasets: [{ label: "Nilai", data: d.status.map((s) => s.value),
                    backgroundColor: d.status.map((s) => STATUS_COLOR[s.key]), borderRadius: 3 }],
            },
            options: {
                plugins: { legend: { display: false }, tooltip: tooltipMoney },
                scales: { y: { ticks: { callback: money } } },
            },
        });

        this.chart(this.refs.sap, {
            type: "doughnut",
            data: {
                labels: ["Terkirim", "Antre", "Gagal"],
                datasets: [{
                    data: [d.sap.posted, d.sap.queued, d.sap.failed],
                    backgroundColor: ["#16a34a", "#2563eb", "#dc2626"], borderWidth: 2,
                }],
            },
            options: { cutout: "62%", plugins: { legend: { position: "bottom" } } },
        });
    }

    pct(z) {
        return z.positions ? Math.round((z.occupied / z.positions) * 100) : 0;
    }

    open(xmlid, extra = {}) {
        this.action.doAction(xmlid, extra);
    }

    openModel(model, name, domain) {
        this.action.doAction({
            type: "ir.actions.act_window", name, res_model: model, domain,
            views: [[false, "list"], [false, "form"]],
        });
    }
}

registry.category("actions").add("foodtrace.dashboard", WmsDashboard);
