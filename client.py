from flask import Flask, request, jsonify
import os
import requests
import threading
import time
import json
from datetime import datetime
import subprocess
import socket

# Store the last API call details
last_call = None

# Dictionary to store last round and purpose status
last_decision = {"round_id": 0, "purpose": None, "accepted": None}

# Socket server and client settings
PORT = 65432
BUFFER_SIZE = 1024
response_tracker = {"accepted": 1, "rejected": 0, "total": 1}  # Track responses

# Reputation scores for each node (default is 100)
reputation_scores = {}
DEFAULT_REPUTATION = 100
REPUTATION_FILE = "reputation_scores.txt"

# For proposer waiting for responses
proposer_wait_event = threading.Event()

# Log accepted responses
accepted_responses = []

# Server control flag
server_running = True

# Flask app for API
app = Flask(__name__)

# Registered nodes
nodes = {}

# Store the last decisions from nodes
node_decisions = {}

@app.route('/last_decision', methods=['POST'])
def receive_last_decision():
    """Handles incoming last decision from nodes."""
    global node_decisions, last_decision

    data = request.get_json()
    ip = data.get('ip')
    decision = data.get('last_decision')

    if not ip or not decision:
        return jsonify({"error": "IP and last decision are required."}), 400

    node_decisions[ip] = decision

    # Check if all decisions are received and update last_decision if applicable
    if len(node_decisions) == len(nodes) - 1:
        decisions = list(node_decisions.values())
        if all(d["purpose"] == decisions[0]["purpose"] for d in decisions):
            if decisions[0]["round_id"] > last_decision["round_id"]:
                log_decision(decisions[0]['round_id'], decisions[0]['purpose'], decisions[0]['accepted'])
                last_decision.update(decisions[0])
                print(f"Updated last_decision: {last_decision}")

    print(f"Received last decision from Node {ip}: {decision}")

    return jsonify({"message": "Decision received successfully."}), 200

def load_reputation_scores():
    """Load reputation scores from a file."""
    global reputation_scores
    if os.path.exists(REPUTATION_FILE):
        try:
            with open(REPUTATION_FILE, "r") as file:
                reputation_scores = json.load(file)
                print("Reputation scores loaded successfully.")
        except Exception as e:
            print(f"Error loading reputation scores: {e}")
    else:
        print("No reputation file found. Starting with default reputation scores.")

def save_reputation_scores():
    """Save reputation scores to a file."""
    try:
        with open(REPUTATION_FILE, "w") as file:
            json.dump(reputation_scores, file, indent=4)
            print("Reputation scores saved successfully.")
    except Exception as e:
        print(f"Error saving reputation scores: {e}")

def adjust_reputation(node_ip, adjustment):
    """
    Adjust the reputation score of a node.
    :param node_ip: IP address of the node.
    :param adjustment: Amount to adjust the reputation (positive or negative).
    """
    global reputation_scores
    if node_ip not in reputation_scores:
        reputation_scores[node_ip] = DEFAULT_REPUTATION
    reputation_scores[node_ip] = max(0, reputation_scores[node_ip] + adjustment)
    print(f"Reputation for Node {node_ip} adjusted to {reputation_scores[node_ip]}")


def notify_node_to_send_decision(node_ip, new_node_ip):
    """Notify a node to send its last decision to a new node."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((node_ip, PORT))
            message = {
                "type": "send_last_decision",
                "target_ip": new_node_ip
            }
            s.sendall(json.dumps(message).encode('utf-8'))
            print(f"Notified Node at {node_ip} to send last decision to {new_node_ip}.")
    except Exception as e:
        print(f"Failed to notify Node at {node_ip}: {e}")

# Rest of the existing code
def get_container_ip():
    try:
        # Use `hostname -I` to fetch the container's IP address
        result = subprocess.run(['hostname', '-I'], stdout=subprocess.PIPE, text=True)
        ip_address = result.stdout.strip().split()[0]  # Get the first IP address
        return ip_address
    except Exception as e:
        print(f"Error getting container IP: {e}")
        return "Unknown"

def save_last_call(ip_address, nodes):
    global last_call
    last_call = {
        "nodes": nodes,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def notify_existing_nodes(own_ip, own_id, nodes):
    for target_node_id, ip in nodes.items():
        if ip == own_ip:  # Skip sending to self
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, PORT))
                message = json.dumps({"type": "new_registration", "ip": own_ip, "nID": own_id, "last_decision":last_decision})
                s.sendall(message.encode('utf-8'))
                print(f"Notified Node {target_node_id} at {ip} about new registration.")
        except Exception as e:
            print(f"Failed to notify Node {target_node_id} at {ip}: {e}")

def notify_acceptors(nodes, round_id, purpose, own_ip):
    for target_node_id, ip in nodes.items():
        if ip == own_ip:  # Skip sending to self
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, PORT))
                message = json.dumps({"type": "accepted_value", "round_id": round_id, "purpose": purpose})
                s.sendall(message.encode('utf-8'))
                print(f"Sent accepted value to Node {target_node_id} at {ip}.")
        except Exception as e:
            print(f"Failed to notify Node {target_node_id} at {ip}: {e}")

def notify_promise(nodes, round_id, own_ip):
    """Notify all nodes about the promise made for a specific round."""
    connections = {}  # Store connections for reuse
    try:
        for target_node_id, ip in nodes.items():
            if ip == own_ip:  # Skip sending to self
                continue
            if ip in connections:  # Avoid duplicate connections
                print(f"Skipping duplicate promise to {ip}.")
                continue
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((ip, PORT))
                message = json.dumps({"type": "promise", "round_id": round_id, "ip": own_ip})
                s.sendall(message.encode('utf-8'))
                print(f"Promise sent for Round {round_id} to {ip}.")
                connections[ip] = s  # Save the connection for reuse
            except Exception as e:
                print(f"Failed to notify Node {target_node_id} at {ip}: {e}")
    except Exception as e:
        print(f"Error during promise notifications: {e}")
    return connections  # Return connections to be reused

def connect_to_api(api_url, ip_address):
    global last_call
    try:
        response = requests.post(f"{api_url}/register", json={"ip": ip_address})
        if response.status_code == 201:
            data = response.json()
            print(f"Connected to API. Node ID: {data['nID']}, IP: {data['ip']}")
            print("Registered Nodes:")
            for node_id, ip in data['nodes'].items():
                print(f"  Node {node_id}: {ip}")
            save_last_call(ip_address, data['nodes'])

            # Notify existing nodes about the new registration
            notify_existing_nodes(ip_address, data['nID'], data['nodes'])

            return data['nID'], data['nodes']
        else:
            print(f"Failed to register: {response.json().get('error', 'Unknown error')}")
    except requests.RequestException as e:
        print(f"Error connecting to API: {e}")
        if last_call:
            print(f"Last known state: Nodes={last_call['nodes']}, Timestamp={last_call['timestamp']}")
    return None, None

def start_socket_server():
    global server_running
    server_running = True  # Ensure the server starts running

    def server():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Enable address reuse
            s.bind((get_container_ip(), PORT))
            s.listen()
            print(f"Socket server listening on port {PORT}")

            while server_running:
                try:
                    conn, addr = s.accept()
                    with conn:
                        print(f"Connected by {addr}")
                        data = conn.recv(BUFFER_SIZE)
                        if data:
                            message = json.loads(data.decode('utf-8'))

                            if message.get("type") == "new_registration":
                                handle_new_registration(message)

                            elif message.get("type") == "accepted_value":
                                handle_accepted_value(message)

                            elif message.get("type") == "promise":
                                handle_promise_request(conn, message)

                            elif message.get("type") == "propose":
                                handle_propose_request(conn, message)

                            elif message.get("type") == "learn":
                                handle_learn_request(message)

                            else:
                                print(f"Unknown message type received: {message}")
                except socket.error as e:
                    if server_running:
                        print(f"Socket error: {e}")

    server_thread = threading.Thread(target=server, daemon=True)
    server_thread.start()

def handle_new_registration(message):
    new_node_id = message["nID"]
    new_ip = message["ip"]
    new_last_decision = message["last_decision"]
    print(f"Node {new_node_id} registered with IP: {new_ip}")

    # Add the new node to local nodes list
    if new_node_id not in last_call["nodes"]:
        last_call["nodes"][new_node_id] = new_ip
        print(f"Added Node {new_node_id} to local nodes list.")

    if new_ip not in reputation_scores:
        reputation_scores[new_ip] = DEFAULT_REPUTATION
        print(f"Initialized reputation for Node {new_ip} to {DEFAULT_REPUTATION}.")

    # Send updated last decision if necessary
    if new_last_decision['round_id'] < last_decision['round_id']:
        payload = {"ip": get_container_ip(), "last_decision": last_decision}
        try:
            requests.post(f"http://{new_ip}:5000/last_decision", json=payload)
            print(f"Sent updated last decision to Node {new_ip}.")
        except Exception as e:
            print(f"Failed to send last decision to Node {new_ip}: {e}")

def handle_accepted_value(message):
    print(f"Accepted value for Round {message['round_id']}: {message['purpose']}")
    last_decision.update({"round_id": message['round_id'], "purpose": message['purpose'], "accepted": True})

handled_promises = set()  # To track handled promises

def handle_promise_request(conn, message):
    """Handle incoming promise requests and avoid processing duplicates."""
    global handled_promises
    round_id = message['round_id']
    sender_ip = message['ip']
    request_id = f"{sender_ip}-{round_id}"  # Unique ID for the promise

    if request_id in handled_promises:
        print(f"Duplicate promise detected: {request_id}. Ignoring.")
        response = {"round_id": round_id, "accepted": False}  # Acknowledge but reject duplicate
        conn.sendall(json.dumps(response).encode('utf-8'))
        return

    handled_promises.add(request_id)  # Mark as handled
    print(f"Processing promise: {request_id}")
    response = {"round_id": round_id, "accepted": True}
    conn.sendall(json.dumps(response).encode('utf-8'))

def handle_propose_request(conn, message):
    """
    Handle a propose request and allow the acceptor to decide.
    """
    global last_decision
    round_id = message['round_id']
    purpose = message['purpose']
    proposer_ip = message['proposer']

    print(f"Propose received for Round {round_id} with purpose: '{purpose}' from {proposer_ip}.")

    # Prompt the user for their decision
    user_decision = input(f"Do you accept the proposal for Round {round_id}, Purpose '{purpose}'? (yes/no): ").strip().lower()

    # Validate input and determine response
    if user_decision == "yes":
        last_decision.update({"round_id": round_id, "purpose": purpose, "accepted": True})
        response = {"round_id": round_id, "accepted": True}
        print(f"Proposal accepted for Round {round_id}, Purpose '{purpose}'.")
    elif user_decision == "no":
        response = {"round_id": round_id, "accepted": False}
        print(f"Proposal rejected for Round {round_id}, Purpose '{purpose}'.")
    else:
        response = {"round_id": round_id, "accepted": False}
        print("Invalid input. Proposal automatically rejected.")

    # Send the response back to the proposer
    conn.sendall(json.dumps(response).encode('utf-8'))

def handle_learn_request(message):
    """Handle a learn request and log the decision."""
    global last_decision
    round_id = message['round_id']
    purpose = message['purpose']
    l = message['l']

    print(f"Learn request received for Round {round_id} with purpose: {purpose}")
    if round_id >= last_decision["round_id"] and l:
        last_decision.update({"round_id": round_id, "purpose": purpose, "accepted": True})
        print(f"Learned value updated to: {last_decision}")

        # Log the decision to decisions.log
        log_decision(round_id, purpose, True)
    elif round_id >= last_decision["round_id"] and l == False:
        log_decision(round_id, purpose, False)
        print(f"Round {round_id} not Learned but Logged.")
    else:
        print(f"Learn request ignored for outdated round {round_id}.")

def stop_socket_server():
    global server_running
    server_running = False
    print("Socket server has been stopped.")

def log_decision(round_id, purpose, accepted):
    """Log the decision to a file."""
    with open("decisions.log", "a") as log_file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file.write(f"{timestamp} - Round: {round_id}, Purpose: {purpose}, Accepted: {accepted}\n")


def propose_purpose_to_nodes(node_id, nodes, purpose, own_ip):
    global last_decision, proposer_wait_event, accepted_responses
    round_id = last_decision["round_id"] + 1  # Increment the last round ID
    last_decision["round_id"] = round_id  # Update the last round ID
    response_tracker = {"accepted": 1, "rejected": 0}
    proposer_wait_event.clear()

    accepted_responses = [own_ip]  # Start with proposer's own acceptance

    print(f"Starting proposal for purpose '{purpose}' in round {round_id}.")

    # Step 1: Notify promise
    connections = notify_promise(nodes, round_id, own_ip)

    # Step 2: Wait for all promise responses
    for ip, conn in connections.items():
        # Filter out nodes with reputation <= 70
        if reputation_scores.get(ip, DEFAULT_REPUTATION) <= 80:
            print(f"Skipping Node at {ip} due to low reputation ({reputation_scores.get(ip, DEFAULT_REPUTATION)}).")
            continue
        try:
            # Wait for acknowledgment of promise
            data = conn.recv(BUFFER_SIZE)
            if not data:
                print(f"Empty response from Node at {ip}.")
                response_tracker["rejected"] += 1
                adjust_reputation(ip, -5)  # Penalize for no response
                continue

            response = json.loads(data.decode('utf-8'))
            if response.get("accepted"):
                print(f"Promise accepted by Node {ip}.")
                response_tracker["accepted"] += 1
                adjust_reputation(ip, 5)  # Penalize for no response
                accepted_responses.append(ip)
            else:
                print(f"Promise rejected by Node {ip}.")
                response_tracker["rejected"] += 1
                adjust_reputation(ip, -10)  # Penalize for no response
        except Exception as e:
            print(f"Error during promise phase for Node at {ip}: {e}")
        finally:
            conn.close()

    # Step 3: Determine if majority accepted the promise
    majority = len(nodes) // 2
    if response_tracker["accepted"] <= majority:
        print(f"Proposal for purpose '{purpose}' cannot proceed as majority did not promise.")
        print(f"Promise Phase Result: Accepted: {response_tracker['accepted']}, Rejected: {response_tracker['rejected']}.")
        return

    print(f"Majority accepted promise. Proceeding with proposal for purpose '{purpose}'.")
    response_tracker = {"accepted": 1, "rejected": 0}  # Reset the tracker
    print(f"Starting proposal for purpose '{purpose}' in round {round_id}.")

    for target_node_id, ip in nodes.items():
        if ip == own_ip:  # Skip sending to self
            continue
       # Filter out nodes with reputation <= 70
        if reputation_scores.get(ip, DEFAULT_REPUTATION) <= 70:
            print(f"Skipping Node at {ip} due to low reputation ({reputation_scores.get(ip, DEFAULT_REPUTATION)}).")
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)  # Timeout for socket operations
                s.connect((ip, PORT))
                message = json.dumps({"type": "propose", "round_id": round_id, "purpose": purpose, "proposer": own_ip})
                s.sendall(message.encode('utf-8'))
                print(f"Sent proposal to Node {target_node_id} at {ip}.")

                # Wait for the response
                data = s.recv(BUFFER_SIZE)
                if not data:
                    print(f"No response from Node {target_node_id} at {ip}.")
                    response_tracker["rejected"] += 1
                    adjust_reputation(ip, -5)  # Penalize for no response
                    continue

                response = json.loads(data.decode('utf-8'))
                if response.get("accepted"):
                    response_tracker["accepted"] += 1
                    adjust_reputation(ip, 5)  # Penalize for no response
                    print(f"Proposal accepted by Node {target_node_id} at {ip}.")
                else:
                    response_tracker["rejected"] += 1
                    print(f"Proposal rejected by Node {target_node_id} at {ip}.")
                    adjust_reputation(ip, -10)  # Penalize for no response
        except Exception as e:
            print(f"Error during proposal phase for Node {target_node_id} at {ip}: {e}")

    # Determine if the proposal was accepted by majority
    majority = len(nodes) // 2 + 1  # Majority threshold
    if response_tracker["accepted"] >= majority:
        print(f"Proposal for purpose '{purpose}' approved by majority.")
        last_decision["round_id"] = round_id
        last_decision["purpose"] = purpose
        last_decision["accepted"] = True
        log_decision(round_id, purpose, True)
        # Broadcast the learned value to all nodes
        broadcast_learn(round_id, purpose, nodes, own_ip, True)
    else:
        print(f"Proposal for purpose '{purpose}' rejected by majority.")
        last_decision["round_id"] = round_id
        last_decision["purpose"] = purpose
        last_decision["accepted"] = False
        log_decision(round_id, purpose, False)
        broadcast_learn(round_id, purpose, nodes, own_ip, False)

    print(f"Final Proposal Result: Accepted: {response_tracker['accepted']}, Rejected: {response_tracker['rejected']}.")

def broadcast_learn(round_id, purpose, nodes, own_ip, ack):
    """
    Broadcasts the learned value to all nodes.
    """
    print(f"Broadcasting learned value for Round {round_id} with purpose '{purpose}'.")
    for target_node_id, ip in nodes.items():
        if ip == own_ip:  # Skip sending to self
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                if ack:
                  message = json.dumps({"type": "learn", "round_id": round_id, "purpose": purpose, "l":True})
                else:
                  message = json.dumps({"type": "learn", "round_id": round_id, "purpose": purpose, "l":False})
                s.connect((ip, PORT))
                s.sendall(message.encode('utf-8'))
                print(f"Sent learn message to Node {target_node_id} at {ip}.")
        except Exception as e:
            print(f"Failed to send learn message to Node {target_node_id} at {ip}: {e}")

def wait_for_notifications():
    global server_running
    print("Waiting for notifications. Press Ctrl+C to stop.")
    try:
        start_socket_server()
        while server_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Stopping the server...")
        stop_socket_server()

def menu(node_id, api_url, nodes):
    global last_decision
    own_ip = get_container_ip()
    while True:
        print("\n--- Node Menu ---")
        print("1. See Registered Nodes")
        print("2. Propose a Value")
        print("3. Wait for Notifications")
        print("4. Exit")
        print("5. View Reputation")
        print("6. View Last Decision")
      
        
        choice = input("Enter your choice: ")
        
        if choice == "1":
            print("\nRegistered Nodes:")
            for node_id, ip in nodes.items():
                print(f"  Node {node_id}: {ip}")

        elif choice == "2":
            purpose = input("Enter the purpose to propose: ")
            propose_purpose_to_nodes(node_id, nodes, purpose, own_ip)

        elif choice == "3":
            wait_for_notifications()
 
        elif choice == "4":
            print("Exiting menu.")
            save_reputation_scores()
            stop_socket_server()
            break

        elif choice == "5":
            print("\nReputation Scores:")
            for ip, score in reputation_scores.items():
                print(f"  Node {ip}: {score}")

        elif choice == "6":
            if last_decision["round_id"] is not None:
                print(f"\nLast Decision:\nRound: {last_decision['round_id']}\nPurpose: {last_decision['purpose']}\nAccepted: {last_decision['accepted']}")
            else:
                print("\nNo decisions have been made yet.")

        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    load_reputation_scores()
    # Start the Flask app in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False), daemon=True)
    flask_thread.start()
    time.sleep(1)
    api_url = input("Enter the API URL (e.g., http://localhost:5000): ")
    ip_address = get_container_ip()
    print(f"Detected container IP address: {ip_address}")

    node_id, nodes = connect_to_api(api_url, ip_address)
    if node_id and nodes:
        menu(node_id, api_url, nodes)
