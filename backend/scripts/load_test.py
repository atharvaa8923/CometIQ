"""Load test: many signed-in users hitting a running CometIQ server at once.

    # seed a realistic dataset (1,500 students, 400 jobs, 40 syllabi) and start the server, then:
    python scripts/load_test.py --base http://127.0.0.1:8000 --concurrency 20 --seconds 60 --json out.json

Closed loop: each virtual user signs in as its own account and repeatedly sends a request from its role's mix, with no
think time (so this measures capacity, not a realistic arrival rate). Roles: 60% students, 25% faculty, 15% employers.
Reports throughput, p50/p95/p99 latency and errors overall and per endpoint. Expensive endpoints are rate limited per
user; for a capacity run start the server with RATE_LIMITS_ENABLED=false, or every faculty request soon returns 429.
"""
import argparse
import asyncio
import json
import random
import statistics
import time
from collections import defaultdict

import httpx

PW = "CometIQ2026!"


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 1)


async def login(c: httpx.AsyncClient, email: str, pw: str) -> dict:
    r = await c.post("/api/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def discover(c: httpx.AsyncClient, fac: dict, emp: dict) -> dict:
    syl = (await c.get("/api/gap/syllabi", headers=fac)).json()
    syl = syl if isinstance(syl, list) else syl.get("items", [])
    with_analysis = [s for s in syl if s.get("latest")]
    sc = (await c.get("/api/curriculum/scorecard", headers=fac)).json()
    pid = next((p["id"] for p in sc.get("programs", []) if "Artificial" in p.get("name", "")), None) or (sc.get("programs") or [{}])[0].get("id")
    jobs = (await c.get("/api/match/employer/jobs", headers=emp)).json()
    jobs = jobs if isinstance(jobs, list) else jobs.get("items", [])
    a0 = with_analysis[0] if with_analysis else (syl[0] if syl else {})
    return {"aid": (a0.get("latest") or {}).get("id"), "sid": a0.get("id"), "pid": pid,
            "job": jobs[0]["id"] if jobs else None}


def mixes(ids: dict) -> dict[str, list[tuple[int, str, str, dict | None]]]:
    """(weight, method, path, body) per role."""
    words = ["sql", "python", "data analy", "tableau", "finance", "machine learning", "marketing"]
    fac = [(4, "GET", "/api/gap/syllabi", None), (3, "GET", "/api/notifications", None),
           (3, "GET", "/api/curriculum/scorecard", None), (2, "GET", "/api/graph/map", None),
           (1, "GET", "/api/search?q={w}", None)]
    if ids["aid"]:
        fac.append((4, "GET", f"/api/gap/analyses/{ids['aid']}", None))
    if ids["pid"]:
        fac += [(2, "GET", f"/api/curriculum/programs/{ids['pid']}/map", None),
                (1, "POST", f"/api/curriculum/programs/{ids['pid']}/simulate", {"ops": []})]
    stu = [(4, "GET", "/api/match/jobs", None), (3, "GET", "/api/path/overview", None), (2, "GET", "/api/path/recommendations", None),
           (2, "GET", "/api/badges/mine", None), (3, "GET", "/api/notifications", None), (1, "GET", "/api/match/learn-next", None),
           (1, "GET", "/api/search?q={w}", None), (1, "GET", "/api/auth/me", None)]
    emp = [(2, "GET", "/api/match/employer/talent", None), (1, "GET", "/api/match/employer/talent?q={w}", None), (1, "GET", "/api/search?q={w}&type=students", None),
           (2, "GET", "/api/match/employer/jobs", None)]
    if ids["job"]:
        emp.append((3, "GET", f"/api/match/employer/jobs/{ids['job']}/candidates", None))
    return {"faculty": fac, "student": stu, "employer": emp, "_words": words}


async def run(base: str, concurrency: int, seconds: float, students: int) -> dict:
    limits = httpx.Limits(max_connections=concurrency + 5, max_keepalive_connections=concurrency + 5)
    async with httpx.AsyncClient(base_url=base, timeout=60, limits=limits) as c:
        fac, emp = await login(c, "faculty@cometiq.app", PW), await login(c, "employer@cometiq.app", PW)
        ids = await discover(c, fac, emp)
        mix = mixes(ids)
        roles = (["student"] * 60 + ["faculty"] * 25 + ["employer"] * 15)
        tokens: list[tuple[str, dict]] = []
        for i in range(concurrency):
            role = roles[(i * 37) % len(roles)]
            if role == "student":
                tokens.append((role, await login(c, f"perf.student{i % students}@utd.edu", "Perf-Student-1")))
            else:
                tokens.append((role, fac if role == "faculty" else emp))
        lat: dict[str, list[float]] = defaultdict(list)
        status: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        errors: list[str] = []
        stop = time.perf_counter() + seconds

        async def user(role: str, h: dict, seed: int) -> None:
            rnd = random.Random(seed)
            choices = mix[role]
            weights = [w for w, *_ in choices]
            while time.perf_counter() < stop:
                _, m, path, body = rnd.choices(choices, weights)[0]
                path = path.replace("{w}", rnd.choice(mix["_words"]))
                key = f"{m} {path.split('?')[0]}"
                t = time.perf_counter()
                try:
                    r = await c.request(m, path, headers=h, json=body)
                    code = r.status_code
                except httpx.HTTPError as e:
                    code = 599
                    errors.append(f"{key}: {type(e).__name__}")
                lat[key].append((time.perf_counter() - t) * 1000)
                status[key][code] += 1

        t0 = time.perf_counter()
        await asyncio.gather(*[user(r, h, i) for i, (r, h) in enumerate(tokens)])
        wall = time.perf_counter() - t0
    allv = [x for v in lat.values() for x in v]
    n_err = sum(n for s in status.values() for code, n in s.items() if code >= 500)
    n_429 = sum(s.get(429, 0) for s in status.values())
    return {
        "concurrency": concurrency, "seconds": round(wall, 1), "requests": len(allv), "throughput_rps": round(len(allv) / wall, 1),
        "p50_ms": pct(allv, 50), "p95_ms": pct(allv, 95), "p99_ms": pct(allv, 99), "max_ms": round(max(allv, default=0), 1),
        "errors_5xx": n_err, "rate_limited_429": n_429, "error_samples": errors[:5],
        "endpoints": sorted(({"endpoint": k, "n": len(v), "p50_ms": pct(v, 50), "p95_ms": pct(v, 95), "p99_ms": pct(v, 99),
                              "mean_ms": round(statistics.mean(v), 1), "status": dict(status[k])} for k, v in lat.items()),
                            key=lambda e: -e["p95_ms"]),
    }


def show(r: dict) -> None:
    print(f"\nconcurrency {r['concurrency']}: {r['requests']} requests in {r['seconds']} s = {r['throughput_rps']} req/s | "
          f"p50 {r['p50_ms']} ms  p95 {r['p95_ms']} ms  p99 {r['p99_ms']} ms  max {r['max_ms']} ms | 5xx {r['errors_5xx']}  429 {r['rate_limited_429']}")
    print(f"  {'endpoint':58} {'n':>6} {'p50':>8} {'p95':>8} {'p99':>8}  status")
    for e in r["endpoints"]:
        print(f"  {e['endpoint'][:58]:58} {e['n']:6} {e['p50_ms']:8} {e['p95_ms']:8} {e['p99_ms']:8}  {e['status']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--concurrency", type=int, nargs="+", default=[20, 50])
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--students", type=int, default=1500)
    ap.add_argument("--json")
    a = ap.parse_args()
    results = []
    for n in a.concurrency:
        r = asyncio.run(run(a.base, n, a.seconds, a.students))
        show(r)
        results.append(r)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(results, f, indent=2)
