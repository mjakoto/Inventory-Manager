from flask import Flask, jsonify, request

app = Flask(__name__)

DATA_STORE = {"items": []}

@app.route('/data', methods=['GET'])
def get_data():
    return jsonify(DATA_STORE)

@app.route('/add', methods=['POST'])
def add_data():
    new_item = request.json.get('item')
    if new_item:
        DATA_STORE["items"].append(new_item)
    return jsonify({"status": "success"})

@app.route('/delete', methods=['POST'])
def delete_data():
    item_to_delete = request.json.get('item')
    if item_to_delete in DATA_STORE["items"]:
        DATA_STORE["items"].remove(item_to_delete)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)