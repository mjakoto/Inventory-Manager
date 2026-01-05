window.onload = function() {
    loadItems();
};

async function loadItems() {
    let response = await fetch('/api/data');
    let data = await response.json();
    
    let list = document.getElementById('itemList');
    list.innerHTML = ""; 

    data.items.forEach(item => {
        let li = document.createElement('li');
        
        // Notice we now pass item.id AND item.name to the functions
        // item is now an object: {id: 1, name: "Apple"}
        li.innerHTML = `
            <span>${item.name}</span>
            <div class="actions">
                <button class="edit" onclick="editItem(${item.id}, '${item.name}')">Edit</button>
                <button class="delete" onclick="deleteItem(${item.id}, '${item.name}')">Delete</button>
            </div>
        `;
        list.appendChild(li);
    });
}

async function toggleHistory() {
    let list = document.getElementById('historyList');
    let btn = document.getElementById('historyBtn');

    if (list.innerHTML.trim() !== "") {
        list.innerHTML = "";
        btn.innerText = "View Change History";
    } else {
        await fetchAndShowHistory();
        btn.innerText = "Hide Change History";
    }
}

async function fetchAndShowHistory() {
    let list = document.getElementById('historyList');
    let response = await fetch('/api/history');
    let data = await response.json();

    list.innerHTML = ""; 

    if (data.history.length === 0) {
        list.innerHTML = "<li>No history yet.</li>";
        return;
    }

    data.history.forEach(log => {
        let li = document.createElement('li');
        
        let color = 'black';
        if (log.action === 'ADDED') color = 'green';
        if (log.action === 'DELETED') color = 'red';
        if (log.action === 'UPDATED') color = 'orange'; 
        
        li.innerHTML = `
            <span style="color:${color}; font-weight:bold;">${log.action}</span>: 
            ${log.item} 
            <span style="font-size:0.8em; color:gray;">(${log.timestamp})</span>
        `;
        list.appendChild(li);
    });
}

async function clearHistory() {
    await fetch('/api/clear_history', { method: 'POST' });
    
    // Clear the list from the screen immediately
    let list = document.getElementById('historyList');
    let btn = document.getElementById('historyBtn');
    
    list.innerHTML = ""; // Make it vanish
    btn.innerText = "View Change History"; // Reset the main button text
}

async function addItem() {
    let input = document.getElementById('newItemInput');
    let value = input.value;
    if (!value) return;

    await fetch('/api/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item: value })
    });

    input.value = "";
    refreshAll();
}

async function editItem(id, oldName) {
    let newName = prompt(`Change name of "${oldName}" to:`, oldName);

    if (!newName || newName === oldName) return;

    await fetch('/api/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // We now send the ID to identify the row, and names for logging
        body: JSON.stringify({ id: id, old_name: oldName, new_name: newName })
    });

    refreshAll();
}

async function deleteItem(id, name) {
    // Direct delete using ID
    await fetch('/api/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: id, name: name })
    });
    refreshAll();
}

function refreshAll() {
    loadItems(); 
    let historyList = document.getElementById('historyList');
    if (historyList.innerHTML.trim() !== "") {
        fetchAndShowHistory();
    }
}