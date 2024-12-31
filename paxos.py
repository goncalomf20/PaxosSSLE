from flask import Flask, request, jsonify
import threading
import socket
import json
import subprocess
from datetime import datetime
import random

app = Flask(__name__)
port = random_port = random.randint(1024, 65535)
expire = {}
nodes = {}
next_node_id = 1
accounts = {}
selected_words_cache = {}

def sum_words(words):
    """Sum the selected words."""
    return ''.join(words) 

@app.route('/<username>', methods=['POST'])
def register_node(username):
    global next_node_id

    ip_address = request.json.get('ip')
    
    if not ip_address:
        return jsonify({'error': 'IP address is required'}), 400
    
    if not username:
        return jsonify({'error': 'Username is required'}), 400

    if username in accounts.keys():
        # Select 3 random indices from the passkey array
        passkey_array = accounts[username]
        if len(passkey_array) == 16:  # Ensure the passkey array has 16 words
            selected_indices = random.sample(range(16), 3)

            # Cache the selected indices for verification
            selected_words_cache[username] = selected_indices

            return jsonify({
                'selected_indices': selected_indices  # Send only the indices
            }), 201
        else:
            return jsonify({'error': 'Invalid passkey format for the user'}), 400
    
    return jsonify({'error': 'Username not allowed to register'}), 400

@app.route('/<username>/verify', methods=['POST'])
def verify_and_register(username):
    # Check if the username exists in the cache
    if username not in selected_words_cache:
        return jsonify({'error': 'No words selected for this user. Register first.'}), 400

    # Get the user-provided sum from the request
    user_sum = request.json.get('sum')
    if not user_sum:
        return jsonify({'error': 'Sum is required'}), 400

    # Retrieve the selected indices from the cache
    selected_indices = selected_words_cache[username]
    passkey_array = accounts.get(username)

    # Validate the passkey array
    if not passkey_array or len(passkey_array) != 16:
        return jsonify({'error': 'Invalid passkey format for this user'}), 400

    # Get the words at the selected indices
    selected_words = [passkey_array[index] for index in selected_indices]

    # Compute the "sum" of the words by concatenation
    calculated_sum = ''.join(selected_words)

    # Verify the provided sum against the calculated sum
    if str(user_sum) == str(calculated_sum):
        # If the sum is correct, register the node
        ip_address = request.json.get('ip')
        if not ip_address:
            return jsonify({'error': 'IP address is required to complete registration'}), 400

        global next_node_id

        # Check if the node is already registered
        for node_id, existing_ip in nodes.items():
            if existing_ip == ip_address:
                return jsonify({'nID': node_id, 'nodes': nodes , 'port': port}), 201

        # Register the new node
        node_id = next_node_id
        nodes[node_id] = ip_address
        next_node_id += 1

        return jsonify({'nID': node_id, 'nodes': nodes , 'port': port}), 201
    else:
        return jsonify({'error': 'Invalid sum provided'}), 400


@app.route('/nodes', methods=['GET'])
def list_nodes():
    return jsonify(nodes), 200

def get_container_ip():
    try:
        result = subprocess.run(['hostname', '-I'], stdout=subprocess.PIPE, text=True, check=True)
        ip_address = result.stdout.strip().split()[0]  # Get the first IP address
        return ip_address
    except (IndexError, subprocess.CalledProcessError) as e:
        print(f"Error getting container IP: {e}")
        return "0.0.0.0"  # Use a fallback that binds to all interfaces

def log_to_file(data):
    """Logs received JSON data to cred.log file."""
    try:
        with open("cred.log", "a") as log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"{timestamp} - {json.dumps(data)}\n")
    except IOError as e:
        print(f"Error writing to log file: {e}")

def socket_server():
    host = get_container_ip() or "0.0.0.0"  # Default to binding to all interfaces
    port = 23843  # Socket server port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        try:
            server_socket.bind((host, port))
            server_socket.listen()
            print(f"Socket server running on {host}:{port}")
        except socket.gaierror as e:
            print(f"Failed to bind socket: {e}")
            return

        while True:
            conn, addr = server_socket.accept()
            with conn:
                print(f"Connection from {addr}")
                data = conn.recv(1024)
                if data:
                    try:
                        passkey_data = json.loads(data.decode('utf-8'))
                        print(f"Received passkey data: {passkey_data}")
                        
                        # Validate JSON structure
                        username = passkey_data.get('username')
                        passkey = passkey_data.get('passkey')
                        timestamp = passkey_data.get('expires_at')
                        if username and passkey:
                            # Split the passkey into an array of 16 words
                            passkey_array = passkey.split()
                            if len(passkey_array) == 16:
                                accounts[username] = passkey_array  # Save to accounts dictionary as array
                                expire[username] = timestamp       # Save expiration time
                                log_to_file(passkey_data)          # Log original data
                                conn.sendall(b"Passkey received and stored")
                            else:
                                conn.sendall(b"Invalid passkey format. Must contain 16 words.")
                        else:
                            conn.sendall(b"Invalid data format. Expected username and passkey")                    
                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON: {e}")
                        conn.sendall(b"Invalid JSON")

if __name__ == '__main__':
    threading.Thread(target=socket_server, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)

