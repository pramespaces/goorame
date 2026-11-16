"""Nota penjualan (HTML siap cetak, bisa disimpan sebagai PDF lewat browser)."""
from html import escape


def build_nota_html(sale, logo_b64: str, company: str = "Goorame", tagline: str = "Budidaya Ikan Gurame") -> str:
    def rp(v):
        return "Rp " + f"{float(v):,.0f}".replace(",", ".")
    lunas = sale.payment_status == "LUNAS"
    status = "LUNAS" if lunas else f"BELUM LUNAS (jatuh tempo {escape(sale.due_date or '-')})"
    color = "#1F6F54" if lunas else "#B26A00"
    return f"""<!DOCTYPE html><html lang="id"><head><meta charset="utf-8">
<title>Nota {escape(sale.invoice_no)}</title>
<style>
 body{{font-family:'Segoe UI',Arial,sans-serif;color:#1d2b25;max-width:720px;margin:24px auto;padding:0 16px}}
 header{{display:flex;align-items:center;gap:16px;border-bottom:3px solid #E9B949;padding-bottom:12px}}
 header img{{height:90px}} h1{{margin:0;color:#14513B;font-size:26px}} .muted{{color:#6b7a72;font-size:13px}}
 table{{width:100%;border-collapse:collapse;margin-top:18px}} th,td{{padding:9px 10px;border-bottom:1px solid #e5dfc8;text-align:left}}
 th{{background:#F4F1E6}} td.r,th.r{{text-align:right}} .total td{{font-weight:700;font-size:17px;border-top:2px solid #14513B}}
 .badge{{display:inline-block;padding:4px 12px;border-radius:99px;color:#fff;background:{color};font-weight:600;font-size:13px}}
 footer{{margin-top:32px;text-align:center}} @media print{{.noprint{{display:none}} body{{margin:0}}}}
</style></head><body>
<header><img src="data:image/png;base64,{logo_b64}" alt="logo">
<div><h1>{escape(company)}</h1><div class="muted">{escape(tagline)}</div></div>
<div style="margin-left:auto;text-align:right"><b>NOTA PENJUALAN</b><br>{escape(sale.invoice_no)}<br>
<span class="muted">{escape(sale.date)}</span></div></header>
<p><b>Pembeli:</b> {escape(sale.buyer_name)}<br><b>Status:</b> <span class="badge">{status}</span></p>
<table><tr><th>Keterangan</th><th class="r">Ekor</th><th class="r">Berat (kg)</th><th class="r">Harga/kg</th><th class="r">Jumlah</th></tr>
<tr><td>Ikan gurame konsumsi</td><td class="r">{sale.quantity_ekor}</td><td class="r">{sale.weight_kg:,.1f}</td>
<td class="r">{rp(sale.price_per_kg)}</td><td class="r">{rp(sale.total_amount)}</td></tr>
<tr class="total"><td colspan="4" class="r">TOTAL</td><td class="r">{rp(sale.total_amount)}</td></tr></table>
{f'<p class="muted">Dibayar ke: {escape(sale.cash_account_name or "-")} · {escape(sale.paid_date or "-")}</p>' if lunas else ''}
{f'<p class="muted">Catatan: {escape(sale.note)}</p>' if sale.note else ''}
<footer><p>Terima kasih atas kepercayaan Anda.</p>
<button class="noprint" onclick="window.print()">Cetak / Simpan PDF</button></footer></body></html>"""
