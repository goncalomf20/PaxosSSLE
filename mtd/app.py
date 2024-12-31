from flask import Flask, render_template, request, redirect, url_for, jsonify
import cv2
import base64
import os
import random
import threading
import time
import json
import csv
import socket
from datetime import datetime, timedelta

app = Flask(__name__)

# Simulated user credentials
VALID_USERNAME = "goncalomf"
VALID_PASSWORD = "password"

# Dictionary to store pass-keys for recognized users
user_passkeys = {}

# Load words from 4000-most-common-english-words-csv.csv
WORD_LIST = []
with open('4000-most-common-english-words-csv.csv', 'r') as file:
    csv_reader = csv.reader(file)
    for row in csv_reader:
        WORD_LIST.extend(row)


# Function to load user data from JSON file
def load_user_data(username):
    filepath = f"allowed/{username}/data.json"
    if os.path.exists(filepath):
        with open(filepath, 'r') as file:
            return json.load(file)
    return None

# Simulated function to check if a face matches using the JSON data
def simulate_face_match(username, captured_image_base64):
    user_data = load_user_data(username)
    if not user_data:
        return False

    # Simulated comparison (just check if the captured image matches the stored image)
    # stored_image_base64 = user_data.get("photo")
    # return captured_image_base64 == stored_image_base64
    return True  # Always return True for now

# Generate a random 16-character pass-key
def generate_passkey():
    return ' '.join(random.choices(WORD_LIST, k=16))

# Function to remove passkey after 1 minute
def expire_passkey(username):
    time.sleep(60)
    user_passkeys.pop(username, None)

# Function to send passkey over a socket
def send_passkey_socket(username, passkey, expiration_time):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("10.0.2.15", 23843))
            data = {
                "username": username,
                "passkey": passkey
            }
            s.sendall(json.dumps(data).encode('utf-8'))
    except Exception as e:
        print(f"Error sending passkey via socket: {e}")

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def handle_login():
    username = request.form['username']
    password = request.form['password']
    if username == VALID_USERNAME and password == VALID_PASSWORD:
        return redirect(url_for('face_scan', username=username))
    return "Invalid credentials, please try again.", 401

@app.route('/face_scan/<username>')
def face_scan(username):
    return render_template('face_scan.html', username=username)

@app.route('/scan_face/<username>', methods=['POST'])
def scan_face(username):
    # success, frame = camera.read()
    # if success:
    #     # Encode frame to base64
    #     _, buffer = cv2.imencode('.jpg', frame)
    #     jpg_as_text = base64.b64encode(buffer).decode('utf-8')

    #     # Simulated face recognition using JSON data
    #     if simulate_face_match(username, jpg_as_text):
    #         passkey = generate_passkey()
    #         user_passkeys[username] = passkey  # Always generate and assign a new passkey
    #         # Start a thread to expire the passkey after 1 minute
    #         threading.Thread(target=expire_passkey, args=(username,)).start()
    #         return redirect(url_for('show_passkey', username=username))

    #     return jsonify({"status": "failure", "message": "Face not recognized."})
    # return jsonify({"status": "error", "message": "Failed to capture image."}), 500
            passkey = generate_passkey()
            expiration_time = datetime.now() + timedelta(days=1)  # Set expiration time to 1 day from now
            user_passkeys[username] = {"passkey": passkey , "ip" : "10.0.2.15" , "port" : "5000"}

            # Send passkey over a socket
            threading.Thread(target=send_passkey_socket, args=(username, passkey, expiration_time)).start()

            # Start a thread to expire the passkey after 1 minute
            threading.Thread(target=expire_passkey, args=(username,)).start()
            return redirect(url_for('show_passkey', username=username))

@app.route('/passkey/<username>')
def show_passkey(username):
    passkey = user_passkeys.get(username)
    if passkey:
        return render_template('passkey.html', passkey=passkey)
    return "Passkey has expired or is invalid.", 404

# Initialize OpenCV video capture
camera = cv2.VideoCapture(0)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

