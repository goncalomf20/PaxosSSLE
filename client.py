import socket

class PaxosClient:
    def __init__(self, server_ip, port=5555):
        self.server_ip = server_ip
        self.port = port

    def send_request(self, request):
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((self.server_ip, self.port))

            # Send request
            client_socket.send(request.encode('utf-8'))

            # Receive response
            response = client_socket.recv(4096).decode('utf-8')
            print(f"[RESPONSE] {response}")

            client_socket.close()
        except Exception as e:
            print(f"[ERROR] {e}")

def main():
    print("Welcome to the Paxos Client!")
    server_ip = input("Enter the Paxos server IP (or press Enter for local): ").strip()
    if not server_ip:
        server_ip = socket.gethostbyname(socket.gethostname())  # Auto-detect local IP

    client = PaxosClient(server_ip, port=5555)

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
            break
        else:
            print("Invalid choice. Try again.")

if __name__ == "__main__":
    main()
