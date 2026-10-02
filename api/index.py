import json
from pathlib import Path

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

app = FastAPI()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


@app.middleware("http")
async def add_cors(request: Request, call_next):
    # Answer browser preflight (OPTIONS) requests directly
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=CORS_HEADERS)
    response = await call_next(request)
    # Always add the CORS headers, even when no Origin header was sent
    for k, v in CORS_HEADERS.items():
        response.headers[k] = v
    return response


# Load the telemetry file that sits next to this script
raw = json.loads((Path(__file__).parent / "q-vercel-latency.json").read_text())
if isinstance(raw, dict):  # if the records are wrapped inside an object, find the list
    raw = next(v for v in raw.values() if isinstance(v, list))
RECORDS = raw


def pick(rec, names):
    for n in names:
        if n in rec:
            return rec[n]
    raise KeyError(f"none of {names} in {list(rec)}")


def percentile(values, p):
    v = sorted(values)
    k = (len(v) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


class Query(BaseModel):
    regions: list[str]
    threshold_ms: float


def compute(q: Query):
    out = {}
    for region in q.regions:
        rows = [r for r in RECORDS if str(r.get("region", "")).lower() == region.lower()]
        lat = [pick(r, ["latency_ms", "latency"]) for r in rows]
        upt = [pick(r, ["uptime_pct", "uptime", "uptime_percent"]) for r in rows]
        if not rows:
            out[region] = {"avg_latency": None, "p95_latency": None, "avg_uptime": None, "breaches": 0}
            continue
        out[region] = {
            "avg_latency": sum(lat) / len(lat),
            "p95_latency": percentile(lat, 95),
            "avg_uptime": sum(upt) / len(upt),
            "breaches": sum(1 for x in lat if x > q.threshold_ms),
        }
    return {**out, "regions": out}


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/")
def post_root(q: Query):
    return compute(q)


@app.post("/api")
def post_api(q: Query):
    return compute(q)
