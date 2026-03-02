import os, requests
from flask import Flask
from dotenv import load_dotenv

# stores all the major config elements

load_dotenv()
AZ_KEY = os.getenv('AZURE_SPEECH_KEY')
REGION = os.getenv('AZURE_REGION')
USER_AGENT = os.getenv('USER_AGENT')

app = Flask(__name__)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": USER_AGENT
})