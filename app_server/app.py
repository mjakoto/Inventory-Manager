import sqlite3
import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)
DB_FILE = 'inventory.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS history 
        (id INTEGER PRIMARY KEY, action TEXT, item TEXT, timestamp TEXT)
    ''')
    conn.commit()
    conn.close()

init_db()

# --- ROUTES ---

@app.route('/data', methods=['GET'])
def get_data():
    conn = get_db_connection()
    items = conn.execute('SELECT id, name FROM items').fetchall()
    conn.close()
    # Now we send both ID and Name
    return jsonify({"items": [{"id": row['id'], "name": row['name']} for row in items]})

@app.route('/history', methods=['GET'])
def get_history():
    conn = get_db_connection()
    logs = conn.execute('SELECT * FROM history ORDER BY id DESC').fetchall()
    conn.close()
    
    history_list = []
    for row in logs:
        history_list.append({
            "action": row["action"],
            "item": row["item"],
            "timestamp": row["timestamp"]
        })
    return jsonify({"history": history_list})

@app.route('/add', methods=['POST'])
def add_data():
    new_item = request.json.get('item')
    if new_item:
        conn = get_db_connection()
        conn.execute('INSERT INTO items (name) VALUES (?)', (new_item,))
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('INSERT INTO history (action, item, timestamp) VALUES (?, ?, ?)', 
                     ('ADDED', new_item, now))
        
        conn.commit()
        conn.close()
    return jsonify({"status": "success"})

@app.route('/update', methods=['POST'])
def update_data():
    # We now look for the unique ID
    item_id = request.json.get('id')
    new_name = request.json.get('new_name')
    old_name = request.json.get('old_name') # Just for the history log
    
    if item_id and new_name:
        conn = get_db_connection()
        
        # TARGETED UPDATE: Only update the specific row with this ID
        conn.execute('UPDATE items SET name = ? WHERE id = ?', (new_name, item_id))
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"{old_name} -> {new_name}"
        conn.execute('INSERT INTO history (action, item, timestamp) VALUES (?, ?, ?)', 
                     ('UPDATED', log_message, now))
        
        conn.commit()
        conn.close()
    return jsonify({"status": "success"})

@app.route('/delete', methods=['POST'])
def delete_data():
    # We now look for the unique ID
    item_id = request.json.get('id')
    item_name = request.json.get('name') # Just for the history log

    if item_id:
        conn = get_db_connection()
        
        # TARGETED DELETE: Only delete the specific row with this ID
        conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('INSERT INTO history (action, item, timestamp) VALUES (?, ?, ?)', 
                     ('DELETED', item_name, now))
        
        conn.commit()
        conn.close()
    return jsonify({"status": "success"})

@app.route('/clear_history', methods=['POST'])
def clear_history():
    conn = get_db_connection()
    conn.execute('DELETE FROM history')
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)