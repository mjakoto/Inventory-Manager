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

@app.route('/data', methods=['GET'])
def get_data():
    conn = get_db_connection()
    items = conn.execute('SELECT name FROM items').fetchall()
    conn.close()
    return jsonify({"items": [row['name'] for row in items]})

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

# --- NEW UPDATE ROUTE ---
@app.route('/update', methods=['POST'])
def update_data():
    old_name = request.json.get('old_name')
    new_name = request.json.get('new_name')
    
    if old_name and new_name:
        conn = get_db_connection()
        
        # 1. Update the item in the database
        conn.execute('UPDATE items SET name = ? WHERE name = ?', (new_name, old_name))
        
        # 2. Log the change in history (showing "Old -> New")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"{old_name} -> {new_name}"
        conn.execute('INSERT INTO history (action, item, timestamp) VALUES (?, ?, ?)', 
                     ('UPDATED', log_message, now))
        
        conn.commit()
        conn.close()
    return jsonify({"status": "success"})
# ------------------------

@app.route('/delete', methods=['POST'])
def delete_data():
    item_to_delete = request.json.get('item')
    if item_to_delete:
        conn = get_db_connection()
        conn.execute('DELETE FROM items WHERE name = ?', (item_to_delete,))
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('INSERT INTO history (action, item, timestamp) VALUES (?, ?, ?)', 
                     ('DELETED', item_to_delete, now))
        
        conn.commit()
        conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)