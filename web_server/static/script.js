// This runs when the page loads
window.onload = function() {
    loadItems();
};

async function loadItems() {
    // Talk to the Python Backend
    let response = await fetch('/api/data');
    let data = await response.json();
    
    let list = document.getElementById('itemList');
    list.innerHTML = ""; // Clear current list

    // Loop through items and add to HTML
    data.items.forEach(item => {
        let li = document.createElement('li');
        li.innerHTML = `
            ${item} 
            <button class="delete" onclick="deleteItem('${item}')">Delete</button>
        `;
        list.appendChild(li);
    });
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
    loadItems(); // Refresh the list
}

async function deleteItem(item) {
    await fetch('/api/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item: item })
    });
    loadItems(); // Refresh the list
}