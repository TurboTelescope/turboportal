import argparse
import requests
import base64
import os
import time
from dotenv import load_dotenv
load_dotenv()


url = "http://tayamni.spa.umn.edu/api/"

sci_cutout_png = "Donkey_Kong_character.png"

token = f'token {os.environ['API_KEY']}'


def parse_args():
    parser = argparse.ArgumentParser(description='add a user')
    parser.add_argument('id', type=str, help='Source ID')
    parser.add_argument('-png', type=str, help='Path to PNG file')
    parser.add_argument('-pos', type=float, nargs=2, default=[45, 35], help='RA and Dec coordinates')

    return parser.parse_args()


if __name__ == "__main__":
    success = 0

    args = parse_args()
    # Use provided PNG path or default
    if args.png is not None:
        sci_cutout_png = args.png
    else:
        print("no png path provided, using default...")

    # Set coordinates
    if args.pos is not None:
        ra = args.pos[0]
        dec = args.pos[1]
    else:
        ra = 35
        dec = 45

    # Set headers with API token
    headers = {
        "Content-Type": "application/json",
        "Authorization": token
    }
            
    # Source payload
    payload = {
        "id": args.id,
        "ra": ra,
        "dec": dec,
        "group_ids": [5]
    }

    # Thumbnail payload
    thumbnail = {
        "obj_id": args.id,
        "data": base64.b64encode(open(sci_cutout_png, "rb").read()).decode('utf-8'),
        "ttype": "new",
        "group_ids": [5]
    }
    # try:
    # Post source
    print("Posting source...")
    response1 = requests.post(url + "sources", json=payload, headers=headers)
    # print(f"Source response: {response.status_code}")
    if response1.status_code == 200:
        success +=1
    print(response1.json())
    
    # Post thumbnail
    print("\nPosting thumbnail...")
    response2 = requests.post(url + "thumbnail", json=thumbnail, headers=headers)
    # print(f"Thumbnail response: {response.status_code}")
    if response2.status_code == 200:
        success +=1
    print(response2.json())
    success = 2

    if success == 2:
        print(f"\nTest post successful, you can view it here:http://localhost:8000/source/{args.id}")
        print("you have 2 minutes to click this link before the test post is automatically deleted...")
        try:
            time.sleep(120)
        except KeyboardInterrupt:
            pass
        finally:
            headers = {"Authorization": f"token ",
                "Content-Type": "application/json"}
            json_data = {"group_id": "8"}

            response3 = requests.delete(f"{url}sources/{args.id}", headers=headers, json=json_data)
            print(response3.json())
            response4 = requests.delete(url+ f"thumnail/{1}", headers={"Authorization": headers["Authorization"]})
            print(response4.json())

