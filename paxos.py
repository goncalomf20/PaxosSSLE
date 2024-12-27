from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory storage for registered nodes
nodes = {}
next_node_id = 1

@app.route('/register', methods=['POST'])
def register_node():
    global next_node_id
    
    # Extract IP address from the request
    ip_address = request.json.get('ip')
    if not ip_address:
        return jsonify({'error': 'IP address is required'}), 400

    # Assign a node ID and store the node
    node_id = next_node_id
    nodes[node_id] = ip_address
    next_node_id += 1

    return jsonify({'nID': node_id, 'ip': ip_address, 'nodes': nodes}), 201

@app.route('/nodes', methods=['GET'])
def list_nodes():
    return jsonify(nodes), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

