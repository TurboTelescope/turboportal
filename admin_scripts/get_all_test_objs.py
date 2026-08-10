import requests
import os
from dotenv import load_dotenv
load_dotenv()

url = "https://tayamni.spa.umn.edu/api/sources"

token = f'token {os.environ['API_KEY']}'

headers = {"Authorization": token}

response = requests.get(url, headers=headers)

print(response.json())