from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import threading
import socket
import json
import subprocess
from datetime import datetime
import random

app = FastAPI()
port = random_port = random.randint(1024, 65535)
expire = {}
nodes = {}
next_node_id = 1
accounts = {}
selected_words_cache = {}

class LogEntry(BaseModel):
    print: str
    timestamp: str

class RegisterRequest(BaseModel):
    ip: str

class VerifyRequest(BaseModel):
    ip: str
    sum: str

def sum_words(words):
    """Sum the selected words."""

@app.post("/log")
async def log_entry(entry: LogEntry):
    try:
        # Append the log entry to the log file
        with open("server.log", "a") as log_file:
            log_file.write(f"{entry.timestamp} - {entry.print}\n")
        return {"message": "Log entry recorded successfully."}
    except IOError as e:
        print(f"Error writing to log file: {e}")
        raise HTTPException(status_code=500, detail="Failed to write log entry.")

@app.post("/{username}")
async def register_node(username: str, request: RegisterRequest):
    global next_node_id

    ip_address = request.ip

    if username in accounts.keys():
        passkey_array = accounts[username]
        if len(passkey_array) == 16:
            selected_indices = random.sample(range(16), 3)
            selected_words_cache[username] = selected_indices
            return JSONResponse(content={"selected_indices": selected_indices}, status_code=201)
        else:
            raise HTTPException(status_code=400, detail="Invalid passkey format for the user")

    raise HTTPException(status_code=400, detail="Username not allowed to register")

@app.post("/{username}/verify")
async def verify_and_register(username: str, request: VerifyRequest):
    if username not in selected_words_cache:
        raise HTTPException(status_code=400, detail="No words selected for this user. Register first.")

    user_sum = request.sum
    selected_indices = selected_words_cache[username]
    passkey_array = accounts.get(username)

    if not passkey_array or len(passkey_array) != 16:
        raise HTTPException(status_code=400, detail="Invalid passkey format for this user")

    selected_words = [passkey_array[index] for index in selected_indices]
    calculated_sum = ''.join(selected_words)

    if str(user_sum) == str(calculated_sum):
        ip_address = request.ip

        global next_node_id

        for node_id, existing_ip in nodes.items():
            if existing_ip == ip_address:
               return JSONResponse(content={"nID": node_id, "nodes": nodes, "port": port}, status_code=201)

        node_id = next_node_id
        nodes[node_id] = ip_address
        next_node_id += 1

        return JSONResponse(content={"nID": node_id, "nodes": nodes, "port": port}, status_code=201)
    else:
        raise HTTPException(status_code=400, detail="Invalid sum provided")

@app.get("/nodes")
async def list_nodes():
    return nodes

def get_container_ip():
    try:
        result = subprocess.run(['hostname', '-I'], stdout=subprocess.PIPE, text=True, check=True)
        ip_address = result.stdout.strip().split()[0]
        return ip_address
    except (IndexError, subprocess.CalledProcessError) as e:
        print(f"Error getting container IP: {e}")
        return "0.0.0.0"

def log_to_file(data):
    try:
        with open("cred.log", "a") as log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"{timestamp} - {json.dumps(data)}\n")
    except IOError as e:
        print(f"Error writing to log file: {e}")

def socket_server():
    host = get_container_ip() or "0.0.0.0"
    port = 23843

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

                        username = passkey_data.get('username')
                        passkey = passkey_data.get('passkey')
                        timestamp = passkey_data.get('expires_at')
                        if username and passkey:
                            passkey_array = passkey.split()
                            if len(passkey_array) == 16:
                                accounts[username] = passkey_array
                                expire[username] = timestamp
                                log_to_file(passkey_data)
                                conn.sendall(b"Passkey received and stored")
                            else:
                                conn.sendall(b"Invalid passkey format. Must contain 16 words.")
                        else:
                            conn.sendall(b"Invalid data format. Expected username and passkey")
                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON: {e}")
                        conn.sendall(b"Invalid JSON")

if __name__ == "__main__":
    threading.Thread(target=socket_server, daemon=True).start()
    import uvicorn
    uvicorn.run(app, host="10.0.2.15", port=5000)
