"""Logika akuntansi double-entry: jurnal, buku besar, neraca saldo,
laba rugi, neraca, arus kas, dan data grafik. Semua laporan mendukung periode
(`start`/`end` berformat YYYY-MM-DD; string kosong = tanpa batas)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import CashAccount, ChartOfAccount, JournalEntry, JournalItem


@dataclass
class JournalLine:
    account_code: str
    debit: float = 0.0
    credit: float = 0.0
    account_name: Optional[str] = None


# ------------------------------------------------------------------ jurnal
def create_double_entry_journal(db: Session, date: str, description: str, ref_type: str,
                                items: List[JournalLine], ref_id: Optional[str] = None) -> JournalEntry:
    """Buat jurnal seimbang. TIDAK commit: pemanggil yang commit, supaya
    transaksi + jurnal tersimpan atomik (semua berhasil atau semua batal)."""
    if len(items) < 2:
        raise ValueError("Jurnal minimal terdiri dari 2 baris (debit dan kredit).")
    if any(i.debit < 0 or i.credit < 0 for i in items):
        raise ValueError("Nilai debit/kredit tidak boleh negatif.")
    if any(i.debit and i.credit for i in items):
        raise ValueError("Satu baris jurnal tidak boleh berisi debit sekaligus kredit.")
    total_debit = round(sum(i.debit for i in items), 2)
    total_credit = round(sum(i.credit for i in items), 2)
    if total_debit != total_credit:
        raise ValueError(f"Jurnal tidak seimbang! Total Debit (Rp {total_debit:,.2f}) "
                         f"!= Total Kredit (Rp {total_credit:,.2f})")
    if total_debit <= 0:
        raise ValueError("Nilai jurnal harus lebih dari nol.")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Tanggal jurnal tidak valid.")

    clean_date = date.replace("-", "")[:6]
    count = db.query(JournalEntry).filter(JournalEntry.date.like(f"{date[:7]}%")).count() + 1
    entry_number = f"JU-{clean_date}-{str(count).zfill(3)}"
    while db.query(JournalEntry).filter(JournalEntry.entry_number == entry_number).first():
        count += 1
        entry_number = f"JU-{clean_date}-{str(count).zfill(3)}"

    journal = JournalEntry(entry_number=entry_number, date=date, description=description,
                           ref_type=ref_type, ref_id=ref_id)
    db.add(journal)
    db.flush()
    for item in items:
        acc = db.query(ChartOfAccount).filter(ChartOfAccount.code == item.account_code).first()
        if not acc:
            raise ValueError(f"Kode akun {item.account_code} tidak ada di Bagan Akun.")
        db.add(JournalItem(journal_id=journal.id, account_code=item.account_code,
                           account_name=item.account_name or acc.name,
                           debit=item.debit, credit=item.credit))
    return journal


def list_journals(db: Session, start: str = "", end: str = "", q: str = "", limit: int = 300):
    query = db.query(JournalEntry)
    if start:
        query = query.filter(JournalEntry.date >= start)
    if end:
        query = query.filter(JournalEntry.date <= end)
    if q:
        like = f"%{q}%"
        query = query.filter((JournalEntry.description.ilike(like)) | (JournalEntry.entry_number.ilike(like))
                             | (JournalEntry.ref_id.ilike(like)))
    entries = query.order_by(JournalEntry.date.desc(), JournalEntry.created_at.desc()).limit(limit).all()
    return [{
        "no": e.entry_number, "date": e.date, "desc": e.description, "type": e.ref_type, "ref": e.ref_id,
        "items": [(i.account_code, i.account_name, i.debit, i.credit) for i in e.items],
        "total": sum(i.debit for i in e.items),
    } for e in entries]


# ------------------------------------------------------------- agregasi dasar
def _totals(db: Session, start: str = "", end: str = "", before: str = "") -> Dict[str, tuple]:
    q = (db.query(JournalItem.account_code, func.coalesce(func.sum(JournalItem.debit), 0.0),
                  func.coalesce(func.sum(JournalItem.credit), 0.0), func.count(JournalItem.id))
         .join(JournalEntry, JournalItem.journal_id == JournalEntry.id))
    if start:
        q = q.filter(JournalEntry.date >= start)
    if end:
        q = q.filter(JournalEntry.date <= end)
    if before:
        q = q.filter(JournalEntry.date < before)
    return {code: (float(d), float(c), int(n)) for code, d, c, n in q.group_by(JournalItem.account_code).all()}


def _signed(normal_balance: str, debit: float, credit: float) -> float:
    return debit - credit if normal_balance == "DEBIT" else credit - debit


def calculate_general_ledger(db: Session, start: str = "", end: str = "") -> List[Dict[str, Any]]:
    """Ringkasan buku besar semua akun: saldo awal (sebelum `start`), mutasi
    periode, dan saldo akhir (sampai `end`)."""
    coas = db.query(ChartOfAccount).order_by(ChartOfAccount.code).all()
    opening = _totals(db, before=start) if start else {}
    period = _totals(db, start=start, end=end)
    rows = []
    for coa in coas:
        od, oc, _ = opening.get(coa.code, (0.0, 0.0, 0))
        pd_, pc, n = period.get(coa.code, (0.0, 0.0, 0))
        opening_bal = _signed(coa.normal_balance, od, oc)
        movement = _signed(coa.normal_balance, pd_, pc)
        rows.append({
            "code": coa.code, "name": coa.name, "category": coa.category,
            "normal_balance": coa.normal_balance, "opening_balance": opening_bal,
            "total_debit": pd_, "total_credit": pc, "movement": movement,
            "ending_balance": opening_bal + movement, "transaction_count": n,
        })
    return rows


def account_ledger(db: Session, code: str, start: str = "", end: str = "") -> Dict[str, Any]:
    """Buku besar satu akun: saldo awal, mutasi dengan saldo berjalan, saldo akhir."""
    coa = db.query(ChartOfAccount).filter(ChartOfAccount.code == code).first()
    if not coa:
        raise ValueError("Akun tidak ditemukan")
    od, oc, _ = _totals(db, before=start).get(code, (0.0, 0.0, 0)) if start else (0.0, 0.0, 0)
    opening = _signed(coa.normal_balance, od, oc)
    q = (db.query(JournalItem, JournalEntry).join(JournalEntry, JournalItem.journal_id == JournalEntry.id)
         .filter(JournalItem.account_code == code))
    if start:
        q = q.filter(JournalEntry.date >= start)
    if end:
        q = q.filter(JournalEntry.date <= end)
    rows, running = [], opening
    for item, entry in q.order_by(JournalEntry.date, JournalEntry.created_at, JournalItem.id).all():
        running += _signed(coa.normal_balance, item.debit, item.credit)
        rows.append({"date": entry.date, "entry_number": entry.entry_number,
                     "description": entry.description, "ref_type": entry.ref_type,
                     "debit": item.debit, "credit": item.credit, "balance": running})
    return {
        "code": coa.code, "name": coa.name, "category": coa.category,
        "normal_balance": coa.normal_balance, "opening": opening, "rows": rows,
        "total_debit": sum(r["debit"] for r in rows), "total_credit": sum(r["credit"] for r in rows),
        "ending": running,
    }


def trial_balance(db: Session, end: str = "") -> Dict[str, Any]:
    """Neraca saldo per tanggal `end`: saldo tiap akun di sisi debit atau kredit."""
    totals = _totals(db, end=end)
    rows = []
    for coa in db.query(ChartOfAccount).order_by(ChartOfAccount.code).all():
        d, c, n = totals.get(coa.code, (0.0, 0.0, 0))
        net = round(d - c, 2)
        rows.append({"code": coa.code, "name": coa.name, "category": coa.category,
                     "debit": net if net > 0 else 0.0, "credit": -net if net < 0 else 0.0,
                     "transaction_count": n})
    td, tc = sum(r["debit"] for r in rows), sum(r["credit"] for r in rows)
    return {"rows": rows, "total_debit": td, "total_credit": tc, "balanced": round(td, 2) == round(tc, 2)}


# ---------------------------------------------------------------- laporan
def calculate_income_statement(db: Session, start: str = "", end: str = "") -> Dict[str, Any]:
    """Laba rugi periode: pendapatan − HPP (akun 5xxx) = laba kotor − beban operasional."""
    ledger = calculate_general_ledger(db, start, end)
    pick = lambda rows: [dict(r, amount=r["movement"]) for r in rows]
    revenues = pick([a for a in ledger if a["category"] == "PENDAPATAN"])
    hpp = pick([a for a in ledger if a["category"] == "BEBAN" and a["code"].startswith("5")])
    operating = pick([a for a in ledger if a["category"] == "BEBAN" and not a["code"].startswith("5")])
    total_revenue = sum(r["amount"] for r in revenues)
    total_hpp = sum(r["amount"] for r in hpp)
    total_operating = sum(r["amount"] for r in operating)
    gross = total_revenue - total_hpp
    net = gross - total_operating
    return {
        "start": start, "end": end,
        "revenues": revenues, "total_revenue": total_revenue,
        "hpp": hpp, "total_hpp": total_hpp, "gross_profit": gross,
        "operating": operating, "total_operating": total_operating,
        "expenses": hpp + operating, "total_expense": total_hpp + total_operating,
        "net_income": net, "margin": (net / total_revenue * 100) if total_revenue else 0.0,
    }


def calculate_balance_sheet(db: Session, end: str = "") -> Dict[str, Any]:
    """Neraca per tanggal `end`. Laba berjalan = laba kumulatif sampai tanggal tsb."""
    ledger = calculate_general_ledger(db, "", end)
    income = calculate_income_statement(db, "", end)
    rows = lambda cat: [dict(a, amount=a["ending_balance"]) for a in ledger if a["category"] == cat]
    assets, liabilities, equities = rows("ASET"), rows("KEWAJIBAN"), rows("EKUITAS")
    total_assets = sum(a["amount"] for a in assets)
    total_liabilities = sum(a["amount"] for a in liabilities)
    total_equity = sum(a["amount"] for a in equities) + income["net_income"]
    return {
        "end": end, "assets": assets, "total_assets": total_assets,
        "liabilities": liabilities, "total_liabilities": total_liabilities,
        "equities": equities, "current_earnings": income["net_income"], "total_equity": total_equity,
        "is_balanced": round(total_assets, 2) == round(total_liabilities + total_equity, 2),
    }


def cash_flow(db: Session, start: str = "", end: str = "") -> Dict[str, Any]:
    """Arus kas berbasis jurnal pada akun kas/bank, dikelompokkan per jenis transaksi."""
    codes = [c.code for c in db.query(CashAccount).all()]
    if not codes:
        return {"opening": 0.0, "rows": [], "total_in": 0.0, "total_out": 0.0, "closing": 0.0, "per_account": []}
    opening = 0.0
    if start:
        for d, c, _ in (v for k, v in _totals(db, before=start).items() if k in codes):
            opening += d - c
    q = (db.query(JournalEntry.ref_type, func.coalesce(func.sum(JournalItem.debit), 0.0),
                  func.coalesce(func.sum(JournalItem.credit), 0.0))
         .join(JournalItem, JournalItem.journal_id == JournalEntry.id)
         .filter(JournalItem.account_code.in_(codes)))
    if start:
        q = q.filter(JournalEntry.date >= start)
    if end:
        q = q.filter(JournalEntry.date <= end)
    rows = [{"type": t, "cash_in": float(d), "cash_out": float(c), "net": float(d - c)}
            for t, d, c in q.group_by(JournalEntry.ref_type).order_by(JournalEntry.ref_type).all()]
    t_in, t_out = sum(r["cash_in"] for r in rows), sum(r["cash_out"] for r in rows)
    totals_end = _totals(db, end=end)
    per_account = []
    for acc in db.query(CashAccount).order_by(CashAccount.code).all():
        d, c, _ = totals_end.get(acc.code, (0.0, 0.0, 0))
        per_account.append({"code": acc.code, "name": acc.name, "journal_balance": d - c,
                            "recorded_balance": acc.balance})
    return {"opening": opening, "rows": rows, "total_in": t_in, "total_out": t_out,
            "closing": opening + t_in - t_out, "per_account": per_account}


# ---------------------------------------------------------------- dashboard
def monthly_series(db: Session, months: int = 6) -> List[Dict[str, Any]]:
    """Pendapatan, beban, dan laba per bulan untuk `months` bulan terakhir."""
    today = datetime.now()
    keys = []
    y, m = today.year, today.month
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    keys.reverse()
    month_expr = func.substr(JournalEntry.date, 1, 7)
    rows = (db.query(month_expr, ChartOfAccount.category, func.sum(JournalItem.debit), func.sum(JournalItem.credit))
            .select_from(JournalItem)
            .join(JournalEntry, JournalItem.journal_id == JournalEntry.id)
            .join(ChartOfAccount, JournalItem.account_code == ChartOfAccount.code)
            .filter(ChartOfAccount.category.in_(["PENDAPATAN", "BEBAN"]), month_expr.in_(keys))
            .group_by(month_expr, ChartOfAccount.category).all())
    data = {k: {"Bulan": k, "Pendapatan": 0.0, "Beban": 0.0} for k in keys}
    for month, cat, d, c in rows:
        if cat == "PENDAPATAN":
            data[month]["Pendapatan"] += float((c or 0) - (d or 0))
        else:
            data[month]["Beban"] += float((d or 0) - (c or 0))
    for v in data.values():
        v["Laba"] = v["Pendapatan"] - v["Beban"]
    return list(data.values())
