"""
Audit Explanation Service
=========================
Translates raw night-audit report data into plain-language, actionable
explanations written for hotel cashiers, front-office executives, and
accountants — not developers.

Usage:
    from app.audit_explanation_service import AuditExplanationService
    explanation = AuditExplanationService.explain(report)   # report = full_report()
"""

from __future__ import annotations
from datetime import datetime as _dt


# ── Time helper ───────────────────────────────────────────────────────────────

def _time_since(dt) -> str:
    """Return a human-readable 'X hours ago' string from a datetime."""
    try:
        if dt is None:
            return ''
        delta = _dt.utcnow() - dt
        total_secs = int(delta.total_seconds())
        if total_secs < 0:
            return ''
        if total_secs < 3600:
            mins = total_secs // 60
            return f'{mins}m ago' if mins > 0 else 'just now'
        hours = total_secs // 3600
        if hours < 24:
            return f'{hours}h ago'
        days = hours // 24
        return f'{days}d ago'
    except Exception:
        return ''


# ── Severity helpers ──────────────────────────────────────────────────────────

_SEV_ORDER  = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
_SEV_BADGE  = {
    'critical': 'bg-danger',
    'high':     'bg-warning text-dark',
    'medium':   'bg-info text-dark',
    'low':      'bg-secondary',
}
_SEV_BORDER = {
    'critical': 'border-danger',
    'high':     'border-warning',
    'medium':   'border-info',
    'low':      'border-secondary',
}
_SEV_ICON   = {
    'critical': 'bi-x-octagon-fill',
    'high':     'bi-exclamation-triangle-fill',
    'medium':   'bi-exclamation-circle',
    'low':      'bi-info-circle',
}


def _f(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _safe_name(obj) -> str:
    if obj is None:
        return '—'
    if hasattr(obj, 'name'):
        return obj.name or '—'
    return str(obj)


def _normalize_record(item, amount_key: str = 'balance', extra: str = '') -> dict:
    """
    Turn a folio/reservation dict (or Reservation object) into a flat display
    record for the affected-records table.
    """
    res = None
    amount = 0.0

    if isinstance(item, dict):
        res = item.get('reservation')
        amount = _f(item.get(amount_key, item.get('balance', 0)))
    else:
        res = item   # Reservation object directly

    if res is None:
        return {}

    try:
        ref   = getattr(res, 'booking_reference', None) or f'#{res.id}'
        guest = _safe_name(getattr(res, 'guest', None))
        room  = getattr(getattr(res, 'room', None), 'room_number', '—')
        res_id = getattr(res, 'id', None)
    except Exception:
        return {}

    return {
        'id':     res_id,
        'ref':    ref,
        'guest':  guest,
        'room':   room,
        'amount': amount,
        'extra':  extra,
    }


def _card(
    issue_code:         str,
    title:              str,
    severity:           str,
    plain_meaning:      str,
    hindi_hint:         str,
    how_it_is_wrong:    str,
    likely_root_causes: list,
    business_risk:      str,
    what_to_do_steps:   list,
    responsible_roles:  list,
    affected_records:   list,
    resolution_actions: list,
    amount:             float = 0.0,
    count:              int   = 0,
    evidence_lines:     list  = None,
    fix_impact_text:    str   = '',
    attribution_lines:  list  = None,
    repeat_alerts:      list  = None,
) -> dict:
    return {
        'issue_code':         issue_code,
        'title':              title,
        'severity':           severity,
        'severity_badge_cls': _SEV_BADGE[severity],
        'severity_border_cls':_SEV_BORDER[severity],
        'severity_icon':      _SEV_ICON[severity],
        'plain_meaning':      plain_meaning,
        'hindi_hint':         hindi_hint,
        'how_it_is_wrong':    how_it_is_wrong,
        'likely_root_causes': likely_root_causes,
        'business_risk':      business_risk,
        'what_to_do_steps':   what_to_do_steps,
        'responsible_roles':  responsible_roles,
        'affected_records':   [r for r in affected_records if r],
        'resolution_actions': resolution_actions,
        'evidence_lines':     evidence_lines or [],
        'fix_impact_text':    fix_impact_text,
        'attribution_lines':  attribution_lines or [],
        'repeat_alerts':      repeat_alerts or [],
        'explain_label':      'What is this?',
        'fix_now_label':      'Fix Now',
        'amount':             amount,
        'count':              count,
    }


# ── Individual issue factories ────────────────────────────────────────────────

def _explain_recon_diff(control: dict, folio: dict, revenue: dict) -> dict | None:
    recon_diff = _f(control.get('reconciliation_difference', 0))
    recon_abs  = abs(recon_diff)
    if recon_abs < 1.0:
        return None

    direction = 'shortfall' if recon_diff < 0 else 'surplus'
    dir_txt   = (
        f'₹{recon_abs:,.2f} less was collected than expected'
        if recon_diff < 0
        else f'₹{recon_abs:,.2f} more was collected than expected'
    )

    # ── Root cause inference ──
    causes = []
    neg_folios = folio.get('negative_folios', [])
    co_list    = folio.get('checkout_outstanding_list', [])
    disc_list  = revenue.get('discount_list', [])
    unauth_disc = [d for d in disc_list
                   if not d.get('authorized_by') or d.get('authorized_by') == '—']

    if neg_folios:
        causes.append(
            f'{len(neg_folios)} folio(s) show an overpayment — '
            'a duplicate payment or post-checkout discount may have been applied.'
        )
    if co_list:
        causes.append(
            f'{len(co_list)} checkout folio(s) have an unpaid balance — '
            'the payment may not have been posted before checkout.'
        )
    if unauth_disc:
        causes.append(
            f'{len(unauth_disc)} unapproved discount(s) reduced the billed amount '
            'without a matching payment adjustment.'
        )
    if not causes:
        causes.append(
            'A payment entry may be missing, duplicated, or posted to the wrong folio.'
        )
        causes.append(
            'A manual adjustment may have changed the revenue figure without a matching payment.'
        )

    # Evidence: summary fact lines
    _accrual_net = _f(control.get('total_posted_revenue', 0))
    _collected   = _f(control.get('total_collected', 0))
    evidence = [
        f'Accrual Net Revenue:    ₹{_accrual_net:,.2f}',
        f'Cash Collected:         ₹{_collected:,.2f}',
        f'Unexplained gap:        ₹{recon_abs:,.2f} ({direction})',
    ]

    return _card(
        issue_code='RECON_DIFF',
        title='Reconciliation Difference Found',
        severity='critical',
        plain_meaning=(
            f"Today's revenue and collected payments do not match. "
            f"{dir_txt.capitalize()}."
        ),
        hindi_hint=f'आज का हिसाब पूरा नहीं मिला — ₹{recon_abs:,.0f} का अंतर है।',
        how_it_is_wrong=(
            'A clean audit means: Net Revenue = Collected + Outstanding. '
            f'Right now there is a {direction} of ₹{recon_abs:,.2f} that is unexplained.'
        ),
        likely_root_causes=causes,
        business_risk=(
            'The business day cannot be certified as financially clean. '
            'Any difference, even ₹1, must be explained before closing the audit.'
        ),
        what_to_do_steps=[
            'Open the Folio Control tab and look for any folio with an unexpected balance.',
            'Check the Payment Summary for payments posted to the wrong folio.',
            'Review the Revenue Summary for any discount or charge that looks unusual.',
            'Correct the folio or payment, then re-run the audit.',
            'If the difference is small (< ₹10) and caused by rounding, document the reason and complete with an override.',
        ],
        responsible_roles=['Accountant', 'Manager'],
        affected_records=[],
        resolution_actions=[
            {'label': 'View Folio Control', 'tab': 'folio'},
            {'label': 'View Payments',      'tab': 'payments'},
        ],
        amount=recon_abs,
        count=1,
        evidence_lines=evidence,
        fix_impact_text=f'Resolving this will make today\'s books balance — ₹{recon_abs:,.2f} difference will clear.',
    )


def _explain_overpayments(folio: dict) -> dict | None:
    neg_folios = folio.get('negative_folios', [])
    if not neg_folios:
        return None

    total_overpay = sum(_f(f.get('balance', 0)) for f in neg_folios)
    records = [_normalize_record(f, amount_key='balance', extra='Overpaid') for f in neg_folios]

    evidence = [
        f'Folio {r["ref"]} (Room {r["room"]}): ₹{abs(r["amount"]):,.2f} overpaid'
        for r in records[:3] if r
    ]

    repeat_alerts = []
    if len(neg_folios) >= 3:
        repeat_alerts.append(
            f'{len(neg_folios)} overpayments in one audit period — check for a systemic billing issue.'
        )

    return _card(
        issue_code='OVERPAY',
        title='Guest Overpayment Not Resolved',
        severity='high',
        plain_meaning=(
            f'{len(neg_folios)} guest(s) have paid more than their total bill. '
            f'₹{abs(total_overpay):,.2f} is sitting as excess in the system.'
        ),
        hindi_hint='कुछ अतिथियों ने ज़रूरत से अधिक भुगतान किया है — धनवापसी बकाया है।',
        how_it_is_wrong=(
            'Every folio should reach zero balance at checkout. '
            'A negative balance means more was collected than the bill — '
            'this money either needs to be refunded or the folio needs to be corrected.'
        ),
        likely_root_causes=[
            'A payment was posted twice on the same folio.',
            'A discount or charge was removed after payment was already collected.',
            'A wrong folio received a payment that belonged to another reservation.',
            'A credit note or advance was applied without adjusting the folio total.',
        ],
        business_risk=(
            'Overpayments are a liability. If the guest has already left, '
            'this becomes a refund obligation. Leaving it unresolved will cause '
            'the next audit to fail as well.'
        ),
        what_to_do_steps=[
            'Open each affected folio (listed below).',
            'Check if a payment was posted twice — reverse the duplicate if found.',
            'If a discount was given after payment, either refund the guest or apply the credit correctly.',
            'If the guest has already checked out, initiate a refund and record it.',
            'Confirm each folio balance reaches zero, then re-run the audit.',
        ],
        responsible_roles=['Front Desk', 'Accountant'],
        affected_records=records,
        resolution_actions=[
            {'label': 'View Folio Control', 'tab': 'folio'},
        ],
        amount=abs(total_overpay),
        count=len(neg_folios),
        evidence_lines=evidence,
        fix_impact_text=f'Resolving ₹{abs(total_overpay):,.2f} in overpayments will remove {len(neg_folios)} folio(s) from the liability list.',
        repeat_alerts=repeat_alerts,
    )


def _explain_unsettled_checkouts(folio: dict) -> dict | None:
    co_list = folio.get('checkout_outstanding_list', [])
    co_total = _f(folio.get('checkout_outstanding_total', 0))
    if not co_list or co_total < 0.01:
        return None

    records = [_normalize_record(f, amount_key='balance', extra='Due after checkout') for f in co_list]

    evidence = []
    for item, rec in zip(co_list[:3], records[:3]):
        if not rec:
            continue
        res = item.get('reservation') if isinstance(item, dict) else item
        time_note = ''
        if res is not None:
            coa = getattr(res, 'checked_out_at', None)
            t = _time_since(coa)
            if t:
                time_note = f' — checked out {t}'
        evidence.append(
            f'Folio {rec["ref"]} (Room {rec["room"]}): ₹{rec["amount"]:,.2f} due after checkout{time_note}'
        )

    repeat_alerts = []
    if len(co_list) >= 3:
        repeat_alerts.append(
            f'{len(co_list)} unsettled checkouts in one period — review checkout payment process.'
        )

    return _card(
        issue_code='UNSETTLED_CHECKOUT',
        title='Checked-Out Guest Has Unpaid Balance',
        severity='critical',
        plain_meaning=(
            f'{len(co_list)} guest(s) have checked out but their bill is not fully paid. '
            f'₹{co_total:,.2f} is outstanding.'
        ),
        hindi_hint=f'चेकआउट के बाद भी ₹{co_total:,.0f} का बिल बकाया है।',
        how_it_is_wrong=(
            'Once a guest checks out, their folio must be fully settled. '
            'An outstanding balance after checkout means revenue is potentially lost — '
            'the guest has left and collection becomes very difficult.'
        ),
        likely_root_causes=[
            'The checkout was completed without collecting final payment.',
            'A payment was posted to the wrong folio — another guest\'s account received it.',
            'A credit card authorization was not captured before checkout.',
            'A corporate account booking was checked out without posting the company invoice.',
            'A late charge (e.g., minibar, room service) was added after checkout.',
        ],
        business_risk=(
            'This is actual lost or at-risk revenue. Guests who have already left '
            'are very difficult to follow up with. Any amount unpaid beyond today '
            'becomes a bad debt risk.'
        ),
        what_to_do_steps=[
            'Contact the guest immediately by phone or email.',
            'Check if a payment was attempted but failed (declined card, wrong folio).',
            'Verify if this is a corporate or OTA booking with a pending invoice — follow up with the account.',
            'If the folio was closed by mistake, request a Manager to reopen it, post the payment, and reclose.',
            'Document the recovery action in the folio notes.',
        ],
        responsible_roles=['Front Desk', 'Accountant', 'Manager'],
        affected_records=records,
        resolution_actions=[
            {'label': 'View Folio Control', 'tab': 'folio'},
        ],
        amount=co_total,
        count=len(co_list),
        evidence_lines=evidence,
        fix_impact_text=f'Collecting ₹{co_total:,.2f} will fully recover this outstanding revenue before it becomes a bad debt.',
        repeat_alerts=repeat_alerts,
    )


def _explain_unauth_discounts(revenue: dict) -> dict | None:
    disc_list = revenue.get('discount_list', [])
    unauth = [
        d for d in disc_list
        if not d.get('authorized_by') or str(d.get('authorized_by', '')).strip() in ('', '—')
    ]
    if not unauth:
        return None

    total_unauth = sum(_f(d.get('discount', 0)) for d in unauth)
    records = []
    for d in unauth:
        r = _normalize_record(
            d,
            amount_key='discount',
            extra=f'Given by: {d.get("given_by","—")} | Reason: {d.get("reason","—")}',
        )
        records.append(r)

    evidence = []
    for d in unauth[:3]:
        ref = d.get('booking_reference') or f'Res #{d.get("reservation_id","?")}'
        amt = _f(d.get('discount', 0))
        by  = d.get('given_by', '—')
        evidence.append(f'{ref}: ₹{amt:,.0f} discount by {by} — no authorization')

    # Attribution: group by who gave the discount
    _by_counts: dict = {}
    for d in unauth:
        by = str(d.get('given_by', '—')).strip() or '—'
        _by_counts[by] = _by_counts.get(by, 0) + 1
    attribution_lines = []
    for by, cnt in _by_counts.items():
        amt_sum = sum(_f(d.get('discount', 0)) for d in unauth if str(d.get('given_by','—')).strip() == by)
        attribution_lines.append(
            f'{"Discount" if cnt == 1 else f"{cnt} discounts"} by: {by} — ₹{amt_sum:,.0f} total, no manager approval'
        )

    # Repeat alerts: same person 2+ discounts
    repeat_alerts = []
    for by, cnt in _by_counts.items():
        if cnt >= 2:
            repeat_alerts.append(
                f'Repeat pattern: {by} applied {cnt} unauthorized discounts today'
            )
    if len(unauth) >= 3 and len(_by_counts) == 1:
        only_by = list(_by_counts.keys())[0]
        repeat_alerts = [f'All {len(unauth)} unauthorized discounts were given by the same person ({only_by}) — escalate to management']

    return _card(
        issue_code='UNAUTH_DISCOUNT',
        title='Discounts Given Without Manager Authorization',
        severity='high',
        plain_meaning=(
            f'{len(unauth)} reservation(s) received a price reduction '
            f'totalling ₹{total_unauth:,.2f} with no manager approval on record.'
        ),
        hindi_hint='बिना अनुमति के छूट दी गई है — कृपया मैनेजर की स्वीकृति लें।',
        how_it_is_wrong=(
            'The hotel\'s policy requires every discount to be approved by a Manager or above. '
            'Discounts without an authorization record cannot be audited and are a revenue risk.'
        ),
        likely_root_causes=[
            'A front-desk agent manually changed the rate during check-in without requesting approval.',
            'A group or corporate rate was applied informally without entering the authorization in the system.',
            'The manager gave verbal approval but it was not recorded.',
            'A complimentary upgrade was given without following the approval workflow.',
        ],
        business_risk=(
            'Unapproved discounts reduce revenue and cannot be justified in an audit. '
            'Repeated patterns may indicate unauthorized tariff manipulation — a fraud risk.'
        ),
        what_to_do_steps=[
            'Review each discounted reservation in the list below.',
            'If the discount was genuinely approved, have a Manager log into the system and add their authorization now.',
            'If the discount should not have been given, reverse it and re-bill the guest.',
            'Remind all front-desk staff of the discount authorization policy.',
        ],
        responsible_roles=['Manager', 'Accountant'],
        affected_records=records,
        resolution_actions=[
            {'label': 'View Revenue Summary', 'tab': 'revenue'},
        ],
        amount=total_unauth,
        count=len(unauth),
        evidence_lines=evidence,
        fix_impact_text=f'Authorizing or reversing ₹{total_unauth:,.2f} in discounts will clear this audit flag and restore the revenue record.',
        attribution_lines=attribution_lines,
        repeat_alerts=repeat_alerts,
    )


def _explain_rate_leakage(revenue: dict) -> dict | None:
    leakage_total = _f(revenue.get('leakage_total', 0))
    leakage_list  = revenue.get('leakage_list', [])
    if leakage_total < 1.0 or not leakage_list:
        return None

    records = []
    for item in leakage_list:
        res = item.get('reservation') if isinstance(item, dict) else item
        r = _normalize_record(item, amount_key='amount', extra=(
            f'Standard: ₹{_f(item.get("standard_tariff",0)):,.0f} '
            f'→ Charged: ₹{_f(item.get("actual_rate",0)):,.0f} '
            f'(by {item.get("user","—")})'
            if isinstance(item, dict) else ''
        ))
        records.append(r)

    sev = 'high' if leakage_total > 5000 else 'medium'

    evidence = []
    for item in leakage_list[:3]:
        if isinstance(item, dict):
            std  = _f(item.get('standard_tariff', 0))
            act  = _f(item.get('actual_rate', 0))
            ref  = item.get('booking_reference') or f'Res #{item.get("reservation_id","?")}'
            usr  = item.get('user', '')
            by_str = f' by {usr}' if usr and usr != '—' else ''
            evidence.append(f'{ref}: Standard ₹{std:,.0f} → Charged ₹{act:,.0f} (gap ₹{std-act:,.0f}){by_str}')

    # Attribution: group by user who overrode the rate
    _user_counts: dict = {}
    for item in leakage_list:
        if isinstance(item, dict):
            usr = str(item.get('user', '—')).strip() or '—'
            _user_counts[usr] = _user_counts.get(usr, 0) + 1
    attribution_lines = []
    for usr, cnt in _user_counts.items():
        if usr != '—':
            attribution_lines.append(f'Rate override{"s" if cnt > 1 else ""} by: {usr} ({cnt} room{"s" if cnt > 1 else ""})')

    # Repeat alerts
    repeat_alerts = []
    for usr, cnt in _user_counts.items():
        if cnt >= 2 and usr != '—':
            repeat_alerts.append(
                f'Repeat pattern: {usr} made {cnt} below-tariff rate overrides today — review authorization'
            )

    return _card(
        issue_code='RATE_LEAKAGE',
        title='Rooms Billed Below Standard Tariff',
        severity=sev,
        plain_meaning=(
            f'{len(leakage_list)} room(s) were charged below the hotel\'s standard rate today. '
            f'Total revenue shortfall: ₹{leakage_total:,.2f}.'
        ),
        hindi_hint=f'कुछ कमरों में मानक दर से कम शुल्क लिया गया — ₹{leakage_total:,.0f} का नुकसान।',
        how_it_is_wrong=(
            'When the actual billed rate is below the published standard tariff and '
            'no discount authorization or promotional rate plan is recorded, '
            'it is treated as unexplained revenue leakage.'
        ),
        likely_root_causes=[
            'A rate override was applied at check-in without a recorded reason or approval.',
            'A walk-in guest was given a negotiated price below the rack rate.',
            'An OTA booking arrived with a lower rate that was not mapped to the correct rate plan.',
            'A seasonal or promotional rate was applied manually instead of through the system rate plan.',
        ],
        business_risk=(
            'Each affected room represents lost revenue per night. '
            'Across multiple rooms and nights, unexplained rate variances '
            'significantly erode RevPAR and cannot be explained to ownership or auditors.'
        ),
        what_to_do_steps=[
            'Review each room in the list below.',
            'Confirm whether the lower rate was intentionally given (promotional, loyalty, group).',
            'If intentional, add a discount reason and authorization entry to the folio.',
            'If accidental, correct the folio rate — contact the guest if the bill has already been shared.',
            'Review whether rate plan assignments need to be corrected in the reservation.',
        ],
        responsible_roles=['Revenue Manager', 'Front Desk', 'Manager'],
        affected_records=records,
        resolution_actions=[
            {'label': 'View Revenue Summary', 'tab': 'revenue'},
        ],
        amount=leakage_total,
        count=len(leakage_list),
        evidence_lines=evidence,
        fix_impact_text=f'Documenting or correcting these rates will account for ₹{leakage_total:,.2f} in revenue variance and clear this flag.',
        attribution_lines=attribution_lines,
        repeat_alerts=repeat_alerts,
    )


def _explain_missing_charges(room_charges: dict) -> dict | None:
    missing_count = int(room_charges.get('missing_count', 0))
    missing_rents = room_charges.get('missing_rent', [])
    if missing_count == 0 or not missing_rents:
        return None

    records = [_normalize_record(r, extra='No charge posted tonight') for r in missing_rents]

    evidence = [
        f'Room {r["room"]} ({r["ref"]}): no charge posted tonight'
        for r in records[:3] if r
    ]

    repeat_alerts = []
    if missing_count >= 3:
        repeat_alerts.append(
            f'{missing_count} rooms missing charges — possible system interruption during charge posting.'
        )

    return _card(
        issue_code='MISSING_CHARGES',
        title='Night Room Charge Not Posted for Occupied Room',
        severity='critical',
        plain_meaning=(
            f'{missing_count} occupied room(s) have no room charge posted for tonight. '
            'These rooms are occupied but tonight\'s revenue was not recorded.'
        ),
        hindi_hint='कुछ कमरों का आज की रात का शुल्क दर्ज नहीं हुआ — राजस्व दर्ज करें।',
        how_it_is_wrong=(
            'Every occupied room must have a room charge posted each night during the night audit. '
            'Missing charges mean tonight\'s room revenue was never recorded — '
            'it will not appear in the daily revenue report.'
        ),
        likely_root_causes=[
            'The night audit charge-posting process was interrupted or skipped for these rooms.',
            'The reservation has no rate assigned — the system had nothing to post.',
            'The room was manually marked as complimentary without being flagged correctly.',
            'A system error interrupted the automatic charge posting.',
        ],
        business_risk=(
            'Direct revenue loss for tonight. If the guest checks out tomorrow '
            'without this being corrected, the hotel loses an entire night\'s room revenue '
            'with no way to recover it.'
        ),
        what_to_do_steps=[
            'Identify each affected room from the list below.',
            'Open the folio for each affected reservation.',
            'Manually post the room charge at the correct rate.',
            'Verify the posted amount matches the agreed rate for the room.',
            'Re-run the audit to confirm all rooms now have charges.',
        ],
        responsible_roles=['Front Desk', 'Night Auditor'],
        affected_records=records,
        resolution_actions=[
            {'label': 'View Room Charges', 'tab': 'charges'},
        ],
        amount=0.0,
        count=missing_count,
        evidence_lines=evidence,
        fix_impact_text=f'Posting {missing_count} room charge(s) will add tonight\'s room revenue to the daily report and clear this blocker.',
        repeat_alerts=repeat_alerts,
    )


def _explain_cash_mismatch(shifts: dict) -> dict | None:
    total_variance = abs(_f(shifts.get('total_variance', 0)))
    shift_list     = shifts.get('shifts', [])
    if total_variance < 1.0:
        return None

    flagged = [s for s in shift_list if s.get('variance_flag') or abs(_f(s.get('variance', 0))) > 0.01]
    sev     = 'high' if total_variance > 500 else 'medium'

    records = []
    for s in flagged:
        variance = _f(s.get('variance', 0))
        records.append({
            'id':     None,
            'ref':    s.get('user_name', '—'),
            'guest':  s.get('shift_type', '—'),
            'room':   s.get('status', '—'),
            'amount': abs(variance),
            'extra':  f'Expected ₹{_f(s.get("expected_cash",0)):,.0f} | Declared ₹{_f(s.get("declared_cash",0)):,.0f}',
        })

    evidence = []
    for s in flagged[:3]:
        name = s.get('user_name', '—')
        exp  = _f(s.get('expected_cash', 0))
        dec  = _f(s.get('declared_cash', 0))
        var  = abs(_f(s.get('variance', 0)))
        evidence.append(f'Shift ({name}): Expected ₹{exp:,.0f} | Declared ₹{dec:,.0f} | Gap ₹{var:,.0f}')

    attribution_lines = [
        f'Shift: {s.get("user_name","—")} — cash variance ₹{abs(_f(s.get("variance",0))):,.0f}'
        for s in flagged[:5]
    ]
    repeat_alerts = []
    if len(flagged) >= 2:
        repeat_alerts.append(f'{len(flagged)} shifts have cash variances — check all drawers independently.')

    return _card(
        issue_code='CASH_MISMATCH',
        title='Cash Count Does Not Match System Records',
        severity=sev,
        plain_meaning=(
            f'The physical cash counted at shift close is ₹{total_variance:,.2f} '
            'different from what the system expected based on transactions.'
        ),
        hindi_hint=f'शिफ्ट बंद होने पर नकदी में ₹{total_variance:,.0f} का फ़र्क़ है।',
        how_it_is_wrong=(
            'At shift close, the cash in the drawer should equal: '
            'Opening Cash + All cash receipts − All cash payments. '
            f'Right now, ₹{total_variance:,.2f} cannot be accounted for.'
        ),
        likely_root_causes=[
            'A cash payment was received but not entered in the system.',
            'Change was given incorrectly to a guest.',
            'A cash refund was given but not recorded as an outgoing transaction.',
            'A receipt was not issued and the transaction was not logged.',
            'A manual adjustment was made to the shift without corresponding cash movement.',
        ],
        business_risk=(
            'Cash variances are both a revenue risk and an integrity concern. '
            'Large or repeated variances may indicate theft or unrecorded transactions.'
        ),
        what_to_do_steps=[
            'Ask the shift staff to recount the cash carefully.',
            'Review the transaction log for the shift — check for any unrecorded cash payments or refunds.',
            'Cross-check receipts against system entries for the shift period.',
            'If a discrepancy remains, document it with the reason and have a Manager sign off.',
            'Repeated variance from the same staff member should be escalated.',
        ],
        responsible_roles=['Night Auditor', 'Manager', 'Accountant'],
        affected_records=records,
        resolution_actions=[
            {'label': 'View Shift Summary', 'tab': 'shifts'},
        ],
        amount=total_variance,
        count=len(flagged),
        evidence_lines=evidence,
        fix_impact_text=f'Reconciling the shift will account for ₹{total_variance:,.2f} in unverified cash and clear the variance flag.',
        attribution_lines=attribution_lines,
        repeat_alerts=repeat_alerts,
    )


def _explain_open_blockers(exceptions: dict) -> dict | None:
    blockers    = exceptions.get('blockers', [])
    blk_count   = int(exceptions.get('blocker_count', 0))
    if blk_count == 0 or not blockers:
        return None

    records = []
    for b in blockers:
        records.append({
            'id':     b.get('reservation_id'),
            'ref':    b.get('type', '—'),
            'guest':  '',
            'room':   '',
            'amount': 0.0,
            'extra':  b.get('detail', ''),
        })

    evidence = [
        f'Blocker: {b.get("type","—")} — {b.get("detail","")}'
        for b in blockers[:3]
    ]

    return _card(
        issue_code='OPEN_BLOCKERS',
        title='System Blockers Preventing Audit Closure',
        severity='critical',
        plain_meaning=(
            f'{blk_count} system-level issue(s) have been flagged that must be '
            'resolved before the night audit can be officially closed.'
        ),
        hindi_hint='ऑडिट बंद करने से पहले कुछ ज़रूरी समस्याएं हल करनी होंगी।',
        how_it_is_wrong=(
            'Blockers are hard stops identified by the audit system. '
            'Unlike warnings, blockers indicate a condition that makes the audit result '
            'unreliable or incomplete. The business day cannot be certified with blockers open.'
        ),
        likely_root_causes=[
            'See the individual blocker descriptions below — each one has a specific cause.',
            'Common causes include: no-shows not posted, reservations in an invalid state, '
            'missing mandatory data.',
        ],
        business_risk=(
            'With blockers open, the business date remains in a pending state. '
            'This affects daily revenue reporting, the next day\'s opening, '
            'and any management reports generated for this date.'
        ),
        what_to_do_steps=[
            'Read each blocker description carefully in the list below.',
            'Handle each one in the order shown (most critical first).',
            'After resolving each blocker, re-run the audit check to confirm it clears.',
            'Once all blockers are resolved, complete the audit.',
        ],
        responsible_roles=['Front Desk', 'Night Auditor', 'Manager'],
        affected_records=records,
        resolution_actions=[
            {'label': 'View Exceptions', 'tab': 'exceptions'},
        ],
        amount=0.0,
        count=blk_count,
        evidence_lines=evidence,
        fix_impact_text=f'Clearing {blk_count} blocker(s) will unblock the audit and allow the business day to be officially closed.',
    )


# ── Plain summary sentence builder ───────────────────────────────────────────

def _build_plain_summary(cards: list, readiness: str) -> str:
    if not cards:
        return (
            'Night Audit is clean — all checks passed. '
            'The business day is ready to be closed.'
        )

    critical = [c for c in cards if c['severity'] == 'critical']
    high     = [c for c in cards if c['severity'] == 'high']
    medium   = [c for c in cards if c['severity'] == 'medium']

    parts = []
    for c in critical + high + medium:
        code = c['issue_code']
        amt  = c['amount']
        cnt  = c['count']

        if code == 'RECON_DIFF':
            parts.append(f'₹{amt:,.0f} remains unreconciled')
        elif code == 'OVERPAY':
            parts.append(f'{cnt} folio(s) have an overpayment (₹{amt:,.0f} total)')
        elif code == 'UNSETTLED_CHECKOUT':
            parts.append(f'{cnt} checked-out guest(s) have unpaid bills (₹{amt:,.0f})')
        elif code == 'UNAUTH_DISCOUNT':
            parts.append(f'{cnt} discount(s) lack manager authorization')
        elif code == 'RATE_LEAKAGE':
            parts.append(f'{cnt} room(s) were billed below standard tariff')
        elif code == 'MISSING_CHARGES':
            parts.append(f'{cnt} room(s) have no charge posted tonight')
        elif code == 'CASH_MISMATCH':
            parts.append(f'cash variance of ₹{amt:,.0f} in shift records')
        elif code == 'OPEN_BLOCKERS':
            parts.append(f'{cnt} system blocker(s) need to be resolved')

    if readiness == 'not_ready':
        prefix = 'Night Audit is NOT ready to close'
    elif readiness == 'warnings':
        prefix = 'Night Audit can close but has warnings'
    else:
        prefix = 'Night Audit is ready'

    return f'{prefix} — {", ".join(parts)}.'


def _build_hindi_summary(cards: list, readiness: str) -> str:
    if not cards:
        return 'नाइट ऑडिट साफ़ है — सभी जाँच पूरी हो गई हैं।'
    if readiness == 'not_ready':
        return f'नाइट ऑडिट बंद करने के लिए तैयार नहीं है — {len(cards)} समस्याएं हल करनी होंगी।'
    return f'नाइट ऑडिट बंद हो सकता है, लेकिन {len(cards)} चेतावनियाँ हैं।'


# ── Top-priority actions ──────────────────────────────────────────────────────

def _build_priority_actions(cards: list) -> list:
    """Returns list of dicts: {text, amount, tab, issue_code, severity, severity_badge_cls}"""
    card_map = {c['issue_code']: c for c in cards}
    actions  = []

    _ORDER = [
        'MISSING_CHARGES',
        'UNSETTLED_CHECKOUT',
        'RECON_DIFF',
        'OPEN_BLOCKERS',
        'OVERPAY',
        'CASH_MISMATCH',
        'UNAUTH_DISCOUNT',
        'RATE_LEAKAGE',
    ]
    _TEXT = {
        'MISSING_CHARGES':    'Post missing night charges immediately — go to Room Charges tab.',
        'UNSETTLED_CHECKOUT': 'Contact checked-out guests with unpaid balances — see Folio Control.',
        'RECON_DIFF':         'Investigate the reconciliation difference — check payments and folios.',
        'OPEN_BLOCKERS':      'Clear all system blockers before attempting to close the audit.',
        'OVERPAY':            'Resolve overpayments — check for duplicate payments or post-checkout discounts.',
        'CASH_MISMATCH':      'Recount and reconcile the cash drawer for the flagged shift(s).',
        'UNAUTH_DISCOUNT':    'Have a Manager authorize or reverse unauthorized discounts.',
        'RATE_LEAKAGE':       'Document the reason for below-tariff rates or correct the folio rates.',
    }
    _TAB = {
        'MISSING_CHARGES':    'charges',
        'UNSETTLED_CHECKOUT': 'folio',
        'RECON_DIFF':         'folio',
        'OPEN_BLOCKERS':      'exceptions',
        'OVERPAY':            'folio',
        'CASH_MISMATCH':      'shifts',
        'UNAUTH_DISCOUNT':    'revenue',
        'RATE_LEAKAGE':       'revenue',
    }

    for code in _ORDER:
        if code in card_map:
            c = card_map[code]
            actions.append({
                'text':              _TEXT[code],
                'amount':            c['amount'],
                'tab':               _TAB[code],
                'issue_code':        code,
                'severity':          c['severity'],
                'severity_badge_cls': c['severity_badge_cls'],
            })

    if not actions:
        return [{'text': 'No immediate action required — audit is clean.',
                 'amount': 0.0, 'tab': '', 'issue_code': '',
                 'severity': 'low', 'severity_badge_cls': 'bg-secondary'}]
    return actions


# ── Main entry point ──────────────────────────────────────────────────────────

class AuditExplanationService:
    """
    Takes the full_report() dict and returns a plain-language explanation
    suitable for display to non-technical hotel staff.
    """

    @staticmethod
    def explain(report: dict) -> dict:
        """
        Returns:
            plain_summary           str
            hindi_summary           str
            audit_readiness_state   'ready' | 'warnings' | 'not_ready'
            top_priority_actions    list[str]
            issue_cards             list[dict]
            has_issues              bool
            issue_count             int
            danger_count            int
            warning_count           int
            all_affected_records    list[dict]  — merged from all cards
        """
        control     = report.get('control', {})
        folio       = report.get('folio', {})
        revenue     = report.get('revenue', {})
        room_chg    = report.get('room_charges', {})
        exceptions  = report.get('exceptions', {})
        shifts      = report.get('shifts', {})

        # ── Build individual cards ──
        raw_cards = [
            _explain_open_blockers(exceptions),
            _explain_recon_diff(control, folio, revenue),
            _explain_unsettled_checkouts(folio),
            _explain_missing_charges(room_chg),
            _explain_overpayments(folio),
            _explain_cash_mismatch(shifts),
            _explain_unauth_discounts(revenue),
            _explain_rate_leakage(revenue),
        ]
        cards = sorted(
            [c for c in raw_cards if c is not None],
            key=lambda c: _SEV_ORDER.get(c['severity'], 99),
        )

        # ── Readiness state ──
        danger_count  = sum(1 for c in cards if c['severity'] == 'critical')
        warning_count = sum(1 for c in cards if c['severity'] in ('high', 'medium'))

        if danger_count > 0:
            readiness = 'not_ready'
        elif warning_count > 0:
            readiness = 'warnings'
        else:
            readiness = 'ready'

        # ── Merged affected records ──
        all_records = []
        for card in cards:
            for rec in card.get('affected_records', []):
                if rec and rec.get('id') or rec.get('ref'):
                    merged = dict(rec)
                    merged['_issue_title']  = card['title']
                    merged['_issue_code']   = card['issue_code']
                    merged['_severity']     = card['severity']
                    merged['_severity_cls'] = card['severity_badge_cls']
                    all_records.append(merged)

        # ── Recon breakdown: explained vs. unexplained gap ──
        recon_card   = next((c for c in cards if c['issue_code'] == 'RECON_DIFF'), None)
        recon_total  = recon_card['amount'] if recon_card else 0.0
        _explaining  = {'OVERPAY', 'UNSETTLED_CHECKOUT', 'UNAUTH_DISCOUNT', 'RATE_LEAKAGE'}
        explained    = sum(c['amount'] for c in cards if c['issue_code'] in _explaining)
        unexplained  = max(0.0, recon_total - explained)
        recon_breakdown = {
            'total':       recon_total,
            'explained':   min(explained, recon_total),
            'unexplained': unexplained,
            'has_gap':     unexplained >= 1.0 and recon_total > 0,
        }

        # ── Derived aggregates ──
        financial_impact = sum(c['amount'] for c in cards)
        issue_counts = {
            'total':    len(cards),
            'critical': sum(1 for c in cards if c['severity'] == 'critical'),
            'high':     sum(1 for c in cards if c['severity'] == 'high'),
            'medium':   sum(1 for c in cards if c['severity'] == 'medium'),
            'low':      sum(1 for c in cards if c['severity'] == 'low'),
        }

        # sub_summary: lead with the top-priority action
        priority_actions = _build_priority_actions(cards)
        if cards:
            top = cards[0]
            if top['severity'] == 'critical':
                sub_summary = f'Start here: {top["plain_meaning"].split(".")[0]}.'
            else:
                sub_summary = f'Review and resolve {len(cards)} audit issue(s) before closing.'
        else:
            sub_summary = 'All checks passed — the audit is clean and ready to close.'

        return {
            'plain_summary':         _build_plain_summary(cards, readiness),
            'hindi_summary':         _build_hindi_summary(cards, readiness),
            'sub_summary':           sub_summary,
            'audit_readiness_state': readiness,
            'top_priority_actions':  priority_actions,
            'issue_cards':           cards,
            'has_issues':            len(cards) > 0,
            'issue_count':           len(cards),
            'danger_count':          danger_count,
            'warning_count':         warning_count,
            'financial_impact':      financial_impact,
            'issue_counts':          issue_counts,
            'recon_breakdown':       recon_breakdown,
            'all_affected_records':  all_records,
        }
