# FoodTrace

WMS gudang cold chain Indoguna Group di atas **Odoo 18 Community**, mengikuti struktur menu dan alur
URS serta user guide Largo, disempurnakan untuk praktik standar gudang dan kemudahan operasional.
Pilot: PT Sarana Kulina Intisejahtera (distributor, satu gudang GENERAL WAREHOUSE, kode SAP `95-SKI`).

## Modul

| Modul | Isi |
|---|---|
| `addons/foodtrace` | Zona frozen/chilled/dry dengan standar suhu dan batas alarm, log suhu (manual, truk, terima, kirim), karton berat aktual (GS1-128 / regex, kg dan lbs), LPN 1 SKU + 1 lot, FEFO, batas sisa umur saat terima dan per customer, over receiving, auto quarantine dan QC release (Good/Damage), status stok Receiving/Available/Picked/Hold/Damage, Picking Job (wave), checker, Loading Job dengan manifest dan surat jalan (QR ke POD), halaman POD untuk driver (suhu wajib, qty diterima, foto), Inventory Check per LPN/lokasi dengan approval dan cetak ulang label, Butcher Out/In (rebag, non rebag, trimming, sisa potong, repack) dengan yield, impor dokumen sinkron POR/SOR SAP (`POST /wms/api/v1/sync`), antrean posting SAP B1 (mode simulasi), laporan ala Largo dan dashboard grafik. |
| `addons/foodtrace_mobile` | Aplikasi handheld (`/wms/hht`): receiving per palet dengan tombol *Simpan palet* dan cetak label LPN, put away beberapa LPN sekaligus, picking job FEFO dengan scan lokasi lalu LPN/lot, staging, checker, loading, inventory check, butcher out, QC hold, suhu ruang, cek stok, cycle count buta. |
| `addons/foodtrace_demo` | Data demo dari tarikan riil SAP B1 Sarana Kulina (13 Nov 2026): 842 item aktif dengan satuan SAP, 69 PO dan SO 7 hari terakhir yang masuk lewat sinkron POR/SOR, SO/PO Open sebagai pekerjaan terbuka, stok akhir sama dengan OnHand SAP, rak FZ/CH/DR berbarcode, lot dan LPN, karton, antrean SAP, picking job, loading, POD, inventory check dan butcher. Perbarui datanya dengan `scripts/sap_xlsx_to_demo.py MASTER.xlsx PO.xlsx SO.xlsx`. Pasang lewat baris perintah (`-i foodtrace_demo`, sekitar 5 menit). |

## Panduan penggunaan

Menu **FoodTrace → Panduan** berisi panduan lengkap: konsep dasar, lalu setiap layar per kelompok pengguna
(operator handheld, admin inbound, admin outbound, kepala gudang/QA, admin master data & SAP) dengan cara
pengisian dan keterangan setiap field. Tombol **?** di pojok kanan atas (dan di bar judul handheld) membuka
keterangan layar yang sedang dibuka. Isi panduan ada di `addons/foodtrace/models/wms_guide_data.py`.

## Menjalankan

```sh
docker compose up
```

Buka http://localhost:8069, buat database, lalu pasang **FoodTrace** dan **FoodTrace - Mobile Terminal**.
Untuk demo, pasang **FoodTrace - Data Demo Sarana Kulina** di database baru (tanpa data demo Odoo);
perusahaan PT Sarana Kulina Intisejahtera dibuat dan admin langsung berpindah ke sana.
Pemasangan demo memutar ulang ±940 dokumen SAP dan butuh sekitar 5 menit: pasang dari baris perintah
(`odoo-bin -d <db> -i foodtrace_demo,foodtrace_mobile --without-demo=all --stop-after-init`) atau naikkan
`limit_time_real` dulu bila memasang dari menu Apps.
Handheld dibuka di `/wms/hht` dari browser terminal.

Catatan: aturan validasi FoodTrace (dock wajib saat terima, zona, umur simpan, over receiving,
1 SKU per LPN) berlaku untuk semua transfer di database tempat modul dipasang.

## Integrasi SAP B1

- Masuk: file sinkron SAP (`POR-…`, `SOR-…`) dikirim ke `POST /wms/api/v1/sync` dengan header
  `X-WMS-Token` (parameter sistem `foodtrace.sync_token`), atau diimpor dari menu Integrasi SAP B1.
  Impor idempoten per nomor dokumen; item yang belum ada di master membuat dokumen berstatus error.
  Satuan baris (`uom_id`) dicocokkan ke satuan SAP item (PCE, PCK, PKT, JAR, BTL, CTN, CAN, BAG, PAIL, TIN,
  PET, TUBE, KG, GRAM) tanpa konversi antarkategori. `destination_outlet` SOR menjadi alamat kirim di bawah
  pelanggan (`destination_code`), dan owner yang sama dengan perusahaan gudang dianggap stok sendiri.
- Keluar: setiap penerimaan/pengiriman selesai masuk antrean posting (GRPO, Delivery, Transfer).
  Mode default simulasi (`foodtrace.sap_mode`); Service Layer/DI API disambungkan setelah Feature Pack
  SAP B1 10 di Sarana Kulina dipastikan.

## Tes

```sh
scripts/run-tests.sh --db_host=localhost --db_user=odoo --db_password=odoo
```
