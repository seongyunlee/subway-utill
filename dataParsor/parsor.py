import pandas as pd

# "source.xlsx" 파일을 불러옵니다. 첫 번째 시트의 첫 번째 행을 헤더로 사용합니다.
df = pd.read_excel("source.xlsx", sheet_name=0, header=0)
df2 = pd.read_excel("source.xlsx", sheet_name=1, header=0).to_dict(orient='records')

stationID = {}
for row in df2:
    stationID[row['NAME']] = row['LINE_CODE']


# 데이터프레임의 각 행을 dictionary로 변환합니다.
data_as_dict = df.to_dict(orient='records')

groupyBySTIN_NM = {}

for row in data_as_dict:
    key = row['STIN_NM'].split("(")[0]
    if row['STIN_NM'] not in groupyBySTIN_NM:
        groupyBySTIN_NM[key] = {"id":len(groupyBySTIN_NM)+1, "stations":[],"aliasName":[]}
    groupyBySTIN_NM[key]["stations"].append(stationID[row["LN_NM"]])
    # 역명은 나온 그대로 저장
    # 이름에 괄호가 있는 경우, 괄호 안의 이름을 별도로 저장합니다.
    # 예) '서울역(경의중앙선)' -> '서울역', '경의중앙선'
    alias = [row['STIN_NM']]

    if "(" in row['STIN_NM']:
        alias.append(row['STIN_NM'].split("(")[1][:-1])
        alias.append(row['STIN_NM'].split("(")[0])
    appended = []
    for a in alias:
        if a[-1]=="역":
            appended.append(a[:-1])
        else:
            appended.append(a+"역")
    alias.extend(appended)
    groupyBySTIN_NM[key]["aliasName"].extend(alias)
# save as json file with encoding
import json
with open('output.json', 'w', encoding='utf-8') as f:
    json.dump(groupyBySTIN_NM, f, ensure_ascii=False, indent=4)

# connect to local mysql server
import pymysql

conn = pymysql.connect(
    host='localhost',
    user='root',
    password='gj9r33s&',
    db="subway",
    charset='utf8'
)
cur = conn.cursor()
for key, value in groupyBySTIN_NM.items():
    try:
        cur.execute("INSERT INTO station (id, name) VALUES (%s, %s)", (value["id"], key))
        for alias in value["aliasName"]:
            cur.execute("INSERT INTO alias_name (station_id, alias_name) VALUES (%s, %s)", (value["id"], alias))
        for line in value["stations"]:
            cur.execute("INSERT INTO station_line (station_id, line_id) VALUES (%s, %s)", (value["id"], line))
    except Exception as e:
        print(e)
conn.commit()
cur.close()


print(groupyBySTIN_NM)

