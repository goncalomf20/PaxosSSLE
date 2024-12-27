import requests
import threading
import time

def connect_to_api(api_url, ip_address):
    try:
        response = requests.post(f"{api_url}/register", json={"ip": ip_address})
        if response.status_code == 201:
            data = response.json()
            print(f"Connected to API. Node ID: {data['nID']}, IP: {data['ip']}")
            print("Registered Nodes:")
            for node_id, ip in data['nodes'].items():
                print(f"  Node {node_id}: {ip}")
            return data['nID']
        else:
            print(f"Failed to register: {response.json().get('error', 'Unknown error')}")
    except requests.RequestException as e:
        print(f"Error connecting to API: {e}")
    return None

def menu(node_id, api_url):
    while True:
        print("\n--- Node Menu ---")
        print("1. See Registered Nodes")
        print("2. Wait for Proposed Value Notification")
        print("3. Exit")
        
        choice = input("Enter your choice: ")
        
        if choice == "1":
            try:
                response = requests.get(f"{api_url}/nodes")
                if response.status_code == 200:
                    nodes = response.json()
                    print("\nRegistered Nodes:")
                    for node_id, ip in nodes.items():
                        print(f"  Node {node_id}: {ip}")
                else:
                    print("Failed to retrieve nodes.")
            except requests.RequestException as e:
                print(f"Error fetching nodes: {e}")

        elif choice == "2":
            print("Waiting for proposed value notification...")
            listen_for_notifications(node_id, api_url)

        elif choice == "3":
            print("Exiting menu.")
            break

        else:
            print("Invalid choice. Please try again.")

def listen_for_notifications(node_id, api_url):
    # Simulated notification listener
    def notification_listener():
        while True:
            try:
                response = requests.get(f"{api_url}/notifications/{node_id}")
                if response.status_code == 200:
                    notification = response.json()
                    if notification:
                        print(f"\nNotification received: {notification['message']}")
                        break
                time.sleep(5)
            except requests.RequestException as e:
                print(f"Error listening for notifications: {e}")
                break

    listener_thread = threading.Thread(target=notification_listener, daemon=True)
    listener_thread.start()
    listener_thread.join()

if __name__ == "__main__":
    api_url = input("Enter the API URL (e.g., http://localhost:5000): ")
    ip_address = input("Enter your IP address: ")
    
    node_id = connect_to_api(api_url, ip_address)
    if node_id:
        menu(node_id, api_url)
