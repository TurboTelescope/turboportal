import requests
import time
import os
import re
from dotenv import load_dotenv
load_dotenv()

url = "https://tayamni.spa.umn.edu/api/"

token = f'token {os.environ['API_KEY']}'


headers = {
            # "Content-Type": "application/json",
            "Authorization": token
           }


def nickname_to_i(nickname):
    # Regex to extract: Turbo number, Mount number, and Side (I or O)
    match = re.match(r"T(\d)M(\d)S([IO])", nickname)
    
    if not match:
        return None
    
    turbo = int(match.group(1))
    mount = int(match.group(2))
    side = match.group(3)
    
    # 1. Determine the base offset based on the Turbo number
    # T2 starts at 0, T1 starts at 4, T3 starts at 8
    offsets = {2: 0, 1: 4, 3: 8}
    base_i = offsets.get(turbo, 0)
    
    # 2. Add the Mount offset
    # Every Mount represents 2 indices (Inside and Outside)
    mount_offset = (mount - 1) * 2
    
    # 3. Add the Side offset
    # Inside (I) is the first index (0), Outside (O) is the second (1)
    side_offset = 0 if side == "I" else 1
    
    return base_i + mount_offset + side_offset


for i in range(12):
    if i < 4:
        lat = ((i//2)*0.0001)
        s = (i/2)-(i//2) + 1
        nickname= f"T2M{((i//2)+1)}S{"I" if s==1 else "O"}"
        name=f"TURBO 2 Mount {((i//2)+1)} {"Inside" if s==1 else "Outside"} Scope"
    if 3 < i < 8:
        lat = ((i//2)*0.0001)
        s = (i/2)-(i//2) + 1
        nickname= f"T1M{((i//2)+1)-2}S{"I" if s==1 else "O"}"
        name=f"TURBO 1 Mount {((i//2)+1)-2} {"Inside" if s==1 else "Outside"} Scope"
    if 7 < i < 12:
        lat = ((i//2)*0.0001)
        s = (i/2)-(i//2) + 1
        nickname= f"T3M{((i//2)+1)-4}S{"I" if s==1 else "O"}"
        name=f"TURBO 3 Mount {((i//2)+1)-4} {"Inside" if s==1 else "Outside"} Scope"
    
    # telescope_data = {
    #     "name": name,
    #     "nickname": nickname,
    #     "lat": 33.9789 + ((i//2)*0.0001),
    #     "lon": -107.187184,
    #     "elevation": 3230.9,
    #     "diameter": 0.2794,
    #     "robotic": True,
    #     "fixed_location": True
    # }
    # print(telescope_data["name"])

    # response = requests.post(url + "telescope", json=telescope_data,  headers=headers)
    # time.sleep(1)

    # print(response.json())
    print(nickname, i, nickname_to_i(nickname))

    instrument_data = {
        "name": f'ZWO ASI 6200mm {nickname}',
        "type": "imager",
        "telescope_id": i+1,
        "band": "Optical",
        "filters": ["sdssg" if s==1 else "sdssr"]

    }

    # print(instrument_data['name'], instrument_data['telescope_id'])
    # response = requests.put(url + f"instrument/{i+1}", json=instrument_data,  headers=headers)
    # time.sleep(1)
    # print(response.json())





# data = {
#     "name": f"Multiple Mirror Telescope",
#     "nickname": f"MMT",
#     "lat": 31.689081,
#     "lon": -110.885148,
#     "elevation": 2616,
#     "diameter": 6.5,
#     "robotic": True,
#     "fixed_location": True
# }

# response = requests.post(url, json=data,  headers=headers)
# time.sleep(1)

# print(response.json())