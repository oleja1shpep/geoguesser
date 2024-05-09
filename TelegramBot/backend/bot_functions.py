import logging
import os
import json
import numpy as np
import requests

from math import cos, sin, asin, sqrt, radians, log
from dotenv import load_dotenv
from geopy.distance import geodesic

from backend.database import MongoDB

database = MongoDB()

load_dotenv()

TOKEN_STATIC = os.getenv("TOKEN_STATIC")
YAGPT_APIKEY = os.getenv("YAGPT_APIKEY")
FOLDER_ID = os.getenv("FOLDER_ID")

with open('./backend/text/translations.json', 'r', encoding='utf-8') as file:
    file = json.load(file)
translation = file['translations']
lang_code = file['lang_code']


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('GEOGESSER')
logger.setLevel(logging.DEBUG)

def form_payload(request):
    logger.debug(FOLDER_ID)
    payload = json.dumps({
    "modelUri": f"gpt://{FOLDER_ID}/yandexgpt",
    "completionOptions": {
        "stream": False,
        "temperature": 0.3,
        "maxTokens": "2000"
    },
    "messages": [
        {
        "role": "user",
        "text": request
        }
    ]
    })
    return payload

def gpt_request(cords, language):
    lat1, lon1, lat2, lon2 = map(str, cords.split())
    logger.debug(f"lat: {lat1}, lon: {lon1}")
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat1}&lon={lon1}&zoom=16"
    response = requests.get(url)
    address = ''
    if response.status_code == 200:
        data = response.json()
        address = data.get('display_name')
        logger.info(f"In function: gpt_request: Got address: {address}")
    else:
        logger.warning(f"In function: gpt_request: Coords request error. Address = {address}")
    
    if (address == "" or address == None or type(address) != str):
        if (language == "english"):
            return f"Unable to come up with interesting fact on `{lat1} {lon1}`"
        else:
            return f"Не удалось найти интересный факт в `{lat1} {lon1}`"
    url_2 = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    request = f"Дай мне забавный факт не больше 50 слов на {language} языке об адресе: {address} (убери из адреса номер дома и переведи его на {language} язык, чтобы пользователь смог прочитать адрес)"
    payload = form_payload(request)
    headers = {
    'Authorization': f'Api-Key {YAGPT_APIKEY}',
    'Content-Type': 'application/json'
    }
    response = requests.request("POST", url_2, headers=headers, data=payload)
    logger.debug(f"In function: gpt_request: response = {response.text}")
    try:
        text = json.loads(response.text)["result"]["alternatives"][0]["message"]["text"]
    except Exception as e:
        logger.error(f"In function: gpt_request: {e}")
        return "Ошибка"

    return text

async def get_url(cords):
    lat1, lon1, lat2, lon2 = map(float, cords.split())
    return f"https://maps.googleapis.com/maps/api/staticmap?path=color:0x0000ff80|weight:5|{lat1},{lon1}|{lat2},{lon2}&markers=icon:https://storage.yandexcloud.net/test-geoguessr/correct_marker.png|{lat1},{lon1}&markers=icon:https://storage.yandexcloud.net/test-geoguessr/marker.png|{lat2},{lon2}&size=600x600&key=AIzaSyB90M6YMN89duMBupapc6x7_K8gRNGw7sk"

async def calculate_score_and_distance(cords):
    lat1, lon1, lat2, lon2 = map(float, cords.split())

    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    metres = 6371 * c * 1000
    score = max(min(-log(metres / 70, 1.0014) + 5000, 5000), 0)
    return [int(score), int(metres)]

async def calculate_score_and_distance_moscow_spb(cords):
    lat1, lon1, lat2, lon2 = map(float, cords.split())
    point1 = (lat1, lon1)
    point2 = (lat2, lon2)
    distance = geodesic(point1, point2).meters
    square = 2651
    score = min(5000, int(182.08274202255325 + (1 / (-1.57363469e-19 * distance**4 + 7.96561566e-15 * distance**3  - 2.97318716e-11*distance**2 + 1.28018881e-07*distance + 2.06281343e-04))))
    return [score, int(distance)]

async def calculate_score_and_distance_russia(cords):
    lat1, lon1, lat2, lon2 = map(float, cords.split())
    point1 = (lat1, lon1)
    point2 = (lat2, lon2)
    distance = geodesic(point1, point2).meters
    score = min(5000, int(182.08274326504306 + (1 / (-4.66456406e-30 * distance**4 + 1.01113230e-22* distance**3 - 1.60579053e-16* distance**2 + 2.97335232e-10 * distance + 2.07552620e-04))))
    return [int(score), int(distance)]

async def calculate_score_and_distance_world(cords):
    lat1, lon1, lat2, lon2 = map(float, cords.split())
    point1 = (lat1, lon1)
    point2 = (lat2, lon2)
    distance = geodesic(point1, point2).meters
    score = min(5000, int(182.08275087546463 + (1 / (-1.47589722e-30* distance**4 +  4.26571047e-23* distance**3 - 9.03248644e-17* distance**2 + 2.23000220e-10* distance  + 2.07554107e-04))))
    return [int(score), int(distance)]

async def create_result_text(score, metres, seed, lang = 'en'):
    txt = ""
    if metres < 10000:
        txt = (translation['score and meters'][lang_code[lang]]).format(score, metres)
    elif metres < 100000:
        txt = (translation['score and kilometers'][lang_code[lang]]).format(score, round(metres / 1000, 2))
    else:
        txt = (translation['score and kilometers'][lang_code[lang]]).format(score, round(metres / 1000, 0))
    txt += f"\nSeed: `{seed}`"
    return txt

async def get_top10_single(mode, lang = 'en'):
    try:
        top_10_users = database.get_top10_single(mode)
        logger.info("connected to db. got top 10 players in signle " + mode)
    except Exception as e:
        logger.error(e)
    txt = ''
    # print("- - - - - - - ")
    # print(top_10_users)
    # print("- - - - - - - ")
    for i in range(len(top_10_users)):
        txt += (translation['top 10'][lang_code[lang]]).format(i + 1, top_10_users[i]["username"], top_10_users[i][mode.lower() +"_single_mean_score"],
                                                              top_10_users[i][mode.lower() +"_single_game_counter"])
    # print(top_10_users)
    return txt

async def get_last5_results_single(tele_id, mode, lang = 'en'):
    try:
        games = database.get_last5_results(tele_id, mode)
        logger.info("connected to db. got last 5 games in signle " + mode)
    except Exception as e:
        logger.error(e)

    txt = ''
    for i in range(len(games)):
        metres = games[i][1]
        if metres < 10000:
            txt += (translation['last 5 res metres'][lang_code[lang]]).format(i + 1, games[i][0], metres)
        elif metres < 100000:
            txt += (translation['last 5 res km'][lang_code[lang]]).format(i + 1, games[i][0], round(metres / 1000, 2))
        else:
            txt += (translation['last 5 res km'][lang_code[lang]]).format(i + 1, games[i][0], round(metres / 1000, 0))

    if len(games) == 0:
        txt = (translation['no games'][lang_code[lang]])
    return txt
