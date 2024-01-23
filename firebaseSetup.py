import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import json

# For each scale we will need to run this script once, this will setup firebase to accept information for that scale
# We are pushing the scale_info.json file
# You must modify lines 2 and 4 with a unique scale number
# Pushing this again will overwrite any values with default values

"""DO NOT PUSH THIS FILE TO GITHUB, CONTAINS ACCESS TOKENS"""
# Fetch the service account key JSON file contents
cred = credentials.Certificate('ece-180-project-firebase-adminsdk-7eg04-74b6c29e0b.json')

# Initialize the app with a service account, granting admin privileges
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://ece-180-project-default-rtdb.firebaseio.com/'
})

ref = db.reference("/")
with open("scale_info.json", "r") as f:
	file_contents = json.load(f)
ref.set(file_contents)