#!/usr/bin/env python
"""Make the Spotlight light curve for one system with the giants pipeline.

    python scripts/giants_lightcurve.py toi-6029

Reads spotlight/systems/<slug>/system.yml (transit.tic, and optionally
transit.sectors), runs giants on the TESS FFI cutouts, removes slow
variability with the transit masked out, and writes
spotlight/systems/<slug>/transit.csv (columns: time [BTJD], flux).
Then run  python scripts/build_spotlight.py --only <slug>.

Needs the giants package (pip install git+https://github.com/nksaunders/giants)
and network access to MAST. Downloads are cached by lightkurve.
"""
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    folder = ROOT / "spotlight" / "systems" / sys.argv[1]
    cfg = yaml.safe_load((folder / "system.yml").read_text())
    tr = cfg["transit"]

    import giants

    target = giants.Target(ticid=int(tr["tic"]))
    target.fetch_and_clean_data(sectors=tr.get("sectors"), flatten=False)
    lc = target.lc.remove_nans().normalize()

    mask = lc.create_transit_mask(period=tr["period"], transit_time=tr["t0"],
                                  duration=1.5 * tr["duration_hours"] / 24.0)
    lc = lc.flatten(window_length=tr.get("flatten_window", 301), mask=mask)

    out = folder / "transit.csv"
    np.savetxt(out, np.c_[lc.time.value, lc.flux.value], delimiter=",",
               header="time,flux", comments="", fmt="%.6f")
    print(f"wrote {out.relative_to(ROOT)}: {len(lc)} points")


if __name__ == "__main__":
    main()
