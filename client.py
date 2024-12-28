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
response_tracker = {"accepted": 0, "rejected": 0, "total": 0}  # Track responses

# For proposer waiting for responses
proposer_wait_event = threading.Event()

# Log accepted responses
accepted_responses = []

# Server control flag
server_running = True


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
                message = json.dumps({"type": "new_registration", "ip": own_ip, "nID": own_id})
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
                                new_node_id = message["nID"]
                                new_ip = message["ip"]
                                print(f"Node {new_node_id} registered with IP: {new_ip}")
                                # Add the new node to local nodes list
                                if new_node_id not in last_call["nodes"]:
                                    last_call["nodes"][new_node_id] = new_ip
                                    print(f"Added Node {new_node_id} to local nodes list.")
                            elif message.get("type") == "accepted_value":
                                print(f"Accepted value for Round {message['round_id']}: {message['purpose']}")
                                last_decision.update({"round_id": message['round_id'], "purpose": message['purpose'], "accepted": True})
                            else:
                                print(f"\nNotification: Round {message['round_id']} - Purpose: {message['purpose']}")
                                response = {"round_id": message['round_id'], "accepted": True}  # Always accept for simplicity
                                conn.sendall(json.dumps(response).encode('utf-8'))
                except socket.error as e:
                    if server_running:
                        print(f"Socket error: {e}")

    server_thread = threading.Thread(target=server, daemon=True)
    server_thread.start()

def stop_socket_server():
    global server_running
    server_running = False
    print("Socket server has been stopped.")

def propose_purpose_to_nodes(node_id, nodes, purpose, own_ip):
    global last_decision, proposer_wait_event, accepted_responses
    round_id = last_decision["round_id"] + 1  # Increment the last round ID
    last_decision["round_id"] = round_id  # Update the last round ID
    response_tracker["accepted"] = 0
    response_tracker["rejected"] = 0
    proposer_wait_event.clear()

    accepted_responses = []  # Reset accepted responses log

    # Automatically accept the purpose as the proposer
    response_tracker["accepted"] += 1
    accepted_responses.append(own_ip)

    for target_node_id, ip in nodes.items():
        if ip == own_ip:  # Skip sending to nodes with the same IP
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, PORT))
                message = json.dumps({"round_id": round_id, "purpose": purpose})
                s.sendall(message.encode('utf-8'))

                # Wait for acknowledgment
                data = s.recv(BUFFER_SIZE)
                response = json.loads(data.decode('utf-8'))
                if response.get("accepted"):
                    response_tracker["accepted"] += 1
                    accepted_responses.append(ip)
                else:
                    response_tracker["rejected"] += 1
        except Exception as e:
            print(f"Failed to send purpose to Node {target_node_id} at {ip}: {e}")

    # Determine final decision based on majority
    if response_tracker["accepted"] > (len(nodes) // 2):
        last_decision["accepted"] = True
        print("\nPurpose accepted by majority.")
        notify_acceptors(nodes, round_id, purpose, own_ip)  # Notify acceptors
    else:
        last_decision["accepted"] = False
        print("\nPurpose rejected by majority.")

    # Update last_call with the decision
    last_decision.update({"round_id": round_id, "purpose": purpose, "accepted": True})
    print(f"Proposal result: {last_decision['accepted']}")
    print(f"Nodes that accepted: {accepted_responses}")

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
        print("5. View Last API Call Details")
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
            stop_socket_server()
            break

        elif choice == "5":
            if last_call:
                print(f"\nLast API Call Details:\nNodes: {last_call['nodes']}\nTimestamp: {last_call['timestamp']}")
            else:
                print("\nNo last API call details available.")

        elif choice == "6":
            if last_decision["round_id"] is not None:
                print(f"\nLast Decision:\nRound: {last_decision['round_id']}\nPurpose: {last_decision['purpose']}\nAccepted: {last_decision['accepted']}")
            else:
                print("\nNo decisions have been made yet.")

        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    api_url = input("Enter the API URL (e.g., http://localhost:5000): ")
    ip_address = get_container_ip()
    print(f"Detected container IP address: {ip_address}")

    node_id, nodes = connect_to_api(api_url, ip_address)
    if node_id and nodes:
        menu(node_id, api_url, nodes)
