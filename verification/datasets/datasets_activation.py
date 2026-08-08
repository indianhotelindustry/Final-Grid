"""
Activation datasets — data that exists to give a silent control a voice.

**This module is deliberately empty. D6 Step 1 is infrastructure only.**
See ``datasets_core`` for why an empty module is preferable to no module.

What belongs here
-----------------
One dataset per empty population. These are the reason D6 exists: each
declares ``activates_invariants``, and commissioning checks the claim
against reality — a dataset that says it activates an invariant and leaves
it VACUOUS has not done its job.

The populations to close, measured against production on 2026-08-07:

===========================  =====  ====================================
Target                       Layer  Evidence it is empty
===========================  =====  ====================================
``INV-A06`` overpayment      D4     0 reservations overpaid by > Rs.1
``INV-C06`` corporate credit D4     ``corporate_bookings`` = 0
``INV-D02`` corrections      D4     no correction or reversal rows
``INV-D05`` voids / notes    D4     ``credit_notes`` = 0, ``void_requests`` = 0
``Q11`` refunds vs voids     D1     VACUOUS
``Q21`` shift cash           D1     no shifts
4 golden master surfaces     D2     UNRESOLVED — no checked-in reservation
===========================  =====  ====================================

Planned. **Re-sequenced 2026-08-08** — see `D6_SEQUENCING_DECISION.md` for
the evidence behind the swap::

    1 DS-ACT-INHOUSE    COMMISSIONED. A checked-in reservation, plus a
                        departed one so the trade is not a net loss.
                        Activates 0 invariants; D2 +3 / -1.
    2 DS-ACT-GROUP      NEXT. A group block. Closes groups.detail, the only
                        UNRESOLVED D2 surface with no planned owner.
                        Activates 0 invariants — no invariant, fault or
                        quantity references group_blocks anywhere.
    3 DS-ACT-OVERPAY    BLOCKED on R-5. A reservation overpaid by more than
                        the materiality threshold — and what that threshold
                        is, is the open decision. Lifts INV-A06 and gives
                        INV-D07 its first real population.
    4 DS-ACT-CORPCREDIT lifts INV-C06; closes the 2 company D2 surfaces.
    5 DS-ACT-CORRECTION lifts INV-D02 — the only RELEASE_BLOCKING one of
                        the four VACUOUS invariants.
    6 DS-ACT-VOIDCN     lifts INV-D05. Also lifts Q11.
    7 DS-ACT-SHIFT      lifts Q21.

Overpayment was not demoted because group coverage is worth more; it is
not. It was demoted because ``DS-ACT-OVERPAY`` cannot be declared
correctly until R-5 settles the threshold that defines its population,
and declaring expectations against an unsettled policy is the mistake the
D5.5 remediation existed to prevent. ``FLT-A07`` is already COMMISSIONED,
so overpayment *detection* is proven; what is missing is a standing
population, which is a coverage gap rather than a correctness risk.

**The DS-ACT- prefix is wrong for two of these.** It means "activates a
VACUOUS D4 control", and ``DS-ACT-INHOUSE`` and ``DS-ACT-GROUP`` activate
none — they exist to give a golden-master resolver an entity to pin to.
Neither this module nor ``datasets_core`` has a category for that. Not
renamed: ``dataset_id@version`` is a dataset's identity and editing it in
place is what the versioning rule exists to prevent. Recorded so the third
one does not inherit the confusion by default.

**Every dataset from DS-ACT-GROUP onward carries a coverage ledger** —
Added, Lost, Changed, and expected vs unexpected movement, measured rather
than asserted. See ``D6_COVERAGE_LEDGER.md``.

Two things to get right
-----------------------
**The threshold, not the table.** ``INV-A06``'s population is reservations
whose canonical ``settlement_balance`` is below ``-1.00``. It is *not* the
``overpayment_logs`` table. Inserting a log row would leave the invariant
VACUOUS and the activation claim would fail commissioning — correctly.
``DS-ACT-OVERPAY`` must produce a reservation that is genuinely overpaid
by more than one rupee. See ``D5_5_CONSISTENCY_AUDIT.md`` Q1.

**Something to be violated by.** The registry requires a perturbation that
breaks a declared expectation. For an activation dataset the natural
perturbation is the one that makes the activated invariant fail, which is
also the proof the invariant works on a real population rather than merely
having a population.

REGISTRY GAP — D2 outcomes cannot be declared
---------------------------------------------
Found while declaring ``DS-ACT-INHOUSE`` on 2026-08-08, and not fixed.

``Expectations`` carries charter elements 3 to 7: financial, invariants,
replay, parity, faults. **There is no element for D2**, so a dataset
cannot declare what the golden master framework should conclude about it.
``Layer.D2_GOLDEN`` exists in the vocabulary and ``evaluate.PROBE_FOR``
maps it to a D5 probe, but ``Expectations.declared_layers()`` is computed
from ``parity``, ``replay``, ``invariants`` and ``faults`` alone, so
``D2_GOLDEN`` is never returned and never swept. It is dead vocabulary.

The consequence is specific and it lands on the first dataset:
``DS-ACT-INHOUSE`` exists mainly to supply the in-house reservation that
three golden-master surfaces have never had, and **that is the one thing
about it the registry cannot check.** The dataset declares the financial
and invariant consequences of the stay, which are real expectations worth
holding, and the D2 resolution has to be verified by running
``gm-capture --db`` against the built dataset by hand.

Closing it means a sixth expectation element and a resolver-count probe.
That is D2/D6 integration work, not a footnote to a dataset, and it is
recorded here rather than worked around silently.

The measured UNRESOLVED population, 2026-08-08, read from the stored
master index rather than from any document::

    inhouse_reservation   3   main.checkout, main.reservation_folio,
                              pos.room_charges_api
    any_company           2   main.get_company_credit, main.company_detail
    any_group             1   groups.detail
                          -
                          6   total

``WAVE0_STATUS.md`` section 4.1 records four and the D2 completion report
records five. Both are wrong; six is what the index says. The ``any_group``
surface is the one no planned dataset covers — ``group_blocks`` is empty
and no ``DS-ACT-GROUP`` is on the list above.

What ``DS-ACT-INHOUSE`` actually does to that population, measured by
capturing masters against the built dataset on 2026-08-08::

    production            158 surfaces captured, 6 UNRESOLVED
    DS-ACT-INHOUSE@1.0    160 surfaces captured, 4 UNRESOLVED

    gained   main.checkout, main.reservation_folio,
             pos.room_charges_api                       (+3)
    lost     reports.night_audit_snapshot               (-1)
    still    any_company x2, any_group x1, night audit x1

The loss is real and is not worked around. ``night_audit_log`` resolves on
production because one ``night_audit_logs`` row exists there; this dataset
declares no night audit, so the surface has nothing to pin to. Declaring
one is not a row you can invent: ``INV-B02`` checks that
``snapshot_hash`` equals a recomputation of ``snapshot_json``, and
``INV-B03`` — the CRITICAL invariant with a demonstrated detection gap
(``FLT-D03``) — checks that recomputing the closed day reproduces the
frozen figures. A hand-written snapshot would either fail both or, worse,
be tuned until it passed. That belongs in a dataset written for it.
"""
from __future__ import annotations

from verification.datasets.model import (
    Commissioning, Event, Expectations, Mode, Origin, Provenance, Purpose,
)
from verification.datasets.registry import dataset

# ---------------------------------------------------------------------------
# DS-ACT-INHOUSE
# ---------------------------------------------------------------------------
#
# The money, derived once here so the declaration below can be read against
# it rather than taken on trust:
#
#   reservation 1, in house, 2 nights x 1,000.00   room     2,000.00
#     GST 5%, split CGST 2.5 + SGST 2.5            tax        100.00
#     advance taken at check-in, cash                     - 1,000.00
#                                                  owed     1,100.00
#
#   reservation 2, departed, 1 night x 1,000.00    room     1,000.00
#     GST 5%                                       tax         50.00
#     settled in full on departure, cash                  - 1,050.00
#                                                  owed         0.00
#                                                  --------------------
#   room revenue 3,000.00  tax 150.00  paid 2,050.00  OUTSTANDING 1,100.00
#
# Every figure is exact at two places and no rounding residue is possible:
# 1,000.00 x 2.5% = 25.00 exactly, six times. That is deliberate. The
# production database cannot make this claim — nine of its reservations
# carry a paisa of residue from two different rounding paths
# (D5_5_REMEDIATION_APPLIED.md section 5) — and a first dataset whose
# arithmetic is arguable would make every failure ambiguous.
#
# WHY THERE IS A SECOND, DEPARTED STAY
# ------------------------------------
# The first draft of this dataset had only the in-house guest, which is
# what the roadmap asked for. Measured against a golden-master capture it
# resolved the three surfaces pinned to ``inhouse_reservation`` and
# **un-resolved four** pinned to ``checked_out_reservation`` — the tax
# invoice, the invoice detail API, the split-billing sub-ledger and the
# settled-folio variant.
#
# That is not a quirk of this declaration. A dataset *replaces* the
# transactional layer rather than adding to it (``builder.strip``), so D2
# coverage over a dataset is never automatically a superset of coverage
# over production. A single-narrative dataset silently trades one
# population for another, and the trade is invisible unless somebody
# captures masters against it and counts — which nothing in D6 does,
# because D6 cannot declare a D2 outcome at all (see REGISTRY GAP above).
#
# So the narrative carries both shapes. It costs one guest, one
# reservation, one night, one folio, two tax rows and one payment, and it
# turns a 3-for-4 trade into a measured 3-for-1 — the one remaining loss
# being the night-audit surface, for the reason given in REGISTRY GAP.

_ROOM_ID = 1              # 101, Deluxe. A preserved master row.
_ROOM_ID_DEPARTED = 2     # 102, Deluxe.
_ROOM_TYPE_ID = 2         # Deluxe, base rate 1,142.86.
_CASH = 1                 # payment mode 1, category direct_payment.


@dataset(
    dataset_id='DS-ACT-INHOUSE',
    version='1.0',
    title='One guest in house part paid, one departed and settled',
    purpose=Purpose.BASELINE,

    business_narrative=(
        'A small hotel with two stays and nothing wrong with either.\n\n'
        'Priya Nair arrives on 13 June for one night in room 102 at '
        '1,050.00 inclusive of 5% GST, settles in full in cash when she '
        'leaves on the 14th, and is invoiced for 1,050.00 with no rounding '
        'adjustment. Rohit Sharma walks in on the 14th and takes room 101 '
        'for two nights, departing on the 16th, at the same rate. He pays '
        '1,000.00 in cash at the desk on arrival. On the morning of the '
        '15th — the business date this dataset represents — he is still in '
        'the room, both his nights are priced, no invoice has been raised '
        'against him, and the hotel is owed 1,100.00.\n\n'
        'Nothing is wrong in this narrative. That is the point of it. '
        'Every declared expectation holds, so the dataset is a positive '
        'control: it is what a perturbation has to be perturbed away from, '
        'and it is the only kind of evidence that can show correct data '
        'passing rather than merely showing broken data failing.\n\n'
        'What it creates that production does not have is a reservation '
        'with status CheckedIn. All 28 production reservations are '
        'CheckedOut, so three declared golden-master surfaces — the open '
        'folio, the checkout screen and POS room charges — have never had '
        'an entity to pin a master to and are recorded UNRESOLVED. Priya '
        'is here so that giving them one does not take the four '
        'checked-out surfaces away; see the note above her rows.\n\n'
        'That D2 claim is NOT declared as an expectation below, and it '
        'cannot be: Expectations carries charter elements 3 to 7 '
        '(financial, invariants, replay, parity, faults) and there is no '
        'element for D2. See the note under REGISTRY GAP in this module.'
    ),

    timeline=(
        Event(date='2026-06-13',
              description='Priya Nair checks into room 102 for one night '
                          'at 1,050.00 inclusive.',
              tables=('guests', 'reservations', 'reservation_rooms',
                      'folios', 'reservation_night_rates', 'tax_lines'),
              amount='1050.00'),
        Event(date='2026-06-14',
              description='She checks out, settles 1,050.00 in cash, and '
                          'is invoiced. The invoice total is exact, so no '
                          'round-off is recorded against it.',
              tables=('payments', 'reservations'),
              amount='1050.00'),
        Event(date='2026-06-14',
              description='Rohit Sharma walks in and takes room 101 for '
                          'two nights, and both nights are priced at '
                          'check-in as the application does.',
              tables=('guests', 'reservations', 'reservation_rooms',
                      'folios', 'reservation_night_rates', 'tax_lines'),
              amount='2100.00'),
        Event(date='2026-06-14',
              description='He pays 1,000.00 in cash at the desk. The '
                          'payment is posted to folio A.',
              tables=('payments',),
              amount='1000.00'),
        Event(date='2026-06-15',
              description='Business date. Rohit is still in house, no '
                          'invoice has been raised against him, and '
                          '1,100.00 is outstanding across the hotel.',
              tables=('business_date',),
              amount='1100.00'),
    ),

    provenance=Provenance(
        origin=Origin.SYNTHETIC,
        author='Wave 0.5 / D6 Step 2',
        created='2026-08-08',
        derivation=(
            'Written by hand from the narrative above. No production row '
            'was copied, transformed or sampled. The guest name and phone '
            'are invented; the room, room type and payment mode are '
            'preserved master rows and are this hotel\'s real '
            'configuration, which is what makes the dataset measure this '
            'hotel rather than an invented one.'),
        contains_real_guest_data=False,
        disclosure='Publishable. Contains no real guest and no real stay.',
        rationale=(
            'SYNTHETIC because the population being created does not exist '
            'in production at all — there is no in-house stay to derive '
            'one from.'),
    ),

    # -- charter elements 3 to 7 -----------------------------------------
    expectations=Expectations(

        # Element 3. Every probe in financials.py, not a chosen subset: a
        # declaration that names only the figures it expects to move is one
        # that cannot notice the figures it did not think about.
        financial={
            'reservations_count': '2',
            'guests_count': '2',
            'folios_count': '2',
            'payments_count': '2',

            'payments_gross': '2050.00',
            'payments_voided': '0.00',
            'payments_net': '2050.00',
            'payments_corrections': '0.00',
            'payments_reversals': '0.00',

            'extra_charges_total': '0.00',
            'extra_charges_room_rent': '0.00',
            'extra_charges_non_room_rent': '0.00',
            'extra_charges_reversals': '0.00',
            'room_revenue': '3000.00',
            'room_discount': '0.00',

            'tax_total': '150.00',
            # 3 bases x 1,000.00. Six tax_lines rows over three charges: if
            # this reported 6,000.00 the R-3 double count would be back.
            'taxable_total': '3000.00',
            'tax_lines_count': '6',
            'tax_base_count': '3',

            'overpayment_total': '0.00',
            'overpayment_count': '0',
            'credit_note_total': '0.00',
            'credit_note_count': '0',
            'void_request_count': '0',
            'corporate_credit_used': '0.00',
            'corporate_bookings': '0',

            # Only the departed stay has been invoiced. The in-house stay
            # has not, so these totals are Priya's alone — which is the
            # assertion that Rohit's invoice columns are genuinely NULL
            # rather than carrying a total the application posted early.
            # Her bill is exact, so nothing rounds and no row is counted.
            'invoice_unrounded_grand_total': '1050.00',
            'invoice_round_off_total': '0.00',
            'invoice_rounded_grand_total': '1050.00',
            'invoice_round_off_rows': '0',

            # Rohit's 1,100.00. Priya contributes nothing: she was settled
            # in full, so a non-zero figure here would mean the departed
            # stay had left money on the table.
            'outstanding': '1100.00',
        },

        # Element 4. Declared from the narrative, not transcribed from a
        # run. Each of these is a property the story above forces:
        invariants={
            # The payment carries a folio_id. Production violates this 40
            # times over; the narrative says it should be possible to hold.
            'INV-A02': 'HOLDS',
            # 1,000.00 x 2.5% = 25.00, four times, exactly.
            'INV-A05': 'HOLDS',
            # Every child row names reservation 1, which exists.
            'INV-C03': 'HOLDS',
            # One reservation in one room. Nothing can collide.
            'INV-C04': 'HOLDS',
            # VACUOUS, not HOLDS. INV-C01's population is payments through
            # an ota_receivable mode, and the only payment here is cash.
            # An empty population proves nothing, so the engine reports
            # VACUOUS and this expectation says so out loud (P10). The
            # first draft of this declaration said HOLDS and commissioning
            # rejected it — which is the gate working.
            'INV-C01': 'VACUOUS',
            # Folio A names reservation 1.
            'INV-D01': 'HOLDS',
            # The payment names mode 1, which exists and is allowed.
            'INV-D03': 'HOLDS',
            # Both tax rows name the room night they tax.
            'INV-D04': 'HOLDS',
            # Every night row names its reservation and falls inside it.
            'INV-D06': 'HOLDS',
            # Priya is the population: CheckedOut, checked_out_at set, and
            # settled to the rupee. On production this invariant runs over
            # 28 reservations and holds; here it runs over exactly one, and
            # a dataset whose only departed guest was unsettled would be
            # declaring a hotel that let someone walk.
            'INV-C02': 'HOLDS',
        },
    ),

    # -- the rows, parents before children -------------------------------
    #
    # Ids are declared rather than left to AUTOINCREMENT and every
    # timestamp is a literal, because a dataset that built differently on
    # two runs would have a content hash that certifies nothing.
    rows=(
        ('guests',
         ('id', 'name', 'phone'),
         ((1, 'Rohit Sharma', '9800000001'),
          (2, 'Priya Nair', '9800000002'),)),

        ('reservations',
         ('id', 'guest_id', 'room_id', 'room_type_id',
          'arrival_date', 'departure_date', 'adults', 'status',
          'rate_per_night', 'standard_tariff', 'expected_tariff',
          'advance_payment', 'source', 'booking_type', 'pricing_mode',
          'created_at', 'checked_in_at', 'checkin_by',
          'noshow_exempt', 'checkout_initiated', 'credit_amount',
          'credit_settled_amount', 'cancellation_amount_refunded',
          'cancellation_amount_forfeited',
          'cancellation_amount_credit_voucher'),
         ((1, 1, _ROOM_ID, _ROOM_TYPE_ID,
           '2026-06-14', '2026-06-16', 1, 'CheckedIn',
           1000.00, 1000.00, 1000.00,
           1000.00, 'Walk-in', 'Regular', 'standard',
           '2026-06-14 09:00:00.000000', '2026-06-14 09:00:00.000000',
           'admin',
           0, 0, 0.0, 0.0, 0.0, 0.0, 0.0),)),

        # The departed stay. Declared as its own entry rather than as a
        # second tuple above because it carries the checkout and invoice
        # columns the in-house row must NOT have — keeping them in one
        # column list would mean giving Rohit a NULL invoice_number and a
        # NULL checked_out_at explicitly, which reads as though somebody
        # meant to fill them in.
        ('reservations',
         ('id', 'guest_id', 'room_id', 'room_type_id',
          'arrival_date', 'departure_date', 'adults', 'status',
          'rate_per_night', 'standard_tariff', 'expected_tariff',
          'advance_payment', 'source', 'booking_type', 'pricing_mode',
          'created_at', 'checked_in_at', 'checkin_by',
          'checked_out_at', 'checkout_by', 'checkout_time',
          'invoice_number', 'invoice_unrounded_grand_total',
          'invoice_round_off_amount', 'invoice_rounded_grand_total',
          'noshow_exempt', 'checkout_initiated', 'credit_amount',
          'credit_settled_amount', 'cancellation_amount_refunded',
          'cancellation_amount_forfeited',
          'cancellation_amount_credit_voucher'),
         ((2, 2, _ROOM_ID_DEPARTED, _ROOM_TYPE_ID,
           '2026-06-13', '2026-06-14', 1, 'CheckedOut',
           1000.00, 1000.00, 1000.00,
           0.0, 'Walk-in', 'Regular', 'standard',
           '2026-06-13 14:00:00.000000', '2026-06-13 14:00:00.000000',
           'admin',
           '2026-06-14 08:30:00.000000', 'admin', '08:30',
           'INV-2026-000001', 1050.00, 0.0, 1050.00,
           0, 1, 0.0, 0.0, 0.0, 0.0, 0.0),)),

        ('reservation_rooms',
         ('id', 'reservation_id', 'room_id', 'is_primary', 'created_at'),
         ((1, 1, _ROOM_ID, 1, '2026-06-14 09:00:00.000000'),
          (2, 2, _ROOM_ID_DEPARTED, 1, '2026-06-13 14:00:00.000000'),)),

        ('folios',
         ('id', 'reservation_id', 'folio_letter', 'label', 'is_closed',
          'created_at'),
         ((1, 1, 'A', 'Guest', 0, '2026-06-14 09:00:00.000000'),
          # Closed, because the stay it belongs to is settled and gone.
          (2, 2, 'A', 'Guest', 1, '2026-06-13 14:00:00.000000'),)),

        ('reservation_night_rates',
         ('id', 'reservation_id', 'stay_date', 'room_type_id', 'room_id',
          'standard_rate', 'resolved_rate', 'final_rate', 'discount_amount',
          'rate_source', 'pricing_mode', 'manual_override', 'tax_rate',
          'is_posted', 'is_locked', 'created_at', 'updated_at'),
         ((1, 1, '2026-06-14', _ROOM_TYPE_ID, _ROOM_ID,
           1000.00, 1000.00, 1000.00, 0.0,
           'base_rate', 'standard', 0, 5, 0, 0,
           '2026-06-14 09:00:00.000000', '2026-06-14 09:00:00.000000'),
          (2, 1, '2026-06-15', _ROOM_TYPE_ID, _ROOM_ID,
           1000.00, 1000.00, 1000.00, 0.0,
           'base_rate', 'standard', 0, 5, 0, 0,
           '2026-06-14 09:00:00.000000', '2026-06-14 09:00:00.000000'),
          # Priya's single night. is_posted stays 0: the night audit has
          # not run in this narrative, so room rent has not been posted
          # into extra_charges. R-2's exclusion therefore has nothing to
          # exclude here, exactly as on production.
          (3, 2, '2026-06-13', _ROOM_TYPE_ID, _ROOM_ID_DEPARTED,
           1000.00, 1000.00, 1000.00, 0.0,
           'base_rate', 'standard', 0, 5, 0, 0,
           '2026-06-13 14:00:00.000000', '2026-06-13 14:00:00.000000'),)),

        # One row per component per night: the shape R-3 exists to handle.
        # Each repeats the full 1,000.00 base, so taxable_total must report
        # 2,000.00 and not 4,000.00.
        ('tax_lines',
         ('id', 'reservation_id', 'charge_source_type', 'charge_source_id',
          'charge_date', 'taxable_amount', 'tax_type', 'tax_rate',
          'tax_amount', 'is_interstate', 'is_exempted', 'sac_code',
          'created_at'),
         ((1, 1, 'room_night', 'night_2026-06-14', '2026-06-14',
           1000.00, 'CGST', 2.5, 25.00, 0, 0, '996311',
           '2026-06-14 09:00:00.000000'),
          (2, 1, 'room_night', 'night_2026-06-14', '2026-06-14',
           1000.00, 'SGST', 2.5, 25.00, 0, 0, '996311',
           '2026-06-14 09:00:00.000000'),
          (3, 1, 'room_night', 'night_2026-06-15', '2026-06-15',
           1000.00, 'CGST', 2.5, 25.00, 0, 0, '996311',
           '2026-06-14 09:00:00.000000'),
          (4, 1, 'room_night', 'night_2026-06-15', '2026-06-15',
           1000.00, 'SGST', 2.5, 25.00, 0, 0, '996311',
           '2026-06-14 09:00:00.000000'),
          # Priya's night. Note the charge_source_id repeats the pattern
          # 'night_<date>' and is unique only WITHIN a reservation — the
          # collision that makes reservation_id part of R-3's grouping key.
          (5, 2, 'room_night', 'night_2026-06-13', '2026-06-13',
           1000.00, 'CGST', 2.5, 25.00, 0, 0, '996311',
           '2026-06-13 14:00:00.000000'),
          (6, 2, 'room_night', 'night_2026-06-13', '2026-06-13',
           1000.00, 'SGST', 2.5, 25.00, 0, 0, '996311',
           '2026-06-13 14:00:00.000000'),)),

        ('payments',
         ('id', 'reservation_id', 'folio_id', 'payment_mode_id', 'amount',
          'payment_date', 'reference_number', 'created_at', 'is_voided',
          'is_correction', 'is_reversal', 'payment_purpose'),
         ((1, 1, 1, _CASH, 1000.00, '2026-06-14', '',
           '2026-06-14 09:05:00.000000', 0, 0, 0, 'settlement'),
          (2, 2, 2, _CASH, 1050.00, '2026-06-14', '',
           '2026-06-14 08:30:00.000000', 0, 0, 0, 'settlement'),)),
    ),

    business_date='2026-06-15',

    # No VACUOUS D4 invariant is lifted by an in-house stay. The four that
    # are VACUOUS on production need an overpayment, a corporate booking, a
    # correction and a void respectively — DS-ACT-OVERPAY and its three
    # siblings. Claiming an activation here would fail commissioning, and
    # correctly.
    activates_invariants=(),

    # -- the discrimination gate -----------------------------------------
    #
    # Two statements, chosen to break two different KINDS of expectation.
    # A perturbation that only moved money would show the financial probes
    # discriminating and say nothing about whether the invariant
    # expectations can fail — and an invariant expectation that cannot
    # fail is the decoration P9 exists to catch.
    perturbation=(
        # The guest paid 500.00, not 1,000.00. Moves the balance.
        'UPDATE payments SET amount = 500.00 WHERE id = 1',
        # The payment loses its folio. This is the production defect
        # INV-A02 reports 40 times over, reproduced deliberately.
        'UPDATE payments SET folio_id = NULL WHERE id = 1',
    ),
    perturbation_breaks=(
        'outstanding',
        'payments_gross',
        'payments_net',
        'INV-A02',
    ),

    principles=('P9', 'P10', 'P14'),
    modes=(Mode.REGRESSION, Mode.CONTINUOUS_VERIFICATION),

    # Declared only after the gate passed, and cross-checked against the
    # evidence on every registry call: ``unbacked_commissioning_claims()``
    # reads the most recent ``*_ds_commission`` pack and reports this
    # dataset if that run did not pass it. A status typed into source is a
    # gate somebody can walk through without doing the work, so the code
    # and the evidence have to agree or the registry says so.
    commissioning_status=Commissioning.COMMISSIONED,
)
def _inhouse():
    pass
