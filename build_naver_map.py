#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""네이버 지하철 역 ID -> 우리 DB station.ID 매핑 생성"""
import json, collections, subprocess, sys

# 네이버 표기와 DB 역명이 다른 경우
NAME_FIX = {
    "419민주묘지": "4.19민주묘지",
    "당고개": "불암산",        # 2024년 역명 변경
    "서구청": "서해구청",      # 2026-07 인천 서구->서해구 개편
    "시청용인대": "시청·용인대",
    "전대에버랜드": "전대·에버랜드",
    "총신대입구": "이수",
}
# 네이버 노선명 -> 우리 LINE_ 코드 (동명이역 판별용)
LINE_MAP = {
    "1호선":"LINE_1","2호선":"LINE_2","3호선":"LINE_3","4호선":"LINE_4","5호선":"LINE_5",
    "6호선":"LINE_6","7호선":"LINE_7","8호선":"LINE_8","9호선":"LINE_9",
    "공항철도":"LINE_AIR","경의중앙선":"LINE_GYEONGUI","경춘선":"LINE_GYEONCHUN",
    "경강선":"LINE_GYEONGANG","수인분당선":"LINE_SUINBUNDANG","신분당선":"LINE_SINBUNDANG",
    "우이신설경전철":"LINE_UISINSUL","신림선":"LINE_SINRIM","서해선":"LINE_SEOHEA",
    "김포도시철도":"LINE_GIMPO","용인경전철":"LINE_EVER","의정부경전철":"LINE_UIJEONGBU",
    "인천1호선":"LINE_INCHEON1","인천2호선":"LINE_INCHEON2","GTX-A":"LINE_GTXA",
}

def load_db():
    """station / alias_name / station_line 을 읽어 이름->(id, lines) 조회표를 만든다"""
    sql = ("SELECT 'S', s.ID, s.NAME FROM station s "
           "UNION ALL SELECT 'A', a.STATION_ID, a.ALIAS_NAME FROM alias_name a "
           "UNION ALL SELECT 'L', l.STATION_ID, l.LINE_ID FROM station_line l;")
    pw = subprocess.run(["sudo","docker","inspect","subway-db","--format",
                         "{{range .Config.Env}}{{println .}}{{end}}"],
                        capture_output=True, text=True).stdout
    pw = next(l.split("=",1)[1] for l in pw.splitlines() if l.startswith("MYSQL_ROOT_PASSWORD="))
    out = subprocess.run(["sudo","docker","exec","-i","subway-db","mysql","-uroot",f"-p{pw}",
                          "-N","--default-character-set=utf8mb4","subway","-e",sql],
                         capture_output=True, text=True).stdout
    names = collections.defaultdict(set); lines = collections.defaultdict(set)
    for row in out.splitlines():
        p = row.split("\t")
        if len(p) != 3: continue
        kind, sid, val = p[0], int(p[1]), p[2]
        if kind in ("S","A"): names[val].add(sid)
        else: lines[sid].add(val)
    return names, lines

def main():
    names, lines = load_db()
    naver = json.load(open("stations.json", encoding="utf-8"))[0]["realInfo"]
    mapping, unresolved, ambiguous = {}, [], []
    for s in naver:
        raw = s["name"].strip().split("(")[0].strip()
        nm = NAME_FIX.get(raw, raw)
        cands = names.get(nm) or names.get(nm + "역") or set()
        if not cands:
            unresolved.append((s["id"], raw)); continue
        if len(cands) > 1:
            want = LINE_MAP.get(s.get("logicalLine", {}).get("name", ""))
            narrowed = {c for c in cands if want in lines.get(c, set())} if want else set()
            if len(narrowed) != 1:
                ambiguous.append((s["id"], raw, sorted(cands),
                                  s.get("logicalLine", {}).get("name"))); continue
            cands = narrowed
        mapping[str(s["id"])] = {"station_id": next(iter(cands)), "name": nm}
    json.dump(mapping, open("naver_station_map.json","w"), ensure_ascii=False, indent=1)
    print(f"네이버 역 {len(naver)}개 -> 매핑 {len(mapping)}")
    print(f"  미해결 {len(unresolved)}: {unresolved[:10]}")
    print(f"  모호 {len(ambiguous)}: {ambiguous[:10]}")
    ids = {v['station_id'] for v in mapping.values()}
    print(f"  커버된 DB 역 {len(ids)}/655")

if __name__ == "__main__":
    main()
