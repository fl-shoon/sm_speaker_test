from google.oauth2.credentials import Credentials
from google.cloud.firestore import Client
from requests.exceptions import HTTPError

import json
import logging
import os
import requests

logging.basicConfig(level=logging.INFO)
fireclient_logger = logging.getLogger(__name__)

_DEVICE_SCHEMA = {
    'temperatureSensor': str,
    'irSensor': bool,
    'brightnessSensor': str,  
}

def _validate_data_types(data):
    invalid_fields = []
    for field, value in data.items():
        if field in _DEVICE_SCHEMA:
            if not isinstance(value, _DEVICE_SCHEMA[field]):
                invalid_fields.append(f"{field} (expected {_DEVICE_SCHEMA[field].__name__}, got {type(value).__name__})")
        else:
            invalid_fields.append(f"{field} (unexpected field)")
    return invalid_fields
  
class FireClient:
    def __init__(self):
        self.db = None
        self.firebase_api = "https://identitytoolkit.googleapis.com/v1/accounts"
        self.api_key = os.environ["FIREBASE_API_KEY"]
        self.email = os.environ["FIREBASE_AUTH_EMAIL"]
        self.password = os.environ["FIREBASE_AUTH_PASSWORD"]
        self.project_id = os.environ["FIREBASE_PROJECT_ID"]
        self.initialize()

    def initialize(self):
        response = self.sign_in_with_email_and_password(self.api_key, self.email, self.password)
        creds = Credentials(response['idToken'], response['refreshToken'])
        self.db = Client(project=self.project_id,credentials=creds)

    def sign_in_with_email_and_password(self, api_key, email, password):
        request_url = "%s:signInWithPassword?key=%s" % (self.firebase_api, api_key)
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"email": email, "password": password, "returnSecureToken": True})
        
        req = requests.post(request_url, headers=headers, data=data)
        try:
            req.raise_for_status()
        except HTTPError as e:
            raise HTTPError(e, req.text)
            
        return req.json()
    
    def fetch_schedule(self):
        try:
            doc_ref = self.db.collection('schedulers').document('medicine_reminder_time')
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()
            else:
                fireclient_logger.info("Failed to fetch schedule")
                return {}
        except Exception as e:
            fireclient_logger.error(f"Error occurred in fetching schedule: {e}")
            
        return {}
        
    def update_sensor_data(self, data = {}):
        try:
            invalid_fields = _validate_data_types(data)

            if invalid_fields:
                fireclient_logger.error(f"Failed to update sensor data. Invalid data type")
                return False

            doc_ref = self.db.collection('speakers').document(os.environ["SPEAKER_ID"])

            doc = doc_ref.get()
            if doc.exists:
                doc_ref.update(data)
                message = "Sensor data updated successfully"
            else:
                doc_ref.set(data)
                message = "Sensor data created successfully"

            fireclient_logger.info(message)
            return True
        except Exception as e:
            fireclient_logger.error(f"Error in sensor data update: {e}")
            
        return False