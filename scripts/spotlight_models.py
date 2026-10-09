"""Transit and Rossiter–McLaughlin models for the System Spotlight.

Visualization-grade, not for inference:
  * transit: jaxoplanet Keplerian orbit + quadratic limb darkening
    (falls back to batman if jaxoplanet isn't installed)
  * RM: flux-weighted mean velocity of the occulted patch of a rigidly
    rotating, quadratically limb-darkened star, integrated on a grid over the
    planet disk at each time step. The planet's sky position comes from the
    same orbit as the transit model, so the two stay consistent.

Times are hours from mid-transit. Parameters (dict):
    period [d], rp_rs, a_rs, b or inc_deg, ecc (0), w_deg (90), u [u1, u2]
RM extras:  lambda_deg, vsini_kms, u_rm [u1, u2] (defaults to u)
"""
import numpy as np


def _inclination(p):
    if "inc_deg" in p:
        return np.radians(p["inc_deg"])
    e, w = p.get("ecc", 0.0), np.radians(p.get("w_deg", 90.0))
    # b = a cos i (1 - e^2) / (1 + e sin w)
    cosi = p["b"] / p["a_rs"] * (1 + e * np.sin(w)) / (1 - e ** 2)
    return np.arccos(cosi)


def _central(p):
    """A unit-radius star whose mass puts the planet at a/R* for the given period."""
    from jaxoplanet.constants import G  # R_sun^3 / (M_sun day^2)
    from jaxoplanet.orbits.keplerian import Central
    mass = 4 * np.pi ** 2 * p["a_rs"] ** 3 / (float(G) * p["period"] ** 2)
    return Central(radius=1.0, mass=mass)


def sky_position(hours, p):
    """Planet position on the sky in stellar radii (x along the orbit's
    projected direction of motion, y perpendicular, z toward observer)."""
    t = np.asarray(hours) / 24.0
    try:
        import jax
        jax.config.update("jax_enable_x64", True)
        from jaxoplanet.orbits.keplerian import Central, System

        e = p.get("ecc", 0.0)
        kw = dict(period=p["period"], time_transit=0.0, inclination=_inclination(p), radius=p["rp_rs"])
        if e > 0:
            kw.update(eccentricity=e, omega_peri=np.radians(p.get("w_deg", 90.0)))
        # Unit star; semimajor in stellar radii.
        sys_ = System(_central(p)).add_body(**kw)
        x, y, z = (np.asarray(v) for v in sys_.relative_position(t))
        return x[0], y[0], z[0]
    except ImportError:
        # Circular-orbit fallback
        inc = _inclination(p)
        phi = 2 * np.pi * t / p["period"]
        return (p["a_rs"] * np.sin(phi), -p["a_rs"] * np.cos(phi) * np.cos(inc),
                p["a_rs"] * np.cos(phi))


def transit_flux(hours, p):
    u = list(p.get("u", [0.4, 0.25]))
    try:
        import jax
        jax.config.update("jax_enable_x64", True)
        from jaxoplanet.light_curves import limb_dark_light_curve
        from jaxoplanet.orbits.keplerian import Central, System

        e = p.get("ecc", 0.0)
        kw = dict(period=p["period"], time_transit=0.0, inclination=_inclination(p), radius=p["rp_rs"])
        if e > 0:
            kw.update(eccentricity=e, omega_peri=np.radians(p.get("w_deg", 90.0)))
        sys_ = System(_central(p)).add_body(**kw)
        lc = limb_dark_light_curve(sys_, u)(np.asarray(hours) / 24.0)
        return 1.0 + np.asarray(lc)[:, 0]
    except ImportError:
        import batman
        bp = batman.TransitParams()
        bp.t0, bp.per, bp.rp, bp.a = 0.0, p["period"], p["rp_rs"], p["a_rs"]
        bp.inc = np.degrees(_inclination(p))
        bp.ecc, bp.w, bp.limb_dark, bp.u = p.get("ecc", 0.0), p.get("w_deg", 90.0), "quadratic", u
        return batman.TransitModel(bp, np.asarray(hours) / 24.0).light_curve(bp)


def _intensity(r2, u):
    mu = np.sqrt(np.clip(1 - r2, 0, 1))
    return 1 - u[0] * (1 - mu) - u[1] * (1 - mu) ** 2


def rm_anomaly(hours, p, n=60):
    """RV anomaly in m/s. Positive = planet blocking the receding (red) limb
    is shown as a negative anomaly, as usual."""
    u = list(p.get("u_rm", p.get("u", [0.5, 0.2])))
    lam = np.radians(p["lambda_deg"])
    vsini = p["vsini_kms"] * 1000.0
    k = p["rp_rs"]
    x, y, z = sky_position(hours, p)
    # Grid over the planet disk
    g = np.linspace(-1, 1, n)
    gx, gy = np.meshgrid(g, g)
    inside = gx ** 2 + gy ** 2 <= 1
    gx, gy = gx[inside] * k, gy[inside] * k
    dA = (2 * k / (n - 1)) ** 2
    total = np.pi * (1 - u[0] / 3 - u[1] / 6)  # integrated stellar flux
    out = np.zeros_like(np.asarray(x, dtype=float))
    for i, (xi, yi, zi) in enumerate(zip(x, y, z)):
        if zi <= 0:  # planet behind the star
            continue
        px, py = xi + gx, yi + gy
        r2 = px ** 2 + py ** 2
        on = r2 < 1
        if not on.any():
            continue
        # Coordinate along the stellar equator (perpendicular to the projected spin axis)
        xs = px[on] * np.cos(lam) - py[on] * np.sin(lam)
        I = _intensity(r2[on], u)
        out[i] = -np.sum(I * vsini * xs) * dA / total
    return out
