import os
import requests
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from flask import Flask, request, jsonify

# --- CONFIGURATION ---
# Get these from your dashboards
GEMINI_API_KEY = "#ADD YOUR API KEY"
META_ACCESS_TOKEN = """ADD YOUR TOKEN KEY"""
META_PHONE_NUMBER_ID = "ADD TEMP NUMBER"
VERIFY_TOKEN = "ADD YOURS" # This must match the token you set in the Meta dashboard

# --- INITIALIZATION ---

# Initialize Flask App
app = Flask(__name__)

# Initialize Google Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-latest')

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- HELPER FUNCTION TO SEND MESSAGES ---

def send_whatsapp_reply(phone_number, message_text):
    """Function to send a reply via the Meta WhatsApp API."""
    url = f"https://graph.facebook.com/v18.0/{META_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": { "body": message_text }
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Reply sent successfully to {phone_number}: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send reply to {phone_number}: {e}")

# --- WEBHOOK ENDPOINT ---

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    # Handle the GET request for webhook verification by Meta
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        else:
            return "Verification token mismatch", 403

    # Handle the POST request when a message is received
    if request.method == 'POST':
        data = request.get_json()
        print("--- Full Webhook Data Received ---")
        print(data)
        print("---------------------------------")

        try:
            # Extract message details from the Meta webhook payload
            # This structure can be complex, we are looking for the actual message
            if 'entry' in data and data['entry'] and 'changes' in data['entry'][0] and data['entry'][0]['changes'] and \
               'value' in data['entry'][0]['changes'][0] and 'messages' in data['entry'][0]['changes'][0]['value'] and data['entry'][0]['changes'][0]['value']['messages']:
                
                message_details = data['entry'][0]['changes'][0]['value']['messages'][0]
                user_message = message_details['text']['body']
                user_phone = message_details['from']

                print(f"Message from {user_phone}: {user_message}")

                # --- Get AI Response from Gemini ---
                print(f"Sending to Gemini: {user_message}")
                response = model.generate_content(user_message)
                ai_reply = response.text
                print(f"Gemini Reply: {ai_reply}")

                # --- Send Reply to User ---
                send_whatsapp_reply(user_phone, ai_reply)

                # --- Save to Firestore ---
                try:
                    doc_ref = db.collection('conversations').document()
                    doc_ref.set({
                        'user_phone': user_phone,
                        'user_message': user_message,
                        'bot_reply': ai_reply,
                        'timestamp': datetime.now()
                    })
                    print("Conversation saved to Firestore.")
                except Exception as e:
                    print(f"Error saving to Firestore: {e}")

        except (KeyError, TypeError, IndexError) as e:
            print(f"Could not extract message details. Error: {e}")
            # Do nothing if the webhook is not a user message (e.g., a delivery status)
            pass

        return jsonify({"status": "processed"}), 200

# --- MAIN EXECUTION ---

if __name__ == "__main__":

    app.run(port=5000, debug=True) # debug=True helps with development
