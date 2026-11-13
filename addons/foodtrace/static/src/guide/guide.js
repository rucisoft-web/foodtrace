import { Component, onMounted, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

/** Isi satu layar panduan: tujuan, langkah, tabel field, tips. Dipakai di dialog dan halaman Panduan. */
export class GuideScreen extends Component {
    static template = "foodtrace.GuideScreen";
    static props = { screen: Object, compact: { type: Boolean, optional: true } };
}

/** Dialog bantuan untuk layar yang sedang dibuka. */
export class GuideDialog extends Component {
    static template = "foodtrace.GuideDialog";
    static components = { Dialog, GuideScreen };
    static props = { data: Object, close: Function };

    setup() {
        this.action = useService("action");
    }

    openGuide(anchor) {
        this.props.close();
        this.action.doAction("foodtrace.action_guide", { additionalContext: { guide_anchor: anchor || null } });
    }
}

/** Buka dialog bantuan untuk kunci layar tertentu (dipakai juga oleh handheld). */
export async function openGuideDialog(env, params) {
    const data = await env.services.orm.call("foodtrace.guide", "get_screen", [], params);
    env.services.dialog.add(GuideDialog, { data });
}

/** Tombol (?) di pojok kanan atas: membaca layar aktif lalu menampilkan keterangannya. */
export class GuideSystray extends Component {
    static template = "foodtrace.GuideSystray";
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.state = useState({ visible: false });
        onWillStart(async () => {
            this.state.visible = await user.hasGroup("foodtrace.group_wms_operator");
        });
    }

    async onClick() {
        const controller = this.actionService.currentController;
        const action = controller?.action || {};
        const props = controller?.props || {};
        await openGuideDialog(this.env, {
            model: action.res_model || props.resModel || null,
            context: action.context || {},
            res_id: props.resId || action.res_id || null,
            tag: action.tag || null,
        });
    }
}

registry.category("systray").add("foodtrace.guide", { Component: GuideSystray }, { sequence: 1 });

/** Menu Panduan: konsep lalu layar per kelompok pengguna, bisa difilter dan dicetak. */
export class GuidePage extends Component {
    static template = "foodtrace.GuidePage";
    static components = { GuideScreen };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({ guide: null, role: "all", query: "" });
        onWillStart(async () => {
            this.state.guide = await this.orm.call("foodtrace.guide", "get_guide", []);
            // Anchor guide-<layar> menunjuk kemunculan pertama layar itu (dipakai tombol bantuan).
            this.firstRole = {};
            for (const role of this.state.guide.roles) {
                for (const screen of role.screens) {
                    this.firstRole[screen.key] ??= role.key;
                }
            }
        });
        onMounted(() => {
            const anchor = this.props.action?.context?.guide_anchor;
            if (anchor) {
                document.getElementById(`guide-${anchor}`)?.scrollIntoView({ block: "start" });
            }
        });
    }

    get roles() {
        const roles = this.state.guide?.roles || [];
        return this.state.role === "all" ? roles : roles.filter((r) => r.key === this.state.role);
    }

    matches(screen) {
        const q = this.state.query.trim().toLowerCase();
        if (!q) {
            return true;
        }
        const text = [screen.title, screen.purpose, ...screen.steps, ...screen.fields.map((f) => `${f.label} ${f.desc}`)]
            .join(" ")
            .toLowerCase();
        return text.includes(q);
    }

    jump(id) {
        document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    print() {
        window.print();
    }
}

registry.category("actions").add("foodtrace.guide", GuidePage);
