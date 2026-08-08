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

Planned. **Re-sequenced twice.** First on 2026-08-08 to put
``DS-ACT-GROUP`` ahead of ``DS-ACT-OVERPAY``
(``D6_SEQUENCING_DECISION.md``), then again by the project owner to put
``DS-ACT-CORRECTION`` ahead of both::

    1 DS-ACT-INHOUSE    COMMISSIONED. A checked-in reservation, plus a
                        departed one so the trade is not a net loss.
                        Activates 0 invariants; D2 +3 / -1.
    2 DS-ACT-CORRECTION COMMISSIONED. Lifts INV-D02, the only VACUOUS
                        invariant that is RELEASE_BLOCKING. The first
                        dataset to activate anything.
    3 DS-ACT-GROUP      NEXT. A group block. Closes groups.detail, the only
                        UNRESOLVED D2 surface with no planned owner.
                        Activates 0 invariants — no invariant, fault or
                        quantity references group_blocks anywhere.
    4 DS-ACT-OVERPAY    BLOCKED on R-5. A reservation overpaid by more than
                        the materiality threshold — and what that threshold
                        is, is the open decision. Lifts INV-A06 and gives
                        INV-D07 its first real population.
    5 DS-ACT-CORPCREDIT lifts INV-C06; closes the 2 company D2 surfaces.
    6 DS-ACT-VOIDCN     lifts INV-D05. Also lifts Q11.
    7 DS-ACT-SHIFT      lifts Q21.

The owner's reason for the second re-sequencing, recorded because it is
the governing principle rather than a one-off preference: **a regression
dataset should activate the highest-risk verification before extending
ordinary business coverage, because Wave 0's objective is verification
completeness rather than business-feature completeness.** On that
principle ``INV-D02`` outranks everything — it is the only VACUOUS
invariant that blocks a release rather than a certificate.

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
            # Added by R-7. Neither stay corrects anything, so the signed
            # figures equal the unsigned ones — which is the assertion
            # that this narrative contains no correction at all.
            'extra_charges_net': '0.00',
            'extra_charges_non_room_rent_net': '0.00',
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

            # Room 3,000.00 + tax 150.00, nothing reversed. Added by R-7 so
            # the balance is decomposable: if `outstanding` ever moves,
            # this says whether the charges or the collections moved.
            'charges_net': '3150.00',

            # Rohit's 1,100.00. Priya contributes nothing: she was settled
            # in full, so a non-zero figure here would mean the departed
            # stay had left money on the table.
            'outstanding': '1100.00',
            # R-8. No credit note in this narrative, so it equals
            # `outstanding` — which is the assertion that nothing here has
            # been written off.
            'net_receivable': '1100.00',
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

        # Element 6. BACKFILLED when the coverage ledger was extended to
        # D1 — this dataset predates that dimension, so the verdicts were
        # measured and then declared. Future datasets declare first.
        #
        # DIVERGED -> AGREED on a dataset is not the framework improving.
        # It means production's divergence needs a population this
        # narrative does not contain, so the dataset cannot see it. Each is
        # declared so that a dataset silently losing the ability to
        # reproduce a known divergence is a failure rather than a quiet
        # green.
        parity={
            'Q12': 'AGREED', 'Q13': 'AGREED', 'Q14': 'AGREED',
            'Q17': 'AGREED', 'Q18': 'AGREED', 'Q20': 'AGREED',
            'Q22': 'AGREED',
        },

        # D2 — the claim this dataset was written to make, and until
        # 2026-08-08 the one thing about it the registry could not check.
        # `Expectations` had no element for D2, so `Layer.D2_GOLDEN` was
        # dead vocabulary and this had to be verified by hand.
        #
        # The three RESOLVED entries are the surfaces that had never had a
        # CheckedIn reservation to pin to. The four UNRESOLVED are declared
        # deliberately: they say which populations this dataset does NOT
        # carry, so quietly acquiring a company or a group block later
        # would be a failure rather than an unnoticed change.
        golden={
            'main.checkout__inhouse_reservation': 'RESOLVED',
            'main.reservation_folio__inhouse_reservation': 'RESOLVED',
            'pos.room_charges_api__inhouse_reservation': 'RESOLVED',
            # Still absent, and the dataset says so.
            'main.get_company_credit__any_company': 'UNRESOLVED',
            'main.company_detail__any_company': 'UNRESOLVED',
            'groups.detail__any_group': 'UNRESOLVED',
            'reports.night_audit_snapshot__night_audit_log': 'UNRESOLVED',
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

    # -- the coverage ledger ---------------------------------------------
    #
    # BACKFILLED from measurement, 2026-08-08, and it is the only one that
    # will be. This dataset was commissioned before the ledger existed, so
    # its declaration was written against `ds-coverage` output rather than
    # ahead of it. DS-ACT-GROUP onward declare first and are measured
    # after, which is the only order in which the ledger can catch
    # anything.
    #
    # Every entry below traces to the narrative, so the backfill is a
    # record of consequences that were already implied rather than a
    # transcription of whatever the tool happened to print:
    coverage_expectation={
        # The three surfaces that need a CheckedIn reservation. This is the
        # dataset's stated purpose and the D2 claim the registry cannot
        # check for itself.
        'surfaces_added': (
            'main.checkout__inhouse_reservation',
            'main.reservation_folio__inhouse_reservation',
            'pos.room_charges_api__inhouse_reservation',
        ),
        # The narrative declares no night audit, so there is no
        # night_audit_logs row for the snapshot surface to pin to. Stated
        # in the report as the one loss that is not worked around.
        'surfaces_lost': (
            'reports.night_audit_snapshot__night_audit_log',
        ),
        # Eight invariants lose their population. Each follows from
        # something the narrative does not contain, and none of them was
        # visible before the ledger existed:
        'quantities_activated': (),
        # Q15 recomputes the night audit, and there is no night audit.
        'quantities_deactivated': ('Q15',),
        'invariants_deactivated': (
            'INV-A03',   # no extra_charges at all, so nothing to group
            'INV-B01',   # no night audit
            'INV-B02',   # no night audit -> no snapshot to hash
            'INV-B03',   # no night audit -> no closed day to recompute
            'INV-B05',   # no night audit -> no audit sequence
            'INV-C01',   # both stays pay cash, so no OTA head is involved
            'INV-C05',   # same population as INV-C01
            'INV-D07',   # no overpayment_logs row
        ),
        # Nothing is activated. An in-house stay lifts none of the four
        # VACUOUS invariants, which is why ACTIVATION reports 0 claims.
        'invariants_activated': (),
    },

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


# ---------------------------------------------------------------------------
# DS-ACT-CORRECTION
# ---------------------------------------------------------------------------
#
# The first dataset written to activate a VACUOUS invariant, and it targets
# the only one of the four that is RELEASE_BLOCKING.
#
# THE CORRECTION PATTERN, WHICH IS THE WHOLE POINT
# ------------------------------------------------
# Neither table can hold a negative amount — `payments` carries
# `CHECK amount > 0`, `extra_charges` carries `CHECK amount >= 0`. The
# application's answer, documented on both models and implemented in
# `services.post_payment_correction`, is to never mutate the original and
# to post up to two new rows instead:
#
#   REVERSAL     is_correction=1, is_reversal=1, amount = THE ORIGINAL
#   REPLACEMENT  is_correction=1, is_reversal=0, amount = the corrected
#
# both carrying `corrects_id` back to the original. The reversal's amount
# is positive and every caller is required to subtract it.
#
# That requirement is why R-7 had to land before this dataset could declare
# a single figure: the probes summed unsigned and were wrong by twice the
# reversed amount. On production the defect was invisible, because
# production has no correction rows at all — which is the same sentence as
# "INV-D02 is VACUOUS".
#
# The money:
#
#   room, 1 night x 1,000.00                        room revenue  1,000.00
#   GST 5% on the room                              tax              50.00
#   laundry raised in error                +500.00
#   laundry reversal                       -500.00
#   laundry, corrected                     +200.00  charges net     200.00
#   GST on the net laundry, 18%                     tax              36.00
#                                                   ------------------------
#                                                   owed          1,286.00
#   payment taken in error               +1,000.00
#   payment reversal                     -1,000.00
#   payment, corrected                   +1,286.00  collected     1,286.00
#                                                   ------------------------
#                                                   OUTSTANDING       0.00
#
# Settled exactly — but only once the reversals are signed. Measured with
# the pre-R-7 probes the same rows read `outstanding = -3,072.00`.
#
# THE PRODUCTION DEFECT THIS DATASET FOUND
# -----------------------------------------
# `gst_service.compute_stay_gst` — the GST behind `calculate_stay_amount`,
# and therefore behind checkout, the invoice and every report — loops over
# a reservation's extra charges and reads `ec.amount` **unsigned**
# (`gst_service.py:492`). It never calls `signed_extra_charge_amount`,
# which is the very function the codebase provides for this.
#
# So a reversed charge is taxed instead of untaxed. On this narrative:
#
#     laundry raised    500.00 x 18%  =  90.00
#     laundry reversed  500.00 x 18%  =  90.00   <- should be -90.00
#     laundry corrected 200.00 x 18%  =  36.00
#                                       216.00   against a truth of 36.00
#     room            1,000.00 x  5%  =  50.00
#                                       ------
#     compute_stay_gst reports          266.00   against a truth of 86.00
#
# **The guest is charged 180.00 of GST on money that was reversed**, and
# the more times a charge is corrected the further it compounds. Every
# layer downstream of `calculate_stay_amount` inherits it.
#
# Per the standing Wave 0 instruction this is REPORTED AND NOT FIXED. No
# application code is touched. The consequence is declared instead:
# `INV-C02` is expected **VIOLATED**, by exactly 180.00, and the dataset
# is the regression test that will notice when the defect is repaired —
# at which point this expectation must be re-declared with evidence.
#
# It is a new instance of a class already on the register (multiple
# independent definitions of a financial quantity: `tax_lines` says one
# thing, `compute_stay_gst` computes another), and the first one anybody
# has been able to point at, because production has never held a
# correction.
#
# WHAT THIS DATASET DELIBERATELY DOES NOT MODEL
# ----------------------------------------------
# **A tax line for the reversal.** `tax_lines` has no `is_reversal` and no
# `corrects_id` column, so the correction pattern that exists for money
# has **no counterpart for tax**. The declared tax lines therefore cover
# the net taxable supply — the room, and the corrected 200.00 laundry —
# because that is what was actually supplied. How a reversed taxed charge
# is meant to unwind its tax line is a question the schema cannot express,
# and inventing a convention here would mean testing the invention.
#
# Recorded as a schema gap alongside the defect above.
#
# **The closed-audit trigger.** The pattern is called "post-audit
# corrections" and exists because a closed night audit must not be
# mutated. This dataset declares no night audit, so it exercises the
# correction shape without the condition that provokes it. Adding one
# would drag in INV-B02's snapshot hash and INV-B03's recomputation, and a
# hand-written snapshot would either fail both or be tuned until it
# passed.

_ROOM_CORR = 3            # 103, Deluxe.


@dataset(
    dataset_id='DS-ACT-CORRECTION',
    version='1.0',
    title='A charge and a payment, each corrected the way the audit requires',
    purpose=Purpose.ACTIVATE_INVARIANT,

    business_narrative=(
        'Anita Desai stays one night in room 103 on 10 July at 1,050.00 '
        'inclusive of 5% GST. A 500.00 laundry charge is posted to her '
        'folio the same evening.\n\n'
        'On the morning of the 11th, as she checks out, two errors come to '
        'light. The laundry was somebody else\'s and only 200.00 of it was '
        'hers, and the 1,000.00 she was asked for at the desk was short of '
        'what she owed. Neither original row is edited. The laundry charge '
        'is reversed in full and re-posted at 200.00; the payment is '
        'reversed in full and re-posted at 1,286.00. All four new rows name '
        'the row they correct and carry the reason.\n\n'
        'She leaves settled to the rupee, owing nothing, and the folio '
        'shows every step: what was charged, what was wrong with it, and '
        'what replaced it.\n\n'
        'Nothing the hotel DID here is wrong. The correction path worked, '
        'which is the only way to give INV-D02 a population it can hold '
        'over — a dataset that activated it with a broken correction would '
        'prove the rule fires but never that a correct correction passes '
        'it.\n\n'
        'What is wrong is what the system then calculates. '
        'compute_stay_gst reads extra charges unsigned, so it taxes the '
        'reversed 500.00 as well as the corrected 200.00 and reports GST '
        'of 266.00 where the truth is 86.00 — 180.00 of tax on money that '
        'was taken back. INV-C02 is therefore declared VIOLATED, by '
        'exactly that amount. The guest paid what she owed; the engine '
        'believes she still owes 180.00. See the note above the '
        'declaration.\n\n'
        'INV-D02 is the only VACUOUS invariant that is RELEASE_BLOCKING, '
        'and until now the only thing exercising it was a D5 fault '
        'injection. Its own VACUOUS message records the consequence: the '
        'signing logic in signed_extra_charge_amount is untested by live '
        'data. This dataset is the first data of that shape the framework '
        'has ever held.'
    ),

    timeline=(
        Event(date='2026-07-10',
              description='Anita Desai checks into room 103 for one night '
                          'at 1,050.00 inclusive.',
              tables=('guests', 'reservations', 'reservation_rooms',
                      'folios', 'reservation_night_rates', 'tax_lines'),
              amount='1050.00'),
        Event(date='2026-07-10',
              description='A 500.00 laundry charge is posted to her folio.',
              tables=('extra_charges',),
              amount='500.00'),
        Event(date='2026-07-10',
              description='She pays 1,000.00 in cash at the desk.',
              tables=('payments',),
              amount='1000.00'),
        Event(date='2026-07-11',
              description='The laundry is found to be wrong. The original '
                          'row is left untouched; a reversal of 500.00 and '
                          'a replacement of 200.00 are posted, both naming '
                          'the charge they correct.',
              tables=('extra_charges',),
              amount='200.00'),
        Event(date='2026-07-11',
              description='The payment is found to be short. It is reversed '
                          'in full and re-posted at 1,286.00, both rows '
                          'naming the payment they correct.',
              tables=('payments',),
              amount='1286.00'),
        Event(date='2026-07-11',
              description='She checks out settled, is invoiced 1,286.00, '
                          'and the hotel is owed nothing.',
              tables=('reservations',),
              amount='0.00'),
    ),

    provenance=Provenance(
        origin=Origin.SYNTHETIC,
        author='Wave 0.6 / D6 Step 2',
        created='2026-08-08',
        derivation=(
            'Written by hand from the narrative above, following the '
            'correction pattern documented on app.models.Payment and '
            'app.models.ExtraCharge and implemented in '
            'app.services.post_payment_correction. No production row was '
            'copied, transformed or sampled — production contains no '
            'correction of any kind, which is why this dataset exists.'),
        contains_real_guest_data=False,
        disclosure='Publishable. Contains no real guest and no real stay.',
        rationale=(
            'SYNTHETIC by necessity rather than choice: the population is '
            'empty in production, so there is nothing to derive from.'),
    ),

    expectations=Expectations(
        financial={
            'reservations_count': '1',
            'guests_count': '1',
            'folios_count': '1',
            # The original, its reversal and its replacement.
            'payments_count': '3',

            # Gross counts every row that was written, including the two
            # that cancel each other.
            'payments_gross': '3286.00',
            'payments_voided': '0.00',
            # 1,000.00 - 1,000.00 + 1,286.00. This figure is the reason R-7
            # exists: unsigned it reads 3,286.00.
            'payments_net': '1286.00',
            # Both the reversal and the replacement are flagged
            # is_correction, so this is 1,000 + 1,286.
            'payments_corrections': '2286.00',
            'payments_reversals': '1000.00',

            'extra_charges_total': '1200.00',
            'extra_charges_room_rent': '0.00',
            'extra_charges_non_room_rent': '1200.00',
            'extra_charges_reversals': '500.00',
            # 500.00 - 500.00 + 200.00. Unsigned it reads 1,200.00.
            'extra_charges_net': '200.00',
            'extra_charges_non_room_rent_net': '200.00',

            'room_revenue': '1000.00',
            'room_discount': '0.00',

            # The room at 5% and the NET laundry at 18%: 50.00 + 36.00.
            # The reversal has no tax line because `tax_lines` cannot
            # express one — the schema has no is_reversal. What was
            # supplied is the room and 200.00 of laundry, and that is what
            # is taxed.
            #
            # This is the figure the engine disagrees with: it computes
            # 266.00 by taxing the reversed 500.00 as well.
            'tax_total': '86.00',
            # 1,000.00 room + 200.00 laundry.
            'taxable_total': '1200.00',
            'tax_lines_count': '4',
            'tax_base_count': '2',

            'overpayment_total': '0.00',
            'overpayment_count': '0',
            'credit_note_total': '0.00',
            'credit_note_count': '0',
            'void_request_count': '0',
            'corporate_credit_used': '0.00',
            'corporate_bookings': '0',

            'invoice_unrounded_grand_total': '1286.00',
            'invoice_round_off_total': '0.00',
            'invoice_rounded_grand_total': '1286.00',
            'invoice_round_off_rows': '0',

            # 1,000 room + 200 net laundry + 86 tax.
            'charges_net': '1286.00',
            # Settled exactly. With the pre-R-7 probes the same rows read
            # -3,072.00, which is what makes this the sharpest single
            # assertion in the dataset.
            'outstanding': '0.00',
            # R-8. A correction is not a write-off: the charge was
            # reversed on the folio, not credited, so there is no credit
            # note and the two figures agree.
            'net_receivable': '0.00',
        },

        invariants={
            # THE TARGET. Population 4 — a reversal and a replacement in
            # each table — every one carrying a corrects_id that resolves
            # inside its own table.
            'INV-D02': 'HOLDS',

            # Three charges on one folio and one reservation, so the two
            # groupings cannot disagree. Note this is a population
            # DS-ACT-INHOUSE did not have.
            'INV-A03': 'HOLDS',
            # Every payment and every charge carries a folio_id.
            'INV-A02': 'HOLDS',
            # 1,000.00 x 2.5% = 25.00, twice, exactly.
            'INV-A05': 'HOLDS',
            'INV-C03': 'HOLDS',
            'INV-C04': 'HOLDS',
            'INV-D01': 'HOLDS',
            'INV-D03': 'HOLDS',
            'INV-D04': 'HOLDS',
            'INV-D06': 'HOLDS',

            # VIOLATED, and this is the finding rather than a defect in
            # the data. The guest paid 1,286.00 against charges of
            # 1,286.00 and owes nothing; `calculate_stay_amount` believes
            # she owes 180.00, because `compute_stay_gst` taxed the
            # reversed 500.00 (see THE PRODUCTION DEFECT above).
            #
            # Declared rather than dodged. Making it HOLD would mean
            # either charging the guest tax on reversed money or dropping
            # the tax from the narrative, and both would hide a live
            # production defect behind a green dataset.
            #
            # When the defect is repaired this expectation MUST be
            # re-declared with evidence — that is the dataset doing its
            # job, not the dataset breaking.
            'INV-C02': 'VIOLATED',

            # Cash only, so the OTA population is empty (P10).
            'INV-C01': 'VACUOUS',
        },

        # Element 6. BACKFILLED when the coverage ledger was extended to
        # D1 — this dataset predates that dimension, so the verdicts were
        # measured and then declared. Future datasets declare first.
        #
        # DIVERGED -> AGREED on a dataset is not the framework improving.
        # It means production's divergence needs a population this
        # narrative does not contain, so the dataset cannot see it. Each is
        # declared so that a dataset silently losing the ability to
        # reproduce a known divergence is a failure rather than a quiet
        # green.
        #
        # Q02, Q07 and Q09 go AGREED -> DIVERGED here, and that is the
        # finding. All three agree on production only because production
        # holds no correction; the first dataset that contains one makes
        # them disagree. Q09 in particular is "Payments total (signed vs
        # raw)" — the D1 quantity that measures exactly the defect class
        # R-7 fixed in the probes, and it had never been able to fire.
        parity={
            'Q02': 'DIVERGED',   # charge count and total by category
            'Q07': 'DIVERGED',   # tax by component
            'Q09': 'DIVERGED',   # payments total, signed vs raw
            'Q12': 'AGREED', 'Q13': 'AGREED', 'Q14': 'AGREED',
            'Q17': 'AGREED', 'Q22': 'AGREED',
        },
    ),

    rows=(
        ('guests',
         ('id', 'name', 'phone'),
         ((1, 'Anita Desai', '9800000003'),)),

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
         ((1, 1, _ROOM_CORR, _ROOM_TYPE_ID,
           '2026-07-10', '2026-07-11', 1, 'CheckedOut',
           1000.00, 1000.00, 1000.00,
           0.0, 'Walk-in', 'Regular', 'standard',
           '2026-07-10 13:00:00.000000', '2026-07-10 13:00:00.000000',
           'admin',
           '2026-07-11 09:15:00.000000', 'admin', '09:15',
           # The invoice the guest was actually given: 1,000 room + 200
           # laundry + 86 tax. NOT the 1,466.00 compute_stay_gst would
           # produce, because that figure includes tax on money the hotel
           # took back.
           'INV-2026-000001', 1286.00, 0.0, 1286.00,
           0, 1, 0.0, 0.0, 0.0, 0.0, 0.0),)),

        ('reservation_rooms',
         ('id', 'reservation_id', 'room_id', 'is_primary', 'created_at'),
         ((1, 1, _ROOM_CORR, 1, '2026-07-10 13:00:00.000000'),)),

        ('folios',
         ('id', 'reservation_id', 'folio_letter', 'label', 'is_closed',
          'created_at'),
         ((1, 1, 'A', 'Guest', 1, '2026-07-10 13:00:00.000000'),)),

        ('reservation_night_rates',
         ('id', 'reservation_id', 'stay_date', 'room_type_id', 'room_id',
          'standard_rate', 'resolved_rate', 'final_rate', 'discount_amount',
          'rate_source', 'pricing_mode', 'manual_override', 'tax_rate',
          'is_posted', 'is_locked', 'created_at', 'updated_at'),
         ((1, 1, '2026-07-10', _ROOM_TYPE_ID, _ROOM_CORR,
           1000.00, 1000.00, 1000.00, 0.0,
           'base_rate', 'standard', 0, 5, 0, 0,
           '2026-07-10 13:00:00.000000', '2026-07-10 13:00:00.000000'),)),

        ('tax_lines',
         ('id', 'reservation_id', 'charge_source_type', 'charge_source_id',
          'charge_date', 'taxable_amount', 'tax_type', 'tax_rate',
          'tax_amount', 'is_interstate', 'is_exempted', 'sac_code',
          'created_at'),
         ((1, 1, 'room_night', 'night_2026-07-10', '2026-07-10',
           1000.00, 'CGST', 2.5, 25.00, 0, 0, '996311',
           '2026-07-10 13:00:00.000000'),
          (2, 1, 'room_night', 'night_2026-07-10', '2026-07-10',
           1000.00, 'SGST', 2.5, 25.00, 0, 0, '996311',
           '2026-07-10 13:00:00.000000'),
          # The laundry that was actually supplied — charge 3, the
          # corrected 200.00 — at the 18% category rate, split 9 + 9.
          # Charges 1 and 2 cancel and carry no tax line between them,
          # because `tax_lines` has no way to express a reversal.
          (3, 1, 'extra_charge', '3', '2026-07-11',
           200.00, 'CGST', 9.0, 18.00, 0, 0, '999719',
           '2026-07-11 09:05:00.000000'),
          (4, 1, 'extra_charge', '3', '2026-07-11',
           200.00, 'SGST', 9.0, 18.00, 0, 0, '999719',
           '2026-07-11 09:05:00.000000'),)),

        # The correction pair, in the order the desk raised them. The
        # original is row 1 and is never edited — that is the property the
        # whole pattern exists to preserve, and a dataset that mutated it
        # would be modelling the defect rather than the control.
        ('extra_charges',
         ('id', 'reservation_id', 'folio_id', 'description', 'amount',
          'charge_date', 'charge_type', 'charge_category',
          'is_correction', 'is_reversal', 'corrects_id',
          'correction_reason', 'created_at'),
         ((1, 1, 1, 'Laundry', 500.00, '2026-07-10',
           'laundry', 'Laundry', 0, 0, None, None,
           '2026-07-10 19:30:00.000000'),
          (2, 1, 1, 'Laundry - reversal', 500.00, '2026-07-11',
           'laundry', 'Laundry', 1, 1, 1,
           'Charge belonged to another room', '2026-07-11 09:05:00.000000'),
          (3, 1, 1, 'Laundry - corrected', 200.00, '2026-07-11',
           'laundry', 'Laundry', 1, 0, 1,
           'Charge belonged to another room', '2026-07-11 09:05:00.000000'),)),

        ('payments',
         ('id', 'reservation_id', 'folio_id', 'payment_mode_id', 'amount',
          'payment_date', 'reference_number', 'created_at', 'is_voided',
          'is_correction', 'is_reversal', 'corrects_id',
          'correction_reason', 'payment_purpose'),
         ((1, 1, 1, _CASH, 1000.00, '2026-07-10', '',
           '2026-07-10 13:05:00.000000', 0, 0, 0, None, None, 'settlement'),
          (2, 1, 1, _CASH, 1000.00, '2026-07-11', '',
           '2026-07-11 09:10:00.000000', 0, 1, 1, 1,
           'Collected short of the folio total', 'settlement'),
          (3, 1, 1, _CASH, 1286.00, '2026-07-11', '',
           '2026-07-11 09:10:00.000000', 0, 1, 0, 1,
           'Collected short of the folio total', 'settlement'),)),
    ),

    business_date='2026-07-11',

    #: The claim this dataset exists to make. Commissioning checks it
    #: against reality: if INV-D02 were still VACUOUS after building, the
    #: ACTIVATION element fails and the dataset is not commissioned.
    activates_invariants=('INV-D02',),

    # -- the discrimination gate -----------------------------------------
    #
    # Break the link, not the money. Nulling `corrects_id` on the payment
    # reversal leaves every figure in the dataset untouched — the amounts,
    # the balance and the counts are all identical — and turns a traceable
    # correction into exactly what INV-D02 forbids: a negative-signed entry
    # with no original.
    #
    # That is the perturbation worth having. One that moved money would
    # break the financial probes and prove nothing about whether the
    # traceability rule can fail.
    perturbation=(
        'UPDATE payments SET corrects_id = NULL WHERE id = 2',
    ),
    perturbation_breaks=(
        'INV-D02',
    ),

    # -- the coverage ledger, declared BEFORE the dataset was built ------
    #
    # Reasoned from the narrative and the production registries, recorded
    # in evidence/20260808_ds_act_correction_prediction/ before this
    # declaration was written. Any discrepancy against `ds-coverage` is a
    # finding, not a transcription error.
    coverage_expectation={
        # None. Every resolver this dataset satisfies already resolves on
        # production, and it has no CheckedIn reservation, no company and
        # no group block. This is an invariant-activation dataset and the
        # declaration says so rather than implying D2 value it does not
        # have.
        'surfaces_added': (),
        'surfaces_lost': (
            'reports.night_audit_snapshot__night_audit_log',
        ),
        'invariants_activated': (
            'INV-D02',
        ),
        'quantities_activated': (),
        'quantities_deactivated': ('Q15',),   # no night audit
        # Seven, not the eight DS-ACT-INHOUSE lost. INV-A03 is the
        # difference: that dataset had no extra_charges at all, this one
        # has three, so INV-A03 keeps a population and should merely
        # change. It is the one entry that cannot be got right by copying
        # the previous ledger.
        'invariants_deactivated': (
            'INV-B01', 'INV-B02', 'INV-B03', 'INV-B05',
            'INV-C01', 'INV-C05', 'INV-D07',
        ),
    },

    principles=('P9', 'P10', 'P11', 'P14'),
    modes=(Mode.REGRESSION, Mode.INVARIANT_ACTIVATION,
           Mode.CONTINUOUS_VERIFICATION),

    # Six of six, ACTIVATION included: INV-D02 is no longer VACUOUS, and
    # the claim is cross-checked against the evidence on every registry
    # call.
    commissioning_status=Commissioning.COMMISSIONED,
)
def _correction():
    pass


# ---------------------------------------------------------------------------
# DS-ACT-VOIDCN
# ---------------------------------------------------------------------------
#
# Activates INV-D05 — void requests and credit notes must reference what
# they cancel — and lifts Q11, the parity quantity separating refunds from
# voids. Two layers from one narrative, which is why it was taken ahead of
# DS-ACT-GROUP; the evidence is in
# evidence/20260808_ds_act_voidcn_prediction/.
#
# THE PRODUCTION DEFECT THIS DATASET DECLARES
# --------------------------------------------
# `services.post_cancellation_disposition` builds a refund like this:
#
#     refund_payment = Payment(
#         ...
#         payment_purpose   = 'refund',
#         is_reversal       = True,
#         correction_reason = f'Cancellation refund | {reason_clean}',
#     )
#
# **`corrects_id` is never set.** The only four assignments of it in
# `services.py` are inside `post_payment_correction` and
# `post_extra_charge_correction`; the refund path is not one of them.
#
# INV-D02 requires every row flagged `is_correction` OR `is_reversal` to
# carry a resolving `corrects_id`. So **every cancellation refund the
# application issues violates INV-D02** — CRITICAL, RELEASE_BLOCKING.
#
# Never seen because production has issued no refund — the same fact that
# kept INV-D02 VACUOUS until DS-ACT-CORRECTION.
#
# The refund below is modelled EXACTLY as the application builds it, and
# INV-D02 is declared VIOLATED. Giving it a corrects_id would produce a
# green dataset describing an application that does not exist. Reported
# and not repaired: no application code is touched.
#
# The money:
#
#   room, 1 night x 1,000.00                     room revenue   1,000.00
#   GST 5% on the room                           tax               50.00
#   minibar                                      charges          200.00
#   GST 18% on the minibar                       tax               36.00
#                                                ------------------------
#                                                raised         1,286.00
#   guest settles in full                      +1,286.00
#   the desk takes it twice; the duplicate is VOIDED and a void_requests
#   row records who asked and why                    0.00 (excluded)
#   minibar disputed: a credit note is issued
#   for 236.00 and the money refunded            - 236.00
#                                                collected      1,050.00
#                                                ------------------------
#                                                OUTSTANDING      236.00
#
# CREDIT NOTES ARE NOT NETTED BY ANY PROBE — a gap, not a defect
# ----------------------------------------------------------------
# `outstanding` reports 236.00 and that is what the probe measures:
# charges raised, less what was collected. The minibar WAS raised, and a
# credit note is the instrument that writes it off rather than a reversal
# row that removes it.
#
# The true receivable is `outstanding - credit_note_total` = 0.00, and no
# probe computes that. Recorded as a candidate R-8 rather than fixed:
# unlike R-7 this is a MISSING quantity rather than a WRONG one, so it
# bakes no error into the baseline — `outstanding` means what it says.
# Both figures are declared below so the relationship is measurable today.

_ROOM_VOID = 4            # 104, Deluxe.
_ADMIN = 1                # the only user on this installation.


@dataset(
    dataset_id='DS-ACT-VOIDCN',
    version='1.0',
    title='A duplicate payment voided, and a disputed charge credited',
    purpose=Purpose.ACTIVATE_INVARIANT,

    business_narrative=(
        'Vikram Rao stays one night in room 104 on 2 August. The bill is '
        '1,286.00 — 1,050.00 for the room including 5% GST, and 236.00 of '
        'minibar including 18%. He settles in full on the 3rd.\n\n'
        'The desk takes the payment twice. The duplicate is voided rather '
        'than deleted, and a void request records who asked for it and '
        'why, so a reversal of 1,286.00 that never reached the bank is '
        'accounted for rather than silently absent.\n\n'
        'Later that day he disputes the minibar. It is not reversed on the '
        'folio — the charge was raised and the folio says so — instead a '
        'credit note is issued against the invoice for 236.00 and the '
        'money is refunded to him.\n\n'
        'Two cancellation instruments, each naming what it cancels: the '
        'void request names its payment, the credit note names its '
        'reservation and the invoice it credits. That is INV-D05, and this '
        'is the first data of that shape the framework has held.\n\n'
        'One thing here is wrong and it is not the hotel doing it. The '
        'refund row is built the way the application builds every refund — '
        'is_reversal set, corrects_id left null — and INV-D02 forbids '
        'exactly that. The invariant is declared VIOLATED rather than '
        'worked around. See the note above this declaration.'
    ),

    timeline=(
        Event(date='2026-08-02',
              description='Vikram Rao checks into room 104 for one night '
                          'at 1,050.00 inclusive.',
              tables=('guests', 'reservations', 'reservation_rooms',
                      'folios', 'reservation_night_rates', 'tax_lines'),
              amount='1050.00'),
        Event(date='2026-08-02',
              description='236.00 of minibar is posted to his folio, '
                          'including 18% GST.',
              tables=('extra_charges', 'tax_lines'),
              amount='236.00'),
        Event(date='2026-08-03',
              description='He settles 1,286.00 in cash and checks out.',
              tables=('payments', 'reservations'),
              amount='1286.00'),
        Event(date='2026-08-03',
              description='The desk takes the same 1,286.00 a second time. '
                          'It is voided, and a void request records who '
                          'asked and why.',
              tables=('payments', 'void_requests'),
              amount='1286.00'),
        Event(date='2026-08-03',
              description='He disputes the minibar. A credit note for '
                          '236.00 is issued against the invoice and the '
                          'money is refunded.',
              tables=('credit_notes', 'payments'),
              amount='236.00'),
    ),

    provenance=Provenance(
        origin=Origin.SYNTHETIC,
        author='Wave 0.7 / D6 Step 2',
        created='2026-08-08',
        derivation=(
            'Written by hand from the narrative above. The refund row '
            'follows app.services.post_cancellation_disposition field for '
            'field, including the missing corrects_id, because what the '
            'application actually produces is the point of the row. No '
            'production row was copied: production holds no void, no '
            'credit note and no refund.'),
        contains_real_guest_data=False,
        disclosure='Publishable. Contains no real guest and no real stay.',
        rationale=(
            'SYNTHETIC by necessity — all three populations are empty in '
            'production, so there is nothing to derive from.'),
    ),

    expectations=Expectations(
        financial={
            'reservations_count': '1',
            'guests_count': '1',
            'folios_count': '1',
            'payments_count': '3',

            'payments_gross': '2808.00',
            'payments_voided': '1286.00',
            # 1,286.00 settled less 236.00 refunded. The voided duplicate
            # is excluded; the refund subtracts because the application
            # flags it is_reversal.
            'payments_net': '1050.00',
            # The refund carries is_reversal but NOT is_correction, so it
            # counts below and not here. The asymmetry is the
            # application's, not this dataset's.
            'payments_corrections': '0.00',
            'payments_reversals': '236.00',

            'extra_charges_total': '200.00',
            'extra_charges_room_rent': '0.00',
            'extra_charges_non_room_rent': '200.00',
            'extra_charges_reversals': '0.00',
            # Nothing on the folio was reversed. The minibar was credited,
            # which is a different instrument living in credit_notes.
            'extra_charges_net': '200.00',
            'extra_charges_non_room_rent_net': '200.00',

            'room_revenue': '1000.00',
            'room_discount': '0.00',

            'tax_total': '86.00',
            'taxable_total': '1200.00',
            'tax_lines_count': '4',
            'tax_base_count': '2',

            'overpayment_total': '0.00',
            'overpayment_count': '0',
            # The activation targets on the financial side.
            'credit_note_total': '236.00',
            'credit_note_count': '1',
            'void_request_count': '1',
            'corporate_credit_used': '0.00',
            'corporate_bookings': '0',

            'invoice_unrounded_grand_total': '1286.00',
            'invoice_round_off_total': '0.00',
            'invoice_rounded_grand_total': '1286.00',
            'invoice_round_off_rows': '0',

            'charges_net': '1286.00',
            # 1,286.00 raised less 1,050.00 net collected. The credit note
            # is NOT netted here, by design: the minibar WAS raised and the
            # folio says so.
            'outstanding': '236.00',
            # R-8, added because of this dataset. The credit note writes
            # off the 236.00, so nothing is actually still collectable.
            # This is the pair of figures that motivated the quantity: one
            # probe reporting 236.00 and another reporting 0.00, each
            # answering a different question correctly.
            'net_receivable': '0.00',
        },

        invariants={
            # THE TARGET. Population 2: one void_requests row naming its
            # payment, one credit_notes row naming its reservation.
            'INV-D05': 'HOLDS',

            # VIOLATED, and it is the application's doing. The refund row
            # carries is_reversal with no corrects_id because that is how
            # post_cancellation_disposition builds every refund. When the
            # refund path is fixed this must be re-declared with evidence.
            'INV-D02': 'VIOLATED',

            'INV-A02': 'HOLDS',
            'INV-A03': 'HOLDS',
            'INV-A05': 'HOLDS',
            'INV-C03': 'HOLDS',
            'INV-C04': 'HOLDS',
            'INV-D01': 'HOLDS',
            'INV-D03': 'HOLDS',
            'INV-D04': 'HOLDS',
            'INV-D06': 'HOLDS',
            'INV-C01': 'VACUOUS',
        },

        # Element 6. BACKFILLED when the coverage ledger was extended to
        # D1 — this dataset predates that dimension, so the verdicts were
        # measured and then declared. Future datasets declare first.
        #
        # DIVERGED -> AGREED on a dataset is not the framework improving.
        # It means production's divergence needs a population this
        # narrative does not contain, so the dataset cannot see it. Each is
        # declared so that a dataset silently losing the ability to
        # reproduce a known divergence is a failure rather than a quiet
        # green.
        #
        # Q11 is the activation this dataset was written for: refunds
        # separated from voids, VACUOUS on production and DIVERGED here
        # because the night audit counts voided payments as refunds.
        # Q09 diverges for the same reason it does on DS-ACT-CORRECTION —
        # the refund row is flagged is_reversal.
        parity={
            'Q09': 'DIVERGED',   # payments total, signed vs raw
            'Q11': 'DIVERGED',   # refunds vs voids — the activation
            'Q12': 'AGREED', 'Q13': 'AGREED', 'Q14': 'AGREED',
            'Q17': 'AGREED', 'Q22': 'AGREED',
        },
    ),

    rows=(
        ('guests',
         ('id', 'name', 'phone'),
         ((1, 'Vikram Rao', '9800000004'),)),

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
         ((1, 1, _ROOM_VOID, _ROOM_TYPE_ID,
           '2026-08-02', '2026-08-03', 1, 'CheckedOut',
           1000.00, 1000.00, 1000.00,
           0.0, 'Walk-in', 'Regular', 'standard',
           '2026-08-02 14:00:00.000000', '2026-08-02 14:00:00.000000',
           'admin',
           '2026-08-03 10:00:00.000000', 'admin', '10:00',
           'INV-2026-000001', 1286.00, 0.0, 1286.00,
           0, 1, 0.0, 0.0, 0.0, 0.0, 0.0),)),

        ('reservation_rooms',
         ('id', 'reservation_id', 'room_id', 'is_primary', 'created_at'),
         ((1, 1, _ROOM_VOID, 1, '2026-08-02 14:00:00.000000'),)),

        ('folios',
         ('id', 'reservation_id', 'folio_letter', 'label', 'is_closed',
          'created_at'),
         ((1, 1, 'A', 'Guest', 1, '2026-08-02 14:00:00.000000'),)),

        ('reservation_night_rates',
         ('id', 'reservation_id', 'stay_date', 'room_type_id', 'room_id',
          'standard_rate', 'resolved_rate', 'final_rate', 'discount_amount',
          'rate_source', 'pricing_mode', 'manual_override', 'tax_rate',
          'is_posted', 'is_locked', 'created_at', 'updated_at'),
         ((1, 1, '2026-08-02', _ROOM_TYPE_ID, _ROOM_VOID,
           1000.00, 1000.00, 1000.00, 0.0,
           'base_rate', 'standard', 0, 5, 0, 0,
           '2026-08-02 14:00:00.000000', '2026-08-02 14:00:00.000000'),)),

        ('extra_charges',
         ('id', 'reservation_id', 'folio_id', 'description', 'amount',
          'charge_date', 'charge_type', 'charge_category',
          'is_correction', 'is_reversal', 'corrects_id',
          'correction_reason', 'created_at'),
         ((1, 1, 1, 'Minibar', 200.00, '2026-08-02',
           'minibar', 'Minibar', 0, 0, None, None,
           '2026-08-02 21:00:00.000000'),)),

        ('tax_lines',
         ('id', 'reservation_id', 'charge_source_type', 'charge_source_id',
          'charge_date', 'taxable_amount', 'tax_type', 'tax_rate',
          'tax_amount', 'is_interstate', 'is_exempted', 'sac_code',
          'created_at'),
         ((1, 1, 'room_night', 'night_2026-08-02', '2026-08-02',
           1000.00, 'CGST', 2.5, 25.00, 0, 0, '996311',
           '2026-08-02 14:00:00.000000'),
          (2, 1, 'room_night', 'night_2026-08-02', '2026-08-02',
           1000.00, 'SGST', 2.5, 25.00, 0, 0, '996311',
           '2026-08-02 14:00:00.000000'),
          (3, 1, 'extra_charge', '1', '2026-08-02',
           200.00, 'CGST', 9.0, 18.00, 0, 0, '996311',
           '2026-08-02 21:00:00.000000'),
          (4, 1, 'extra_charge', '1', '2026-08-02',
           200.00, 'SGST', 9.0, 18.00, 0, 0, '996311',
           '2026-08-02 21:00:00.000000'),)),

        ('payments',
         ('id', 'reservation_id', 'folio_id', 'payment_mode_id', 'amount',
          'payment_date', 'reference_number', 'created_at', 'is_voided',
          'voided_at', 'voided_by_user_id', 'void_reason',
          'is_correction', 'is_reversal', 'corrects_id',
          'correction_reason', 'payment_purpose'),
         # The settlement.
         ((1, 1, 1, _CASH, 1286.00, '2026-08-03', '',
           '2026-08-03 09:50:00.000000', 0, None, None, None,
           0, 0, None, None, 'settlement'),
          # The duplicate, voided rather than deleted. is_voided excludes
          # it from every net figure while the row survives, which is the
          # whole point of voiding instead of deleting.
          (2, 1, 1, _CASH, 1286.00, '2026-08-03', '',
           '2026-08-03 09:52:00.000000', 1,
           '2026-08-03 09:55:00.000000', _ADMIN,
           'Duplicate capture at the desk',
           0, 0, None, None, 'settlement'),
          # The refund, field for field as post_cancellation_disposition
          # builds it: payment_purpose refund, is_reversal set,
          # is_correction NOT set, corrects_id NULL. That last omission is
          # the INV-D02 violation, and it is the application's.
          (3, 1, 1, _CASH, 236.00, '2026-08-03', '',
           '2026-08-03 16:00:00.000000', 0, None, None, None,
           0, 1, None, 'Cancellation refund | Minibar disputed',
           'refund'),)),

        # The two cancellation instruments INV-D05 exists for.
        ('void_requests',
         ('id', 'payment_id', 'requested_by_user_id', 'requested_at',
          'reason', 'status', 'decided_by_user_id', 'decided_at'),
         ((1, 2, _ADMIN, '2026-08-03 09:54:00.000000',
           'Duplicate capture at the desk', 'approved', _ADMIN,
           '2026-08-03 09:55:00.000000'),)),

        ('credit_notes',
         ('id', 'credit_note_number', 'reservation_id',
          'original_invoice_number', 'reason', 'taxable_amount',
          'cgst_amount', 'sgst_amount', 'igst_amount', 'total_amount',
          'issued_by_user_id', 'issued_at', 'notes'),
         ((1, 'CN-2026-000001', 1, 'INV-2026-000001',
           'Minibar disputed by guest', 200.00, 18.00, 18.00, 0.0, 236.00,
           _ADMIN, '2026-08-03 15:55:00.000000',
           'Refunded in cash the same day'),)),
    ),

    business_date='2026-08-03',

    # INV-D02 as well as the target. The refund row is flagged
    # is_reversal, which puts it in INV-D02's population — so this dataset
    # lifts that invariant out of VACUOUS too, and reports it VIOLATED
    # because of the missing corrects_id.
    #
    # It was NOT in the first draft of this claim, or of the coverage
    # expectation below. The declaration reasoned correctly that INV-D02
    # would be violated and declared it, and then failed to notice that
    # giving an invariant a population IS an activation. Every expectation
    # passed; only the coverage ledger caught it. Recorded rather than
    # quietly added — it is the second time the ledger has found movement
    # that careful reading of the narrative did not.
    activates_invariants=('INV-D05', 'INV-D02'),

    # -- the discrimination gate -----------------------------------------
    #
    # Point the void request at a payment that does not exist. Every
    # figure in the dataset is untouched — no amount, count or balance
    # moves — and the cancellation record stops naming anything real,
    # which is exactly what INV-D05 forbids.
    perturbation=(
        'UPDATE void_requests SET payment_id = 99999 WHERE id = 1',
    ),
    perturbation_breaks=(
        'INV-D05',
    ),

    # -- the coverage ledger, declared BEFORE the dataset was built ------
    # See evidence/20260808_ds_act_voidcn_prediction/prediction.md.
    coverage_expectation={
        'surfaces_added': (),
        'surfaces_lost': (
            'reports.night_audit_snapshot__night_audit_log',
        ),
        # INV-D02 was missed by the prediction and found by the ledger —
        # see the note on activates_invariants above.
        'invariants_activated': (
            'INV-D05', 'INV-D02',
        ),
        # Q11 lifted from VACUOUS. Until the ledger measured D1 this was
        # the dataset's headline claim and had to be checked by hand.
        'quantities_activated': ('Q11',),
        'quantities_deactivated': ('Q15',),   # no night audit
        # Seven, the same set DS-ACT-CORRECTION lost. INV-A03 survives
        # here too, because there is an extra charge on the folio.
        'invariants_deactivated': (
            'INV-B01', 'INV-B02', 'INV-B03', 'INV-B05',
            'INV-C01', 'INV-C05', 'INV-D07',
        ),
    },

    principles=('P9', 'P10', 'P11', 'P14'),
    modes=(Mode.REGRESSION, Mode.INVARIANT_ACTIVATION,
           Mode.CONTINUOUS_VERIFICATION),

    # Six of six, ACTIVATION included: INV-D05 is no longer VACUOUS.
    commissioning_status=Commissioning.COMMISSIONED,
)
def _voidcn():
    pass
