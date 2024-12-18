import socket
import argparse

class PaxosClient:
    def __init__(self, server_ip, port=5555):
        self.server_ip = server_ip
        self.port = port
        self.client_socket = None

    def connect_to_server(self):
        """Establish a connection to the server."""
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.server_ip, self.port))
            print(f"[INFO] Connected to server {self.server_ip}:{self.port}")
        except Exception as e:
            print(f"[ERROR] Unable to connect to server: {e}")

    def close_connection(self):
        """Gracefully close the connection."""
        if self.client_socket:
            self.client_socket.close()
            print("[INFO] Disconnected from server.")

    def send_request(self, request):
        """Send a request to the server and handle the response."""
        try:
            if not self.client_socket:
                print("[ERROR] Not connected to the server. Please connect first.")
                return

            # Send request
            self.client_socket.send(request.encode('utf-8'))

            # Receive response
            response = self.client_socket.recv(4096).decode('utf-8')
            print(f"[RESPONSE] {response}")

        except Exception as e:
            print(f"[ERROR] {e}")
            self.close_connection()  # Disconnect on error

    def reconnect(self):
        """Attempt to reconnect to the server if disconnected."""
        if self.client_socket:
            print("[INFO] Reconnecting...")
            self.close_connection()
        self.connect_to_server()

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Paxos Client to interact with Paxos Server.")
    parser.add_argument("server_ip", help="The IP address of the Paxos server.")
    parser.add_argument("port", type=int, default=5555, nargs="?", help="The port of the Paxos server (default is 5555).")

    # Parse the command line arguments
    args = parser.parse_args()

    client = PaxosClient(args.server_ip, args.port)

    # Connect to the server
    client.connect_to_server()

    while True:
        print("\nOptions:")
        print("1. Propose a value")
        print("2. Check status of acceptors")
        print("3. List all connected clients")
        print("4. Exit")

        choice = input("Enter your choice: ")

        if choice == "1":
            value = input("Enter value to propose: ")
            client.send_request(value)
        elif choice == "2":
            client.send_request("status")
        elif choice == "3":
            client.send_request("clients")
        elif choice == "4":
            print("Exiting client.")
            client.close_connection()  # Close the connection on exit
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
