"""
The canonical table classification for production initialization.

Separated from the tool that uses it because this is the part that carries
business meaning and the part a reviewer must read. The tool is mechanism;
this is policy.

Why a declared list rather than a rule
--------------------------------------
Classification cannot be derived from schema alone. Nothing in DDL says
``rooms`` is configuration and ``reservations`` is activity — both are
tables with columns and keys. Any rule that claimed to infer it would be
guessing with extra steps.

So every table is declared, with a stated reason, and the declaration is
then **cross-checked mechanically** against two things the schema *does*
know (see ``production_initialize.verify_classification``):

1. **Every live table must appear here.** A table the database has and
   this module does not name aborts the run. There is no catch-all and no
   default, because a default is how a table nobody classified gets
   silently preserved — or silently destroyed.
2. **No MASTER table may hold a foreign key into a TRANSACTION table.**
   Configuration does not depend on activity. If it appears to, either the
   classification is wrong or the schema is, and both are worth stopping
   for.

The rule that this replaces
---------------------------
``reset_transactional_data.py`` ships with the application and classifies
tables for the same purpose. Wave 0 found it has **no dynamic catch-all**,
so four tables it does not name simply survive a reset:

    reservation_rooms, credit_vouchers, credit_voucher_redemptions,
    ota_payouts

``reservation_rooms`` is the one that mattered — 28 rows on the production
database, every one a child of a reservation the reset deletes, leaving
orphaned room allocations pointing at reservations that no longer exist.
(Recorded at ``verification/datasets/schema.py``,
``UNCLASSIFIED_BY_ADMIN_RESET``.)

All four are classified TRANSACTION here, and the abort-on-unknown rule
above is what stops the same class of omission recurring.
"""
from __future__ import annotations

#: The four classes. A table is exactly one of them.
MASTER = 'MASTER'            # configuration; preserved verbatim
TRANSACTION = 'TRANSACTION'  # business activity; cleared
SYSTEM = 'SYSTEM'            # framework state; preserved or reinitialised
TEMPORARY = 'TEMPORARY'      # ephemeral working data; cleared

#: What the tool does with each class.
ACTION = {
    MASTER: 'Preserved',
    SYSTEM: 'Preserved or Reinitialized',
    TRANSACTION: 'Cleared',
    TEMPORARY: 'Cleared',
}

#: SYSTEM is the one class whose action is not uniform, so each of its two
#: members says which it is. Reporting both as "Preserved or Reinitialized"
#: would leave a reader unable to tell what happened to either.
ACTION_OVERRIDE = {
    'schema_migrations': 'Preserved',
    'business_date': 'Reinitialized',
}


def action_for(table: str) -> str:
    cls, _reason = CLASSIFICATION[table]
    return ACTION_OVERRIDE.get(table, ACTION[cls])

#: table -> (classification, reason)
#:
#: The reason is not decoration. It is what a reviewer checks, and what a
#: future engineer needs when the schema grows a table this list does not
#: have.
CLASSIFICATION: dict = {

    # -- MASTER: the hotel's configuration ------------------------------
    'room_types': (MASTER, 'Room type catalogue and base tariff. Referenced '
                           'by rooms, rate plans and reservations; '
                           'references nothing.'),
    'rooms': (MASTER, 'The physical rooms. References only room_types. A '
                      'hotel does not lose its rooms when it stops '
                      'trading.'),
    'rate_plans': (MASTER, 'Tariff plans against room types. Pricing '
                           'configuration, not a sale.'),
    'payment_modes': (MASTER, 'Settlement heads and their categories '
                              '(direct_payment, ota_receivable). Chart of '
                              'accounts for money in.'),
    'pos_items': (MASTER, 'Sellable item catalogue with prices. A menu '
                          'master.'),
    'companies': (MASTER, 'Corporate accounts and travel agents, with '
                          'credit limits. A counterparty ledger, not a '
                          'transaction.'),
    'equipment': (MASTER, 'Maintenance asset register, keyed to rooms. The '
                          'assets themselves, not work done on them.'),
    'preventive_schedules': (MASTER, 'Maintenance schedules against '
                                     'equipment. A plan, not an event.'),
    'loyalty_config': (MASTER, 'Loyalty programme parameters.'),
    'loyalty_milestones': (MASTER, 'Loyalty tier definitions.'),
    'settings': (MASTER, 'Hotel profile, tax policy, GST regime, printers '
                         'and every operational switch. The single most '
                         'important table to preserve.'),
    'users': (MASTER, 'Operator accounts, roles and permissions. Clearing '
                      'these would lock the hotel out of its own system.'),

    # -- SYSTEM: framework state ----------------------------------------
    'schema_migrations': (SYSTEM, 'Applied migration versions. Preserved '
                                  'verbatim: clearing it would make the '
                                  'application re-run every migration '
                                  'against an already-migrated schema.'),
    'business_date': (SYSTEM, 'The PMS operating date. The one table that '
                              'is neither preserved nor cleared but '
                              'REINITIALIZED — set to today and unlocked.'),

    # -- TEMPORARY: ephemeral working data ------------------------------
    'notification_queue': (TEMPORARY, 'Outbound work queue. Anything '
                                      'undelivered refers to stays that '
                                      'will not exist after the reset.'),
    'precheckin_tokens': (TEMPORARY, 'Short-lived guest links. Expire by '
                                     'design and are meaningless once '
                                     'their reservation is gone.'),
    'revenue_alerts': (TEMPORARY, 'Generated advisory output. Regenerated '
                                  'from data that is about to be removed.'),

    # -- TRANSACTION: business activity ---------------------------------
    'reservations': (TRANSACTION, 'The booking. Root of the activity '
                                  'graph.'),
    'guests': (TRANSACTION, 'Guest records created per stay. Not a master '
                            'in this schema — there is no separate guest '
                            'profile table, so a guest exists because a '
                            'stay did. See --preserve-guests for the CRM '
                            'case.'),
    'reservation_rooms': (TRANSACTION, 'Room allocation per stay. NOT '
                                       'classified by '
                                       'reset_transactional_data.py, which '
                                       'is why 28 orphans would survive '
                                       'that tool.'),
    'reservation_passengers': (TRANSACTION, 'Occupants of a stay.'),
    'reservation_night_rates': (TRANSACTION, 'Priced room nights. The '
                                             'revenue source.'),
    'folios': (TRANSACTION, 'The bill a stay is invoiced on.'),
    'extra_charges': (TRANSACTION, 'Charges posted to a folio.'),
    'payments': (TRANSACTION, 'Money received against a stay.'),
    'tax_lines': (TRANSACTION, 'GST raised per charge. Derived from '
                               'activity.'),
    'checkin_records': (TRANSACTION, 'Check-in events.'),
    'cico_charge_logs': (TRANSACTION, 'Check-in/check-out charge audit '
                                      'entries.'),
    'credit_notes': (TRANSACTION, 'Credit issued against an invoice.'),
    'credit_vouchers': (TRANSACTION, 'Vouchers issued to guests. NOT '
                                     'classified by '
                                     'reset_transactional_data.py.'),
    'credit_voucher_redemptions': (TRANSACTION, 'Voucher usage. NOT '
                                                'classified by '
                                                'reset_transactional_data.'
                                                'py.'),
    'void_requests': (TRANSACTION, 'Requests to void a payment.'),
    'overpayment_logs': (TRANSACTION, 'Recorded guest overpayments.'),
    'no_show_logs': (TRANSACTION, 'No-show events and their charges.'),
    'night_audit_logs': (TRANSACTION, 'Closed business days and their '
                                      'frozen snapshots. A new pilot has '
                                      'no audit history.'),
    'night_audit_reopen_logs': (TRANSACTION, 'Reopen events against closed '
                                             'days.'),
    'shifts': (TRANSACTION, 'Front-desk cash shifts.'),
    'shift_adjustments': (TRANSACTION, 'Float and payout movements within '
                                       'a shift.'),
    'group_blocks': (TRANSACTION, 'A group booking. A sale, despite '
                                  'looking configuration-shaped.'),
    'guest_feedback': (TRANSACTION, 'Feedback against a stay.'),
    'guest_id_documents': (TRANSACTION, 'Identity documents captured at '
                                        'check-in. Also a data-protection '
                                        'reason to clear rather than '
                                        'retain.'),
    'foreign_national_info': (TRANSACTION, 'Form C / immigration data per '
                                           'guest. Same reasoning.'),
    'precheckin_submissions': (TRANSACTION, 'Guest-submitted pre-arrival '
                                            'data.'),
    'loyalty_transactions': (TRANSACTION, 'Points earned and spent.'),
    'loyalty_redemptions': (TRANSACTION, 'Points redeemed against a '
                                         'stay.'),
    'maintenance_requests': (TRANSACTION, 'Work raised against a room. The '
                                          'work, not the asset.'),
    'equipment_health_logs': (TRANSACTION, 'Readings against equipment. '
                                           'The readings, not the '
                                           'equipment.'),
    'ota_payouts': (TRANSACTION, 'Remittances received from channels. NOT '
                                 'classified by '
                                 'reset_transactional_data.py.'),
    'staff_performance_daily': (TRANSACTION, 'Derived daily staff '
                                             'statistics.'),
    'audit_logs': (TRANSACTION, 'The general audit trail. Cleared because '
                                'it records activity that will not exist. '
                                'THE TOOL WARNS ON THIS — see '
                                'CLEARED_WITH_WARNING.'),
    'backup_logs': (TRANSACTION, 'History of backups taken by the '
                                 'application.'),
    'webhook_logs': (TRANSACTION, 'Inbound and outbound integration '
                                  'traffic.'),
    'notification_logs': (TRANSACTION, 'Record of notifications already '
                                       'sent, keyed to a reservation. '
                                       'History of activity, unlike '
                                       'notification_queue which is the '
                                       'pending work itself.'),
}

# NOTE, kept because it is the tool proving itself: the first draft of this
# list omitted `notification_logs`, and the very first dry run aborted on
# it rather than defaulting it to preserved or cleared. That is precisely
# the omission `reset_transactional_data.py` makes silently for four
# tables, and the reason abort-on-unknown is not negotiable.

#: Tables that are cleared but whose clearing is reported as a warning,
#: because losing them has a consequence beyond the pilot.
#:
#: This is not a safety valve — they ARE cleared. It exists so the report
#: cannot be read as "nothing of consequence was removed" when something
#: of consequence was.
CLEARED_WITH_WARNING = {
    'audit_logs': ('The general audit trail is the compliance record of '
                   'who did what. Clearing it is correct for a fresh '
                   'environment and irreversible for the old one — the '
                   'pre-initialization backup is the only remaining '
                   'copy.'),
    'night_audit_logs': ('Frozen night-audit snapshots are release '
                         'evidence under Phase 2.6 §13 and immutable under '
                         'P12. They survive only in the backup.'),
    'guest_id_documents': ('Identity documents. Clearing is the correct '
                           'data-protection outcome; confirm the backup is '
                           'held under the same controls as the live '
                           'database.'),
    'foreign_national_info': ('Immigration records may carry a statutory '
                              'retention period independent of this '
                              'system. Confirm before discarding the '
                              'backup.'),
}


def classify(table: str):
    """Return ``(classification, reason)`` or ``None`` if undeclared."""
    return CLASSIFICATION.get(table)


def tables_of(classification: str) -> set:
    return {t for t, (c, _r) in CLASSIFICATION.items() if c == classification}


def cleared_classes() -> tuple:
    return (TRANSACTION, TEMPORARY)
