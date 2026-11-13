{
    "name": "FoodTrace - Mobile Terminal",
    "summary": "Aplikasi handheld (HHT) ala Largo: receiving per palet + cetak LPN, put away multi-LPN, picking job FEFO, staging, checker, loading, inventory check, butcher out, QC hold, suhu, cek stok",
    "version": "18.0.1.1.0",
    "category": "Inventory/Inventory",
    "license": "LGPL-3",
    "author": "Indoguna Group",
    "depends": ["foodtrace"],
    "data": [
        "views/hht_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "foodtrace_mobile/static/src/hht/**/*",
        ],
    },
    "application": True,
    "installable": True,
}
