"""Tandai partner lama sebagai Source/Destination dari dokumen yang sudah ada."""


def migrate(cr, version):
    for code, column in (("incoming", "wms_is_source"), ("outgoing", "wms_is_destination")):
        cr.execute(f"""
            UPDATE res_partner rp SET {column} = TRUE
             WHERE rp.id IN (
                SELECT COALESCE(p.commercial_partner_id, p.id)
                  FROM stock_picking sp
                  JOIN stock_picking_type t ON t.id = sp.picking_type_id
                  JOIN res_partner p ON p.id = sp.partner_id
                 WHERE t.code = %s)
        """, (code,))
