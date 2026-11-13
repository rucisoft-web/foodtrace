"""Isi panduan penggunaan FoodTrace.

Struktur:
- CONCEPTS: konsep dasar yang perlu dipahami semua pengguna sebelum membuka layar.
- ROLES: kelompok pengguna dan layar yang mereka pakai, urut sesuai alur kerja.
- SCREENS: satu entri per layar. `fields` berisi (nama_field, keterangan). Nama field yang ada di model
  diganti label aslinya saat ditampilkan, jadi label di panduan selalu sama dengan label di layar.
  Nama yang diawali "#" adalah isian non-model (mis. kotak scan di handheld) dan ditampilkan apa adanya.
"""

CONCEPTS = [
    {
        "key": "about",
        "title": "Apa itu FoodTrace",
        "body": [
            "FoodTrace adalah sistem manajemen gudang (WMS) untuk gudang makanan cold chain Indoguna Group. "
            "Satu gudang dikelola satu unit usaha (PT distributor). Stok dicatat sampai tingkat lot, tanggal "
            "kedaluwarsa, palet (LPN), bin, dan untuk daging/keju sampai berat aktual per karton.",
            "FoodTrace tidak menggantikan SAP Business One. SAP tetap memegang PO, SO, harga dan akuntansi. "
            "FoodTrace menerima dokumen PO/SO dari SAP, menjalankan pekerjaan fisik di gudang, lalu mengirim hasilnya "
            "(Goods Receipt, Delivery, Transfer) kembali ke SAP.",
        ],
    },
    {
        "key": "zones",
        "title": "Zona penyimpanan: Frozen, Chilled, Dry",
        "body": [
            "Setiap item punya satu zona wajib, dan setiap bin berada di satu zona. Sistem menolak menyimpan item "
            "di bin zona lain, misalnya keju frozen tidak bisa disimpan di rak dry.",
            "Pengaturan suhu ruang dijaga oleh sistem pendingin gudang, jadi FoodTrace tidak mencatat suhu. "
            "Zona dipakai untuk memastikan setiap barang disimpan, diambil, dan dilaporkan di ruang yang benar.",
        ],
    },
    {
        "key": "locations",
        "title": "Lokasi dan area",
        "body": [
            "Kode lokasi dibaca dari besar ke kecil: gudang / zona / area / bin. Contoh SKI/Stock/FZ/BLK/A01-1 "
            "artinya gudang SKI, zona Frozen, area Bulk (rak palet), baris A bay 01 level 1. Barcode bin ditempel "
            "di rak, misalnya SKI-FZ-A01-1.",
            "Area menentukan status stok: RCV (dock terima) = Receiving; BLK (rak palet) dan PCK (picking) = "
            "Available; OUT (outbound staging) = Picked; QC (karantina) dan RTN (retur) = Hold; DMG (rusak) dan "
            "WST (waste) = Damage.",
        ],
    },
    {
        "key": "lpn",
        "title": "LPN (License Plate Number)",
        "body": [
            "LPN adalah nomor unik untuk satu palet atau satu kemasan besar, dicetak sebagai label barcode. "
            "Aturannya: satu LPN hanya berisi 1 item dan 1 lot. Sistem menolak mencampur item atau lot berbeda di "
            "satu LPN.",
            "LPN dibuat saat receiving (tombol Simpan palet), dipindah utuh saat put away dan bin transfer, dan "
            "dipecah otomatis bila diambil sebagian saat picking.",
        ],
    },
    {
        "key": "lot",
        "title": "Lot, kedaluwarsa dan FEFO",
        "body": [
            "Setiap penerimaan barang dicatat lot dan tanggal kedaluwarsanya. Picking memakai FEFO (First Expired "
            "First Out): sistem menyarankan lot yang paling cepat kedaluwarsa lebih dulu.",
            "Lot yang sudah kedaluwarsa diblokir dan tidak bisa dikirim. Item bisa punya batas sisa umur minimum "
            "saat diterima (misalnya 60%), dan customer bisa punya batas sisa umur minimum saat dikirim (misalnya "
            "hotel minta minimal 60%). Lot di bawah batas ditolak dengan pesan yang jelas.",
        ],
    },
    {
        "key": "catch",
        "title": "Karton berat aktual (catch weight)",
        "body": [
            "Daging, keju blok dan sejenisnya dijual per kg tetapi diterima per karton dengan berat berbeda-beda. "
            "Untuk item ini setiap karton discan satu per satu. Barcode GS1-128 atau label pemasok dibaca otomatis "
            "untuk mengambil berat, lot dan kedaluwarsa. Bila barcode tidak terbaca, berat diisi manual.",
            "Label dalam lbs (pemasok Amerika) otomatis dikonversi ke kg. Setiap karton tetap bisa dilacak sampai "
            "dikirim ke customer.",
        ],
    },
    {
        "key": "status",
        "title": "Status stok dan karantina",
        "body": [
            "Status stok: Receiving (baru diterima, belum disimpan), Available (siap dijual), Picked (sudah diambil, "
            "menunggu kirim), Hold (karantina, tidak bisa diambil), Damage (rusak/waste).",
            "Stok masuk Hold karena dua hal: item ditandai wajib karantina, atau QA menahan LPN secara manual "
            "(QC Hold). QA melepas stok lewat QC Release: sebagian bisa dinyatakan GOOD "
            "(kembali ke rak) dan sebagian DAMAGE.",
        ],
    },
    {
        "key": "flow_in",
        "title": "Alur inbound",
        "body": [
            "1. PO dibuat di SAP dan dikirim ke FoodTrace sebagai dokumen sinkron POR, tampil di Inbound Document. "
            "2. Truk tiba: operator membuka penerimaan di handheld dan memilih Loading dock (mis. DOCK_01). 3. Barang dihitung atau karton discan per "
            "palet, lalu Simpan palet mencetak label LPN. 4. Selesai receiving: kelebihan di atas toleransi ditolak, "
            "barang karantina diarahkan ke area QC. 5. Put away: scan LPN lalu scan bin tujuan. 6. Goods Receipt "
            "terkirim otomatis ke antrean SAP.",
        ],
    },
    {
        "key": "flow_out",
        "title": "Alur outbound",
        "body": [
            "1. SO dari SAP masuk sebagai dokumen sinkron SOR. 2. Admin outbound menggabungkan beberapa dokumen "
            "menjadi Picking Job per rute. 3. Picker mengambil barang sesuai urutan lokasi dan FEFO, lalu meletakkan "
            "di outbound staging (scan lokasi staging). 4. Checker mencocokkan setiap LPN/lot dengan dokumen. "
            "5. Loading Job: barang discan saat dimuat ke truk, manifest dicetak, lalu Close loading membuat Goods "
            "Issue. 6. Surat jalan dicetak dengan QR POD. 7. Di tujuan, driver mengisi POD: penerima, qty diterima, foto.",
        ],
    },
    {
        "key": "sap",
        "title": "Integrasi SAP B1",
        "body": [
            "Masuk: PO (POR) dan SO (SOR) dari SAP diterima otomatis lewat API sinkron. Dokumen yang "
            "sama tidak akan dibuat dua kali. Bila ada item yang belum ada di master FoodTrace, dokumen berstatus "
            "Gagal sampai item dibuat dan dokumen diproses ulang.",
            "Keluar: setiap penerimaan, pengiriman dan transfer yang selesai masuk antrean posting. Antrean dikirim "
            "setiap 5 menit. Posting yang gagal tampil merah di dashboard dan bisa dikirim ulang setelah penyebabnya "
            "diperbaiki.",
        ],
    },
    {
        "key": "help",
        "title": "Cara memakai bantuan",
        "body": [
            "Tombol tanda tanya (?) di pojok kanan atas membuka keterangan layar yang sedang dibuka: tujuan layar, "
            "langkah pengisian, dan arti setiap field. Di handheld tombol yang sama ada di bar judul.",
            "Menu Panduan berisi seluruh panduan ini, dikelompokkan per peran, dan bisa dicetak.",
        ],
    },
]

ROLES = [
    {
        "key": "operator",
        "name": "Operator gudang (handheld)",
        "desc": "Checker penerimaan, forklift/put away, picker, checker outbound, loader. Bekerja dengan handheld "
                "scanner di lantai gudang.",
        "screens": ["hht.home", "hht.receipts", "hht.receipt", "hht.putaway", "hht.deliveries", "hht.delivery",
                    "hht.check", "hht.loadings", "hht.loading", "hht.ic", "hht.butcher", "hht.count",
                    "hht.lookup", "hht.hold"],
    },
    {
        "key": "inbound",
        "name": "Admin inbound",
        "desc": "Memantau Inbound Document dari SAP, menyelesaikan penerimaan per loading dock, tally karton, "
                "dan mencetak label LPN.",
        "screens": ["inbound_document", "receipt", "tally", "carton", "putaway"],
    },
    {
        "key": "outbound",
        "name": "Admin outbound",
        "desc": "Mengatur antrean pengiriman, membuat Picking Job, Loading Job, mencetak manifest dan surat jalan, "
                "memantau POD.",
        "screens": ["delivery", "picking_job", "checker", "loading", "pod", "pod_driver"],
    },
    {
        "key": "qa",
        "name": "Kepala gudang / QA",
        "desc": "Mengawasi karantina dan QC release, menyetujui inventory check, butcher/repack, "
                "dan membaca dashboard serta laporan.",
        "screens": ["dashboard", "stock_status", "report_by_location", "report_by_item", "qc_release", "inventory_check", "butcher_out",
                    "butcher_in", "lpn", "reports"],
    },
    {
        "key": "master",
        "name": "Admin master data & SAP",
        "desc": "Menjaga data item, bin, customer/supplier, format barcode, standar zona, serta memantau "
                "sinkron dan posting SAP.",
        "screens": ["product", "location", "partner", "barcode_template", "zone_standard", "warehouse",
                    "sync_document", "sap_document"],
    },
]

SCREENS = {
    # ------------------------------------------------------------------ handheld
    "hht.home": {
        "title": "Handheld: menu utama",
        "purpose": "Pintu masuk semua tugas operator. Angka di pojok tombol adalah jumlah pekerjaan yang menunggu.",
        "steps": [
            "Buka /wms/hht di browser handheld dan login dengan akun operator.",
            "Pilih tugas: Receiving, Put away, Picking, Checker, Loading, Inventory check, Cycle count, Cek stok, "
            "Butcher out, QC hold.",
            "Tombol rumah di kiri atas selalu kembali ke menu ini.",
        ],
        "fields": [
            ("#Angka pada tombol", "Receiving: penerimaan terbuka. Picking: pengiriman terbuka. Checker: dokumen "
                                   "di staging menunggu dicek. Loading: loading job terbuka. "
                                   "QC hold: jumlah stok yang ditahan."),
            ("#Pesan hijau / merah", "Muncul di bawah judul setelah setiap scan. Hijau = berhasil, merah = ditolak "
                                     "dengan alasannya. Handheld juga bergetar beda untuk berhasil dan gagal. "
                                     "Ketuk pesan untuk menutupnya."),
        ],
    },
    "hht.receipts": {
        "title": "Handheld: daftar penerimaan",
        "purpose": "Memilih dokumen penerimaan (PO) yang akan dikerjakan.",
        "steps": [
            "Scan nomor PO di surat jalan supplier, atau ketuk dokumen di daftar.",
        ],
        "fields": [
            ("#Scan nomor PO / dokumen", "Nomor dokumen FoodTrace (SKI/IN/…) atau nomor PO SAP (Source)."),
            ("#Kartu dokumen", "Nomor, tanggal rencana, nama supplier, nomor PO, jumlah item."),
        ],
    },
    "hht.receipt": {
        "title": "Handheld: receiving per palet",
        "purpose": "Mencatat barang yang benar-benar diterima, per palet, lengkap dengan lot, kedaluwarsa dan LPN.",
        "steps": [
            "Pilih Loading dock tempat truk dibongkar (mis. DOCK_01) dan isi No. container bila ada.",
            "Ketuk item yang sedang dihitung (kartu hijau = item aktif).",
            "Item berat aktual: scan barcode setiap karton. Bila barcode rusak, isi Berat manual lalu tekan + karton.",
            "Item biasa: isi Qty diterima lalu Tambah.",
            "Isi Lot dan tanggal kedaluwarsa bila tidak terbaca dari barcode.",
            "Setelah satu palet penuh: isi No. palet, tanggal produksi, Packaging, Grade dan EST bila ada, lalu Simpan palet & cetak LPN. "
            "Tempel label LPN di palet. Scan berikutnya otomatis membuka palet baru.",
            "Setelah semua item: isi plat kendaraan, driver dan nomor surat jalan supplier, lalu Selesai receiving.",
        ],
        "fields": [
            ("#Loading dock", "Dock bongkar, mis. DOCK_01. Wajib sebelum Selesai receiving."),
            ("#No. container", "Nomor container impor; ikut tercetak di label LPN."),
            ("#Kartu item", "Kode item, zona, qty diterima / qty PO, dan jumlah karton untuk item berat aktual."),
            ("#Scan barcode karton", "Barcode GS1-128 atau label pemasok. Berat, lot dan kedaluwarsa diambil "
                                     "otomatis. Karton yang sama tidak bisa discan dua kali."),
            ("#Berat manual (kg)", "Diisi hanya bila barcode tidak terbaca, ditimbang di timbangan dock."),
            ("#Qty diterima", "Jumlah satuan (karton, pak) untuk item tanpa berat aktual."),
            ("#Lot / tanggal kedaluwarsa", "Dari kemasan. Wajib untuk item ber-lot bila tidak ada di barcode."),
            ("#No. palet / tanggal produksi / remark", "Info palet yang ikut tercetak di label LPN."),
            ("#Packaging / Grade / EST", "Jenis kemasan, grade daging, dan nomor establishment (RPH) dari label "
                                         "pemasok. Tercetak di label LPN."),
            ("#Plat, driver, surat jalan", "Data kendaraan pemasok, untuk audit dan klaim."),
        ],
        "tips": [
            "Qty melebihi PO di atas toleransi supplier ditolak. Kelebihan dibuatkan PO terpisah oleh purchasing.",
            "Qty kurang dari PO tidak apa-apa: sisanya otomatis jadi backorder.",
            "Lot dengan sisa umur di bawah batas item ditolak saat Selesai receiving.",
        ],
    },
    "hht.putaway": {
        "title": "Handheld: put away / bin transfer",
        "purpose": "Memindahkan satu atau beberapa LPN ke bin tujuan dengan satu kali scan lokasi.",
        "steps": [
            "Scan LPN pertama. Sistem menampilkan isi LPN dan saran bin kosong di zona yang benar.",
            "Scan LPN lain bila ingin memindah beberapa palet sekaligus (misalnya satu trip forklift).",
            "Scan barcode bin tujuan. Semua LPN di daftar dipindah sekaligus.",
            "Tanda X menghapus LPN dari daftar sebelum dipindah.",
        ],
        "fields": [
            ("#Scan LPN / lokasi", "Scan pertama harus LPN. Selanjutnya: LPN = tambah ke daftar, bin = pindahkan."),
            ("#Saran", "Bin kosong di zona item. Boleh memilih bin lain asal zonanya sama."),
        ],
        "tips": ["Bin zona lain ditolak (misalnya item frozen ke rak dry)."],
    },
    "hht.deliveries": {
        "title": "Handheld: daftar picking",
        "purpose": "Memilih Picking Job atau dokumen pengiriman yang akan diambil.",
        "steps": [
            "Kerjakan Picking Job lebih dulu bila ada: satu job menggabungkan beberapa customer dalam satu rute.",
            "Dokumen dengan label prioritas (High) dikerjakan lebih dulu; urutan daftar sudah memperhitungkan "
            "prioritas, tanggal kirim dan rute.",
        ],
        "fields": [
            ("#Picking job", "Nomor job, rute, jumlah dokumen, persen stok yang sudah tereservasi."),
            ("#Outbound document", "Nomor, customer, rute, tanggal kirim, jumlah item."),
        ],
    },
    "hht.delivery": {
        "title": "Handheld: picking FEFO",
        "purpose": "Mengambil barang sesuai lokasi dan lot yang disarankan sistem.",
        "steps": [
            "Langkah 1: pergi ke lokasi yang tertulis, scan barcode bin. Lokasi salah ditolak.",
            "Langkah 2: scan LPN, lot atau kode item. Barang atau lot yang salah ditolak.",
            "Bila mengambil sebagian, isi qty dulu sebelum scan barang. Kosong = ambil semua.",
            "Sistem otomatis lanjut ke baris berikutnya. Kartu abu-abu = sudah diambil.",
            "Setelah semua diambil, letakkan barang di outbound staging dan scan barcode lokasi staging.",
            "Penjualan langsung tanpa loading job: tekan Langsung Goods Issue.",
        ],
        "fields": [
            ("#Ke lokasi", "Bin asal, diurutkan sesuai jalur gudang."),
            ("#Ambil", "Qty, satuan, kode item, lot, kedaluwarsa dan LPN yang harus diambil."),
            ("#Untuk", "Pada Picking Job: dokumen dan customer tujuan baris ini, untuk memisahkan barang."),
            ("#Qty (kosong = semua)", "Untuk ambil sebagian. LPN otomatis dipecah, sisanya tetap di rak."),
            ("#Stok kurang", "Item yang stoknya tidak cukup. Lapor ke admin outbound."),
        ],
    },
    "hht.check": {
        "title": "Handheld: checker outbound",
        "purpose": "Pemeriksaan kedua sebelum muat: setiap LPN/lot dicocokkan dengan dokumen.",
        "steps": [
            "Scan nomor dokumen pengiriman yang ada di staging.",
            "Scan setiap LPN, lot atau kode item. Baris yang cocok berubah abu-abu.",
            "Barang yang tidak ada di dokumen ditolak: kembalikan ke picker.",
            "Setelah semua cocok, dokumen berstatus Sudah dicek dan siap dimuat.",
        ],
        "fields": [
            ("#Scan nomor outbound document", "Nomor SKI/OUT/… atau nomor SO."),
            ("#Baris", "Item, qty, lot dan LPN hasil picking."),
        ],
    },
    "hht.loadings": {
        "title": "Handheld: daftar loading",
        "purpose": "Memilih loading job (kendaraan) yang sedang dimuat.",
        "steps": ["Loading job dibuat admin outbound di web. Pilih sesuai plat kendaraan di dock."],
        "fields": [("#Kartu loading", "Nomor, plat kendaraan, pengemudi, baris dimuat / total, dokumen.")],
    },
    "hht.loading": {
        "title": "Handheld: muat ke kendaraan",
        "purpose": "Memastikan hanya barang untuk kendaraan ini yang dimuat.",
        "steps": [
            "Scan setiap LPN/lot/item saat dinaikkan ke truk. Barang untuk kendaraan lain ditolak.",
            "Setelah progres 100%, tekan Close loading. Goods Issue terkirim ke SAP dan surat jalan bisa dicetak.",
        ],
        "fields": [("#Progres", "Baris dimuat dibanding total baris di semua dokumen kendaraan ini.")],
    },
    "hht.ic": {
        "title": "Handheld: inventory check",
        "purpose": "Mengecek fisik satu LPN atau satu lokasi dan melaporkan selisih qty atau kedaluwarsa.",
        "steps": [
            "Scan LPN atau barcode lokasi. Sistem menampilkan qty dan kedaluwarsa menurut sistem.",
            "Ubah qty atau tanggal bila berbeda dengan fisik. Centang Label rusak bila label LPN perlu dicetak ulang.",
            "Kirim untuk approval. Selisih baru berlaku setelah disetujui kepala gudang.",
        ],
        "fields": [
            ("#Qty", "Qty fisik hasil hitung."),
            ("#Tanggal", "Kedaluwarsa fisik di kemasan."),
            ("#Label rusak, cetak ulang", "Menandai LPN masuk daftar Need to Print."),
        ],
    },
    "hht.butcher": {
        "title": "Handheld: butcher out",
        "purpose": "Mengeluarkan bahan (LPN daging) dari gudang ke ruang potong.",
        "steps": [
            "Isi nomor SPK/dokumen potong.",
            "Isi qty bila hanya sebagian LPN yang dikeluarkan. Kosong = satu LPN utuh.",
            "Scan LPN bahan. Stok langsung berkurang dari gudang.",
            "Hasil potong dicatat di web: Butcher → Butcher In / Repack.",
        ],
        "fields": [
            ("#Ref. SPK / dokumen", "Nomor perintah potong, menghubungkan bahan dengan hasil."),
            ("#Qty", "Dalam satuan item (kg untuk daging)."),
        ],
    },
    "hht.count": {
        "title": "Handheld: cycle count (buta)",
        "purpose": "Menghitung isi bin tanpa melihat qty sistem, supaya hasil hitung jujur.",
        "steps": [
            "Scan bin. Muncul daftar item dan lot di bin tersebut tanpa qty.",
            "Isi qty hasil hitung setiap baris, lalu Simpan hitungan.",
            "Selisih ditinjau dan diterapkan kepala gudang di menu Cycle Count / Stock Take.",
        ],
        "fields": [("#Qty", "Qty fisik dalam satuan item.")],
    },
    "hht.lookup": {
        "title": "Handheld: cek stok",
        "purpose": "Melihat stok dari satu scan: LPN, bin, item atau lot.",
        "steps": ["Scan apa saja. Hasil diurutkan dari kedaluwarsa terdekat."],
        "fields": [
            ("#Baris hasil", "Kode item, status, qty, lot, kedaluwarsa, lokasi dan LPN."),
            ("#Status", "available, receiving, picked, hold, damage. Lihat konsep Status stok."),
        ],
    },
    "hht.hold": {
        "title": "Handheld: QC hold",
        "purpose": "Menahan LPN yang dicurigai bermasalah (kemasan rusak, bau, dll.) supaya tidak terambil.",
        "steps": [
            "Scan LPN. Stok dipindah ke area karantina zonanya dan berstatus Hold.",
            "Pelepasan (QC Release) dilakukan QA di web.",
        ],
        "fields": [("#Scan LPN", "Label LPN di palet.")],
    },
    # ------------------------------------------------------------------ inbound
    "inbound_document": {
        "title": "Inbound Document (dokumen sumber SAP)",
        "model": "stock.picking",
        "purpose": "Daftar semua dokumen inbound dari SAP (POR, mis. 95-SKI-POR-2611515786) dan status "
                   "penerimaannya. Titik awal admin inbound setiap hari.",
        "steps": [
            "Filter Belum diterima tampil otomatis. Pakai Datang hari ini untuk jadwal bongkar.",
            "Cari dengan nomor POR, nomor referensi vendor, atau nomor container.",
            "Buka baris untuk masuk ke dokumen receiving-nya.",
        ],
        "fields": [
            ("origin", "Nomor dokumen sumber SAP (POR)."),
            ("name", "Nomor receiving di FoodTrace."),
            ("partner_id", "Pemasok (source)."),
            ("wms_inbound_type", "Jenis inbound dari SAP."),
            ("wms_vendor_ref", "Nomor referensi / DO vendor."),
            ("wms_container_no", "Nomor container."),
            ("wms_dock_id", "Loading dock tempat bongkar."),
            ("scheduled_date", "Tanggal rencana datang."),
            ("wms_line_count", "Jumlah baris item."),
            ("wms_sap_state", "Status posting Goods Receipt ke SAP."),
            ("state", "Status penerimaan."),
        ],
    },
    "receipt": {
        "title": "Receiving (dokumen penerimaan)",
        "model": "stock.picking",
        "purpose": "Dokumen penerimaan barang dari supplier, transfer atau retur. Biasanya dibuat otomatis dari "
                   "PO SAP (dokumen sinkron POR).",
        "steps": [
            "Buka dokumen berstatus Ready. Cek supplier, PO dan item.",
            "Isi Loading dock (mis. DOCK_01), No. container dan referensi vendor.",
            "Untuk item berat aktual pakai Tally karton. Untuk item lain isi Quantity per baris, lot dan "
            "kedaluwarsa di detail operasi.",
            "Isi tab WMS: plat kendaraan, driver, nomor surat jalan supplier.",
            "Validate. Kurang dari PO = backorder; lebih dari toleransi = ditolak.",
        ],
        "fields": [
            ("partner_id", "Supplier pengirim barang."),
            ("origin", "Nomor PO SAP (95-SKI-POR-…)."),
            ("scheduled_date", "Rencana tiba."),
            ("location_dest_id", "Lokasi tujuan awal. Baris bisa diarahkan ke bin atau ke QC secara otomatis."),
            ("wms_inbound_type", "Purchase Order, Titipan, Transfer, Retur, Butcher, Sampling."),
            ("wms_vehicle_plate", "Plat nomor truk pemasok."),
            ("wms_driver", "Nama pengemudi pemasok."),
            ("wms_delivery_note", "Nomor surat jalan dari supplier."),
            ("wms_dock_id", "Loading dock tempat truk dibongkar. Wajib sebelum validasi."),
            ("wms_container_no", "Nomor container (dari SAP atau diisi saat bongkar)."),
            ("wms_vendor_ref", "Nomor referensi / DO vendor dari SAP."),
            ("wms_sync_id", "Dokumen sinkron SAP asal dokumen ini."),
            ("wms_sap_state", "Status posting Goods Receipt ke SAP."),
        ],
    },
    "tally": {
        "title": "Tally karton",
        "model": "wms.tally.wizard",
        "purpose": "Mencatat setiap karton item berat aktual dari scan barcode, lalu mengisi qty dan lot dokumen.",
        "steps": [
            "Pilih item. Arahkan kursor ke Scan barcode karton dan scan karton satu per satu.",
            "Bila barcode rusak: isi Berat manual, Lot manual dan Kedaluwarsa manual, lalu tekan Tambah karton.",
            "Cek jumlah karton dan total berat, lalu Simpan ke penerimaan.",
        ],
        "fields": [
            ("move_id", "Item di dokumen yang sedang ditally."),
            ("barcode", "Hasil scan. Berat, lot, kedaluwarsa dan nomor karton dibaca dari format barcode item."),
            ("manual_weight", "Berat timbang bila barcode tidak terbaca."),
            ("manual_lot", "Lot dari kemasan untuk input manual."),
            ("manual_expiry", "Kedaluwarsa dari kemasan untuk input manual."),
            ("carton_count", "Jumlah karton yang sudah discan."),
            ("total_weight", "Total berat semua karton, menjadi qty terima dalam kg."),
        ],
    },
    "carton": {
        "title": "Karton (serial number)",
        "model": "wms.carton",
        "purpose": "Daftar setiap karton berat aktual: dari mana diterima, di mana sekarang, dan dikirim ke siapa.",
        "steps": ["Cari dengan nomor karton, lot atau item untuk melacak satu karton (recall, klaim)."],
        "fields": [
            ("name", "Nomor karton dari barcode atau nomor urut manual."),
            ("product_id", "Item."),
            ("lot_id", "Lot karton."),
            ("weight_kg", "Berat aktual dalam kg."),
            ("weight_lb", "Berat sesuai label bila labelnya lbs."),
            ("package_id", "LPN tempat karton berada."),
            ("location_id", "Lokasi terakhir."),
            ("state", "Tersedia, Karantina, Terkirim, Waste."),
            ("in_picking_id", "Dokumen penerimaan."),
            ("out_picking_id", "Dokumen pengiriman."),
            ("manual_weight", "Tercentang bila berat diisi manual, untuk audit."),
        ],
    },
    "putaway": {
        "title": "Put Away / Bin Transfer (web)",
        "model": "stock.picking",
        "purpose": "Dokumen pemindahan internal. Di lantai gudang pakai handheld; menu ini untuk melihat riwayat "
                   "dan koreksi.",
        "steps": ["Setiap pemindahan dari handheld, QC hold dan QC release tercatat sebagai dokumen di sini."],
        "fields": [
            ("location_id", "Lokasi asal."),
            ("location_dest_id", "Lokasi tujuan. Harus di zona item."),
            ("origin", "Alasan: Bin transfer HHT, QC Hold, QC release (GOOD/DAMAGE), Auto release karantina."),
        ],
    },
    # ------------------------------------------------------------------ outbound
    "delivery": {
        "title": "Outbound Document (pengiriman)",
        "model": "stock.picking",
        "purpose": "Dokumen pengiriman ke customer, biasanya dibuat otomatis dari SO SAP (dokumen sinkron SOR).",
        "steps": [
            "Filter Ready dan kelompokkan per Shipping group (rute).",
            "Centang beberapa dokumen satu rute, lalu Aksi → Buat Picking Job.",
            "Pantau kolom Tahap outbound: Picking, Di staging, Sudah dicek, Loading, Terkirim, Diterima.",
        ],
        "fields": [
            ("partner_id", "Customer tujuan. Batas sisa umur minimum customer berlaku saat kirim."),
            ("origin", "Nomor SO SAP."),
            ("wms_shipping_group", "Rute/shipping group dari SAP, dasar pengelompokan picking job dan muat."),
            ("wms_priority", "Prioritas dari SAP. High dikerjakan lebih dulu."),
            ("wms_outbound_type", "Sales Order, Butcher, Dispose, Transfer, RTV, Chill-frozen, Lainnya."),
            ("wms_stage", "Tahap fisik: Open → Picking → Di staging → Sudah dicek → Loading → Terkirim → Diterima."),
            ("wms_staging_location_id", "Lokasi staging tempat barang diletakkan setelah picking."),
            ("wms_loading_id", "Loading job (kendaraan) dokumen ini."),
            ("wms_pod_id", "Bukti terima dari customer."),
        ],
    },
    "picking_job": {
        "title": "Picking Job",
        "model": "stock.picking.batch",
        "purpose": "Menggabungkan beberapa dokumen pengiriman (satu rute) menjadi satu tugas ambil, supaya picker "
                   "sekali jalan.",
        "steps": [
            "Dibuat dari Outbound Document: centang dokumen → Aksi → Buat Picking Job. Stok langsung direservasi FEFO.",
            "Isi driver dan transporter bila sudah diketahui.",
            "Picker mengerjakan job di handheld menu Picking.",
        ],
        "fields": [
            ("name", "Nomor job."),
            ("description", "Rute (shipping group) yang digabung."),
            ("user_id", "Picker yang ditugaskan."),
            ("picking_ids", "Dokumen pengiriman di job ini."),
            ("wms_use_tote", "Centang bila memakai tote/tray per customer."),
            ("wms_driver", "Nama driver."),
            ("wms_transporter", "Transporter atau plat kendaraan."),
            ("wms_ready_pct", "Persen qty yang sudah tereservasi/diambil."),
            ("wms_total_weight", "Perkiraan total berat (kg)."),
        ],
    },
    "checker": {
        "title": "Checker (outbound staging)",
        "model": "stock.picking",
        "purpose": "Daftar dokumen yang sedang dipicking atau sudah di staging dan menunggu pemeriksaan checker.",
        "steps": ["Checker bekerja di handheld menu Checker. Layar ini untuk memantau antrean."],
        "fields": [("wms_stage", "Picking = sedang diambil, Di staging = menunggu dicek.")],
    },
    "loading": {
        "title": "Loading Job",
        "model": "wms.loading",
        "purpose": "Daftar dokumen yang dimuat ke satu kendaraan, dasar manifest dan surat jalan.",
        "steps": [
            "New: isi tanggal, plat kendaraan, pengemudi, lalu tambahkan dokumen yang sudah dicek.",
            "Cetak manifest untuk loader.",
            "Loader scan muat di handheld. Pantau Sudah dimuat.",
            "Close loading (GI) setelah semua dimuat. Goods Issue masuk antrean SAP dan POD dibuat per dokumen.",
            "Cetak surat jalan (berisi QR POD) untuk driver.",
            "Cancel loading mengembalikan semua dokumen ke status Sudah dicek.",
        ],
        "fields": [
            ("name", "Nomor loading (LD/yymm/nnnn)."),
            ("date", "Tanggal muat."),
            ("vehicle_plate", "Plat nomor kendaraan pengiriman."),
            ("driver", "Nama pengemudi."),
            ("picking_ids", "Dokumen pengiriman di kendaraan ini."),
            ("line_count", "Jumlah baris LPN/item yang harus dimuat."),
            ("loaded_count", "Jumlah baris yang sudah discan muat."),
            ("total_weight", "Total berat (kg) muatan."),
            ("state", "Open, Close (sudah GI), Cancel."),
        ],
    },
    "pod": {
        "title": "POD (Proof of Delivery)",
        "model": "wms.pod",
        "purpose": "Bukti terima dari customer: qty diterima, nama penerima dan foto.",
        "steps": [
            "POD dibuat otomatis saat Close loading.",
            "Driver mengisi lewat QR di surat jalan. Admin bisa mengisi manual dari surat jalan yang ditandatangani.",
            "Baris merah = qty diterima beda dengan qty kirim: tindak lanjuti sebagai retur/klaim.",
        ],
        "fields": [
            ("picking_id", "Dokumen pengiriman."),
            ("partner_id", "Customer."),
            ("state", "Dalam perjalanan / Diterima."),
            ("received_by", "Nama penerima di customer."),
            ("received_at", "Waktu terima."),
            ("has_difference", "Ada selisih qty kirim dan terima."),
            ("photo", "Foto barang atau surat jalan bertanda tangan."),
            ("remark", "Catatan penerima atau driver."),
        ],
    },
    "pod_driver": {
        "title": "Halaman POD untuk driver",
        "purpose": "Halaman web sederhana yang dibuka driver dari QR surat jalan, tanpa login.",
        "steps": [
            "Scan QR di surat jalan dengan kamera HP.",
            "Isi nama penerima (wajib).",
            "Ubah qty bila ada barang ditolak atau kurang, isi catatan.",
            "Ambil foto barang/surat jalan bertanda tangan, lalu Kirim POD.",
        ],
        "fields": [
            ("#Diterima oleh", "Nama penerima."),
            ("#Qty per item", "Qty yang benar-benar diterima."),
            ("#Foto bukti terima", "Langsung dari kamera HP."),
        ],
    },
    # ------------------------------------------------------------------ QA / kepala gudang
    "dashboard": {
        "title": "Dashboard gudang",
        "purpose": "Ringkasan kondisi gudang hari ini untuk kepala gudang dan manajemen.",
        "steps": ["Muat ulang untuk data terbaru. Kotak merah perlu tindakan hari ini."],
        "fields": [
            ("#Nilai stok", "Qty × harga pokok standar, jumlah item dan lot."),
            ("#Expired ≤ 1 bulan", "Nilai stok yang kedaluwarsa dalam 30 hari: dorong penjualan atau promo."),
            ("#Sudah kedaluwarsa", "Diblokir, menunggu proses waste."),
            ("#Hold", "Nilai stok di karantina menunggu QC release."),
            ("#Item low", "Item di bawah stok minimum."),
            ("#SAP B1", "Posting gagal, antrean, dan dokumen sinkron error."),
            ("#Kartu zona", "Nilai stok, jumlah item dan lot, serta okupansi rak per zona."),
            ("#Grafik", "Nilai per zona, profil kedaluwarsa, okupansi rak, "
                        "arus masuk/keluar 30 hari, status stok, posting SAP, nilai per item group."),
        ],
    },
    "stock_status": {
        "title": "Stock Status / posisi stok",
        "model": "stock.quant",
        "purpose": "Posisi stok per bin, lot dan LPN dengan status Largo.",
        "steps": [
            "Kelompokkan per Status stok, Zona atau Lokasi.",
            "Filter Expired 1/2/3/4 bulan untuk laporan kedaluwarsa.",
            "Pilih baris lalu QC Hold untuk menahan, atau QC Release untuk melepas stok Hold.",
        ],
        "fields": [
            ("product_id", "Item."),
            ("location_id", "Bin."),
            ("lot_id", "Lot."),
            ("package_id", "LPN."),
            ("quantity", "Qty on hand."),
            ("wms_status", "Receiving, Available, Picked, Hold, Damage (dari area lokasi)."),
            ("wms_zone", "Zona item."),
            ("wms_expiration_date", "Kedaluwarsa lot."),
        ],
    },
    "qc_release": {
        "title": "QC Release",
        "model": "wms.qc.release.wizard",
        "purpose": "Melepas stok karantina: sebagian bisa GOOD (kembali ke rak) dan sebagian DAMAGE.",
        "steps": [
            "Dari Stock Status / QC Hold, pilih baris berstatus Hold lalu QC Release.",
            "Isi qty GOOD dan/atau DAMAGE, lokasi GOOD dan alasan/hasil QC, lalu Release.",
        ],
        "fields": [
            ("quantity", "Qty yang sedang ditahan."),
            ("qty_good", "Qty layak jual, dipindah ke lokasi GOOD."),
            ("qty_damage", "Qty rusak, dipindah ke area DMG zona yang sama."),
            ("good_location_id", "Lokasi tujuan stok GOOD (bawaan: ruang zona asal)."),
            ("reason", "Hasil pemeriksaan QC, tercatat di dokumen pemindahan."),
        ],
        "tips": ["GOOD + DAMAGE tidak boleh melebihi qty yang ditahan. Sisanya tetap Hold."],
    },
    "inventory_check": {
        "title": "Inventory Check dan approval",
        "model": "wms.inventory.check",
        "purpose": "Cek fisik per LPN atau per lokasi dengan persetujuan kepala gudang sebelum stok berubah.",
        "steps": [
            "Operator membuat dari handheld, atau New di web: pilih Per LPN/Per lokasi, isi LPN/lokasi, Ambil stok "
            "sistem.",
            "Isi Qty fisik dan Expiry fisik yang berbeda, lalu Kirim untuk approval.",
            "Kepala gudang membuka menu Inventory Check Approval, meninjau baris merah, lalu Approve atau Reject.",
            "Approve: qty disesuaikan, expiry lot diubah, LPN yang berubah masuk Need to Print.",
        ],
        "fields": [
            ("mode", "Per LPN atau Per lokasi."),
            ("location_id", "Lokasi yang dicek (termasuk sub-lokasi)."),
            ("package_id", "LPN yang dicek."),
            ("user_id", "Checker."),
            ("approved_by", "Kepala gudang yang menyetujui."),
            ("state", "Draft, Menunggu approval, Approved, Rejected."),
            ("difference_count", "Jumlah baris berselisih."),
            ("reprint_count", "Jumlah LPN yang perlu cetak ulang label."),
            ("#Qty sistem / Qty fisik", "Qty menurut sistem dan hasil hitung."),
            ("#Expiry sistem / Expiry fisik", "Kedaluwarsa di sistem dan di kemasan."),
            ("#Perlu cetak ulang", "Otomatis bila qty/expiry LPN berubah; bisa dicentang manual bila label rusak."),
        ],
    },
    "butcher_out": {
        "title": "Butcher Out (bahan keluar)",
        "model": "wms.butcher",
        "purpose": "Mencatat bahan (LPN daging) yang keluar dari gudang ke ruang potong.",
        "steps": [
            "New, isi Ref. dokumen/SPK.",
            "Tambah baris: pilih LPN (item, lot, lokasi, qty terisi otomatis), ubah qty bila sebagian.",
            "Selesai: stok berkurang dari gudang dan masuk lokasi produksi.",
        ],
        "fields": [
            ("ref", "Nomor SPK/perintah potong."),
            ("#LPN", "LPN bahan."),
            ("#Item, Lot, Lokasi", "Terisi dari LPN."),
            ("#Qty / Berat (kg)", "Qty bahan dikeluarkan dan beratnya dalam kg."),
            ("total_kg", "Total berat bahan."),
            ("yield_pct", "Berat hasil (semua Butcher In terkait) dibanding berat bahan."),
        ],
    },
    "butcher_in": {
        "title": "Butcher In / Repack (hasil masuk)",
        "model": "wms.butcher",
        "purpose": "Mencatat hasil potong atau repack sebagai lot dan LPN baru lengkap dengan grade, brand dan "
                   "cutting type.",
        "steps": [
            "New, pilih Butcher Out asal (supaya yield terhitung) dan ref. SPK.",
            "Tambah baris per hasil: proses, item hasil, lokasi simpan, qty, grade, brand, cutting type, expiry.",
            "Selesai: lot dan LPN baru dibuat langsung di lokasi simpan. Cetak label LPN hasil.",
        ],
        "fields": [
            ("source_id", "Butcher Out bahan, dasar perhitungan yield."),
            ("#Proses", "Rebag, Non rebag, Trimming, Sisa potong, Repack."),
            ("#Item", "Item hasil (boleh sama atau beda dengan bahan)."),
            ("#Lot hasil", "Kosong = dibuat otomatis dari nomor dokumen."),
            ("#Lokasi", "Bin simpan hasil, harus di zona item."),
            ("#Grade / Brand / Cutting type", "Tercatat di lot dan tercetak di label LPN."),
            ("#Expiry hasil", "Kosong = tanggal hari ini + umur simpan item."),
            ("yield_pct", "Persen hasil dibanding bahan."),
        ],
    },
    "report_by_location": {
        "title": "Laporan Stok per Lokasi",
        "model": "stock.quant",
        "purpose": "Melihat barang apa saja dan berapa jumlahnya di satu lokasi: satu bin, satu rak, satu area atau "
                   "satu zona.",
        "steps": [
            "Ketik nama atau barcode lokasi di kotak pencarian lalu pilih 'Search Location'. Contoh: SKI-FZ-A01-1 "
            "(satu bin), FZ/BLK/A01 (satu bay), FZ (seluruh zona frozen). Sub-lokasi ikut terhitung.",
            "Hasil dikelompokkan per lokasi; klik grup untuk melihat isinya per item, lot dan LPN.",
            "Tampilan Pivot memberi ringkasan lokasi × item dengan total qty. Ekspor ke Excel dari menu Aksi.",
            "Di lantai gudang, hal yang sama bisa dilihat dari handheld menu Cek stok dengan scan barcode bin.",
        ],
        "fields": [
            ("location_id", "Lokasi (bin)."),
            ("product_id", "Item code dan nama item."),
            ("lot_id", "Lot."),
            ("package_id", "LPN."),
            ("wms_expiration_date", "Kedaluwarsa."),
            ("quantity", "Qty on hand; total per grup lokasi tampil di baris grup."),
            ("reserved_quantity", "Qty yang sudah dipesan untuk pengiriman."),
            ("wms_status", "Status stok."),
        ],
    },
    "report_by_item": {
        "title": "Laporan Lokasi per Item",
        "model": "stock.quant",
        "purpose": "Melihat satu item code tersimpan di lokasi mana saja, dengan lot, kedaluwarsa dan qty-nya.",
        "steps": [
            "Ketik item code (mis. HUS2LEP002) atau nama item di kotak pencarian lalu pilih 'Search Product'.",
            "Hasil dikelompokkan per item; klik grup untuk melihat semua lokasinya. Urutkan kolom Kedaluwarsa "
            "untuk melihat lot mana yang harus keluar lebih dulu (FEFO).",
            "Tambahkan filter Available untuk hanya melihat stok yang bisa dijual, atau Hold untuk yang ditahan.",
            "Di handheld: menu Cek stok, scan barcode item atau ketik item code.",
        ],
        "fields": [
            ("product_id", "Item code dan nama item."),
            ("location_id", "Lokasi tempat item berada."),
            ("lot_id", "Lot."),
            ("package_id", "LPN."),
            ("wms_expiration_date", "Kedaluwarsa."),
            ("quantity", "Qty di lokasi itu; total semua lokasi tampil di baris grup item."),
            ("wms_status", "Status stok di lokasi itu."),
        ],
    },
    "lpn": {
        "title": "LPN List dan Need to Print",
        "model": "stock.quant.package",
        "purpose": "Daftar LPN dengan isinya; Need to Print berisi LPN yang labelnya harus dicetak ulang.",
        "steps": ["Pilih LPN lalu Cetak label LPN. Tanda Need to Print hilang setelah dicetak."],
        "fields": [
            ("name", "Nomor LPN."),
            ("wms_product_id", "Item di LPN."),
            ("wms_lot_id", "Lot."),
            ("wms_qty", "Qty."),
            ("wms_expiration_date", "Kedaluwarsa."),
            ("wms_status", "Status stok."),
            ("wms_pallet_no", "Nomor palet fisik."),
            ("wms_closed", "Palet sudah ditutup di receiving."),
            ("wms_need_reprint", "Label perlu dicetak ulang."),
        ],
    },
    "reports": {
        "title": "Reports",
        "purpose": "Laporan standar Largo untuk kontrol harian dan bulanan.",
        "steps": ["Semua laporan bisa difilter, dikelompokkan dan diekspor ke Excel."],
        "fields": [
            ("#Stok per Lokasi", "Barang apa saja dan jumlahnya di satu bin, rak, area atau zona."),
            ("#Lokasi per Item", "Satu item code ada di lokasi mana saja, dengan lot dan qty."),
            ("#Material In / Out", "Barang masuk dan keluar per periode."),
            ("#Transfer Log", "Semua pemindahan internal."),
            ("#Cycle Count / Adjustment", "Penyesuaian stok hasil hitung."),
            ("#Item Low", "Item di bawah stok minimum."),
            ("#Warehouse Transfer", "Transfer antar gudang."),
            ("#Expired Report", "Stok per periode kedaluwarsa 1/2/3/4 bulan."),
            ("#Inventory Check Discrepancy", "Selisih inventory check per item."),
            ("#Stock Card", "Kartu stok: riwayat pergerakan per item dan lot."),
        ],
    },
    # ------------------------------------------------------------------ master data & SAP
    "product": {
        "title": "Item Master (tab FoodTrace)",
        "model": "product.template",
        "purpose": "Pengaturan gudang per item. Kode item wajib sama dengan ItemCode SAP.",
        "steps": ["Buka item, tab FoodTrace. Lengkapi zona dan aturan sebelum item pertama kali diterima."],
        "fields": [
            ("default_code", "ItemCode SAP. Wajib untuk sinkron dan posting."),
            ("tracking", "Harus By Lots untuk semua barang makanan."),
            ("expiration_time", "Umur simpan total (hari), dasar perhitungan sisa umur."),
            ("wms_zone", "Zona wajib item."),
            ("wms_catch_weight", "Item berat aktual: setiap karton discan dan ditimbang; satuan kg."),
            ("wms_barcode_template_ids", "Format barcode karton yang dipakai pemasok item ini."),
            ("wms_min_receive_life_pct", "Sisa umur minimum saat diterima (%)."),
            ("wms_auto_quarantine", "Setiap penerimaan otomatis masuk karantina."),
            ("wms_quarantine_days", "Lama karantina."),
            ("wms_auto_release", "Dilepas otomatis setelah lama karantina habis."),
            ("wms_units_per_pallet", "Qty per palet penuh, untuk perencanaan put away."),
            ("wms_multi_qty", "Boleh diambil eceran (LPN dipecah)."),
            ("wms_picking_strategy", "FEFO (bawaan) atau FIFO."),
            ("wms_min_stock", "Stok minimum; di bawahnya item masuk laporan Item Low."),
            ("wms_item_group", "Item group SAP."),
            ("wms_sub_group", "Sub group SAP."),
            ("wms_country", "Negara asal."),
        ],
    },
    "location": {
        "title": "Bin / Rak Master",
        "model": "stock.location",
        "purpose": "Struktur lokasi gudang dan atributnya.",
        "steps": [
            "Buat ruang zona (FZ/CH/DR) dengan Zona suhu terisi; bin di bawahnya mewarisi zona.",
            "Isi Area dan Barcode setiap bin, lalu cetak label barcode rak.",
        ],
        "fields": [
            ("name", "Nama bin, mis. A01-1."),
            ("location_id", "Lokasi induk."),
            ("barcode", "Barcode yang ditempel di rak, mis. SKI-FZ-A01-1."),
            ("wms_zone", "Zona suhu. Kosong = ikut induk."),
            ("wms_area", "Area: RCV, IN, BLK, PCK, QC, RTN, DMG, WST, OUT, PRD, ruang. Menentukan status stok."),
            ("wms_max_pallets", "Kapasitas palet bin."),
            ("wms_max_weight", "Berat maksimum bin (kg)."),
        ],
    },
    "partner": {
        "title": "Source & Destination Master (customer/supplier)",
        "model": "res.partner",
        "purpose": "Supplier (source) dan customer (destination) beserta aturan gudangnya.",
        "steps": [
            "Kode partner (Reference) harus sama dengan CardCode SAP supaya dokumen sinkron cocok.",
            "Partner otomatis masuk Source Master saat dipakai di dokumen inbound, dan Destination Master saat "
            "dipakai di dokumen outbound. Centang manual untuk partner baru.",
        ],
        "fields": [
            ("ref", "CardCode SAP."),
            ("wms_is_source", "Tampil di Source Master (pemasok)."),
            ("wms_is_destination", "Tampil di Destination Master (pelanggan)."),
            ("wms_min_shelf_life_pct", "Customer: sisa umur minimum barang yang boleh dikirim (%)."),
            ("wms_over_receive_pct", "Supplier: toleransi kelebihan terima di atas PO (%)."),
            ("wms_owner_code", "Kode owner di file sinkron SAP (untuk partner perusahaan sendiri)."),
        ],
    },
    "barcode_template": {
        "title": "Format Serial Number / barcode karton",
        "model": "wms.barcode.template",
        "purpose": "Mengajari sistem membaca barcode karton tiap pemasok: berat, lot, kedaluwarsa, nomor karton.",
        "steps": [
            "GS1-128: cukup pilih jenis GS1, sistem membaca AI 01/10/17/21/310x/320x.",
            "Format khusus: pilih Pola regex dan tulis pola dengan grup bernama weight, lot, expiry, carton.",
            "Isi Contoh barcode lalu Uji contoh barcode untuk memastikan hasilnya benar. Hubungkan ke item.",
        ],
        "fields": [
            ("name", "Nama format, mis. 'Label US berat lbs'."),
            ("kind", "GS1-128 atau Pola regex."),
            ("pattern", "Pola regex dengan grup bernama (khusus jenis regex)."),
            ("weight_unit", "Satuan berat di label: Kg atau Lbs (otomatis dikonversi ke kg)."),
            ("weight_decimals", "Jumlah desimal berat pada pola regex (mis. 0600 dengan 2 desimal = 6,00)."),
            ("min_weight", "Berat minimum wajar per karton; di luar rentang ditolak."),
            ("max_weight", "Berat maksimum wajar per karton."),
            ("sample", "Contoh barcode untuk diuji."),
            ("product_tmpl_ids", "Item yang memakai format ini."),
        ],
    },
    "zone_standard": {
        "title": "Standar zona",
        "model": "wms.zone.standard",
        "purpose": "Daftar zona penyimpanan (Frozen, Chilled, Dry) dengan kode lokasi, umur simpan bawaan dan warna.",
        "steps": ["Ubah hanya atas persetujuan kepala gudang."],
        "fields": [
            ("zone", "Frozen, Chilled, Dry."),
            ("code", "Kode zona di nama lokasi (FZ, CH, DR)."),
            ("shelf_life_days", "Umur simpan bawaan untuk item baru di zona ini."),
            ("color", "Warna zona di dashboard dan handheld."),
        ],
    },
    "warehouse": {
        "title": "Gudang (kode SAP)",
        "model": "stock.warehouse",
        "purpose": "Menghubungkan gudang FoodTrace dengan kode gudang di file sinkron SAP.",
        "steps": ["Isi Kode gudang SAP persis seperti nilai 'warehouse' di file POR/SOR, mis. 95-SKI."],
        "fields": [
            ("name", "Nama gudang."),
            ("code", "Kode pendek, menjadi awalan nomor dokumen (SKI/IN, SKI/OUT)."),
            ("wms_sap_code", "Kode gudang SAP."),
        ],
    },
    "sync_document": {
        "title": "Dokumen masuk SAP (POR/SOR)",
        "model": "wms.sync.document",
        "purpose": "PO dan SO dari SAP sebelum menjadi dokumen gudang. Tempat memeriksa dokumen yang gagal.",
        "steps": [
            "Filter status Gagal setiap pagi. Baca Pesan gagal (biasanya item atau gudang belum dipetakan).",
            "Perbaiki master data, lalu Proses ulang.",
            "Dokumen masuk otomatis dari SAP lewat API sinkron; nomor yang sama tidak dibuat dua kali.",
        ],
        "fields": [
            ("name", "Nomor dokumen SAP lengkap (95-SKI-POR-…)."),
            ("direction", "Inbound (PO) atau Outbound (SO)."),
            ("doc_type", "Jenis dari SAP: Purchase Order, Sales Order, dll."),
            ("web_trans_no", "Nomor transaksi web SAP."),
            ("doc_entry", "DocEntry SAP."),
            ("partner_code", "CardCode supplier/customer."),
            ("warehouse_code", "Kode gudang SAP."),
            ("owner_code", "Owner stok."),
            ("shipping_group", "Rute pengiriman."),
            ("doc_date", "Tanggal dokumen."),
            ("delivery_date", "Tanggal kirim/terima rencana."),
            ("priority", "Prioritas SAP."),
            ("state", "Baru, Jadi picking, Gagal."),
            ("error", "Penyebab gagal."),
            ("picking_id", "Dokumen gudang yang dibuat."),
            ("payload", "Isi file asli dari SAP, untuk penelusuran."),
        ],
    },
    "sap_document": {
        "title": "Antrean posting SAP (GR/GI)",
        "model": "wms.sap.document",
        "purpose": "Hasil kerja gudang yang dikirim ke SAP: Goods Receipt PO, Delivery, Transfer, Adjustment, Retur.",
        "steps": [
            "Filter Gagal. Baca Pesan gagal, perbaiki penyebabnya (item tanpa kode SAP, stok negatif di SAP, batch "
            "ganda, koneksi), lalu Kirim ulang.",
            "Antrean dikirim otomatis setiap 5 menit.",
        ],
        "fields": [
            ("name", "Referensi unik, mencegah posting dua kali."),
            ("picking_id", "Dokumen gudang asal."),
            ("doc_type", "Jenis dokumen SAP."),
            ("sap_company_db", "Company DB SAP tujuan."),
            ("state", "Antre, Terkirim, Gagal."),
            ("sap_doc_num", "Nomor dokumen di SAP setelah terkirim."),
            ("error", "Pesan dari SAP bila gagal."),
            ("attempts", "Jumlah percobaan kirim."),
            ("posted_at", "Waktu terkirim."),
        ],
    },
}

# Layar yang dibuka dari web: (model, kunci konteks) → kunci layar.
MODEL_SCREENS = {
    "wms.tally.wizard": "tally",
    "wms.carton": "carton",
    "wms.loading": "loading",
    "wms.pod": "pod",
    "stock.picking.batch": "picking_job",
    "stock.quant": "stock_status",
    "wms.qc.release.wizard": "qc_release",
    "wms.inventory.check": "inventory_check",
    "wms.inventory.check.line": "inventory_check",
    "stock.quant.package": "lpn",
    "product.template": "product",
    "product.product": "product",
    "stock.location": "location",
    "res.partner": "partner",
    "wms.barcode.template": "barcode_template",
    "wms.zone.standard": "zone_standard",
    "stock.warehouse": "warehouse",
    "wms.sync.document": "sync_document",
    "wms.sap.document": "sap_document",
    "stock.move.line": "reports",
    "stock.move": "reports",
}
