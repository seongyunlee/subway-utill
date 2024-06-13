viaBaseUrl = "https://map.naver.com/p/api/pubtrans/subway-directions?start=%s&goal=%s&via[]=%s&serviceDay=1&departureTime=2024-04-18T%s:00:00.000Z&lang=ko&pathType=duration&includeDetailOperation=true"
baseUrl = "https://map.naver.com/p/api/pubtrans/subway-directions?start=%s&goal=%s&serviceDay=1&departureTime=2024-04-18T%s:00:00.000Z&lang=ko&pathType=duration&includeDetailOperation=true"


import requests
import json
import random
import pymysql



def getSubwayPath(start, goal, via):
    if via:
        url = viaBaseUrl % (start, goal, via, "12")
    else:
        url = baseUrl % (start, goal, "12")
    response = requests.get(url)
    return response.json()

def getInterStaion(data):
    for path in data['paths']:
        if path['optimizationMethod']!="MINIMUM_DURATION":
            continue
        interStation = set()
        duration = path['duration']
        for legs in path['legs']:
            for step in legs['steps']:
                for station in step['stations']:
                    interStation.add(str(station['id']))
        return interStation, duration
    
def getTime(data):
    for path in data['paths']:
        if path['optimizationMethod']!="MINIMUM_DURATION":
            continue
        return path['duration']

def getAverageTime(start, goal, via):
    times = []
    for i in ["08", "12", "17"]:
        if via:
            url = viaBaseUrl % (start, goal, via, i)
        else:
            url = baseUrl % (start, goal, i)
        response = requests.get(url)
        data = response.json()
        times.append(getTime(data))
    return sum(times)/len(times)


# jsonify
def dict_to_json(dict):
    return json.dumps(dict, ensure_ascii=False)

def parseStationJSON():
    stationName = {}
    with open('stations.json') as f:
        data = json.load(f)
        for station in data[0]["realInfo"]:
            name = station["name"].strip().split("(")[0].strip()
            stationName[str(station["id"])] = name
    return stationName

stationName = parseStationJSON()
stationList = list(stationName.keys())

def makeProblem():
    while True:
        startStation = random.choice(stationList)
        goalStation = random.choice(stationList)
        if startStation!=goalStation:
            break
    res = getSubwayPath(startStation, goalStation, None)
    stationBetween, _ = getInterStaion(res)
    answer = None
    while True:
        answer = random.choice(list(stationBetween))
        if answer!=startStation and answer!=goalStation:
            break
    answerDuration = getAverageTime(startStation, goalStation, answer)
    if answerDuration>70:
        return makeProblem()
    wrongChoice = []
    while len(wrongChoice)<3:
        choice = random.choice(stationList)
        if choice in [startStation, goalStation, answer]+[station[0] for station in wrongChoice]:
            continue
        time = getAverageTime(startStation, goalStation, choice)
        if time - 10 > answerDuration:
            wrongChoice.append([choice, time])
    return {
        "start":stationName[startStation],"end":stationName[goalStation],
        "answer":{"stationName":stationName[answer], "duration":answerDuration},
        "wrong":[{"stationName":stationName[station], "duration":time} for station, time in wrongChoice]
    }
conn = pymysql.connect(
    host='zeehacheol-db-main.cv4ey4i6e7gl.ap-northeast-2.rds.amazonaws.com',
    user='api-server',
    password=']NK9+c#HUK7ZR}9',
    db="subway",
    charset='utf8'
    )
cur = conn.cursor()

def findStationID(stationName):
    cur.execute("SELECT id FROM station WHERE name=%s", (stationName))
    id = cur.fetchone()
    if not id:
        cur.execute("SELECT id FROM alias_name WHERE alias_name=%s", (stationName))
        id = cur.fetchone()
    if not id:
        raise Exception("Station not found")
    return id
    


def saveProblem(problem):
    sql = "INSERT INTO best_route_problem (ANSWER, CHOICE1, CHOICE2, CHOICE3, CHOICE4, START_STATION, END_STATION, CHOICE1_TIME, CHOICE2_TIME, CHOICE3_TIME, CHOICE4_TIME, DIFFICULTY_INDEX) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ((SELECT BOARDING_CNT from station where ID=%s)+(SELECT BOARDING_CNT from station where ID=%s)))"

    answerIndex = random.randint(0, 3)
    answerId = findStationID(problem["answer"]["stationName"])
    endStationId = findStationID(problem["end"])
    startStationId = findStationID(problem["start"])
    choices = []
    idx = 0
    for i in range(4):
        if i==answerIndex:
            choices.append([findStationID(problem["answer"]["stationName"]), problem["answer"]["duration"]])
        else:
            choices.append([findStationID(problem["wrong"][idx]["stationName"]), problem["wrong"][idx]["duration"]])
            idx += 1
    cur.execute(sql, (answerId, choices[0][0], choices[1][0], choices[2][0], choices[3][0], startStationId, endStationId, choices[0][1], choices[1][1], choices[2][1], choices[3][1],  startStationId, endStationId))
    conn.commit()




failed = []
for idx in range(1000):
    print("Making problem %d" % idx)
    try:
        problem = makeProblem()
        saveProblem(problem)
    except Exception as e:
        print(e)
        failed.append(problem)
        
# save failed as json file
with open('failed.json', 'w', encoding='utf-8') as f:
    json.dump(failed, f, ensure_ascii=False, indent=4)




cur.close()


    
    


"""
https://map.naver.com/p/api/pubtrans/subway-directions?start=333&goal=226&via%5B%5D=214&lang=ko&pathType=duration&includeDetailOperation=true
https://map.naver.com/p/api/pubtrans/subway-directions?start=1000&goal=333&via%5B%5D=226&serviceDay=1&departureTime=2024-04-18T08:00:00.000Z&lang=ko&pathType=duration&includeDetailOperation=true
"""