import requests
import os
from dotenv import load_dotenv
load_dotenv()

url = "http://tayamni.spa.umn.edu/api/user/3/roles"

token = f'token {os.environ['API_KEY']}'


# payload = {"roleIds": ["Super admin"]}
# headers = {
#     "Content-Type": "application/json",
#     "Authorization": token
# }

# response = requests.post(url, json=payload, headers=headers)

# print(response.json())


import requests

url = "http://tayamni.spa.umn.edu/api/user/3"

headers = {"Authorization": token}

response = requests.get(url, headers=headers)

print(response.json())