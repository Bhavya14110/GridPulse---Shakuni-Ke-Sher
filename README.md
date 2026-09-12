# GridPulse

**AI-powered renewable generation forecasting for grid operators.**

GridPulse takes the same weather forecast a utility already receives, converts it
into a 24–72 hour power forecast with a trained ML model, flags the hours where
generation will breach the site's operating limits, and explains exactly what to
do about each one.

Built by team **Shakuni Ke Sher** for the Hackout hackathon — theme: Renewable
Energy Intelligence.

---

## The pipeline

```
  Open-Meteo forecast API  (free, no API key)
        │   future GHI · direct/diffuse radiation · cloud cover
        │   temperature · wind speed at 10 m and 100 m
        ▼
  Feature builder                              backend/app/services/feature_builder.py
        │   cyclical time · solar geometry · clear-sky index
        │   wind shear · lagged + rolling generation
        ▼
  XGBoost model, one per technology            backend/ml/train_model.py
        │   trained on 15 months of physics-derived history
        │   predicts capacity factor, run recursively over the horizon
        ▼
  Rule engine                                  backend/app/services/alert_engine.py
        │   over-generation · under-generation · ramp events
        │   measured against each site's real limits
        ▼
  Recommendation engine                        backend/app/services/recommendation_engine.py
        │   curtail · charge/dispatch storage · backup · spinning reserve
        │   each with a reason sentence built from the actual numbers
        ▼
  Dashboard                                    frontend/
```

This is how solar and wind forecasting genuinely works in industry: you do not
forecast power directly, you forecast weather and then convert it to power. The
conversion step is the model. Everything downstream is deterministic and
explainable, which is what an operator about to curtail 100 MW actually needs.

---

## Quick start

Prerequisites: **Python 3.10+** and **Node 18+**. Nothing else — no API keys, no
accounts, no database server.

```bash
# 1. Backend
cd gridpulse/backend
pip install -r requirements.txt

python seed_data.py                      # create the DB + six demo sites
pip install -r requirements-train.txt    # adds scikit-learn, for training only

python ml/build_historical_dataset.py    # pull 15 months of weather, ~60s
python ml/train_model.py                 # train solar + wind models, ~30s
python ml/verify_tree_model.py           # confirm the numpy scorer matches XGBoost

uvicorn app.main:app --reload --port 8000
```

```bash
# 2. Frontend (new terminal)
cd gridpulse/frontend
npm install
npm run dev
```

Open **http://localhost:3000**. API docs live at **http://localhost:8000/docs**.

The backend warms its forecast cache a couple of seconds after startup, so give
it ~30 seconds before the first page load if you want it instant.

### Configuration

Everything has a working default. To override anything, copy `.env.example` to
`.env` at the repo root:

```bash
cp .env.example .env
```

Open-Meteo requires no key. The `.env` pattern is in place for anything you add
later that does — no secrets go in committed code.

---

## Where the training data comes from

Nobody hands out utility SCADA data during a hackathon, and generating random
numbers would teach a model nothing. So GridPulse builds a **physics-derived
historical record** instead:

1. `build_historical_dataset.py` pulls **15 months of real ERA5 reanalysis
   weather** for each site from Open-Meteo's archive API.
2. It replays that weather through standard first-order generation models:

   **Solar** — performance-ratio model with a temperature derate:

   ```
   P = capacity × (GHI / 1000) × 0.78 × (1 − 0.004 × (T_cell − 25))
   T_cell = T_ambient + 0.03 × GHI
   ```

   **Wind** — a four-region turbine power curve on hub-height (100 m) wind:
   zero below 3.5 m/s cut-in, cubic between cut-in and 12.5 m/s rated, flat at
   rated up to 25 m/s, zero above cut-out.

3. It adds 6% proportional noise so the mapping isn't perfectly deterministic —
   real arrays have soiling, wake effects and inverter clipping.

The result is a weather-correlated, physically plausible generation history that
carries all the structure that matters: the diurnal cycle, the seasonal swing,
cloud events, storm shutdowns, the summer temperature derate. That structure is
what the model learns.

**Swapping in real data is a file swap.** Point `train_model.py` at a CSV of
actual SCADA output with the same columns and nothing else in the pipeline
changes.

---

## Model performance

From the most recent training run (`backend/ml/saved_models/metrics.json`, which
is also what the dashboard's model page reads):

| | Solar | Wind |
|---|---|---|
| MAE | **0.97%** of capacity | **1.43%** of capacity |
| RMSE | 1.92% of capacity | 2.28% of capacity |
| R² | 0.9931 | 0.9932 |
| vs. persistence baseline | **81.4% better** | **75.9% better** |
| Held-out hours | 6,579 | 6,579 |

Trained on 65,808 site-hours across six sites and four continents.

**Two things make these numbers defensible rather than decorative:**

*The split is chronological.* We hold out the most recent 20% of the record and
never touch it during training. Randomly shuffling hourly time-series data lets
the model see 13:00 and 15:00 while predicting 14:00, which inflates scores
enormously and means nothing operationally.

*The persistence baseline is the honest comparison.* "Assume the next hour looks
like this one" is what a control room does without a model. Beating it by 76–81%
on unseen hours is a real result.

**And one caveat we state up front:** the R² figures are very high because the
training targets come from a physics model plus noise, so the mapping the model
is learning genuinely exists in the data. Against real SCADA, day-ahead solar
forecasts typically land around 4–8% of capacity MAE — real plants also have
outages, soiling and grid curtailment that no weather feed predicts. Read these
numbers as *the model correctly learned the weather-to-power relationship*, not
as *this would score this well on a live fleet*.

---

## Flagging and recommendations

Rule-based and fully traceable. The forecast is ML; the decision is not. An
operator needs to see the comparison, not be told a black box disagreed with
them.

**Flags**

| Rule | Condition |
|---|---|
| Over-generation | forecast > 85% of the site's **grid export limit** |
| Under-generation | forecast < the higher of 15% of capacity and the site's **firm delivery schedule** |
| Ramp | hour-over-hour swing > 25% of capacity |

Two of those compare against something more specific than nameplate, because
reality does:

- A plant that can make 180 MW behind a 95 MW substation is over-generating at
  81 MW, whatever headroom the panels still have. Grid-connection constraints are
  the single biggest cause of real curtailment.
- A plant that sold 45 MW day-ahead is short at 30 MW, even though 30 MW is a
  perfectly healthy output. That's the number a trader is exposed on.

Sites without those constraints fall back to the plain percentage-of-capacity
rules. Every threshold is per-site and editable.

**Recommendations**

| Situation | Action |
|---|---|
| Over-generation, battery has headroom | Charge storage with the surplus |
| Over-generation, no headroom | Curtail, capped at the binding limit |
| Under-generation | Dispatch storage first, then secure replacement supply |
| Sharp ramp down | Hold spinning reserve, synchronised before the ramp |
| Sharp ramp up | Confirm downstream absorption capacity |

The storage branch is quantitative, not a lookup: it works out how many MWh the
surplus is and how many the battery can actually take, and when the battery
covers only part of it, it recommends **both** — charge what fits, curtail the
rest. It also tracks state of charge forward through the horizon, so charging at
noon correctly reduces what's available three hours later.

Each recommendation carries a `reason` string assembled from the same numbers
the chart is drawing. A real one, verbatim from the API:

> Forecast peaks at 100.6 MW across 4h (06:00–09:00 UTC on 13 Sep), 106% of the
> 95.0 MW substation export limit. The 60 MWh battery is already at 100% and has
> no headroom left, leaving 9.2 MWh with nowhere to go — issue a curtailment
> instruction capped at 95.0 MW export, trimming up to 5.6 MW at the peak hour.

If the forecast changes, that sentence changes with it. Nothing in the UI is
hardcoded demo text.

---

## The demo portfolio

Six real locations, seeded by `backend/seed_data.py`. Five run on purely live
weather with nothing staged:

| Site | Type | Capacity | Location |
|---|---|---|---|
| Bhadla Phase III | Solar | 180 MW | Rajasthan, India |
| Mojave Ridge Solar | Solar | 92 MW | California, USA |
| Atacama Solar One | Solar | 110 MW | Antofagasta, Chile |
| Gujarat Coastal Wind | Wind | 120 MW | Jamnagar, India |
| North Sea Alpha | Wind | 240 MW | Offshore Denmark |
| Texas Panhandle Wind | Wind | 150 MW | Texas, USA |

**Bhadla Phase III is the hero demo site**, and it's worth being explicit about
how it's set up. Real weather on judging day might just be flat, which would make
the system look weak through no fault of its own. Rather than fake its numbers,
we gave it two entirely ordinary operating constraints that guarantee its 72h
window contains both event types on any day of the year:

- **A 95 MW substation export limit** against 180 MW of panels. Midday output
  exceeds what the grid connection accepts → over-generation fires → curtailment
  is recommended. DC-oversized farms behind undersized substations are extremely
  common in India and Australia.
- **A 45 MW firm delivery schedule** for the 03:00–12:00 UTC block. Morning and
  evening shoulder hours fall short of it → under-generation fires → backup or
  day-ahead purchase is recommended.

Both constraints are stored fields, shown on the site page, and used by the rule
engine like any other site's. The forecast itself is entirely live.

---

## API

| Endpoint | What it returns |
|---|---|
| `GET /api/sites` | All configured sites |
| `POST /api/sites` | Add a site (name, type, lat, lon, capacity_kw) |
| `DELETE /api/sites/{id}` | Remove a site |
| `GET /api/sites/{id}/weather` | Current + forecast weather driving the prediction |
| `GET /api/sites/{id}/forecast?hours=72` | Hourly generation forecast with an 80% confidence band |
| `GET /api/sites/{id}/historical?days=7` | Rolling day-ahead backtest: forecast vs actual |
| `GET /api/sites/{id}/alerts` | Flagged over/under-generation and ramp windows |
| `GET /api/sites/{id}/recommendations` | Recommended actions with reasons |
| `GET /api/portfolio/summary` | Aggregated stats and per-site status for the landing page |
| `GET /api/model/metrics` | Full training report |
| `GET /api/health` | Readiness, plus whether the models are trained |

Each site's forecast is computed once and cached in SQLite for 20 minutes, and
an APScheduler job refreshes all of them every 15 minutes — including once,
immediately, at startup. Cached responses come back in about 5 ms.

Adding a site needs **no retraining**. The models predict capacity factor from
weather, so a brand new site anywhere on earth starts forecasting on the next
refresh with nothing but a coordinate and a nameplate rating.

---

## Dashboard

**Portfolio view** — world map with per-site status pins, five KPI cards, a
cross-portfolio action queue sorted by urgency, and site cards with live
utilisation.

**Site detail** — 72h forecast chart with the confidence band and risk windows
shaded directly on the timeline, recorded output stitched to the forecast across
a `NOW` marker, clear-sky potential for context, the recommendation panel, the
day-ahead backtest chart, the weather driving the prediction, and the full site
configuration the rule engine is comparing against.

**Model report** — held-out metrics, the persistence comparison, and feature
importances per technology.

---

## Two-minute walkthrough

1. **Portfolio view.** Six live sites on the map, colour-coded by status. KPI row
   across the top: capacity online, current output, next 24h forecast, sites
   needing action, and how much of the at-risk curtailment storage can absorb.

2. **Open Bhadla Phase III.** The 72-hour chart carries recorded output, the
   forecast with its confidence band, and both an **over-generation** window
   (red, midday, crossing the 95 MW export limit) and an **under-generation**
   window (blue, morning shoulder, short of the 45 MW delivery schedule) — on
   the same chart, on any day.

3. **Read one recommendation aloud.** They're assembled from live numbers:

   > Forecast peaks at 100.6 MW across 4h (06:00–09:00 UTC on 13 Sep), 106% of
   > the 95.0 MW substation export limit. The 60 MWh battery is already at 100%
   > and has no headroom left, leaving 9.2 MWh with nowhere to go — issue a
   > curtailment instruction capped at 95.0 MW export, trimming up to 5.6 MW at
   > the peak hour.

4. **Yesterday's forecast vs actual.** The credibility panel — a rolling
   day-ahead replay the model never saw the answers to, scored in MAE, RMSE and
   R² right underneath.

5. **The one-sentence version.** *We convert the same weather forecast a utility
   already gets into a power forecast, using a model trained on a
   physics-derived historical record, then flag the risk windows and explain the
   grid action automatically.*

Optional: hit **Add site**, drop in any coordinate, and watch it start
forecasting on the next refresh — no retraining.

---

## Project layout

```
gridpulse/
├── backend/
│   ├── app/
│   │   ├── main.py                     FastAPI app, CORS, scheduler
│   │   ├── api/                        sites.py · portfolio.py
│   │   ├── core/                       config.py · database.py
│   │   ├── models/                     SQLAlchemy: Site, ForecastCache
│   │   ├── schemas/                    Pydantic request/response models
│   │   └── services/
│   │       ├── weather_service.py      Open-Meteo forecast + archive client
│   │       ├── generation_model.py     PV and turbine physics, solar geometry
│   │       ├── feature_builder.py      one feature set for train and serve
│   │       ├── forecasting_service.py  recursive inference, bands, backtests
│   │       ├── alert_engine.py         over/under/ramp rules
│   │       ├── recommendation_engine.py  actions + reason strings
│   │       └── forecast_store.py       SQLite cache in front of the pipeline
│   ├── ml/
│   │   ├── build_historical_dataset.py
│   │   ├── train_model.py
│   │   └── saved_models/               model artifacts + metrics.json
│   └── seed_data.py
├── frontend/
│   └── src/
│       ├── app/                        portfolio · sites/[id] · model
│       ├── components/                 charts, map, panels, KPIs
│       └── lib/                        api client, types, formatting
└── docs/architecture.md
```

---

## Stack

**Backend** — Python, FastAPI, SQLAlchemy + SQLite, pandas, numpy, APScheduler.
XGBoost and scikit-learn are training-only (`requirements-train.txt`); inference
scores the saved model with numpy so the serving bundle stays small.

**Frontend** — Next.js 15 (App Router), TypeScript, Tailwind CSS, Recharts,
react-leaflet, Framer Motion.

**Data** — Open-Meteo forecast and ERA5 archive APIs. No key, no signup, no
rate-limit management.

---

## Deploying

The repo ships a `vercel.json` that deploys both halves as one Vercel project
using [Services](https://vercel.com/docs/services): the Next.js frontend and the
FastAPI backend build separately and share a domain.

```json
"rewrites": [
  { "source": "/api/(.*)", "destination": { "service": "backend" } },
  { "source": "/(.*)",     "destination": { "service": "frontend" } }
]
```

Because the API already lives under `/api`, that split needs no code changes and
no CORS configuration — the frontend calls the backend same-origin. Import the
repo on Vercel and deploy; there are no environment variables to set.

A few things are arranged specifically so this works:

- **The trained models are committed.** `backend/ml/saved_models/*.json` is
  tracked (9 MB), because a deployment never gets to run the training script.
  The 65,808-row dataset they were built from stays out of the repo.
- **The database seeds itself.** Serverless filesystems are ephemeral, so the
  app calls `seed_if_empty()` on startup and writes SQLite to `/tmp`. Every cold
  start rebuilds the portfolio; everything stored is derived data anyway.
- **The scheduler switches off.** A background refresh loop only makes sense
  where a process outlives the request that started it, so on a serverless host
  forecasts are built on demand instead.
- **Neither `xgboost` nor `scikit-learn` is a runtime dependency.** This is the
  one that mattered: the first deploy failed at 958 MB against a 500 MB function
  limit, and xgboost's Linux wheel (~154 MB compressed, plus the scipy it drags
  in) was most of it. Training still uses XGBoost; *serving* reads the same
  saved JSON model through `app/services/tree_model.py`, a ~120-line numpy tree
  walker. `ml/verify_tree_model.py` asserts the two agree to ~5e-7 on both
  synthetic inputs and live feature matrices, so the model is unchanged — only
  the code that adds up its leaves is.

Cold start costs one Open-Meteo round trip per site. The portfolio endpoint
fetches all six concurrently, which keeps that near **1.2 s**; afterwards the
cache serves in **~20 ms** for as long as the instance stays warm.

To host the backend somewhere else instead, set `NEXT_PUBLIC_API_BASE_URL` to
its URL at build time and add the frontend's origin to `GRIDPULSE_CORS_ORIGINS`
on the backend.

---

## Troubleshooting

**"No trained model for 'solar'"** — run the two `ml/` scripts, in order.

**The dashboard says it can't reach the API** — the backend needs to be on port
8000, or set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`.

**"table sites has no column named …"** — the schema changed under an existing
database. `python seed_data.py --reset` rebuilds it.

**First page load is slow** — a cold cache means one Open-Meteo round trip per
site. Wait for `background refresh complete` in the backend log, then reload.
