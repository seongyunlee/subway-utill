# 문제 생성 파이프라인

DB 가 비었을 때 역/노선 데이터와 두 게임의 문제를 다시 만드는 절차.

## 1. 역 · 노선 (station / station_line / alias_name)

한국어 위키백과의 노선별 `분류:○○의 역` 과 `분류:YYYY년 개업한 철도역` 에서 뽑는다.
개통분만 걸러지고, 미개통·무정차역은 제외된다.

## 2. 노선도 ↔ DB 매핑

    ./build_station_map.py --fetch --stations stations_from_db.json \
        --out station_svg_map.json --save-svg linemap.svg

노선도(위키미디어 커먼즈, 퍼블릭 도메인)의 `<text>` 인덱스를 station.ID 에 잇는다.
노선도가 갱신되면 다시 돌린다. `--diff` 로 이전 매핑과 비교하면 신설역·역명변경이 드러난다.
전부 매핑되면 exit 0, 실패한 역이 있으면 exit 1.

`stations_from_db.json` 은 DB 에서 뽑는다:

    SELECT JSON_ARRAYAGG(JSON_OBJECT(
      'id', s.ID, 'name', s.NAME,
      'lines',  COALESCE((SELECT JSON_ARRAYAGG(l.LINE_ID) FROM station_line l WHERE l.STATION_ID=s.ID), JSON_ARRAY()),
      'aliases',COALESCE((SELECT JSON_ARRAYAGG(a.ALIAS_NAME) FROM alias_name a WHERE a.STATION_ID=s.ID), JSON_ARRAY())
    )) FROM station s;

## 3. 빈칸 맞추기 (fill_blank_problem)

노선도에서 역명을 `???` 로 가리고 320x280 으로 크롭해 PNG 를 만든다.

    ./render_all.py --crops crops_final.json --outdir final
    aws s3 cp final/ s3://subwaygame/fillblank/ --recursive --exclude "*" \
        --include "*.png" --acl public-read --content-type image/png

주변 역명이 하나도 안 보이는 역은 풀 수 없으므로 제외한다(655 중 541 생성).
이름이 겹치는 역(신촌 2개)은 함께 가려야 정답이 노출되지 않는다.
파일명은 `{station_id}.png` — UUID 를 쓰면 DB 가 날아갈 때 매핑을 복구할 수 없다.

## 4. 최적경로 (best_route_problem)

네이버 지하철 경로탐색 API 를 크롤링한다.

    ./gen_bestroute.py --count 2000 --delay 0.5 --out bestroute_problems.json
    ./load_bestroute.py --src bestroute_problems.json --out bestroute_seed.sql

난이도는 "정답과 가장 가까운 오답의 시간차"로 정의하고 밴드별 할당량으로 층화 추출한다
(hard 4~10분 30% / medium 10~25분 40% / easy 25분+ 30%).
출발역+도착역 승하차 합은 실측 상관계수가 +0.04 로 실제 난이도와 무관했다.

소요시간은 08/12/17 세 시간대 평균이다. 급행 운행이 시간대별로 달라 한 번만 재면 왜곡된다.
2000건에 약 5시간 40분, API 약 52,000회. 중간에 끊겨도 이어서 돌아간다.

`watch_and_load.sh` 는 생성이 끝나면 자동으로 SQL 생성 + 적재까지 한다.

### 적재 후 반드시

`BestRouteRepository` 가 인덱스로 문제를 캐싱하므로, 재적재하면 옛 PROBLEM_ID 가
계속 나가 제출 검증이 깨진다. 백엔드를 재기동하거나 `evictProblemCache()` 를 호출한다.
