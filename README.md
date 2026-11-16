# Goorame (versi Python penuh · Streamlit)

Sistem akuntansi & budidaya ikan gurame. Tanpa Node.js, tanpa server API terpisah:
UI, logika bisnis, dan database semuanya Python.

## Menjalankan
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python -m streamlit run app.py
```
Buka http://localhost:8501. Saat pertama dijalankan, `goorame.db` (SQLite) dibuat dan
diisi data awal (bagan akun, 3 rekening, 4 kolam, contoh transaksi).

Login awal: `pemilik` / `admin123` (semua menu) dan `pekerja` / `pekerja123`
(hanya Dashboard & Stok Kolam). **Ganti/hapus akun ini sebelum dipakai sungguhan.**

Untuk PostgreSQL: set `DATABASE_URL` dan `pip install psycopg2-binary`.

## Struktur
```
app.py                 login + navigasi (menu dibatasi sesuai role)
views/                 satu file per halaman (dashboard, kolam, penjualan, pengeluaran,
                       utang, kas, akuntansi, laporan)
app/models/            tabel SQLAlchemy (sama dengan backend lama)
app/services/
  accounting_service.py  jurnal double-entry, buku besar, laba rugi, neraca
  operations.py          semua transaksi (dulu endpoint FastAPI)
app/core/              config, database, security, seeder
```

## Fitur
Dashboard (grafik, peringatan jatuh tempo) · Stok Kolam · Penjualan + nota cetak · Pengeluaran ·
Utang & Piutang · Kas & Bank · Jurnal Umum (template cepat) · **Buku Besar** (per akun, saldo berjalan,
filter periode, neraca saldo) · Laporan (laba rugi, neraca, arus kas, ekspor Excel/CSV) · Pengaturan
(ganti sandi, kelola pengguna, backup).

## Hosting
Lihat `PANDUAN_HOSTING.pdf` (langkah lengkap + daftar perangkat lunak) atau gunakan `Dockerfile`. Untuk hosting wajib memakai
PostgreSQL lewat `DATABASE_URL` (lihat `.streamlit/secrets.toml.example`).

## Perbedaan dari versi lama
- Satu transaksi = satu commit: saldo kas, stok kolam, dan jurnal tersimpan bersama atau batal bersama.
- Validasi tambahan: nominal harus > 0, penjualan tidak boleh melebihi stok kolam, pembayaran utang tidak boleh melebihi sisa, kode akun jurnal harus ada di COA.
- Kategori pengeluaran tak dikenal kini masuk ke akun 6190 (sebelumnya merujuk kode 5004 yang tidak ada di COA).
