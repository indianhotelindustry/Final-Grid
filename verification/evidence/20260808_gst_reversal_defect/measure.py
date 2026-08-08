"""Quantify the GST-on-reversed-money defect."""
import os
import sys
from decimal import Decimal as D

sys.path.insert(0, os.getcwd())

from verification.datasets import builder, registry          # noqa: E402
from verification import runner                              # noqa: E402
from verification.dbcopy import CopyHandle                   # noqa: E402

d = registry.get('DS-ACT-CORRECTION')
m = builder.build(d, slot='_gst')
handle = CopyHandle(source_path=m.db_path, copy_path=m.db_path,
                    method='direct', source_hash_before='', source_size=0)
app = runner._build_app(handle)

with app.app_context():
    from app.models import Reservation
    from app.gst_service import (compute_stay_gst, get_room_gst_rate,
                                 get_category_gst_rate)

    r = Reservation.query.get(1)
    room_rate = get_room_gst_rate(D('1000'), r.room_type)
    laundry_rate = get_category_gst_rate('Laundry')
    print('room GST rate      : %s%%' % room_rate)
    print('laundry GST rate   : %s%%' % laundry_rate)
    print()
    room_gst = (D('1000') * room_rate / D('100')).quantize(D('0.01'))
    gross_extras = D('1200')       # 500 + 500 + 200, unsigned
    net_extras = D('200')          # 500 - 500 + 200, signed
    gross_gst = (D('500') * laundry_rate / D('100')).quantize(D('0.01')) * 2 \
        + (D('200') * laundry_rate / D('100')).quantize(D('0.01'))
    net_gst = (net_extras * laundry_rate / D('100')).quantize(D('0.01'))
    print('room GST           : %s' % room_gst)
    print('extras GST as computed (unsigned, %s): %s'
          % (gross_extras, gross_gst))
    print('extras GST if signed   (net, %s)     : %s' % (net_extras, net_gst))
    print()
    print('compute_stay_gst reports : %s' % compute_stay_gst(r))
    print('it should report         : %s' % (room_gst + net_gst))
    print('GST charged on reversed money: %s' % (gross_gst - net_gst))

builder.discard(m)
