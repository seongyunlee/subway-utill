#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
최적경로 문제 생성기 (네이버 지하철 경로탐색 API)

문제: 출발역 -> 도착역 을 갈 때 보기 4개 중 "경유하면 가장 빠른 역"을 고르기.

난이도는 '정답과 가장 가까운 오답의 시간차(margin)'로 정의한다.
승하차 인원 기반 지표는 실측 상관계수가 +0.04 로 무의미했다.
margin 밴드별 할당량을 두고 층화 추출해서 난이도 풀이 한쪽으로 쏠리지 않게 한다.

시간대는 08/12/17 세 번을 평균한다. 급행 운행이 시간대별로 달라 한 번만 재면
경로 소요시간이 왜곡된다. (속도보다 정확도 우선)
"""
import argparse, datetime, json, math, os, random, time, urllib.parse, urllib.request

BASE = "https://map.naver.com/p/api/pubtrans/subway-directions"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HOURS = ("08", "12", "17")
MAX_ANSWER_DURATION = 70        # 정답 경로가 이보다 길면 문제로 안 씀 (분)

# (이름, margin 하한, margin 상한, 목표 비율)  — margin ∈ [lo, hi)
BANDS = [("hard", 4, 10, 0.30), ("medium", 10, 25, 0.40), ("easy", 25, 10**6, 0.30)]
MAX_CANDIDATE_TRIES = 40        # 밴드 조건을 만족하는 오답 3개를 찾는 시도 상한

# 밴드별로 후보를 "경로에서 얼마나 떨어진 역"에서 뽑을지 (최단경로까지의 직선거리 기준 순위 구간).
# 무작위 784개에서 뽑으면 대부분 수십 분씩 우회해 hard 밴드가 거의 안 걸린다.
# 경로 근처 역일수록 우회 시간이 작아 좁은 시간차를 만들기 쉽다.
# 시간대 평균(급행 반영)과 경로당 1문제 원칙은 그대로 두고, 후보 선정만 좁힌다.
DISTANCE_WINDOW = {"hard": (0.0, 0.10), "medium": (0.05, 0.35), "easy": (0.25, 1.0)}


def load_coords(path="stations.json"):
    out = {}
    for s in json.load(open(path, encoding="utf-8"))[0]["realInfo"]:
        try:
            out[str(s["id"])] = (float(s["latitude"]), float(s["longitude"]))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def haversine(a, b):
    lat1, lon1 = a; lat2, lon2 = b
    p = math.pi / 180
    h = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2)
    return 12742 * math.asin(math.sqrt(h))


def candidates_for_band(ids, coords, path_ids, band_name, used, sid):
    """최단경로에서 가까운 순으로 정렬한 뒤 밴드에 맞는 거리 구간만 돌려준다"""
    ref = [coords[s] for s in path_ids if s in coords]
    if not ref:
        return [c for c in ids if sid(c) not in used]
    scored = []
    for c in ids:
        if sid(c) in used or c not in coords:
            continue
        scored.append((min(haversine(coords[c], r) for r in ref), c))
    scored.sort()
    lo, hi = DISTANCE_WINDOW[band_name]
    n = len(scored)
    window = scored[int(n * lo):max(int(n * hi), int(n * lo) + 1)]
    return [c for _, c in window] or [c for _, c in scored]


class Api:
    def __init__(self, delay, date):
        self.delay, self.date, self.calls = delay, date, 0

    def directions(self, start, goal, via=None, hour="12"):
        q = {"start": start, "goal": goal, "serviceDay": "1",
             "departureTime": f"{self.date}T{hour}:00:00.000Z",
             "lang": "ko", "pathType": "duration", "includeDetailOperation": "true"}
        url = f"{BASE}?{urllib.parse.urlencode(q)}"
        if via:
            url += f"&via[]={via}"
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Referer": "https://map.naver.com/"})
        for attempt in range(4):
            try:
                time.sleep(self.delay)
                self.calls += 1
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.load(r)
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))


def shortest(data):
    for p in data.get("paths", []):
        if p.get("optimizationMethod") == "MINIMUM_DURATION":
            return p
    return None


def via_stations(path):
    out = set()
    for leg in path["legs"]:
        for step in leg["steps"]:
            for s in step.get("stations", []):
                out.add(str(s["id"]))
    return out


def avg_duration(api, start, goal, via):
    """08/12/17 평균. 급행 시간대 차이를 반영하려면 한 번만 재서는 안 된다."""
    ds = []
    for h in HOURS:
        p = shortest(api.directions(start, goal, via, h))
        if p is None:
            return None
        ds.append(p["duration"])
    return sum(ds) / len(ds)


def make_problem(api, ids, smap, rnd, band, coords):
    """band = (name, lo, hi, _). margin 이 [lo, hi) 안에 들어오는 문제를 만든다.

    보기 중복은 네이버 ID 가 아니라 우리 station.ID 로 막아야 한다.
    네이버는 환승역을 노선별 다른 ID 로 들고 있어(서울역이 4개) ID 만 보면
    같은 역이 정답이자 오답으로 들어간다.
    """
    name, lo, hi, _ = band
    sid = lambda n: smap[n]["station_id"]

    start, goal = rnd.sample(ids, 2)
    if sid(start) == sid(goal):
        return None
    p = shortest(api.directions(start, goal))
    if p is None or p["duration"] > MAX_ANSWER_DURATION:
        return None

    used = {sid(start), sid(goal)}
    mids = [s for s in via_stations(p) if s in smap and sid(s) not in used]
    if not mids:
        return None
    answer = rnd.choice(mids)
    ans_dur = avg_duration(api, start, goal, answer)
    if ans_dur is None or ans_dur > MAX_ANSWER_DURATION:
        return None
    used.add(sid(answer))

    # 모든 오답은 ans+lo 보다 느려야 하고(그래야 margin 이 lo 밑으로 안 내려감),
    # 그중 최소 하나는 ans+hi 안에 들어와야 margin 이 이 밴드에 속한다.
    pool = candidates_for_band(ids, coords, via_stations(p), name, used, sid)
    rnd.shuffle(pool)
    picked, in_band, tries = [], False, 0
    for c in pool:
        if len(picked) >= 3 or tries >= MAX_CANDIDATE_TRIES:
            break
        tries += 1
        if sid(c) in used:
            continue
        d = avg_duration(api, start, goal, c)
        if d is None or d < ans_dur + lo:
            continue
        near = d < ans_dur + hi
        # 마지막 한 자리는 밴드 조건을 채울 후보로만 채운다
        if len(picked) == 2 and not in_band and not near:
            continue
        picked.append((c, d))
        used.add(sid(c))
        in_band = in_band or near
    if len(picked) < 3 or not in_band:
        return None

    margin = min(d for _, d in picked) - ans_dur
    return {"start": start, "goal": goal, "answer": answer, "answer_duration": ans_dur,
            "wrong": [{"naver_id": c, "duration": d} for c, d in picked],
            "margin": margin, "band": name}


def pick_band(done, total, rnd):
    """목표 비율에 가장 못 미치는 밴드를 고른다"""
    counts = {b[0]: 0 for b in BANDS}
    for p in done:
        if p.get("band") in counts:
            counts[p["band"]] += 1
    deficits = [(b[3] * total - counts[b[0]], b) for b in BANDS]
    worst = max(d for d, _ in deficits)
    cands = [b for d, b in deficits if d >= worst - 1e-9]
    return rnd.choice(cands)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=2000)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--out", default="bestroute_problems.json")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()

    smap = json.load(open("naver_station_map.json", encoding="utf-8"))
    coords = load_coords()
    ids = sorted(smap)
    rnd = random.Random(a.seed)
    api = Api(a.delay, datetime.date.today().isoformat())

    done = json.load(open(a.out, encoding="utf-8")) if os.path.exists(a.out) else []
    seen = {(p["start"], p["goal"]) for p in done}
    print(f"역 {len(ids)}개 / 기존 {len(done)}건에서 이어서 {a.count}건 목표", flush=True)
    print("밴드 목표: " + ", ".join(f"{b[0]} {b[3]:.0%}" for b in BANDS), flush=True)

    t0, fails = time.time(), 0
    while len(done) < a.count:
        band = pick_band(done, a.count, rnd)
        try:
            p = make_problem(api, ids, smap, rnd, band, coords)
        except Exception as e:
            fails += 1
            print(f"  오류 {type(e).__name__}: {e}", flush=True)
            if fails > 30:
                print("오류 과다, 중단"); break
            continue
        if p is None or (p["start"], p["goal"]) in seen:
            continue
        seen.add((p["start"], p["goal"]))
        done.append(p)
        json.dump(done, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
        if len(done) % 20 == 0:
            el = time.time() - t0
            cnt = {b[0]: sum(1 for x in done if x.get("band") == b[0]) for b in BANDS}
            rate = el / max(1, len(done) - 0)
            print(f"  {len(done)}/{a.count}  {el/60:.0f}분  API {api.calls}회  "
                  f"{cnt}  남은예상 {(a.count-len(done))*rate/3600:.1f}h", flush=True)
    print(f"완료 {len(done)}건 / API {api.calls}회 / {(time.time()-t0)/60:.0f}분")


if __name__ == "__main__":
    main()
