#!/usr/bin/env python
"""Build assets/data/spotlight.json for the homepage System Spotlight.

Each system lives in its own folder:

    spotlight/systems/<slug>/system.yml      parameters + which data files to use
    spotlight/systems/<slug>/<data files>    light curve, RVs, RM RVs

Folders whose name starts with "_" (like _template) are skipped.
Run from the repository root:

    python scripts/build_spotlight.py               # rebuild everything
    python scripts/build_spotlight.py --only toi-6029   # rebuild one, keep the rest
    python scripts/build_spotlight.py --plots       # also write quick-look PNGs
    python scripts/build_spotlight.py --demo        # illustrative placeholder data

Then commit assets/data/spotlight.json. Visualization only: parameters come
from the papers; nothing here is fitted except per-instrument RV offsets, an
optional linear trend on the RM night, and a small ephemeris refinement so
multi-year photometry folds cleanly.

Requirements: numpy, pyyaml, jaxoplanet (or batman-package); matplotlib for --plots.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spotlight_models as models  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SYSTEMS = ROOT / "spotlight" / "systems"
OUT = ROOT / "assets" / "data" / "spotlight.json"
MAX_MODEL_POINTS = 300
BTJD = 2457000.0


# ---------------------------------------------------------------- helpers
def to_btjd(t):
    t = np.asarray(t, dtype=float)
    return t - BTJD if np.nanmedian(t) > 2.4e6 else t


def hours_from_midtransit(time, period, t0):
    phase = ((np.asarray(time) - t0 + 0.5 * period) % period) - 0.5 * period
    return phase * 24.0


def bin_series(x, y, width, xmin, xmax):
    edges = np.arange(xmin, xmax + width, width)
    idx = np.digitize(x, edges) - 1
    bx, by, be = [], [], []
    for i in range(len(edges) - 1):
        m = idx == i
        n = m.sum()
        if n < 3:
            continue
        bx.append(x[m].mean())
        by.append(np.median(y[m]))
        be.append(1.2533 * y[m].std(ddof=1) / np.sqrt(n))
    return np.array(bx), np.array(by), np.array(be)


def thin(x, y, n=MAX_MODEL_POINTS):
    if len(x) <= n:
        return x, y
    keep = np.linspace(0, len(x) - 1, n).round().astype(int)
    return x[keep], y[keep]


def rnd(a, digits):
    return [round(float(v), digits) for v in a]


def limb_darkening(d, default):
    """u: [u1, u2] or Kipping q: [q1, q2]."""
    if d and "u" in d:
        return list(d["u"])
    if d and "q" in d:
        q1, q2 = d["q"]
        return [2 * np.sqrt(q1) * q2, np.sqrt(q1) * (1 - 2 * q2)]
    return default


def eccentricity(o):
    """e, omega [deg] from e/w_deg or secosw/sesinw."""
    if "secosw" in o:
        e = o.get("ecc", o["secosw"] ** 2 + o["sesinw"] ** 2)
        w = np.degrees(np.arctan2(o["sesinw"], o["secosw"]))
        return float(e), float(w)
    return float(o.get("ecc", 0.0)), float(o.get("w_deg", 90.0))


def orbit_params(cfg):
    o = cfg["orbit"]
    e, w = eccentricity(o)
    p = {"period": o["period"], "rp_rs": o["rp_rs"], "a_rs": o["a_rs"], "ecc": e, "w_deg": w}
    if "inc_deg" in o:
        p["inc_deg"] = o["inc_deg"]
    elif "cos_i" in o:
        p["inc_deg"] = float(np.degrees(np.arccos(o["cos_i"])))
    else:
        p["b"] = o["b"]
    return p


def tweak(p, d):
    """Chi-by-eye overrides for the plotted model only (see the 'tweak:' keys in system.yml).
    Any of b, rp_rs, a_rs, inc_deg, vsini_kms and u replace the paper values (u is the limb
    darkening of whichever tab the tweak sits under); shift_minutes moves the model in time."""
    t = dict((d or {}).get("tweak") or {})
    shift = float(t.pop("shift_minutes", 0.0)) / 60.0
    if "b" in t:
        p.pop("inc_deg", None)
    if "inc_deg" in t:
        p.pop("b", None)
    if "u" in t:
        p["u_rm" if "u_rm" in p else "u"] = list(t.pop("u"))
    p.update({k: v for k, v in t.items() if k in ("b", "rp_rs", "a_rs", "inc_deg", "vsini_kms")})
    return shift


def impact_parameter(p):
    if "b" in p:
        return p["b"]
    return p["a_rs"] * np.cos(np.radians(p["inc_deg"]))


def duration_hours(p):
    b, k, a = impact_parameter(p), p["rp_rs"], p["a_rs"]
    sini = np.sqrt(1 - (b / a) ** 2)
    return float(p["period"] / np.pi * np.arcsin(np.sqrt((1 + k) ** 2 - b ** 2) / (a * sini)) * 24)


# ---------------------------------------------------------------- readers
def read_table(path, fmt=None, tel=None):
    """Return dict(time, value, err) from the formats in use:
    csv  — '#time,flux,flux_err' (Keck RVs in km/s, light curves)
    radvel — whitespace 'time mnvel errvel tel ...' (m/s), optional tel filter
    feros — whitespace 'ID BJD RV RVe ...' (m/s)
    ts — whitespace 'time flux' (no header)
    fits — lightkurve LIGHTCURVE table (TIME, FLUX, FLUX_ERR, QUALITY)
    """
    path = Path(path)
    if path.suffix.lower() in (".fits", ".fit"):  # lightkurve-style LIGHTCURVE extension
        from astropy.io import fits
        with fits.open(path) as h:
            d = h[1].data
            q = d["QUALITY"] == 0 if "QUALITY" in d.columns.names else np.ones(len(d), bool)
            return (np.asarray(d["TIME"], float)[q], np.asarray(d["FLUX"], float)[q],
                    np.asarray(d["FLUX_ERR"], float)[q])
    text = path.read_text().splitlines()
    head = text[0].lstrip("#").strip().lower()
    fmt = fmt or ("csv" if "," in text[0] else "radvel" if head.startswith("time") else
                  "feros" if head.startswith("id") else "ts")
    if fmt == "csv":
        arr = np.genfromtxt(path, delimiter=",", skip_header=1, dtype=float, usecols=(0, 1, 2))
        return arr[:, 0], arr[:, 1], arr[:, 2]
    rows = [r.split() for r in text if r.strip() and not r.lstrip().startswith("#")]
    if fmt == "radvel":
        rows = rows[1:]
        if tel:
            rows = [r for r in rows if len(r) > 3 and r[3] == tel]
        a = np.array([[float(r[0]), float(r[1]), float(r[2])] for r in rows])
    elif fmt == "feros":
        a = np.array([[float(r[1]), float(r[2]), float(r[3])] for r in rows[1:]])
    else:  # ts
        a = np.array([[float(r[0]), float(r[1]), np.nan] for r in rows])
    return a[:, 0], a[:, 1], a[:, 2]


# ---------------------------------------------------------------- Keplerian RV
def kepler_rv(t, P, t0, K, e, w_deg):
    """Stellar RV [m/s] with transit time t0 (same units as t)."""
    w = np.radians(w_deg)
    f_tr = np.pi / 2 - w
    E_tr = 2 * np.arctan(np.sqrt((1 - e) / (1 + e)) * np.tan(f_tr / 2))
    M_tr = E_tr - e * np.sin(E_tr)
    M = 2 * np.pi * (np.asarray(t) - t0) / P + M_tr
    E = M.copy()
    for _ in range(50):
        E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
    f = 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))
    return K * (np.cos(f + w) + e * np.cos(w))


# ---------------------------------------------------------------- transit
def detrend(t, f, P, t0, dur, window_hours):
    """Divide out slow variability with a running median of the out-of-transit
    points (transit masked), e.g. for raw light curves of oscillating giants."""
    order = np.argsort(t)
    t, f = t[order], f[order]
    oot = np.abs(hours_from_midtransit(t, P, t0)) > 0.75 * dur
    to, fo = t[oot], f[oot]
    half = window_hours / 48.0
    lo, hi = np.searchsorted(to, t - half), np.searchsorted(to, t + half)
    trend = np.array([np.median(fo[a:b]) if b - a > 5 else np.nan for a, b in zip(lo, hi)])
    good = np.isfinite(trend)
    return t[good], f[good] / trend[good]


def refine_ephemeris(time, flux, cfg, dur):
    """Small (period, t0) grid search so multi-year data folds cleanly."""
    o = cfg["orbit"]
    P0, T0 = o["period"], o["t0"]
    sigP = o.get("period_err", 0.0)
    h = np.linspace(-0.75 * dur, 0.75 * dur, 400)
    model = models.transit_flux(h, orbit_params(cfg))
    best = (np.inf, P0, T0)
    for P in (np.linspace(P0 - 4 * sigP, P0 + 4 * sigP, 41) if sigP else [P0]):
        for dt in np.linspace(-3, 3, 121) / 24.0:
            x = hours_from_midtransit(time, P, T0 + dt)
            near = np.abs(x) < dur
            if near.sum() < 20:
                continue
            chi = np.sum((flux[near] - np.interp(x[near], h, model, left=1, right=1)) ** 2)
            if chi < best[0]:
                best = (chi, P, T0 + dt)
    _, P, T = best
    print(f"  ephemeris refined: P {P0:.6f}→{P:.6f} d, t0 shift {(T - T0) * 24:+.2f} h")
    return P, T


def transit_block(cfg, folder, dur):
    tr, o = cfg["transit"], cfg["orbit"]
    P, t0 = o["period"], o["t0"]
    half = tr.get("window_hours", 1.7 * dur) / 2.0
    t, f, _ = read_table(folder / tr["data"])
    t = to_btjd(t)
    good = np.isfinite(t) & np.isfinite(f)
    if tr.get("time_range"):  # BTJD; e.g. only the sectors the ephemeris is good for
        good &= (t >= tr["time_range"][0]) & (t <= tr["time_range"][1])
    t, f = t[good], f[good]
    if np.nanmedian(np.abs(f)) < 0.5:  # stored as flux - 1
        f = f + 1.0
    if tr.get("detrend_hours"):
        t, f = detrend(t, f, P, t0, dur, tr["detrend_hours"])
    if tr.get("refine", True):
        P, t0 = refine_ephemeris(t, f, cfg, dur)
    x = hours_from_midtransit(t, P, t0)
    keep = np.abs(x) <= half
    x, f = x[keep], f[keep]
    oot = np.abs(x) > 0.6 * dur
    if oot.any():
        f = f / np.median(f[oot])
    bx, by, be = bin_series(x, f, tr.get("bin_minutes", 30) / 60.0, -half, half)
    p = orbit_params(cfg)
    p["u"] = limb_darkening(tr, [0.4, 0.25])
    shift = tweak(p, tr)
    mx = np.linspace(-half, half, MAX_MODEL_POINTS)
    my = models.transit_flux(mx - shift, p)
    dil = tr.get("dilution")
    if dil == "auto":  # fraction of the aperture flux from the target, matched to the data
        dm = 1 - models.transit_flux(x - shift, p)
        dil = float(np.clip(np.sum(dm * (1 - f)) / np.sum(dm * dm), 0.05, 1.0))
        print(f"  dilution (auto): {dil:.2f} of the aperture flux from the target")
    if dil:
        my = 1 - (1 - my) * dil
    out = {"x": rnd(bx, 3), "y": rnd(by, 6), "yerr": rnd(be, 6),
           "model_x": rnd(mx, 3), "model_y": rnd(my, 6)}
    if tr.get("caption"):
        out["caption"] = tr["caption"]
    return out, (P, t0)


# ---------------------------------------------------------------- orbit (RV)
def rv_block(cfg, folder, eph, dur):
    rv = cfg.get("rv")
    if not rv:
        return None
    o = cfg["orbit"]
    P, t0 = eph
    e, w = eccentricity(o)
    K = rv["K"]
    xs, ys, es, inst, labels = [], [], [], [], []
    for i, d in enumerate(rv["data"]):
        t, v, s = read_table(folder / d["file"], d.get("format"), d.get("tel"))
        t = to_btjd(t)
        v, s = v * d.get("scale", 1.0), s * d.get("scale", 1.0)
        if rv.get("exclude_transit"):  # drop epochs inside the transit window (RM-affected)
            out_tr = np.abs(hours_from_midtransit(t, P, t0)) > 0.5 * dur
            t, v, s = t[out_tr], v[out_tr], s[out_tr]
        s = np.sqrt(s ** 2 + d.get("jitter", 0.0) ** 2)  # fitted jitter in quadrature, as in the paper
        kep = kepler_rv(t, P, t0, K, e, w)
        wgt = 1 / s ** 2
        offset = np.sum(wgt * (v - kep)) / np.sum(wgt)
        ph = ((t - t0) / P + 0.5) % 1 - 0.5
        xs += list(ph); ys += list(v - offset); es += list(s); inst += [i] * len(t)
        labels.append(d["label"])
    mx = np.linspace(-0.5, 0.5, MAX_MODEL_POINTS)
    my = kepler_rv(t0 + mx * P, P, t0, K, e, w)
    order = np.argsort(xs)
    return {"x": rnd(np.array(xs)[order], 4), "y": rnd(np.array(ys)[order], 1),
            "yerr": rnd(np.array(es)[order], 1), "inst": [int(inst[j]) for j in order],
            "labels": labels, "K": K, "model_x": rnd(mx, 4), "model_y": rnd(my, 1)}


# ---------------------------------------------------------------- RM
def rm_block(cfg, folder, eph, dur):
    rm = cfg.get("rm")
    if not rm:
        return None
    o = cfg["orbit"]
    P, t0 = eph
    e, w = eccentricity(o)
    p = orbit_params(cfg)
    p.update(lambda_deg=rm["lambda_deg"], vsini_kms=rm["vsini_kms"],
             u_rm=limb_darkening(rm, [0.5, 0.2]))
    shift = tweak(p, rm)
    out = {"x": [], "y": []}
    half = 0.8 * dur
    if rm.get("data"):
        t, v, s = read_table(folder / rm["data"], rm.get("format"))
        t = to_btjd(t)
        v, s = v * rm.get("scale", 1.0), s * rm.get("scale", 1.0)
        s = np.sqrt(s ** 2 + rm.get("jitter", 0.0) ** 2)
        x = hours_from_midtransit(t, P, t0)
        # Remove the orbit, then an offset (+ optional slope) against the RM model
        resid = v - kepler_rv(t, P, t0, rm.get("K", cfg.get("rv", {}).get("K", 0.0)), e, w)
        model_at = models.rm_anomaly(x - shift, p)
        A = np.vstack([np.ones_like(x)] + ([x] if rm.get("slope", False) else [])).T
        coef, *_ = np.linalg.lstsq(A / s[:, None], (resid - model_at) / s, rcond=None)
        v = resid - A @ coef
        out = {"x": rnd(x, 3), "y": rnd(v, 1), "yerr": rnd(s, 1)}
        half = max(half, float(np.max(np.abs(x))) + 0.3)
    mx = np.linspace(-half, half, MAX_MODEL_POINTS)
    out["model_x"], out["model_y"] = rnd(mx, 3), rnd(models.rm_anomaly(mx - shift, p), 1)
    out["lambda_deg"] = rm["lambda_deg"]
    if "lambda_err" in rm:
        out["lambda_err"] = rm["lambda_err"]
    out["b"] = round(float(impact_parameter(p)), 3)
    return out


# ---------------------------------------------------------------- demo
def demo_systems():
    """Illustrative placeholders so the page works before real data exists."""
    rng = np.random.default_rng(4)
    p = {"period": 5.0, "rp_rs": 0.06, "a_rs": 6.5, "b": 0.3, "u": [0.4, 0.25]}
    mx = np.linspace(-5, 5, MAX_MODEL_POINTS)
    my = models.transit_flux(mx, p)
    bx = np.arange(-5, 5, 0.5) + 0.25
    by = models.transit_flux(bx, p) + rng.normal(0, 4e-4, bx.size)
    return [{"id": "demo", "name": "Example system", "description": "Illustrative data",
             "paper": {}, "example": True,
             "transit": {"x": rnd(bx, 3), "y": rnd(by, 6), "model_x": rnd(mx, 3), "model_y": rnd(my, 6)}}]


# ---------------------------------------------------------------- main
def build_one(folder):
    cfg = yaml.safe_load((folder / "system.yml").read_text())
    dur = cfg["transit"].get("duration_hours") or duration_hours(orbit_params(cfg))
    transit, _ = transit_block(cfg, folder, dur)
    # RVs and the RM night use the published ephemeris: it was fit jointly with
    # those data, while the refinement above only serves to fold the photometry.
    eph = (cfg["orbit"]["period"], cfg["orbit"]["t0"])
    entry = {"id": folder.name, "name": cfg["name"], "description": cfg.get("description", ""),
             "paper": cfg.get("paper", {}), "transit": transit}
    rv = rv_block(cfg, folder, eph, dur)
    if rv:
        entry["rv"] = rv
    rm = rm_block(cfg, folder, eph, dur)
    if rm:
        entry["rm"] = rm
    if cfg.get("order") is not None:
        entry["order"] = cfg["order"]
    return entry


def quicklook(entry, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = [k for k in ("transit", "rv", "rm") if k in entry]
    fig, axes = plt.subplots(1, len(panels), figsize=(4.2 * len(panels), 3.2))
    for ax, k in zip(np.atleast_1d(axes), panels):
        d = entry[k]
        ax.errorbar(d["x"], d["y"], d.get("yerr"), fmt="o", ms=3, color="0.4", lw=0.8)
        ax.plot(d["model_x"], d["model_y"], color="C3")
        ax.set_title(f"{entry['name']} — {k}")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="rebuild only these system folders; keep the others")
    ap.add_argument("--plots", action="store_true", help="write quick-look PNGs to spotlight/quicklook/")
    ap.add_argument("--demo", action="store_true", help="write illustrative placeholder data")
    args = ap.parse_args()

    if args.demo:
        systems = demo_systems()
    else:
        folders = sorted(f for f in SYSTEMS.iterdir() if f.is_dir() and not f.name.startswith("_")
                         and (f / "system.yml").exists())
        existing = {}
        if args.only and OUT.exists():
            existing = {s["id"]: s for s in json.loads(OUT.read_text()).get("systems", []) if not s.get("example")}
        systems = []
        for f in folders:
            if args.only and f.name not in args.only and f.name in existing:
                systems.append(existing[f.name])
                continue
            print(f"building {f.name} ...")
            entry = build_one(f)
            systems.append(entry)
            if args.plots:
                (ROOT / "spotlight" / "quicklook").mkdir(exist_ok=True)
                quicklook(entry, ROOT / "spotlight" / "quicklook" / f"{f.name}.png")
        systems.sort(key=lambda s: (s.get("order", 999), s["name"]))
        if not systems:
            sys.exit("No systems found in spotlight/systems/ (folders starting with _ are skipped).")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"version": 2, "systems": systems}, separators=(",", ":")))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(systems)} systems, {OUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
