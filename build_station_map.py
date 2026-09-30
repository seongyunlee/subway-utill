#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수도권 전철 노선도 SVG <-> DB station 매핑 생성기

노선도는 개통/역명변경 때마다 갱신되므로, 갱신될 때마다 이 스크립트를 다시 돌려
station_svg_map.json 을 재생성한다. --diff 로 이전 매핑과 무엇이 달라졌는지 확인할 수 있다.

사용법:
    # 위키미디어 커먼즈에서 최신 노선도를 받아 매핑 생성
    ./build_station_map.py --fetch --stations stations.json --out station_svg_map.json

    # 로컬 SVG 로 생성 + 이전 매핑과 비교
    ./build_station_map.py --svg linemap.svg --stations stations.json \
        --out station_svg_map.json --diff station_svg_map.prev.json

stations.json 스키마:  [{"id": 1, "name": "강남역", "lines": ["LINE_2"], "aliases": ["강남"]}, ...]
DB에서 뽑으려면:
    SELECT JSON_ARRAYAGG(JSON_OBJECT('id', s.ID, 'name', s.NAME,
             'lines', (SELECT JSON_ARRAYAGG(l.LINE_ID) FROM station_line l WHERE l.STATION_ID=s.ID),
             'aliases',(SELECT JSON_ARRAYAGG(a.ALIAS_NAME) FROM alias_name a WHERE a.STATION_ID=s.ID)))
    FROM station s;

종료 코드: 0 = 전부 매핑됨 / 1 = 매핑 실패한 역 있음 (CI 에서 실패 처리 가능)
"""
from __future__ import annotations
import argparse, collections, json, math, re, sys, urllib.parse, urllib.request

COMMONS_FILE = "File:Seoul subway linemap ko.svg"
UA = "subway-game-map-sync/1.0"

# ─── 노선도 표기가 DB 역명과 다른 경우의 보정 ──────────────────────────────
# 노선도가 낡아 옛 역명을 쓰는 경우 등. 새 사례가 생기면 여기에 추가한다.
LABEL_FIX = {
    "서구청": "서해구청",   # 2026-07 인천 서구->서해구 개편에 따른 역명 변경
}

# 노선도가 "역명(노선)" 으로 동명이역을 구분해 표기하는 경우의 노선 힌트
PAREN_LINE = {
    "지하": "LINE_2",         # 신촌(지하)
    "경의선": "LINE_GYEONGUI",  # 신촌(경의선)
}

# 노선도에는 있으나 게임 대상이 아닌 라벨 (미개통/정기운행 없음)
IGNORE_LABELS = {"도라산", "학익"}

# 역명이 아닌 라벨 (범례, 노선명, 제목 등) 판별용.
# 주의: 이 패턴은 "역 매칭에 실패한 뒤"에만 적용한다. 사전 필터로 쓰면
# 4.19민주묘지 같은 정상 역명을 걸러내 버린다.
NON_STATION = re.compile(
    r"호선$|^경강선$|^경춘선$|^서해선$|^신림선$|^신분당선$|^수인·분당선$|^경의·중앙선$"
    r"|^우이신설선$|^김포도시철도$|^용인경전철$|^의정부경전철$|^인천국제공항철도$"
    r"|노선도|환승역|GTX|Not to scale"
)


# ─── SVG 파싱 ──────────────────────────────────────────────────────────────
TEXT_RE = re.compile(r'<text[^>]*transform="matrix\(([^)]*)\)"[^>]*>(.*?)</text>', re.S)
TSPAN_RE = re.compile(r"<tspan[^>]*>([^<]*)</tspan>")


def fetch_commons_svg() -> tuple[str, str]:
    """커먼즈에서 최신 노선도 SVG 와 리비전 타임스탬프를 가져온다."""
    q = urllib.parse.urlencode(
        {"action": "query", "titles": COMMONS_FILE, "prop": "imageinfo",
         "iiprop": "url|timestamp", "format": "json"}
    )
    req = urllib.request.Request(
        "https://commons.wikimedia.org/w/api.php?" + q, headers={"User-Agent": UA}
    )
    info = json.load(urllib.request.urlopen(req, timeout=60))
    ii = next(iter(info["query"]["pages"].values()))["imageinfo"][0]
    svg = urllib.request.urlopen(
        urllib.request.Request(ii["url"], headers={"User-Agent": UA}), timeout=120
    ).read().decode("utf-8")
    return svg, ii["timestamp"]


def parse_elements(svg: str) -> list[dict]:
    """<text> 요소를 (index, x, y, text) 로 파싱. 여러 줄 <tspan> 은 이어붙인다."""
    out = []
    for i, m in enumerate(TEXT_RE.finditer(svg)):
        coords, body = m.group(1).split(), m.group(2)
        text = (
            "".join(p.strip() for p in TSPAN_RE.findall(body))
            if "<tspan" in body
            else body.strip()
        )
        out.append({"idx": i, "x": float(coords[-2]), "y": float(coords[-1]), "text": text})
    return out


def group_instances(elements: list[dict]) -> list[dict]:
    """같은 좌표에 겹쳐 그려진 요소들(외곽선/본문 레이어)을 하나의 라벨로 묶는다.

    마스킹할 때 이 묶음을 통째로 가려야 밑 레이어의 글자가 비치지 않는다.
    """
    groups = collections.defaultdict(list)
    for e in elements:
        groups[(e["text"], round(e["x"], 1), round(e["y"], 1))].append(e["idx"])
    return [
        {"text": k[0], "x": k[1], "y": k[2], "idx": sorted(v)} for k, v in groups.items()
    ]


# ─── 매핑 ──────────────────────────────────────────────────────────────────
def core(name: str) -> str:
    return name[:-1] if name.endswith("역") else name


def build_mapping(instances: list[dict], stations: list[dict]) -> tuple[dict, list, list]:
    by_id = {s["id"]: s for s in stations}
    lookup = collections.defaultdict(list)
    for s in stations:
        for key in {s["name"], core(s["name"]), *s.get("aliases", [])}:
            lookup[key].append(s)

    def line_mates(st):
        return [
            o for o in stations
            if o["id"] != st["id"] and set(o["lines"]) & set(st["lines"])
        ]

    mapping: dict[int, list[int]] = {}
    unmatched, ambiguous = [], []

    for inst in instances:
        raw, hint = inst["text"], None
        paren = re.match(r"^(.+?)\((.+)\)$", raw)
        if paren and paren.group(2) in PAREN_LINE:
            hint, raw = PAREN_LINE[paren.group(2)], paren.group(1)
        raw = LABEL_FIX.get(raw, raw)

        if not raw or raw in IGNORE_LABELS:
            continue

        cands = lookup.get(raw) or lookup.get(raw + "역") or []
        if hint:
            cands = [c for c in cands if hint in c["lines"]] or cands
        if not cands:
            # 매칭 실패 후에 범례/노선명 여부를 판정한다 (사전 필터 금지)
            if not NON_STATION.search(raw):
                unmatched.append(inst)
            continue

        if len(cands) > 1:
            # 동명이역: 주변 라벨에 같은 노선 역이 몇 개나 있는지로 판별
            near = sorted(
                instances, key=lambda o: math.hypot(inst["x"] - o["x"], inst["y"] - o["y"])
            )[1:12]
            near_names = {o["text"] for o in near}

            def score(c):
                return sum(
                    1 for m in line_mates(c)
                    if m["name"] in near_names or core(m["name"]) in near_names
                )

            ranked = sorted(cands, key=score, reverse=True)
            if len(ranked) > 1 and score(ranked[0]) == score(ranked[1]):
                ambiguous.append((inst["text"], [c["id"] for c in cands]))
                continue
            cands = [ranked[0]]

        mapping.setdefault(cands[0]["id"], []).extend(inst["idx"])

    return {k: sorted(set(v)) for k, v in mapping.items()}, unmatched, ambiguous


# ─── 검증 ──────────────────────────────────────────────────────────────────
def validate(mapping, elements, stations) -> list[str]:
    els = {e["idx"]: e for e in elements}
    by_id = {s["id"]: s for s in stations}
    problems = []

    owners = collections.Counter(i for v in mapping.values() for i in v)
    dupes = [i for i, c in owners.items() if c > 1]
    if dupes:
        problems.append(f"두 역에 중복 배정된 text 요소: {dupes}")

    for sid, idx in mapping.items():
        coords = {(round(els[i]["x"], 1), round(els[i]["y"], 1)) for i in idx}
        if len(coords) > 1:
            problems.append(f"{by_id[sid]['name']}(id={sid}) 요소 좌표가 흩어져 있음: {coords}")

    def pos(sid):
        e = els[mapping[sid][0]]
        return e["x"], e["y"]

    for s in stations:
        if s["id"] not in mapping:
            continue
        mates = [
            o for o in stations
            if o["id"] != s["id"] and o["id"] in mapping and set(o["lines"]) & set(s["lines"])
        ]
        if not mates:
            continue
        x, y = pos(s["id"])
        d = min(math.hypot(x - pos(o["id"])[0], y - pos(o["id"])[1]) for o in mates)
        # 라벨이 엉뚱한 역에 배정됐는지(지도 반대편 등)를 잡는 게 목적이라 임계값은 느슨하게 둔다.
        # GTX-A 는 역간 간격이 실제로 1000px 가까이 되므로 그보다 커야 한다.
        if d > 1500:
            problems.append(
                f"{s['name']}(id={s['id']}, {','.join(s['lines'])}) 같은 노선 역이 {d:.0f}px 떨어져 있음"
            )
    return problems


def diff_mapping(old: dict, new: dict, stations) -> None:
    by_id = {s["id"]: s for s in stations}
    o = {int(k): v for k, v in old.items()}
    n = {int(k): v for k, v in new.items()}
    added = sorted(set(n) - set(o))
    removed = sorted(set(o) - set(n))
    moved = sorted(i for i in set(o) & set(n) if o[i] != n[i])
    name = lambda i: by_id.get(i, {}).get("name", f"id={i}")
    print("\n[이전 매핑과 비교]")
    print(f"  새로 매핑됨 {len(added)}: {[name(i) for i in added][:20]}")
    print(f"  사라짐      {len(removed)}: {[name(i) for i in removed][:20]}")
    print(f"  요소 변경   {len(moved)}: {[name(i) for i in moved][:20]}")
    if not (added or removed or moved):
        print("  변화 없음")


# ─── main ──────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="노선도 SVG <-> DB station 매핑 생성")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--fetch", action="store_true", help="위키미디어 커먼즈에서 최신본 다운로드")
    src.add_argument("--svg", help="로컬 SVG 경로")
    ap.add_argument("--stations", required=True, help="stations.json 경로")
    ap.add_argument("--out", default="station_svg_map.json")
    ap.add_argument("--save-svg", help="--fetch 로 받은 SVG 를 저장할 경로")
    ap.add_argument("--diff", help="비교할 이전 매핑 JSON")
    args = ap.parse_args()

    if args.fetch:
        svg, ts = fetch_commons_svg()
        print(f"커먼즈 최신 리비전: {ts}  ({len(svg):,} bytes)")
        if args.save_svg:
            open(args.save_svg, "w", encoding="utf-8").write(svg)
            print(f"저장: {args.save_svg}")
    else:
        svg = open(args.svg, encoding="utf-8").read()

    stations = json.load(open(args.stations, encoding="utf-8"))
    elements = parse_elements(svg)
    instances = group_instances(elements)
    mapping, unmatched, ambiguous = build_mapping(instances, stations)

    print(f"text 요소 {len(elements)} -> 라벨 인스턴스 {len(instances)}")
    print(f"매핑된 역: {len(mapping)}/{len(stations)}")

    missing = [s for s in stations if s["id"] not in mapping]
    if missing:
        print(f"\n[매핑 실패한 DB 역 {len(missing)}]")
        for s in missing:
            print(f"   {s['id']:5d} {s['name']}  lines={','.join(s['lines'])}")
        print("   -> 노선도 표기가 바뀌었을 수 있다. LABEL_FIX 에 보정을 추가하라.")

    if unmatched:
        labels = sorted({i["text"] for i in unmatched})
        print(f"\n[DB 에 없는 노선도 라벨 {len(labels)}]")
        print(f"   {labels}")
        print("   -> 신설역이면 station 테이블에 추가, 범례면 NON_STATION 에 추가하라.")

    if ambiguous:
        print(f"\n[동명이역 판별 실패 {len(ambiguous)}]: {ambiguous}")

    problems = validate(mapping, elements, stations)
    print(f"\n[검증] {'문제 없음' if not problems else f'{len(problems)}건'}")
    for p in problems:
        print(f"   - {p}")

    if args.diff:
        try:
            diff_mapping(json.load(open(args.diff, encoding="utf-8")), mapping, stations)
        except FileNotFoundError:
            print(f"\n[이전 매핑 없음: {args.diff}] 최초 생성으로 간주")

    json.dump(mapping, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n저장: {args.out}  ({len(mapping)}개 역)")
    return 1 if missing or ambiguous else 0


if __name__ == "__main__":
    sys.exit(main())
