import requests

API_URL = "https://www.sadim.cloud/api/add_bots"

payload = {
    "bot_token": "7774145310:AAFHo1qqU7RCya4F8j_J1u8WYKBT5M9EATk",
    "user_id": 7019373567,          # آيدي تيليجرام الذي سيصله إشعار التفعيل
    "admin_token": "123456"
}

response = requests.post(API_URL, json=payload, timeout=30)

print("Status Code:", response.status_code)
print("Response:", response.json())