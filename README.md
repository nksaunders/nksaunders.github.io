# nksaunders.space

Personal academic site, served by GitHub Pages with its built-in Jekyll.
No theme, no framework: one page (`index.html`), one stylesheet, one script.

## Everyday edits

| To change… | Edit |
|---|---|
| Selected publications | `_data/publications.yml` (newest at top; `first_author: true` adds the star) |
| Mentoring | `_data/mentoring.yml` |
| Research areas and figures | `_data/research.yml`, images in `assets/img/` |
| Software | `_data/software.yml` |
| Headline, intro text, links | `index.html`, `_config.yml` |
| CV | replace `files/nsaunders_cv.pdf` |
| Off-sky page text, pets, kitchen, outdoors | `_data/personal.yml`, photos in `assets/img/personal/` |
| Current Favorites (4 posters) | `_data/favorites.yml`, then `scripts/fetch_posters.py` |
| Top ten by decade | the workbook in `films/`, then `scripts/import_films.py` |

Push to the published branch and GitHub rebuilds the site in a minute or two.

## System Spotlight

The homepage panel shows one GTG system at random from
`assets/data/spotlight.json` (generated; don't edit by hand), with up to three
tabs: Transit (binned TESS light curve + model), Orbit (phase-folded RVs,
per-instrument offsets removed) and Obliquity (RM night with the orbit
removed, + model).

To add a system:

1. Copy `spotlight/systems/_template/` to `spotlight/systems/<slug>/` and put
   the light curve and RV files in it (giants CSVs, Keck CSVs, radvel-style
   text files and FEROS tables are all read as-is).
2. Fill in `system.yml` with the paper's parameters.
3. Run `python scripts/build_spotlight.py --plots`, look at
   `spotlight/quicklook/<slug>.png`, and commit `assets/data/spotlight.json`.

Models are visualization-grade (`scripts/spotlight_models.py`): a jaxoplanet
Keplerian orbit with quadratic limb darkening for the transit, and for RM the
flux-weighted rotation velocity of the occulted patch, integrated on a grid
along the same orbit (checked against jaxoplanet.starry's
`surface_radial_velocity` to ~1%). Install with
`pip install -r scripts/requirements.txt`.

## Off-sky page (/off-sky/)

**Decade lists.** Drop the workbook (.xlsx, one tab per decade named "1970s"
etc.) or per-decade CSVs into `films/`. Each sheet needs a header row Rank,
Film, Year, Director; lines above it are ignored. Run
`python scripts/import_films.py` and commit `_data/decades.yml`. Decades are
shown newest first.

**Posters.** Edit `_data/favorites.yml`, then run
`TMDB_API_KEY=... python scripts/fetch_posters.py` (free key from
themoviedb.org → Settings → API). It writes `_data/posters.yml`. Until a film
has a poster, the page shows a typeset title card in its place.

## Preview locally

Double-clicking `index.html` shows an unstyled page full of `{% ... %}` tags;
that's the template before Jekyll fills it in. To see the real thing:

```
pip install python-liquid pyyaml
python scripts/preview.py
```

and open http://localhost:8000 (re-run after edits). If you'd rather use
Jekyll itself: `gem install bundler jekyll && jekyll serve`.

## Fonts

Charis SIL (subset, with the single-story *a* via `ss01`) and IBM Plex Mono,
both under the SIL Open Font License; licenses are in `assets/fonts/`.
