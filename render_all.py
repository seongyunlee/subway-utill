#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""크롭 전량 렌더: viewBox 적용 + 대상(및 동명이역) 마스킹 -> PNG"""
import json, os, subprocess, sys, tempfile, time, argparse, collections
from PIL import Image

# Chrome(스냅)은 창을 약 780x493 아래로 줄이지 못한다. 요청 크기가 그보다 작으면
# 스크린샷이 SVG 아래 빈 페이지까지 담아 하단에 흰 띠가 생긴다.
# 넉넉한 창으로 찍고 좌상단을 잘라내 정확한 크기를 얻는다.
MIN_WIN_W, MIN_WIN_H = 900, 700

def build(crops_path, smap_path, stations_path):
    crops = {int(k): v for k, v in json.load(open(crops_path)).items()}
    smap = {int(k): v for k, v in json.load(open(smap_path)).items()}
    stations = {s["id"]: s for s in json.load(open(stations_path))}

    # 정답으로 인정되는 문자열이 겹치는 역끼리 묶는다.
    # 겹치는 역이 같은 크롭 안에 보이면 답이 노출되므로 함께 가려야 한다.
    by_answer = collections.defaultdict(set)
    for s in stations.values():
        for a in {s["name"], *s["aliases"]}:
            by_answer[a].add(s["id"])
    twins = {sid: set().union(*(by_answer[a] for a in {s["name"], *s["aliases"]}))
             for sid, s in stations.items()}
    return crops, smap, stations, twins

def mask_indices(sid, crops, smap, twins):
    """대상 + 크롭 안에 걸치는 동명이역의 text 요소 인덱스"""
    idx = list(smap[sid])
    vx, vy, w, h = crops[sid]["viewBox"]
    for t in twins[sid]:
        if t == sid or t not in smap:
            continue
        idx += smap[t]          # 같은 이름이면 무조건 함께 마스킹 (크롭 밖이면 무해)
    return sorted(set(idx))

def render(svg, sid, crops, idx, out_png, scale=1.0):
    vx, vy, w, h = crops[sid]["viewBox"]
    ow, oh = int(round(w * scale)), int(round(h * scale))
    js = (f"<script>window.addEventListener('load',()=>{{"
          f"const g=document.querySelector('svg');"
          f"g.setAttribute('viewBox','{vx} {vy} {w} {h}');"
          f"g.setAttribute('width','{ow}');g.setAttribute('height','{oh}');"
          f"g.style.width='{ow}px';g.style.height='{oh}px';g.style.display='block';"
          f"const e=[...g.querySelectorAll('text')];"
          f"for(const i of {json.dumps(idx)}){{if(e[i]){{e[i].textContent='???';e[i].style.fill='red';}}}}"
          f"}});</script>")
    html = ('<!doctype html><meta charset="utf-8">'
            '<body style="margin:0;background:#fff">' + svg + js + '</body>')
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html); path = f.name
    raw = out_png + ".raw.png"
    try:
        subprocess.run(["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
                        "--hide-scrollbars", "--force-device-scale-factor=1",
                        f"--window-size={max(ow, MIN_WIN_W)},{max(oh, MIN_WIN_H)}",
                        "--virtual-time-budget=8000",
                        f"--screenshot={raw}", f"file://{path}"],
                       capture_output=True, timeout=120)
        if not os.path.exists(raw):
            return False
        Image.open(raw).convert("RGB").crop((0, 0, ow, oh)).save(out_png)
    finally:
        os.unlink(path)
        if os.path.exists(raw):
            os.remove(raw)
    return os.path.exists(out_png) and os.path.getsize(out_png) > 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", default="linemap.svg")
    ap.add_argument("--crops", default="crops15.json")
    ap.add_argument("--map", default="station_svg_map.json")
    ap.add_argument("--stations", default="stations_from_db.json")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--only", type=int, nargs="*", help="특정 station id 만")
    a = ap.parse_args()

    svg = open(a.svg, encoding="utf-8").read()
    crops, smap, stations, twins = build(a.crops, a.map, a.stations)
    os.makedirs(a.outdir, exist_ok=True)

    ids = a.only if a.only else sorted(crops)
    unknown = [i for i in ids if i not in crops]
    if unknown:
        print(f"  크롭 대상이 아니라 건너뜀: {unknown}")
        ids = [i for i in ids if i in crops]
    manifest, fails, t0 = {}, [], time.time()
    for n, sid in enumerate(ids, 1):
        idx = mask_indices(sid, crops, smap, twins)
        out = os.path.join(a.outdir, f"{sid}.png")
        ok = render(svg, sid, crops, idx, out)
        if not ok:
            fails.append(sid); continue
        manifest[sid] = {"station_id": sid, "name": stations[sid]["name"],
                         "file": out, "scale": crops[sid]["scale"],
                         "viewBox": crops[sid]["viewBox"],
                         "masked_elements": len(idx),
                         "neighbors_visible": crops[sid]["neighbors_visible"],
                         "bytes": os.path.getsize(out)}
        if n % 50 == 0 or n == len(ids):
            el = time.time() - t0
            print(f"  {n}/{len(ids)}  {el:.0f}s  (예상 총 {el/n*len(ids):.0f}s)", flush=True)
    json.dump(manifest, open(os.path.join(a.outdir, "manifest.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"\n완료 {len(manifest)}/{len(ids)}  실패 {fails or '없음'}")
    if manifest:
        b = sorted(m["bytes"] for m in manifest.values())
        print(f"파일크기 min/p50/max: {b[0]//1024}KB / {b[len(b)//2]//1024}KB / {b[-1]//1024}KB")

if __name__ == "__main__":
    main()
