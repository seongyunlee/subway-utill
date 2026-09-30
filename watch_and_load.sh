#!/bin/bash
# 2000건 생성이 끝나면 난이도 지표 계산 -> SQL 생성 -> DB 적재까지 자동으로 한다.
# (캐시 비우기와 배포는 백엔드 재기동이 필요해서 사람이 확인 후 진행)
cd /home/lee/.openclaw/workspace/projects/subway/subway-utill
LOG=autoload.log
: > "$LOG"
echo "[$(date)] 생성 종료 대기" >> "$LOG"
while pgrep -f "gen_bestroute.py --count 2000" >/dev/null; do sleep 60; done
echo "[$(date)] 생성 종료 감지" >> "$LOG"
python3 -c "import json;print('생성 건수', len(json.load(open('bestroute_problems.json'))))" >> "$LOG" 2>&1

python3 load_bestroute.py --src bestroute_problems.json --out bestroute_seed.sql >> "$LOG" 2>&1 || {
  echo "[$(date)] SQL 생성 실패" >> "$LOG"; echo FAILED > LOAD_STATUS; exit 1; }

PW=$(sudo docker inspect subway-db --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^MYSQL_ROOT_PASSWORD=//p')
sudo docker cp bestroute_seed.sql subway-db:/tmp/br.sql >/dev/null
sudo docker exec subway-db sh -c "mysql -uroot -p'$PW' subway < /tmp/br.sql" >> "$LOG" 2>&1 || {
  echo "[$(date)] 적재 실패" >> "$LOG"; echo FAILED > LOAD_STATUS; exit 1; }
sudo docker exec subway-db rm -f /tmp/br.sql

sudo docker exec subway-db mysql -uroot -p"$PW" -t --default-character-set=utf8mb4 subway -e "
SELECT COUNT(*) rows_now, MIN(DIFFICULTY_INDEX) di_min,
       ROUND(AVG(DIFFICULTY_INDEX)) di_avg, MAX(DIFFICULTY_INDEX) di_max
FROM best_route_problem;" >> "$LOG" 2>&1
echo "[$(date)] 적재 완료" >> "$LOG"
echo DONE > LOAD_STATUS
