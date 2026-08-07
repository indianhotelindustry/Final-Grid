"""
GST E-Invoice & Export Service
================================
Provides:
  1. e-Invoice JSON generation per GSTN IRN schema (Schema v1.1)
     — Used for B2B invoices where buyer has a GSTIN
     — Returns a dict ready to POST to the IRP (Invoice Registration Portal)
     — Also downloadable as JSON from the billing UI

  2. GSTR-1 Excel export
     — B2C summary (HSN-wise) + B2B detail rows
     — Ready to upload to GST portal or share with CA

  3. GSTR-3B summary
     — Outward taxable supplies breakdown for the return period

All functions are pure (no DB writes). Caller passes data from gst_service.get_gst_report().
"""
from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# E-Invoice JSON builder (GSTN IRN Schema v1.1)
# ---------------------------------------------------------------------------

def build_einvoice_json(reservation, gst_summary, hotel_gstin: str,
                        hotel_name: str, hotel_address: str,
                        hotel_state_code: str) -> dict[str, Any]:
    """
    Build an IRN-ready e-invoice JSON dict for a single reservation.
    Only applicable when the guest/company has a GSTIN (B2B supply).
    For B2C (no buyer GSTIN) this JSON is still useful as a structured record.
    """
    from app.models import Settings
    from app.gst_service import get_hotel_gstin, get_hotel_state_code

    r = reservation
    guest = r.guest
    nights = (r.departure_date - r.arrival_date).days
    invoice_date = (r.checked_out_at or datetime.utcnow()).strftime('%d/%m/%Y')
    invoice_no = r.booking_reference or f'INV-{r.id}'

    # Buyer details
    buyer_gstin = ''
    buyer_name = guest.name if guest else 'Guest'
    buyer_addr = guest.address or '' if guest else ''
    buyer_state = r.billing_state_code or hotel_state_code

    # Try company GSTIN if billing is corporate
    if hasattr(r, 'checkin_record') and r.checkin_record and r.checkin_record.company_id:
        from app.models import Company
        from app.models import db
        company = db.session.get(Company, r.checkin_record.company_id)
        if company:
            buyer_gstin = company.gstin or ''
            buyer_name = company.name
            buyer_state = company.state_code or buyer_state

    # Build item list from tax lines
    items = []
    seen = set()
    item_no = 1
    for tl in gst_summary.lines:
        key = (tl.charge_source_type, tl.charge_source_id)
        if key in seen:
            continue
        seen.add(key)

        taxable = float(tl.taxable_amount)
        gst_rate = float(tl.tax_rate * 2) if tl.tax_type in ('CGST', 'SGST') else float(tl.tax_rate)
        cgst_amt = sgst_amt = igst_amt = 0.0

        for tl2 in gst_summary.lines:
            if (tl2.charge_source_type, tl2.charge_source_id) == key:
                if tl2.tax_type == 'CGST':
                    cgst_amt = float(tl2.tax_amount)
                elif tl2.tax_type == 'SGST':
                    sgst_amt = float(tl2.tax_amount)
                elif tl2.tax_type == 'IGST':
                    igst_amt = float(tl2.tax_amount)

        desc = 'Accommodation Charges' if tl.charge_source_type == 'room_night' else 'Other Hotel Services'
        items.append({
            'SlNo': str(item_no),
            'PrdDesc': desc,
            'IsServc': 'Y',
            'HsnCd': tl.sac_code or '996311',
            'Qty': 1.0,
            'Unit': 'OTH',
            'UnitPrice': round(taxable, 2),
            'TotAmt': round(taxable, 2),
            'Discount': 0,
            'AssAmt': round(taxable, 2),
            'GstRt': round(gst_rate, 2),
            'IgstAmt': round(igst_amt, 2),
            'CgstAmt': round(cgst_amt, 2),
            'SgstAmt': round(sgst_amt, 2),
            'CesRt': 0,
            'CesAmt': 0,
            'TotItemVal': round(taxable + cgst_amt + sgst_amt + igst_amt, 2),
        })
        item_no += 1

    total_taxable = float(gst_summary.taxable_amount)
    total_cgst = float(gst_summary.cgst)
    total_sgst = float(gst_summary.sgst)
    total_igst = float(gst_summary.igst)
    grand_total = float(gst_summary.grand_total)

    return {
        'Version': '1.1',
        'TranDtls': {
            'TaxSch': 'GST',
            'SupTyp': 'B2B' if buyer_gstin else 'B2C',
            'RegRev': 'N',
            'EcmGstin': None,
            'IgstOnIntra': 'N',
        },
        'DocDtls': {
            'Typ': 'INV',
            'No': invoice_no,
            'Dt': invoice_date,
        },
        'SellerDtls': {
            'Gstin': hotel_gstin,
            'LglNm': hotel_name,
            'TrdNm': hotel_name,
            'Addr1': hotel_address[:100] if hotel_address else '',
            'Loc': hotel_name,
            'Pin': 110001,
            'Stcd': hotel_state_code,
            'Ph': '',
            'Em': '',
        },
        'BuyerDtls': {
            'Gstin': buyer_gstin or 'URP',
            'LglNm': buyer_name,
            'TrdNm': buyer_name,
            'Pos': buyer_state or hotel_state_code,
            'Addr1': buyer_addr[:100] if buyer_addr else 'NA',
            'Loc': 'NA',
            'Pin': 999999,
            'Stcd': buyer_state or hotel_state_code,
            'Ph': guest.phone if guest else '',
            'Em': guest.email if guest else '',
        },
        'ItemList': items,
        'ValDtls': {
            'AssVal': round(total_taxable, 2),
            'CgstVal': round(total_cgst, 2),
            'SgstVal': round(total_sgst, 2),
            'IgstVal': round(total_igst, 2),
            'CesVal': 0,
            'Discount': 0,
            'OthChrg': 0,
            'RndOffAmt': 0,
            'TotInvVal': round(grand_total, 2),
        },
        'PayDtls': {
            'Nm': buyer_name,
            'Mode': 'Cash/UPI/Card',
        },
    }


# ---------------------------------------------------------------------------
# GSTR-1 Excel export
# ---------------------------------------------------------------------------

def build_gstr1_excel(gst_data: dict, hotel_gstin: str, hotel_name: str) -> io.BytesIO:
    """
    Build a GSTR-1 style Excel workbook.
    Sheets:
      1. Summary       — rate-wise taxable + tax totals
      2. B2C Detail    — all tax lines (HSN-wise)
      3. HSN Summary   — HSN-wise aggregated
    Returns a BytesIO buffer ready to send_file().
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError('openpyxl not installed. Run: pip install openpyxl')

    wb = openpyxl.Workbook()

    hdr_fill = PatternFill('solid', fgColor='1F4E79')
    hdr_font = Font(color='FFFFFF', bold=True)
    title_font = Font(bold=True, size=12)
    sub_font = Font(bold=True, size=10)
    center = Alignment(horizontal='center')
    right = Alignment(horizontal='right')

    def _style_header_row(ws, row_num, num_cols):
        for c in range(1, num_cols + 1):
            cell = ws.cell(row_num, c)
            cell.fill = hdr_fill
            cell.font = hdr_font
            cell.alignment = center

    def _autowidth(ws):
        for col in ws.columns:
            max_len = max((len(str(cell.value or '')) for cell in col), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 40)

    period = f"{gst_data['from_date'].strftime('%d %b %Y')} to {gst_data['to_date'].strftime('%d %b %Y')}"

    # ---- Sheet 1: Summary ----
    ws1 = wb.active
    ws1.title = 'GSTR-1 Summary'
    ws1.append([f'GSTR-1 Summary — {hotel_name}'])
    ws1.cell(1, 1).font = title_font
    ws1.append([f'GSTIN: {hotel_gstin}   |   Period: {period}'])
    ws1.append([f'Generated: {datetime.now().strftime("%d %b %Y %H:%M")}'])
    ws1.append([])

    # Totals block
    ws1.append(['Metric', 'Amount (₹)'])
    _style_header_row(ws1, ws1.max_row, 2)
    ws1.append(['Total Taxable Turnover', float(gst_data['total_taxable'])])
    ws1.append(['CGST Collected', float(gst_data['cgst_total'])])
    ws1.append(['SGST Collected', float(gst_data['sgst_total'])])
    ws1.append(['IGST Collected', float(gst_data['igst_total'])])
    ws1.append(['Total Tax Liability', float(gst_data['total_tax'])])
    ws1.append(['Grand Total (Taxable + Tax)', float(gst_data['grand_total'])])
    ws1.append([])

    # Rate-wise breakdown
    ws1.append(['GST Rate', 'Taxable (₹)', 'CGST (₹)', 'SGST (₹)', 'IGST (₹)', 'Total Tax (₹)'])
    _style_header_row(ws1, ws1.max_row, 6)
    for rate_key, g in gst_data.get('rate_groups', {}).items():
        ws1.append([
            rate_key,
            float(g['taxable']),
            float(g['cgst']),
            float(g['sgst']),
            float(g['igst']),
            float(g['cgst'] + g['sgst'] + g['igst']),
        ])
    _autowidth(ws1)

    # ---- Sheet 2: B2C Detail ----
    ws2 = wb.create_sheet('B2C Detail')
    ws2.append([f'B2C Tax Lines — {hotel_name} — {period}'])
    ws2.cell(1, 1).font = title_font
    ws2.append([])
    headers2 = ['Date', 'Reservation Ref', 'Charge Type', 'SAC Code',
                'Taxable (₹)', 'Tax Type', 'Rate %', 'Tax (₹)', 'Interstate']
    ws2.append(headers2)
    _style_header_row(ws2, ws2.max_row, len(headers2))

    for tl in gst_data.get('rows', []):
        ws2.append([
            tl.charge_date.strftime('%d/%m/%Y'),
            tl.reservation.booking_reference or f'RES-{tl.reservation_id}' if tl.reservation else str(tl.reservation_id),
            tl.charge_source_type.replace('_', ' ').title(),
            tl.sac_code or '',
            float(tl.taxable_amount),
            tl.tax_type,
            float(tl.tax_rate),
            float(tl.tax_amount),
            'Yes' if tl.is_interstate else 'No',
        ])
    _autowidth(ws2)

    # ---- Sheet 3: HSN Summary ----
    ws3 = wb.create_sheet('HSN Summary')
    ws3.append([f'HSN/SAC Summary — {hotel_name} — {period}'])
    ws3.cell(1, 1).font = title_font
    ws3.append([])
    headers3 = ['HSN/SAC', 'Description', 'Taxable (₹)', 'CGST (₹)', 'SGST (₹)', 'IGST (₹)', 'Total Tax (₹)']
    ws3.append(headers3)
    _style_header_row(ws3, ws3.max_row, len(headers3))

    hsn_groups: dict = {}
    seen_hsn: set = set()
    for tl in gst_data.get('rows', []):
        sac = tl.sac_code or '996319'
        key = (tl.reservation_id, tl.charge_source_type, tl.charge_source_id)
        if sac not in hsn_groups:
            hsn_groups[sac] = {'taxable': Decimal('0'), 'cgst': Decimal('0'),
                               'sgst': Decimal('0'), 'igst': Decimal('0')}
        if key not in seen_hsn:
            hsn_groups[sac]['taxable'] += Decimal(str(tl.taxable_amount))
            seen_hsn.add(key)
        if tl.tax_type == 'CGST':
            hsn_groups[sac]['cgst'] += Decimal(str(tl.tax_amount))
        elif tl.tax_type == 'SGST':
            hsn_groups[sac]['sgst'] += Decimal(str(tl.tax_amount))
        elif tl.tax_type == 'IGST':
            hsn_groups[sac]['igst'] += Decimal(str(tl.tax_amount))

    sac_desc = {
        '996311': 'Room Accommodation',
        '996331': 'Restaurant / F&B',
        '998523': 'Laundry Services',
        '998432': 'Telephone / Internet',
        '996319': 'Other Hotel Services',
    }
    for sac, g in sorted(hsn_groups.items()):
        total_tax = g['cgst'] + g['sgst'] + g['igst']
        ws3.append([
            sac,
            sac_desc.get(sac, 'Hotel Services'),
            float(g['taxable']),
            float(g['cgst']),
            float(g['sgst']),
            float(g['igst']),
            float(total_tax),
        ])
    _autowidth(ws3)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# GSTR-3B summary builder
# ---------------------------------------------------------------------------

def build_gstr3b_summary(gst_data: dict) -> dict:
    """
    Build a GSTR-3B style summary dict for the return period.
    Table 3.1 — Outward taxable supplies.
    """
    total_taxable = float(gst_data['total_taxable'])
    cgst = float(gst_data['cgst_total'])
    sgst = float(gst_data['sgst_total'])
    igst = float(gst_data['igst_total'])
    total_tax = float(gst_data['total_tax'])

    # Nil-rated / exempt (tax_type == EXEMPT)
    nil_taxable = sum(
        float(tl.taxable_amount)
        for tl in gst_data.get('rows', [])
        if tl.tax_type == 'EXEMPT'
    )

    return {
        'period': f"{gst_data['from_date'].strftime('%b %Y')}",
        'from_date': gst_data['from_date'],
        'to_date': gst_data['to_date'],
        'table_3_1': {
            'a_outward_taxable': {
                'taxable': round(total_taxable - nil_taxable, 2),
                'igst': round(igst, 2),
                'cgst': round(cgst, 2),
                'sgst': round(sgst, 2),
                'cess': 0.0,
            },
            'b_outward_taxable_zero_rated': {
                'taxable': 0.0, 'igst': 0.0, 'cess': 0.0,
            },
            'd_inward_reverse_charge': {
                'taxable': 0.0, 'igst': 0.0, 'cgst': 0.0, 'sgst': 0.0, 'cess': 0.0,
            },
            'e_nil_exempt': {
                'taxable': round(nil_taxable, 2),
            },
        },
        'table_3_2_interstate': round(igst, 2),
        'total_tax_liability': round(total_tax, 2),
        'grand_total': round(float(gst_data['grand_total']), 2),
    }
