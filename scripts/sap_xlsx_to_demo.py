#!/usr/bin/env python3
"""Ubah tarikan SAP B1 (xlsx) menjadi data demo foodtrace_demo.

Pemakaian:
    python3 scripts/sap_xlsx_to_demo.py MASTER.xlsx PO.xlsx SO.xlsx [--today 2026-11-13] [--days 7]

Masukan (format tarikan read-only dari SAP B1, sheet pertama):
    MASTER  ItemCode, ItemName, U_Group, U_SubGroup, U_Brand, UoM (Inventory), OnHand (Total), ItemCost,
            StockValue, Last Purchase Price, Transaksi Terakhir
    PO      DocDate, DocDueDate, DocNum, NumAtCard, CardCode, CardName, ShipToCode, ItemCode, Dscription,
            Quantity, UoM, Price, LineTotal, Currency, LineTotalFC, Status
    SO      DocDate, DocDueDate, DocNum, NumAtCard, CardCode, CardName, ShipToCode, ItemCode, Dscription,
            Quantity, UoM, Price, LineTotal, Status

Keluaran di addons/foodtrace_demo/data/sarkul/:
    master_item.csv  semua item aktif + zona, berat aktual, negara asal (zona dari usulan lama bila ada)
    po.csv           semua baris PO (tanpa harga)
    so.csv           baris SO Closed dalam N hari terakhir s/d tanggal tarik + semua SO Open (tanpa harga)

Harga jual/beli sengaja tidak dibawa: WMS tidak memakainya. ItemCost dibawa sebagai nilai stok.
"""

import argparse
import csv
import datetime as dt
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "addons" / "foodtrace_demo" / "data" / "sarkul"
OLD_ZONES = ROOT / "scripts" / "zona_usulan_2025.csv"

COUNTRY = {
    "IT": "IT-ITALY", "FR": "FR-FRANCE", "ID": "ID-INDONESIA", "NL": "NL-NETHERLANDS", "SP": "ES-SPAIN",
    "PO": "PT-PORTUGAL", "PT": "PT-PORTUGAL", "CR": "HR-CROATIA", "NZ": "NZ-NEW ZEALAND", "DE": "DK-DENMARK",
    "GE": "DE-GERMANY", "SZ": "CH-SWITZERLAND", "SG": "SG-SINGAPORE", "US": "US-UNITED STATES",
    "AU": "AU-AUSTRALIA", "AR": "AR-ARGENTINA", "BE": "BE-BELGIUM", "RU": "RU-RUSSIA", "CH": "CN-CHINA",
    "PL": "PL-POLAND", "MY": "MY-MALAYSIA",
}


def sheet(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    head = [str(h).strip() for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:] if r and r[0] is not None]


def guess_zone(group, sub, name, uom):
    """Zona bila item belum punya usulan: aturan sederhana dari group SAP dan nama."""
    name = (name or "").upper()
    group, sub = group or "", sub or ""
    if "FRZ" in name or "FROZEN" in name or "BEKU" in name:
        return "frozen"
    if group.startswith(("D-", "C-", "J-")) or sub in ("FROZEN FRUIT", "PIZZA DOUGH"):
        return "frozen"
    if group.startswith("H-"):
        return "dry" if "UHT" in name else "chilled"
    if group.startswith(("A-", "B-")) or sub in ("FRESH PASTA",) or (sub == "TRUFFLE" and uom == "GRAM"):
        return "chilled"
    return "dry"


def num(value):
    return float(value or 0)


def day(value):
    return value.strftime("%Y-%m-%d") if value else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("master")
    ap.add_argument("po")
    ap.add_argument("so")
    ap.add_argument("--today", default="2026-11-13", help="Tanggal tarik data (YYYY-MM-DD)")
    ap.add_argument("--days", type=int, default=7, help="Hari SO Closed terakhir yang dibawa")
    args = ap.parse_args()
    today = dt.datetime.strptime(args.today, "%Y-%m-%d")
    start = today - dt.timedelta(days=args.days - 1)
    OUT.mkdir(parents=True, exist_ok=True)

    old = {}
    if OLD_ZONES.exists():
        old = {r["item_code"]: r for r in csv.DictReader(OLD_ZONES.open(encoding="utf-8"))}

    master = sheet(args.master)
    with (OUT / "master_item.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["item_code", "item_name", "item_group", "sub_group", "brand", "uom", "onhand", "item_cost",
                    "last_price", "last_trx", "zone", "catch_weight", "country"])
        for r in master:
            code = str(r["ItemCode"]).strip()
            uom = (r["UoM (Inventory)"] or "PCE").strip().upper()
            zone = (old.get(code) or {}).get("zone") or guess_zone(r["U_Group"], r["U_SubGroup"], r["ItemName"], uom)
            w.writerow([code, (r["ItemName"] or "").strip(), r["U_Group"] or "", r["U_SubGroup"] or "",
                        r["U_Brand"] or "", uom, round(num(r["OnHand (Total)"]), 3),
                        round(num(r["ItemCost"]), 2), round(num(r["Last Purchase Price"]), 2),
                        day(r["Transaksi Terakhir"]), zone, 1 if uom == "KG" else 0,
                        COUNTRY.get(code[1:3], code[1:3])])

    head = ["date", "due_date", "doc_num", "ref", "card_code", "card_name", "ship_to", "item_code", "item_name",
            "qty", "uom", "status"]

    def line(r):
        return [day(r["DocDate"]), day(r["DocDueDate"]), r["DocNum"], (r["NumAtCard"] or "").strip(),
                r["CardCode"], (r["CardName"] or "").strip(), (r["ShipToCode"] or "").strip(), r["ItemCode"],
                (r["Dscription"] or "").strip(), num(r["Quantity"]), (r["UoM"] or "").strip().upper(), r["Status"]]

    po = sheet(args.po)
    with (OUT / "po.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        for r in po:
            w.writerow(line(r))

    so = sheet(args.so)
    kept = [r for r in so if r["Status"] == "Open" or start <= r["DocDate"] <= today]
    with (OUT / "so.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        for r in kept:
            w.writerow(line(r))
    print(f"master {len(master)} item, PO {len(po)} baris, SO {len(kept)} dari {len(so)} baris -> {OUT}")


if __name__ == "__main__":
    main()
