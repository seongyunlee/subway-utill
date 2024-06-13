# read file
file = open("역 순위.csv", "r", encoding="utf-8")
line = file.readline()
stations = line.split(",")
stations = [station.strip() for station in stations]

start = 200000
#send post request
import requests

for i in range(len(stations)):
    try:
        url = "http://localhost:8080/admin/saveCnt"
        data = {
            "stationName": stations[i],
            "boardingCnt": start
        }
        response = requests.post(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        start-=100
    except Exception as e:
        print("error",stations[i])
        break