"""Property tests: invariants of the scoring code, checked on thousands of random inputs (Hypothesis).

These are pure functions, so no database is needed. Each property runs 1,000+ generated cases; failures are shrunk to the
smallest input that breaks the rule and printed.
"""
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from app.services import gap as gapsvc
from app.services import match as matchsvc
from app.services import simulator
from app.services import versions as vs

MANY = settings(max_examples=1500, deadline=None)
NAMES = [f"Skill{i}" for i in range(40)]

demand_row = st.fixed_dictionaries({"demand": st.floats(0, 1, allow_nan=False), "job_count": st.integers(0, 500)})


@st.composite
def demand_lists(draw):
    names = draw(st.lists(st.sampled_from(NAMES), unique=True, max_size=30))
    rows = [{"name": n, "skill_id": NAMES.index(n), **draw(demand_row)} for n in names]
    return sorted(rows, key=lambda r: -r["demand"])


@st.composite
def syllabus_skills(draw):
    names = draw(st.lists(st.sampled_from(NAMES), unique=True, max_size=40))
    return {n: {"mentions": draw(st.integers(1, 12)), "excerpts": ["…"]} for n in names}


topics = st.lists(st.sampled_from(NAMES + ["Intro", "Review", "Exam"]), max_size=15)


# ── CometGap coverage score ────────────────────────────────────────────────────
@MANY
@given(syllabus_skills(), topics, demand_lists(), st.integers(1, 40))
def test_score_is_between_0_and_100(skills, tps, demand, top_n):
    rows, score = vs.score(skills, tps, demand, top_n)
    assert 0.0 <= score <= 100.0
    assert len(rows) == min(top_n, len(demand))
    assert {r["status"] for r in rows} <= {"covered", "partial", "missing"}


@MANY
@given(syllabus_skills(), topics, demand_lists(), st.integers(1, 40), st.sampled_from(NAMES), st.integers(1, 5))
def test_more_mentions_never_lower_the_score(skills, tps, demand, top_n, name, extra):
    _, before = vs.score(skills, tps, demand, top_n)
    more = {**skills, name: {"mentions": skills.get(name, {"mentions": 0})["mentions"] + extra, "excerpts": ["…"]}}
    _, after = vs.score(more, tps, demand, top_n)
    assert after >= before


@MANY
@given(syllabus_skills(), demand_lists(), st.integers(1, 40))
def test_teaching_everything_scores_100_and_nothing_scores_0(skills, demand, top_n):
    full = {d["name"]: {"mentions": 3, "excerpts": ["…"]} for d in demand}
    if any(d["demand"] > 0 for d in demand[:top_n]):
        assert vs.score(full, [], demand, top_n)[1] == 100.0
        assert vs.score({}, [], demand, top_n)[1] == 0.0


# ── Semester comparison: the parts add up ──────────────────────────────────────
pct = st.floats(0, 100, allow_nan=False).map(lambda x: round(x, 1))


@MANY
@given(pct, pct, pct, pct, pct, pct)
def test_attribution_parts_add_up_to_the_total(a_stored, b_stored, a_cur, b_cur, b_syl_a_dem, a_syl_b_dem):
    e = vs.attribute(a_stored, b_stored, a_cur, b_cur, b_syl_a_dem, a_syl_b_dem)
    assert round(e["course_revision"] + e["demand_change"] + e["method_update"], 1) == e["total"]
    assert e["total"] == round(b_stored - a_stored, 1)


@MANY
@given(pct, pct, pct, pct)
def test_attribution_without_method_change_has_no_method_part(a, b, b_syl_a_dem, a_syl_b_dem):
    # scored with the current method: stored == current, so nothing may be attributed to a method update
    e = vs.attribute(a, b, a, b, b_syl_a_dem, a_syl_b_dem)
    assert abs(e["method_update"]) <= 0.1   # at most the rounding remainder
    if b_syl_a_dem == b and a_syl_b_dem == a:   # demand had no effect: all of it is the course revision
        assert e["demand_change"] == 0 and e["course_revision"] == e["total"]


@MANY
@given(syllabus_skills(), syllabus_skills(), topics, topics, demand_lists(), demand_lists(), st.integers(1, 40))
def test_attribution_on_real_scores(ska, skb, ta, tb, da, db_, n):
    A = vs.score(ska, ta, da, n)[1]
    B = vs.score(skb, tb, db_, n)[1]
    e = vs.attribute(A, B, A, B, vs.score(skb, tb, da, n)[1], vs.score(ska, ta, db_, n)[1])
    assert round(e["course_revision"] + e["demand_change"] + e["method_update"], 1) == e["total"] == round(B - A, 1)
    if ska == skb and ta == tb:
        assert abs(e["course_revision"]) <= 0.1   # same syllabus: no revision effect


# ── Faculty-reviewed score ─────────────────────────────────────────────────────
@MANY
@given(demand_lists(), st.data())
def test_reviewed_score_bounds_and_counts(demand, data):
    rows = [{**d, "status": data.draw(st.sampled_from(["covered", "partial", "missing"]))} for d in demand]
    reviews = {}
    for r in rows:
        if data.draw(st.booleans()):
            fs = data.draw(st.sampled_from(["practiced", "mentioned_only", "not_covered", "not_relevant"]))
            reviews[r["skill_id"]] = SimpleNamespace(faculty_status=fs, decision=gapsvc.decision_for(r["status"], fs),
                                                     action=data.draw(st.sampled_from([None, "planned", "done"])))
    s = gapsvc.review_summary({"skills": rows}, reviews)
    assert s["reviewed"] == len(reviews) == s["confirmed"] + s["corrected"]
    assert s["reviewed_score"] is None or 0.0 <= s["reviewed_score"] <= 100.0
    assert 0.0 <= s["reviewed_demand_share"] <= 100.0
    assert 0 <= s["gaps_reviewed"] <= s["gaps_total"] <= s["total"]


# ── CometMatch fit score ───────────────────────────────────────────────────────
@st.composite
def jobs(draw):
    ids = draw(st.lists(st.integers(0, 39), unique=True, max_size=15))
    skills = [SimpleNamespace(skill_id=i, importance=draw(st.sampled_from(["required", "preferred"])),
                              skill=SimpleNamespace(name=NAMES[i], category="x")) for i in ids]
    return SimpleNamespace(skills=skills)


levels = st.dictionaries(st.integers(0, 39), st.fixed_dictionaries({"level": st.floats(0, 1.5, allow_nan=False), "sources": st.just([])}))
bonuses = st.lists(st.fixed_dictionaries({"title": st.just("Cert"), "kind": st.just("certification"), "points": st.integers(0, 20),
                                          "skills": st.sets(st.integers(0, 39), max_size=5)}), max_size=6)


@MANY
@given(jobs(), levels, bonuses)
def test_fit_score_bounds_and_bonus_cap(job, skills, bon):
    r = matchsvc.score_job(job, skills, bonuses=bon)
    assert 0.0 <= r["base_score"] <= 100.0 and 0.0 <= r["score"] <= 100.0
    assert 0 <= r["bonus"] <= matchsvc.BONUS_CAP and sum(b["points"] for b in r["bonus_items"]) == r["bonus"]
    assert r["score"] >= r["base_score"]
    assert len(r["matched"]) + len(r["partial"]) + len(r["missing"]) == len(job.skills)


@MANY
@given(jobs(), levels, st.integers(0, 39))
def test_learning_a_skill_never_lowers_fit(job, skills, sid):
    before = matchsvc.score_job(job, skills)["score"]
    after = matchsvc.score_job(job, {**skills, sid: {"level": 1.0, "sources": []}})["score"]
    assert after >= before


# ── Program simulator coverage ─────────────────────────────────────────────────
@MANY
@given(st.data())
def test_simulator_coverage_bounds(data):
    n_courses, n_skills = data.draw(st.integers(0, 8)), data.draw(st.integers(0, 12))
    courses = {f"c{i}": {"code": f"BUAN {6000 + i}"} for i in range(n_courses)}
    skills = [{"id": j, "demand": data.draw(st.one_of(st.none(), st.floats(0, 1, allow_nan=False))), "in_market": data.draw(st.booleans())}
              for j in range(n_skills)]
    cells = {c: {str(s["id"]): data.draw(st.sampled_from(["I", "P", "M", "-"])) for s in skills} for c in courses}
    m = simulator._metrics(courses, cells, skills)
    assert 0.0 <= m["coverage"] <= 100.0
    market = sum(s["in_market"] for s in skills)
    assert 0 <= m["never_practiced"] <= m["no_mastery"] <= market
