
import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("ARCGIS_CLIENT_ID")
CLIENT_SECRET = os.getenv("ARCGIS_CLIENT_SECRET")
print(CLIENT_ID)
print(CLIENT_SECRET)