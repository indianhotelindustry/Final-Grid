"""
Core datasets — an ordinary hotel, where everything should hold.

**This module is deliberately empty. D6 Step 1 is infrastructure only.**

Why an empty module rather than no module
-----------------------------------------
``registry.load_all()`` imports this module by name. An empty module with
no declarations makes the registry work and report honestly that nothing
is registered; deleting it would make ``load_all()`` raise ``ImportError``
and every registry call fail. Making ``load_all()`` tolerant of a missing
module instead would hide a genuinely absent declaration file later, which
is the opposite of what this framework is for.

So the platform is proved to work before any business knowledge enters it.

What belongs here
-----------------
The **positive controls**: narratives in which nothing is wrong. A walk-in
stay paid in cash. A stay spanning a closed night audit. A multi-night
stay with tax and a discount.

These exist so that "nothing is wrong" becomes a measured statement rather
than an assumption, and so a perturbation has something normal to be
perturbed away from. A framework that has only ever seen broken data
cannot tell you that correct data passes.

What does NOT belong here
-------------------------
Datasets whose purpose is to activate a VACUOUS control. Those go in
``datasets_activation`` so that the reason a dataset exists is visible
from the file it lives in.

Before writing the first declaration
------------------------------------
Read ``D5_5_CONSISTENCY_AUDIT.md``. The authoritative financial position
is established there, and three of the probes in ``financials.py`` are
known to be wrong (R-1, R-2, R-3 in ``D5_5_REMEDIATION.md``). A dataset
declaring a financial expectation against an uncorrected probe would bake
the probe's defect into the baseline.

Adding one::

    from verification.datasets.model import (
        Event, Expectations, Mode, Origin, Provenance, Purpose, Status,
    )
    from verification.datasets.registry import dataset

    @dataset(
        dataset_id='DS-CORE-WALKIN',
        version='1.0',
        title='...',
        purpose=Purpose.BASELINE,
        business_narrative='...',
        timeline=(Event(date='...', description='...'),),
        provenance=Provenance(origin=Origin.SYNTHETIC, ...),
        expectations=Expectations(financial={...}, invariants={...}),
        rows=(('table', ('col',), (('value',),)),),
        business_date='...',
        perturbation=('UPDATE ...',),
        perturbation_breaks=('...',),
        principles=('P1',),
        modes=(Mode.REGRESSION,),
    )
    def _walkin():
        pass
"""
from __future__ import annotations

# No datasets are declared yet. See the module docstring.
