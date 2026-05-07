from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
from dotenv import load_dotenv

load_dotenv()  # Natively pulls local .env variables tracking AIRTABLE_TOKEN

app = Flask(__name__)
CORS(app)

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appryWRqjOFw4EajV")

@app.route('/api/airtable/<table>', methods=['GET'])
def proxy_airtable(table):
    if not AIRTABLE_TOKEN:
        return jsonify({"error": "AIRTABLE_TOKEN absent from local environment trace"}), 500
        
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        # Forward frontend parameters explicitly routing them to Airtable dynamically
        response = requests.get(url, headers=headers, params=request.args)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e), "details": response.text if 'response' in locals() else ""}), 500

if __name__ == '__main__':
    print("Starting GroceryCompare Secure API Routing on Port 5000...")
    app.run(debug=True, port=5000)
