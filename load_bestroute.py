#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bestroute_problems.json -> best_route_problem INSERT SQL

DIFFICULTY_INDEX 는 "쉬움 점수"다 (리포지토리가 내림차순으로 뽑으므로 0번 = 가장 쉬움).

원본은 출발역+도착역의 승하차 인원 합을 썼는데, 실측 상관계수가 +0.04 로
실제 난이도와 무관했다. 이 게임의 난이도는 "정답과 가장 가까운 오답의 시간차"가
좌우하므로 그것을 주 지표로 쓰고, 역 인지도는 보조로만 반영한다.
(역을 알아야 위치를 가늠할 수 있으므로 완전히 버리지는 않는다)
"""
import json, random, argparse, subprocess

W_MARGIN = 700          # 시간차 가중치 (주 지표)
W_FAME = 300            # 역 인지도 가중치 (보조)
MARGIN_CAP = 60         # 이 이상 벌어지면 더 쉬워지지 않는다고 본다 (분)
FAME_CAP = 250_000      # 출발+도착 승하차 합 상한

def boarding_counts():
    pw = subprocess.run(["sudo","docker","inspect","subway-db","--format",
                         "{{range .Config.Env}}{{println .}}{{end}}"],
                        capture_output=True, text=True).stdout
    pw = next(l.split("=",1)[1] for l in pw.splitlines() if l.startswith("MYSQL_ROOT_PASSWORD="))
    out = subprocess.run(["sudo","docker","exec","-i","subway-db","mysql","-uroot",f"-p{pw}",
                          "-N","subway","-e","SELECT ID, COALESCE(BOARDING_CNT,0) FROM station;"],
                         capture_output=True, text=True).stdout
    return {int(r.split()[0]): int(r.split()[1]) for r in out.splitlines() if r.strip()}

def easiness(margin, fame):
    m = min(max(margin, 0) / MARGIN_CAP, 1.0)
    f = min(max(fame, 0) / FAME_CAP, 1.0)
    return int(round(W_MARGIN * m + W_FAME * f))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="bestroute_problems.json")
    ap.add_argument("--out", default="bestroute_seed.sql")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    smap = json.load(open("naver_station_map.json", encoding="utf-8"))
    problems = json.load(open(a.src, encoding="utf-8"))
    bc = boarding_counts()
    rnd = random.Random(a.seed)
    sid = lambda n: smap[n]["station_id"]

    rows, skipped, stats = [], 0, []
    for p in problems:
        try:
            start, goal, ans = sid(p["start"]), sid(p["goal"]), sid(p["answer"])
            wrong = [(sid(w["naver_id"]), w["duration"]) for w in p["wrong"]]
        except KeyError:
            skipped += 1; continue
        picks = [(ans, p["answer_duration"])] + wrong
        ids = {x[0] for x in picks}
        if len(ids) != 4 or start in ids or goal in ids:
            skipped += 1; continue              # 보기 중복 방어 (생성기에서도 막지만 이중 확인)

        margin = p.get("margin")
        if margin is None:
            margin = min(d for _, d in wrong) - p["answer_duration"]
        di = easiness(margin, bc.get(start, 0) + bc.get(goal, 0))
        stats.append((p.get("band", "?"), margin, di))

        rnd.shuffle(picks)                      # 정답 위치를 섞는다
        c = [x[0] for x in picks]; t = [int(round(x[1])) for x in picks]
        rows.append(f"  ({start}, {goal}, {ans}, {c[0]}, {c[1]}, {c[2]}, {c[3]}, "
                    f"{t[0]}, {t[1]}, {t[2]}, {t[3]}, 0, 0, {di})")

    sql = ("-- best_route_problem 적재 (네이버 지하철 경로탐색 크롤링)\n"
           "-- DIFFICULTY_INDEX = 쉬움 점수 (시간차 70% + 역 인지도 30%, 0~1000)\n"
           "SET NAMES utf8mb4;\nSTART TRANSACTION;\nDELETE FROM best_route_problem;\n"
           "INSERT INTO best_route_problem\n"
           "  (START_STATION, END_STATION, ANSWER, CHOICE1, CHOICE2, CHOICE3, CHOICE4,\n"
           "   CHOICE1_TIME, CHOICE2_TIME, CHOICE3_TIME, CHOICE4_TIME,\n"
           "   CORRECT_CNT, WRONG_CNT, DIFFICULTY_INDEX) VALUES\n"
           + ",\n".join(rows) + ";\nCOMMIT;\n")
    open(a.out, "w", encoding="utf-8").write(sql)

    print(f"문제 {len(problems)}건 -> INSERT {len(rows)}행 (건너뜀 {skipped})")
    if stats:
        import collections
        band = collections.Counter(s[0] for s in stats)
        print("  밴드 분포:", dict(band))
        dis = sorted(s[2] for s in stats)
        print(f"  DIFFICULTY_INDEX  min={dis[0]} p25={dis[len(dis)//4]} "
              f"중앙={dis[len(dis)//2]} p75={dis[3*len(dis)//4]} max={dis[-1]}")
        for b in ("easy","medium","hard"):
            v=[s[2] for s in stats if s[0]==b]
            if v: print(f"    {b:7s} n={len(v):4d}  DI 중앙 {sorted(v)[len(v)//2]}")

if __name__ == "__main__":
    main()
