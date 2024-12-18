import socket
import threading
import random
import json

class Acceptor:
    def __init__(self, client_address):
        self.client_address = client_address
        self.highest_proposal_number = 0
        self.accepted_value = None

    def prepare(self, proposal_number):
        """Phase 1: Prepare"""
        print(f"[PREPARE] {self.client_address}: Received proposal number {proposal_number}. Current highest proposal: {self.highest_proposal_number}")
        if proposal_number > self.highest_proposal_number:
            self.highest_proposal_number = proposal_number
            return True  # Promise to accept
        return False

    def accept(self, proposal_number, proposal_value):
        """Phase 2: Accept"""
        print(f"[ACCEPT] {self.client_address}: Received proposal number {proposal_number} with value '{proposal_value}'.")
        if proposal_number >= self.highest_proposal_number:
            self.highest_proposal_number = proposal_number
            self.accepted_value = proposal_value
            print(f"[ACCEPTED] {self.client_address}: Value '{proposal_value}' accepted.")
            return proposal_value
        return None


class PaxosServer:
    def __init__(self, port=5555):
        self.host = '10.0.2.15'  # Get the local machine's IP
        self.port = port
        self.acceptors = {}  # Connected clients dynamically registered
        self.lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"[SERVER] Paxos Server running on {self.host}:{self.port}")

    def broadcast_status(self):
        """Show the current state of all acceptors."""
        status = {str(addr): {"value": acc.accepted_value} for addr, acc in self.acceptors.items()}
        return json.dumps(status, indent=2)

    def list_clients(self):
        """List all connected clients' IPs."""
        return json.dumps([str(addr) for addr in self.acceptors.keys()], indent=2)

    def handle_client(self, client_socket, client_address):
        print(f"[CONNECT] Client {client_address} connected.")
        acceptor = Acceptor(client_address)

        # Register the client as an Acceptor
        with self.lock:
            self.acceptors[client_address] = acceptor

        try:
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break

                request = data.decode('utf-8')
                print(f"[REQUEST] From {client_address}: {request}")

                if request.lower() == "status":
                    status = self.broadcast_status()
                    client_socket.send(f"Current Acceptor Status:\n{status}".encode('utf-8'))
                elif request.lower() == "clients":
                    clients = self.list_clients()
                    client_socket.send(f"Connected clients:\n{clients}".encode('utf-8'))
                elif request.lower() == "exit":
                    print(f"[DISCONNECT] Client {client_address} requested exit.")
                    break  # Exit the loop if the client sends an exit command
                else:
                    # Start Paxos Proposal
                    proposal_number = random.randint(1, 1000)
                    print(f"[PROPOSAL] Proposal number {proposal_number} with value '{request}'")

                    # Phase 1: Prepare
                    prepare_responses = []
                    for addr, acc in self.acceptors.items():
                        promise = acc.prepare(proposal_number)
                        prepare_responses.append((addr, promise))

                    successful_promises = [addr for addr, promise in prepare_responses if promise]

                    if len(successful_promises) >= len(self.acceptors) // 2 + 1:
                        # Phase 2: Accept
                        accepted = []
                        for addr, acc in self.acceptors.items():
                            result = acc.accept(proposal_number, request)
                            if result:
                                accepted.append(addr)

                        if len(accepted) >= len(self.acceptors) // 2 + 1:
                            print(f"[ACCEPTED] Proposal '{request}' has been accepted.")
                            client_socket.send(f"Proposal '{request}' accepted by majority.\n".encode('utf-8'))
                        else:
                            print(f"[REJECTED] Proposal '{request}' failed in accept phase.")
                            client_socket.send(f"Proposal '{request}' failed to gain majority acceptance.\n".encode('utf-8'))
                    else:
                        print(f"[FAILED] Not enough promises for proposal '{request}'.")
                        client_socket.send(f"Proposal '{request}' failed in prepare phase.\n".encode('utf-8'))

        except Exception as e:
            print(f"[ERROR] {client_address}: {e}")
        finally:
            # Remove client on disconnect
            with self.lock:
                if client_address in self.acceptors:
                    del self.acceptors[client_address]
            print(f"[DISCONNECT] Client {client_address} disconnected.")
            client_socket.close()

    def start(self):
        print("[SERVER] Waiting for clients...")
        while True:
            client_socket, client_address = self.server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client_socket, client_address)).start()


if __name__ == "__main__":
    server = PaxosServer(port=5555)
    server.start()
