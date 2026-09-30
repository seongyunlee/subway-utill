#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';

const API_KEY = process.env.SEOUL_OPEN_API_KEY;
if (!API_KEY) {
  console.error('SEOUL_OPEN_API_KEY is required');
  process.exit(1);
}

const OUT_DIR = '/home/lee/.openclaw/workspace/projects/subway/subway-utill/dataParsor';

const lineMap = {
  '1호선': 'LINE_1',
  '2호선': 'LINE_2',
  '3호선': 'LINE_3',
  '4호선': 'LINE_4',
  '5호선': 'LINE_5',
  '6호선': 'LINE_6',
  '7호선': 'LINE_7',
  '8호선': 'LINE_8',
  '9호선': 'LINE_9',
  '공항철도': 'LINE_AIR',
  '경의중앙선': 'LINE_GYEONGUI',
  '우이신설선': 'LINE_UISINSUL',
  '경강선': 'LINE_GYEONGANG',
  '경춘선': 'LINE_GYEONCHUN',
  '신림선': 'LINE_SINRIM',
  '에버라인': 'LINE_EVER',
  '인천1호선': 'LINE_INCHEON1',
  '서해선': 'LINE_SEOHEA',
  '김포골드라인': 'LINE_GIMPO',
  '신분당선': 'LINE_SINBUNDANG',
  '인천2호선': 'LINE_INCHEON2',
  '수인분당선': 'LINE_SUINBUNDANG',
  '의정부경전철': 'LINE_UIJEONGBU'
};

function normalizeLine(name) {
  const cleaned = (name || '').trim();
  if (lineMap[cleaned]) return lineMap[cleaned];
  return `LINE_${cleaned.replace(/[^\p{L}\p{N}]+/gu, '_').toUpperCase()}`;
}

function hashCode(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (h * 31 + str.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

async function fetchPage(start, end) {
  const url = `http://openapi.seoul.go.kr:8088/${API_KEY}/json/SearchSTNBySubwayLineInfo/${start}/${end}/`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function main() {
  const step = 1000;
  let start = 1;
  let total = Infinity;
  const rows = [];

  while (start <= total) {
    const end = start + step - 1;
    const json = await fetchPage(start, end);
    const body = json.SearchSTNBySubwayLineInfo;
    if (!body) throw new Error(`Unexpected response: ${JSON.stringify(json).slice(0, 500)}`);

    total = Number(body.list_total_count || 0);
    const pageRows = body.row || [];
    rows.push(...pageRows);

    if (!pageRows.length) break;
    start = end + 1;
  }

  const byName = new Map();
  for (const r of rows) {
    const stationName = (r.STATION_NM || '').trim();
    if (!stationName) continue;

    const lineCode = normalizeLine(r.LINE_NUM || '');
    const key = stationName;

    if (!byName.has(key)) {
      byName.set(key, {
        id: hashCode(stationName) % 900000 + 100000,
        stations: new Set(),
        aliasName: new Set([stationName])
      });
    }

    const item = byName.get(key);
    item.stations.add(lineCode);

    if (r.STATION_CD) item.aliasName.add(String(r.STATION_CD));
    if (r.FR_CODE) item.aliasName.add(String(r.FR_CODE));
  }

  const output = {};
  for (const [name, v] of byName.entries()) {
    output[name] = {
      id: v.id,
      stations: [...v.stations],
      aliasName: [...v.aliasName]
    };
  }

  const rawPath = path.join(OUT_DIR, 'seoul-master.raw.json');
  const outPath = path.join(OUT_DIR, 'output.latest.json');

  await fs.writeFile(rawPath, JSON.stringify(rows, null, 2), 'utf-8');
  await fs.writeFile(outPath, JSON.stringify(output, null, 2), 'utf-8');

  console.log(`saved ${rows.length} rows -> ${Object.keys(output).length} stations`);
  console.log(`raw: ${rawPath}`);
  console.log(`normalized: ${outPath}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
