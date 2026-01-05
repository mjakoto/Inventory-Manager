window.onload = function() {
    loadItems();
};

// 1. Load the main inventory list
async function loadItems() {
    let response = await fetch('/api/data');
    let data = await response.json();
    
    let list = document.getElementById('itemList');
    list.innerHTML = ""; 

    data.items.forEach(item => {
        let li = document.createElement('li');
        li.innerHTML = `
            ${item} 
            <button class="delete" onclick="deleteItem('${item}')">Delete</button>
        `;
        list.appendChild(li);
    });
}

// 2. NEW: Toggle the History List on/off
async function toggleHistory() {
    let list = document.getElementById('historyList');
    let btn = document.getElementById('historyBtn');

    // CHECK: Is the list currently showing anything?
    if (list.innerHTML.trim() !== "") {
        // YES -> So Hide it (Clear the list)
        list.innerHTML = "";
        btn.innerText = "View Change History";
    } else {
        // NO -> So Show it (Fetch data)
        await fetchAndShowHistory();
        btn.innerText = "Hide Change History";
    }
}

// Helper function to actually get the history
async function fetchAndShowHistory() {
    let list = document.getElementById('historyList');
    let response = await fetch('/api/history');
    let data = await response.json();

    list.innerHTML = ""; // Clear to prevent duplicates

    if (data.history.length === 0) {
        list.innerHTML = "<li>No history yet.</li>";
        return;
    }

    data.history.forEach(log => {
        let li = document.createElement('li');
        let color = log.action === 'ADDED' ? 'green' : 'red';
        li.innerHTML = `
            <span style="color:${color}; font-weight:bold;">${log.action}</span>: 
            ${log.item} 
            <span style="font-size:0.8em; color:gray;">(${log.timestamp})</span>
        `;
        list.appendChild(li);
    });
}

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
    loadItems(); // Always refresh inventory
    
    // SMART REFRESH: Only refresh history if it is already open
    let historyList = document.getElementById('historyList');
    if (historyList.innerHTML.trim() !== "") {
        fetchAndShowHistory();
    }
}

// 4. Delete Item
async function deleteItem(item) {
    await fetch('/api/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item: item })
    });
    loadItems(); 
    
    // SMART REFRESH: Only refresh history if it is already open
    let historyList = document.getElementById('historyList');
    if (historyList.innerHTML.trim() !== "") {
        fetchAndShowHistory();
    }
}