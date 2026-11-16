"""Operasi bisnis Goorame (dulu endpoint FastAPI) sebagai fungsi Python biasa.

Semua fungsi `commit` sekali di akhir; jika ada error, sesi di-rollback sehingga
saldo kas, stok kolam, dan jurnal tidak pernah setengah tersimpan.
Kesalahan validasi dilempar sebagai ValueError dengan pesan berbahasa Indonesia.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.models.accounting import CashAccount, ChartOfAccount, JournalEntry
from app.models.expense import CashTransfer, Expense, SupplierInvoice, SupplierPayment
from app.models.pond import Pond, StockMutation
from app.models.sale import Sale
from app.models.user import User
from app.services.accounting_service import (
    JournalLine, calculate_general_ledger, calculate_income_statement,
    create_double_entry_journal, trial_balance,
)

EXPENSE_COA_MAP = {
    "PAKAN": ("1160", "Persediaan Pakan Ikan"),
    "GAJI": ("6110", "Beban Gaji & Upah Tenaga Kerja"),
    "OBAT": ("1170", "Persediaan Obat, Vitamin & Garam"),
    "OPERASIONAL": ("6120", "Beban Listrik, Aerator & Pompa Air"),
}
SUPPLIER_CATEGORY_MAP = {
    "Pakan": ("1160", "Persediaan Pakan Ikan"),
    "Bibit": ("1150", "Persediaan Benih Gurame"),
    "Obat / Suplemen": ("1170", "Persediaan Obat, Vitamin & Garam"),
}
DEFAULT_DEBIT = ("6190", "Beban Operasional Lain-lain")

POND_TYPES = ["PEMBESARAN", "BIBIT", "PANEN", "KARANTINA"]
COA_CATEGORIES = ["ASET", "KEWAJIBAN", "EKUITAS", "PENDAPATAN", "BEBAN"]


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _positive(value: float, label: str):
    if value is None or value <= 0:
        raise ValueError(f"{label} harus lebih dari nol.")


def _commit(db: Session):
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _cash(db: Session, cash_id: Optional[str]) -> CashAccount:
    acc = db.query(CashAccount).filter(CashAccount.id == cash_id).first() if cash_id else None
    if not acc:
        raise ValueError("Dompet Kas/Bank tidak valid")
    return acc


# ---------------------------------------------------------------- auth
def login(db: Session, username: str, password: str) -> User:
    user = db.query(User).filter(User.username == (username or "").strip().lower()).first()
    if not user:
        raise ValueError("Username tidak terdaftar di sistem")
    if not password:
        raise ValueError("Kata sandi harus diisi")
    if not verify_password(password, user.password_hash):
        raise ValueError("Kata sandi tidak sesuai")
    return user


# --------------------------------------------------------------- kolam
def create_pond(db: Session, name, type_, dimension, capacity_ekor, initial_stock=0, initial_kg=0.0) -> Pond:
    if not (name or "").strip():
        raise ValueError("Nama kolam harus diisi.")
    _positive(capacity_ekor, "Kapasitas")
    if initial_stock < 0 or initial_kg < 0:
        raise ValueError("Stok awal tidak boleh negatif.")
    pond = Pond(
        name=name.strip(), type=type_, dimension=dimension or "-",
        capacity_ekor=int(capacity_ekor), initial_stock=int(initial_stock),
        current_ekor=int(initial_stock), current_kg_estimasi=float(initial_kg),
        total_tebar=int(initial_stock), total_mati=0, total_panen=0,
        survival_rate=100.0, status="AKTIF",
    )
    db.add(pond)
    _commit(db)
    return pond


def _update_survival(pond: Pond):
    if pond.total_tebar > 0:
        sr = ((pond.total_tebar - pond.total_mati) / pond.total_tebar) * 100.0
        pond.survival_rate = round(max(0.0, min(100.0, sr)), 1)


def tebar_bibit(db: Session, pond_id, ekor, weight_kg, note="Tebar bibit baru") -> StockMutation:
    pond = db.query(Pond).filter(Pond.id == pond_id).first()
    if not pond:
        raise ValueError("Kolam tidak ditemukan")
    _positive(ekor, "Jumlah ekor")
    if weight_kg < 0:
        raise ValueError("Berat tidak boleh negatif.")
    m = StockMutation(
        pond_id=pond.id, date=_today(), type="TEBAR", ekor=int(ekor), weight_kg=float(weight_kg),
        note=note, reference_id=f"TBR-{datetime.now().strftime('%Y%m%d%H%M')}",
    )
    db.add(m)
    pond.total_tebar += int(ekor)
    pond.current_ekor += int(ekor)
    pond.current_kg_estimasi += float(weight_kg)
    _update_survival(pond)
    _commit(db)
    return m


def catat_mortalitas(db: Session, pond_id, ekor, weight_kg, note="Kematian harian") -> StockMutation:
    pond = db.query(Pond).filter(Pond.id == pond_id).first()
    if not pond:
        raise ValueError("Kolam tidak ditemukan")
    _positive(ekor, "Jumlah ekor")
    if ekor > pond.current_ekor:
        raise ValueError(f"Jumlah ikan mati melebihi stok kolam ({pond.current_ekor} ekor).")
    m = StockMutation(
        pond_id=pond.id, date=_today(), type="MATI", ekor=int(ekor), weight_kg=float(weight_kg),
        note=note, reference_id=f"MT-{datetime.now().strftime('%Y%m%d%H%M')}",
    )
    db.add(m)
    pond.total_mati += int(ekor)
    pond.current_ekor = max(0, pond.current_ekor - int(ekor))
    pond.current_kg_estimasi = max(0.0, pond.current_kg_estimasi - float(weight_kg))
    _update_survival(pond)
    _commit(db)
    return m


# ------------------------------------------------------------ penjualan
def create_sale(db: Session, buyer_name, pond_id, quantity_ekor, weight_kg, price_per_kg,
                payment_status="LUNAS", cash_account_id=None, due_date=None, note=None) -> Sale:
    if not (buyer_name or "").strip():
        raise ValueError("Nama pembeli harus diisi.")
    _positive(weight_kg, "Berat (kg)")
    _positive(price_per_kg, "Harga per kg")
    if quantity_ekor < 0:
        raise ValueError("Jumlah ekor tidak boleh negatif.")
    date_str = _today()
    total = round(weight_kg * price_per_kg, 2)
    invoice_no = f"INV-{date_str.replace('-', '')[:6]}-{str(db.query(Sale).count() + 1).zfill(3)}"

    cash_acc = None
    if payment_status == "LUNAS":
        cash_acc = _cash(db, cash_account_id)
    elif not due_date:
        raise ValueError("Penjualan tempo wajib punya tanggal jatuh tempo.")

    pond = db.query(Pond).filter(Pond.id == pond_id).first() if pond_id else None
    if pond and quantity_ekor > pond.current_ekor:
        raise ValueError(f"Jumlah ekor ({quantity_ekor}) melebihi stok {pond.name} ({pond.current_ekor}).")

    sale = Sale(
        invoice_no=invoice_no, date=date_str, buyer_name=buyer_name.strip(),
        pond_id=pond_id, quantity_ekor=int(quantity_ekor), weight_kg=float(weight_kg),
        price_per_kg=float(price_per_kg), total_amount=total, payment_status=payment_status,
        due_date=due_date, paid_date=date_str if payment_status == "LUNAS" else None,
        cash_account_id=cash_acc.id if cash_acc else None,
        cash_account_name=cash_acc.name if cash_acc else None, note=note,
    )
    db.add(sale)

    if cash_acc:
        cash_acc.balance += total
        debit = JournalLine(cash_acc.code, debit=total, account_name=cash_acc.name)
        desc = f"Penjualan Tunai {invoice_no} ({buyer_name})"
    else:
        debit = JournalLine("1140", debit=total, account_name="Piutang Usaha")
        desc = f"Penjualan Tempo {invoice_no} ({buyer_name})"
    create_double_entry_journal(
        db, date_str, desc, "PENJUALAN",
        [debit, JournalLine("4110", credit=total, account_name="Penjualan Ikan Gurame Konsumsi")],
        ref_id=invoice_no,
    )

    if pond:
        db.add(StockMutation(
            pond_id=pond.id, date=date_str, type="PANEN", ekor=int(quantity_ekor),
            weight_kg=float(weight_kg), note=f"Panen penjualan {invoice_no} ({buyer_name})",
            reference_id=invoice_no,
        ))
        pond.total_panen += int(quantity_ekor)
        pond.current_ekor = max(0, pond.current_ekor - int(quantity_ekor))
        pond.current_kg_estimasi = max(0.0, pond.current_kg_estimasi - float(weight_kg))

    _commit(db)
    return sale


def pay_receivable(db: Session, sale_id, cash_account_id) -> Sale:
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise ValueError("Penjualan tidak ditemukan")
    if sale.payment_status == "LUNAS":
        raise ValueError("Penjualan ini sudah lunas")
    cash_acc = _cash(db, cash_account_id)
    date_str = _today()
    sale.payment_status = "LUNAS"
    sale.paid_date = date_str
    sale.cash_account_id = cash_acc.id
    sale.cash_account_name = cash_acc.name
    cash_acc.balance += sale.total_amount
    create_double_entry_journal(
        db, date_str, f"Pelunasan Piutang {sale.invoice_no} ({sale.buyer_name})", "PENJUALAN",
        [JournalLine(cash_acc.code, debit=sale.total_amount, account_name=cash_acc.name),
         JournalLine("1140", credit=sale.total_amount, account_name="Piutang Usaha")],
        ref_id=sale.invoice_no,
    )
    _commit(db)
    return sale


# ----------------------------------------------------------- pengeluaran
def create_expense(db: Session, category, nominal, cash_account_id, note=None) -> Expense:
    _positive(nominal, "Nominal")
    cash_acc = _cash(db, cash_account_id)
    if cash_acc.balance < nominal:
        raise ValueError(f"Saldo {cash_acc.name} tidak mencukupi (Tersedia: Rp {cash_acc.balance:,.2f})")
    date_str = _today()
    expense_no = f"BBN-{date_str.replace('-', '')[:6]}-{str(db.query(Expense).count() + 1).zfill(3)}"
    expense = Expense(
        expense_no=expense_no, date=date_str, category=category, nominal=float(nominal),
        cash_account_id=cash_acc.id, cash_account_name=cash_acc.name, note=note,
    )
    db.add(expense)
    cash_acc.balance -= nominal
    code, name = EXPENSE_COA_MAP.get(category.upper(), DEFAULT_DEBIT)
    create_double_entry_journal(
        db, date_str, f"Beban {category}: {note or expense_no}", "BEBAN",
        [JournalLine(code, debit=nominal, account_name=name),
         JournalLine(cash_acc.code, credit=nominal, account_name=cash_acc.name)],
        ref_id=expense_no,
    )
    _commit(db)
    return expense


# ---------------------------------------------------------------- utang
def create_supplier_invoice(db: Session, supplier_name, item_category, total_amount, due_date, note=None) -> SupplierInvoice:
    if not (supplier_name or "").strip():
        raise ValueError("Nama supplier harus diisi.")
    _positive(total_amount, "Total tagihan")
    if not due_date:
        raise ValueError("Tanggal jatuh tempo harus diisi.")
    date_str = _today()
    prefix = "".join(filter(str.isalnum, supplier_name))[:3].upper() or "SUP"
    number = f"INV-{prefix}-{str(db.query(SupplierInvoice).count() + 1).zfill(3)}"
    while db.query(SupplierInvoice).filter(SupplierInvoice.invoice_number == number).first():
        number += "X"
    inv = SupplierInvoice(
        invoice_number=number, date=date_str, supplier_name=supplier_name.strip(),
        item_category=item_category, total_amount=float(total_amount), paid_amount=0.0,
        due_date=due_date, status="BELUM_LUNAS", note=note,
    )
    db.add(inv)
    code, name = SUPPLIER_CATEGORY_MAP.get(item_category, DEFAULT_DEBIT)
    create_double_entry_journal(
        db, date_str, f"Utang Pembelian {item_category} dari {supplier_name} ({number})", "UTANG",
        [JournalLine(code, debit=total_amount, account_name=name),
         JournalLine("2110", credit=total_amount, account_name="Utang Usaha Pemasok")],
        ref_id=number,
    )
    _commit(db)
    return inv


def pay_supplier_invoice(db: Session, invoice_id, amount, cash_account_id, note=None) -> SupplierPayment:
    inv = db.query(SupplierInvoice).filter(SupplierInvoice.id == invoice_id).first()
    if not inv:
        raise ValueError("Faktur tagihan supplier tidak ditemukan")
    _positive(amount, "Jumlah pembayaran")
    sisa = inv.total_amount - inv.paid_amount
    if amount > sisa + 0.005:
        raise ValueError(f"Pembayaran melebihi sisa utang (Rp {sisa:,.2f}).")
    cash_acc = _cash(db, cash_account_id)
    if cash_acc.balance < amount:
        raise ValueError(f"Saldo {cash_acc.name} tidak cukup")
    date_str = _today()
    payment_no = f"PAY-{date_str.replace('-', '')[:6]}-{str(db.query(SupplierPayment).count() + 1).zfill(3)}"
    pay = SupplierPayment(
        payment_no=payment_no, invoice_id=inv.id, date=date_str, amount=float(amount),
        cash_account_id=cash_acc.id, cash_account_name=cash_acc.name, note=note,
    )
    db.add(pay)
    inv.paid_amount += amount
    if inv.paid_amount >= inv.total_amount:
        inv.status = "LUNAS"
    cash_acc.balance -= amount
    create_double_entry_journal(
        db, date_str, f"Pembayaran Utang {inv.invoice_number} ke {inv.supplier_name}", "UTANG",
        [JournalLine("2110", debit=amount, account_name="Utang Usaha Pemasok"),
         JournalLine(cash_acc.code, credit=amount, account_name=cash_acc.name)],
        ref_id=payment_no,
    )
    _commit(db)
    return pay


# ------------------------------------------------------------- kas/bank
def create_cash_account(db: Session, name, type_, account_number=None, initial_balance=0.0) -> CashAccount:
    if not (name or "").strip():
        raise ValueError("Nama rekening harus diisi.")
    if initial_balance < 0:
        raise ValueError("Saldo awal tidak boleh negatif.")
    n = db.query(CashAccount).count() + 1
    code = f"11{str(n).zfill(2)}"
    while db.query(ChartOfAccount).filter(ChartOfAccount.code == code).first():
        n += 1
        code = f"11{str(n).zfill(2)}"
    db.add(ChartOfAccount(
        code=code, name=name.strip(), category="ASET", normal_balance="DEBIT",
        description=f"Rekening {type_}: {name.strip()}",
    ))
    acc = CashAccount(code=code, name=name.strip(), type=type_,
                      account_number=account_number, balance=float(initial_balance))
    db.add(acc)
    _commit(db)
    return acc


def transfer_cash(db: Session, from_account_id, to_account_id, amount, note=None) -> CashTransfer:
    _positive(amount, "Nominal transfer")
    src, dst = _cash(db, from_account_id), _cash(db, to_account_id)
    if src.id == dst.id:
        raise ValueError("Rekening asal dan tujuan tidak boleh sama")
    if src.balance < amount:
        raise ValueError(f"Saldo {src.name} tidak cukup")
    date_str = _today()
    transfer_no = f"TRF-{date_str.replace('-', '')[:6]}-{str(db.query(CashTransfer).count() + 1).zfill(3)}"
    tr = CashTransfer(
        transfer_no=transfer_no, date=date_str, from_account_id=src.id, from_account_name=src.name,
        to_account_id=dst.id, to_account_name=dst.name, amount=float(amount), note=note,
    )
    db.add(tr)
    src.balance -= amount
    dst.balance += amount
    create_double_entry_journal(
        db, date_str, f"Transfer Dana dari {src.name} ke {dst.name}", "TRANSFER",
        [JournalLine(dst.code, debit=amount, account_name=dst.name),
         JournalLine(src.code, credit=amount, account_name=src.name)],
        ref_id=transfer_no,
    )
    _commit(db)
    return tr


# ------------------------------------------------------------ akuntansi
def create_coa(db: Session, code, name, category, normal_balance, description=None) -> ChartOfAccount:
    code = (code or "").strip()
    if not code or not (name or "").strip():
        raise ValueError("Kode dan nama akun harus diisi.")
    if db.query(ChartOfAccount).filter(ChartOfAccount.code == code).first():
        raise ValueError(f"Kode akun {code} sudah terdaftar")
    coa = ChartOfAccount(code=code, name=name.strip(), category=category.upper(),
                         normal_balance=normal_balance.upper(), description=description)
    db.add(coa)
    _commit(db)
    return coa


def update_coa(db: Session, code, name=None, category=None, normal_balance=None, description=None):
    coa = db.query(ChartOfAccount).filter(ChartOfAccount.code == code).first()
    if not coa:
        raise ValueError("Akun tidak ditemukan")
    if name is not None:
        coa.name = name
    if category is not None:
        coa.category = category.upper()
    if normal_balance is not None:
        coa.normal_balance = normal_balance.upper()
    if description is not None:
        coa.description = description
    _commit(db)
    return coa


def create_manual_journal(db: Session, date, description, lines) -> JournalEntry:
    if not (description or "").strip():
        raise ValueError("Keterangan jurnal harus diisi.")
    j = create_double_entry_journal(db, date, description.strip(), "MANUAL", lines)
    _commit(db)
    return j


# ------------------------------------------------------------ dashboard
def dashboard_summary(db: Session) -> dict:
    ponds = db.query(Pond).all()
    cash = db.query(CashAccount).all()
    unpaid = db.query(SupplierInvoice).filter(SupplierInvoice.status == "BELUM_LUNAS").all()
    tempo = db.query(Sale).filter(Sale.payment_status == "TEMPO").all()
    inc = calculate_income_statement(db)
    month_start = datetime.now().strftime("%Y-%m-01")
    inc_m = calculate_income_statement(db, month_start, "")
    return {
        "total_cash": sum(c.balance for c in cash),
        "total_fish_count": sum(p.current_ekor for p in ponds),
        "total_fish_weight": round(sum(p.current_kg_estimasi for p in ponds), 1),
        "total_capacity": sum(p.capacity_ekor for p in ponds),
        "total_payable_due": sum(i.total_amount - i.paid_amount for i in unpaid),
        "total_receivable_due": sum(s.total_amount for s in tempo),
        "net_income": inc["net_income"],
        "total_revenue": inc["total_revenue"],
        "total_expense": inc["total_expense"],
        "month_revenue": inc_m["total_revenue"],
        "month_expense": inc_m["total_expense"],
        "month_net": inc_m["net_income"],
        "pond_count": len(ponds),
    }


def get_alerts(db: Session) -> list:
    """Peringatan operasional: utang/piutang jatuh tempo, saldo akun janggal, stok kolam."""
    today = datetime.now().strftime("%Y-%m-%d")
    soon = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    alerts = []
    for i in db.query(SupplierInvoice).filter(SupplierInvoice.status != "LUNAS").all():
        sisa = i.total_amount - i.paid_amount
        if i.due_date < today:
            alerts.append(("error", f"Utang {i.invoice_number} ({i.supplier_name}) lewat jatuh tempo {i.due_date}: Rp {sisa:,.0f}"))
        elif i.due_date <= soon:
            alerts.append(("warning", f"Utang {i.invoice_number} ({i.supplier_name}) jatuh tempo {i.due_date}: Rp {sisa:,.0f}"))
    for s in db.query(Sale).filter(Sale.payment_status == "TEMPO").all():
        if s.due_date and s.due_date < today:
            alerts.append(("error", f"Piutang {s.invoice_no} ({s.buyer_name}) lewat jatuh tempo {s.due_date}: Rp {s.total_amount:,.0f}"))
        elif s.due_date and s.due_date <= soon:
            alerts.append(("warning", f"Piutang {s.invoice_no} ({s.buyer_name}) jatuh tempo {s.due_date}: Rp {s.total_amount:,.0f}"))
    for p in db.query(Pond).all():
        if p.capacity_ekor and p.current_ekor > p.capacity_ekor:
            alerts.append(("warning", f"{p.name} melebihi kapasitas ({p.current_ekor}/{p.capacity_ekor} ekor)"))
        if p.survival_rate < 80 and p.total_tebar > 0:
            alerts.append(("warning", f"Survival rate {p.name} rendah ({p.survival_rate:.1f}%)"))
    for r in calculate_general_ledger(db):
        if r["ending_balance"] < -0.005:
            alerts.append(("warning", f"Saldo akun {r['code']} {r['name']} berlawanan dengan saldo normalnya"))
    tb = trial_balance(db)
    if not tb["balanced"]:
        alerts.append(("error", "Neraca saldo tidak seimbang: periksa jurnal."))
    return alerts


# ----------------------------------------------------------- pengguna
def _min_password(pw: str):
    if not pw or len(pw) < 6:
        raise ValueError("Kata sandi minimal 6 karakter.")


def uses_default_password(user: User) -> bool:
    defaults = {"pemilik": "admin123", "pekerja": "pekerja123"}
    pw = defaults.get(user.username)
    return bool(pw and verify_password(pw, user.password_hash))


def change_password(db: Session, user_id, old_password, new_password) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("Pengguna tidak ditemukan")
    if not verify_password(old_password or "", user.password_hash):
        raise ValueError("Kata sandi lama tidak sesuai")
    _min_password(new_password)
    user.password_hash = get_password_hash(new_password)
    _commit(db)


def create_user(db: Session, username, full_name, role, password) -> User:
    username = (username or "").strip().lower()
    if not username or not username.replace("_", "").replace(".", "").isalnum():
        raise ValueError("Username hanya boleh huruf, angka, titik, atau garis bawah.")
    if role not in ("PEMILIK", "PEKERJA"):
        raise ValueError("Role tidak valid.")
    if db.query(User).filter(User.username == username).first():
        raise ValueError(f"Username '{username}' sudah dipakai.")
    _min_password(password)
    user = User(username=username, full_name=(full_name or "").strip() or role.title(),
                role=role, password_hash=get_password_hash(password))
    db.add(user)
    _commit(db)
    return user


def reset_password(db: Session, user_id, new_password) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("Pengguna tidak ditemukan")
    _min_password(new_password)
    user.password_hash = get_password_hash(new_password)
    _commit(db)


def delete_user(db: Session, user_id, acting_user_id) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("Pengguna tidak ditemukan")
    if user.id == acting_user_id:
        raise ValueError("Anda tidak dapat menghapus akun yang sedang dipakai.")
    if user.role == "PEMILIK" and db.query(User).filter(User.role == "PEMILIK").count() <= 1:
        raise ValueError("Harus tersisa minimal satu akun Pemilik.")
    db.delete(user)
    _commit(db)
