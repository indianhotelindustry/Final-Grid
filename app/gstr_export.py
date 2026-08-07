"""
GSTR-1 JSON Export — India Hotel PMS
=====================================
Generates the GSTR-1 JSON structure for direct upload to the GST portal.

Sections produced:
  - b2b   : B2B invoices (billing party has GSTIN via company on check-in record)
  - b2cs  : B2C Small invoices (consumer, no GSTIN)
  - cdnr  : Credit/debit notes referencing B2B invoices

References:
  - GSTR-1 JSON schema: https://developer.gst.gov.in
  - SAC codes per gst_service.py
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.models import (
    CreditNote, CheckInRecord, Company, Reservation, TaxLine, db,
)
from app import gst_service

TWO = Decimal('0.01')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q2(val) -> float:
    """Quantize a Decimal to 2 places and return as float for JSON."""
    return float(Decimal(str(val or 0)).quantize(TWO, rounding=ROUND_HALF_UP))


def _invoice_date_str(res: Reservation) -> str:
    """Return invoice date as DD-MM-YYYY string (GST portal format)."""
    dt = res.checked_out_at or res.created_at
    if dt:
        return dt.strftime('%d-%m-%Y')
    return ''


def _get_company_for_reservation(res: Reservation) -> Company | None:
    """
    Find the billing company (with GSTIN) for a reservation via CheckInRecord.
    Returns None if no company or company has no GSTIN (treat as B2C).
    """
    cir = CheckInRecord.query.filter_by(reservation_id=res.id).first()
    if cir and cir.company_id:
        company = Company.query.get(cir.company_id)
        if company and company.gstin and len(company.gstin.strip()) == 15:
            return company
    return None


def _aggregate_tax_lines(reservation_id: int) -> dict:
    """
    Aggregate TaxLine records for a reservation into a summary dict.
    Returns {taxable, cgst, sgst, igst, total_tax, rate (total GST%), is_interstate}.
    """
    tls = TaxLine.query.filter_by(reservation_id=reservation_id).all()
    if not tls:
        return None

    seen = set()
    taxable = Decimal('0')
    cgst = Decimal('0')
    sgst = Decimal('0')
    igst = Decimal('0')
    gst_rate = Decimal('0')
    interstate = False

    for tl in tls:
        key = (tl.charge_source_type, tl.charge_source_id)
        if key not in seen:
            taxable += Decimal(str(tl.taxable_amount))
            seen.add(key)
        if tl.tax_type == 'CGST':
            cgst += Decimal(str(tl.tax_amount))
            gst_rate = Decimal(str(tl.tax_rate)) * 2  # CGST rate * 2 = total GST rate
        elif tl.tax_type == 'SGST':
            sgst += Decimal(str(tl.tax_amount))
        elif tl.tax_type == 'IGST':
            igst += Decimal(str(tl.tax_amount))
            gst_rate = Decimal(str(tl.tax_rate))
            interstate = True

    total_tax = cgst + sgst + igst
    return {
        'taxable': taxable,
        'cgst': cgst,
        'sgst': sgst,
        'igst': igst,
        'total_tax': total_tax,
        'rate': gst_rate,
        'is_interstate': interstate,
    }


# ---------------------------------------------------------------------------
# Rate-wise breakdown for a single reservation
# ---------------------------------------------------------------------------

def _rate_wise_breakdown(reservation_id: int) -> list[dict]:
    """
    Break down a reservation's tax lines by GST rate.
    Returns a list of dicts: [{rate, taxable, cgst, sgst, igst, total_tax}].
    Needed because a single invoice may have charges at different GST rates
    (e.g. room at 12% and laundry at 18%).
    """
    tls = TaxLine.query.filter_by(reservation_id=reservation_id).all()
    if not tls:
        return []

    # Determine rate key per source
    source_rate: dict[tuple, Decimal] = {}
    for tl in tls:
        key = (tl.charge_source_type, tl.charge_source_id)
        if tl.tax_type == 'CGST':
            source_rate[key] = Decimal(str(tl.tax_rate)) * 2
        elif tl.tax_type == 'IGST':
            source_rate[key] = Decimal(str(tl.tax_rate))
        elif tl.tax_type == 'EXEMPT':
            source_rate[key] = Decimal('0')

    # Aggregate by rate
    buckets: dict[Decimal, dict] = defaultdict(lambda: {
        'taxable': Decimal('0'), 'cgst': Decimal('0'),
        'sgst': Decimal('0'), 'igst': Decimal('0'),
    })
    seen = set()
    for tl in tls:
        key = (tl.charge_source_type, tl.charge_source_id)
        rate = source_rate.get(key, Decimal('0'))
        if key not in seen:
            buckets[rate]['taxable'] += Decimal(str(tl.taxable_amount))
            seen.add(key)
        if tl.tax_type == 'CGST':
            buckets[rate]['cgst'] += Decimal(str(tl.tax_amount))
        elif tl.tax_type == 'SGST':
            buckets[rate]['sgst'] += Decimal(str(tl.tax_amount))
        elif tl.tax_type == 'IGST':
            buckets[rate]['igst'] += Decimal(str(tl.tax_amount))

    result = []
    for rate, b in sorted(buckets.items()):
        total_tax = b['cgst'] + b['sgst'] + b['igst']
        result.append({
            'rate': rate,
            'taxable': b['taxable'],
            'cgst': b['cgst'],
            'sgst': b['sgst'],
            'igst': b['igst'],
            'total_tax': total_tax,
        })
    return result


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def generate_gstr1_json(
    from_date: date,
    to_date: date,
    gstin: str,
    fp: str,
) -> dict:
    """
    Generate the GSTR-1 JSON structure for the given filing period.

    Args:
        from_date: Start of the period (inclusive).
        to_date:   End of the period (inclusive).
        gstin:     Hotel's GSTIN (15 chars).
        fp:        Filing period in MMYYYY format (e.g. '032026').

    Returns:
        A dict suitable for json.dumps() and upload to the GST portal.
    """
    from sqlalchemy import func

    # Fetch all checked-out reservations with invoices in the date range
    reservations = (
        Reservation.query
        .filter(
            Reservation.status == 'CheckedOut',
            Reservation.invoice_number.isnot(None),
            func.date(Reservation.checked_out_at) >= from_date,
            func.date(Reservation.checked_out_at) <= to_date,
        )
        .all()
    )

    hotel_state = gst_service.get_hotel_state_code()

    # ── B2B: group invoices by recipient GSTIN ───────────────────────────
    b2b_by_gstin: dict[str, list] = defaultdict(list)
    # ── B2CS: aggregate by rate + place of supply ────────────────────────
    b2cs_buckets: dict[tuple, dict] = defaultdict(lambda: {
        'taxable': Decimal('0'), 'cgst': Decimal('0'),
        'sgst': Decimal('0'), 'igst': Decimal('0'),
    })

    for res in reservations:
        company = _get_company_for_reservation(res)
        breakdown = _rate_wise_breakdown(res.id)
        if not breakdown:
            continue

        inv_date = _invoice_date_str(res)
        inv_no = res.invoice_number
        pos = res.billing_state_code or hotel_state

        if company:
            # B2B invoice
            items = []
            for b in breakdown:
                items.append({
                    'num': len(items) + 1,
                    'itm_det': {
                        'rt': _q2(b['rate']),
                        'txval': _q2(b['taxable']),
                        'camt': _q2(b['cgst']),
                        'samt': _q2(b['sgst']),
                        'iamt': _q2(b['igst']),
                        'csamt': 0,
                    }
                })

            b2b_by_gstin[company.gstin.strip()].append({
                'inum': inv_no,
                'idt': inv_date,
                'val': _q2(sum(b['taxable'] + b['total_tax'] for b in breakdown)),
                'pos': pos,
                'rchrg': 'N',
                'inv_typ': 'R',
                'itms': items,
            })
        else:
            # B2CS (consumer, no GSTIN)
            is_interstate = gst_service.is_interstate(res.billing_state_code)
            supply_type = 'INTER' if is_interstate else 'INTRA'
            for b in breakdown:
                key = (_q2(b['rate']), pos, supply_type)
                b2cs_buckets[key]['taxable'] += b['taxable']
                b2cs_buckets[key]['cgst'] += b['cgst']
                b2cs_buckets[key]['sgst'] += b['sgst']
                b2cs_buckets[key]['igst'] += b['igst']

    # Format B2B
    b2b = []
    for ctin, invoices in sorted(b2b_by_gstin.items()):
        b2b.append({
            'ctin': ctin,
            'inv': invoices,
        })

    # Format B2CS
    b2cs = []
    for (rate, pos, sply_ty), amounts in sorted(b2cs_buckets.items()):
        entry = {
            'sply_ty': sply_ty,
            'pos': pos,
            'rt': rate,
            'txval': _q2(amounts['taxable']),
            'camt': _q2(amounts['cgst']),
            'samt': _q2(amounts['sgst']),
            'iamt': _q2(amounts['igst']),
            'csamt': 0,
        }
        b2cs.append(entry)

    # ── CDNR: Credit notes referencing B2B invoices ──────────────────────
    credit_notes = (
        CreditNote.query
        .filter(
            CreditNote.issued_at >= from_date,
            CreditNote.issued_at <= to_date,
        )
        .all()
    )

    cdnr_by_gstin: dict[str, list] = defaultdict(list)
    for cn in credit_notes:
        res = Reservation.query.get(cn.reservation_id)
        if not res:
            continue
        company = _get_company_for_reservation(res)
        if not company:
            continue  # only B2B credit notes go in CDNR

        pos = res.billing_state_code or hotel_state
        is_interstate = gst_service.is_interstate(res.billing_state_code)

        # Determine the GST rate from the credit note amounts
        taxable = Decimal(str(cn.taxable_amount or 0))
        cgst = Decimal(str(cn.cgst_amount or 0))
        igst = Decimal(str(cn.igst_amount or 0))

        if taxable > 0:
            if is_interstate and igst > 0:
                rate = (igst / taxable * 100).quantize(TWO)
            elif cgst > 0:
                rate = (cgst / taxable * 200).quantize(TWO)  # CGST is half
            else:
                rate = Decimal('0')
        else:
            rate = Decimal('0')

        cn_date = cn.issued_at.strftime('%d-%m-%Y') if cn.issued_at else ''
        total = Decimal(str(cn.total_amount or 0))

        cdnr_by_gstin[company.gstin.strip()].append({
            'ntty': 'C',
            'nt_num': cn.credit_note_number,
            'nt_dt': cn_date,
            'val': _q2(total),
            'pos': pos,
            'rchrg': 'N',
            'inv_typ': 'R',
            'itms': [{
                'num': 1,
                'itm_det': {
                    'rt': _q2(rate),
                    'txval': _q2(taxable),
                    'camt': _q2(cn.cgst_amount or 0),
                    'samt': _q2(cn.sgst_amount or 0),
                    'iamt': _q2(cn.igst_amount or 0),
                    'csamt': 0,
                }
            }],
        })

    cdnr = []
    for ctin, notes in sorted(cdnr_by_gstin.items()):
        cdnr.append({
            'ctin': ctin,
            'nt': notes,
        })

    # ── Assemble final structure ─────────────────────────────────────────
    result = {
        'gstin': gstin,
        'fp': fp,
    }
    if b2b:
        result['b2b'] = b2b
    if b2cs:
        result['b2cs'] = b2cs
    if cdnr:
        result['cdnr'] = cdnr

    return result
