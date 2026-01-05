// Load current items immediately when page opens
window.onload = function() {
    loadItems();
};

// --- CORE FUNCTIONS ---

// 1. Load the main inventory list
async function loadItems() {
    let response = await fetch('/api/data');
    let data = await response.json();
    
    let list = document.getElementById('itemList');
    list.innerHTML = ""; 

    data.items.forEach(item => {
        let li = document.createElement('li');
        
        // We added a container for the buttons to keep them tidy
        li.innerHTML = `
            <span>${item}</span>
            <div class="actions">
                <button class="edit" onclick="editItem('${item}')">Edit</button>
                <button class="delete" onclick="deleteItem('${item}')">Delete</button>
            </div>
        `;
        list.appendChild(li);
    });
}

// 2. Toggle the History List on/off
async function toggleHistory() {
    let list = document.getElementById('historyList');
    let btn = document.getElementById('historyBtn');

    // If list has content, hide it
    if (list.innerHTML.trim() !== "") {
        list.innerHTML = "";
        btn.innerText = "View Change History";
    } else {
        // If empty, fetch data and show it
        await fetchAndShowHistory();
        btn.innerText = "Hide Change History";
    }
}

// Helper: Fetch history data and draw it
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
        
        // Color coding for different actions
        let color = 'black';
        if (log.action === 'ADDED') color = 'green';
        if (log.action === 'DELETED') color = 'red';
        if (log.action === 'UPDATED') color = 'orange'; // New color for updates
        
        li.innerHTML = `
            <span style="color:${color}; font-weight:bold;">${log.action}</span>: 
            ${log.item} 
            <span style="font-size:0.8em; color:gray;">(${log.timestamp})</span>
        `;
        list.appendChild(li);
    });
}

// --- ACTION FUNCTIONS ---

// 3. Add Item
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

// 4. Edit Item (NEW)
async function editItem(oldName) {
    // Popup asking for new name
    let newName = prompt(`Change name of "${oldName}" to:`, oldName);

    // If cancelled or empty, do nothing
    if (!newName || newName === oldName) return;

    await fetch('/api/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_name: oldName, new_name: newName })
    });

    refreshAll();
}

// 5. Delete Item
async function deleteItem(item) {
    //if(!confirm(`Are you sure you want to delete "${item}"?`)) return;

    await fetch('/api/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item: item })
    });
    refreshAll();
}

// Helper: Refreshes the main list AND history (if it's open)
function refreshAll() {
    loadItems(); 
    
    // Check if history is currently open
    let historyList = document.getElementById('historyList');
    if (historyList.innerHTML.trim() !== "") {
        fetchAndShowHistory();
    }
}