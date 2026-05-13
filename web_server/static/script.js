const DEFAULT_CATEGORIES = [
    "Hardware",
    "Peripherals",
    "Networking",
    "Cables",
    "Office",
    "Servers",
    "Laptops",
    "Desktops",
    "Monitors",
    "Printers",
    "Mobile Devices",
    "Audio / Video",
    "Security",
    "Power",
    "Accessories",
];

const DEFAULT_LOCATIONS = [
    "Warehouse A",
    "Warehouse B",
    "Warehouse C",
    "Retail Floor",
    "Receiving",
    "Shipping Dock",
    "Back Office",
    "Repair Bench",
    "Staging Area",
    "Data Center Cage",
    "Remote Site",
    "Storage Room",
];

const state = {
    authenticated: false,
    username: null,
    filters: {
        search: "",
        category: "",
        location: "",
        stock_status: "all",
        sort: "updated_at",
        direction: "desc",
    },
    metadata: {
        categories: [...DEFAULT_CATEGORIES],
        locations: [...DEFAULT_LOCATIONS],
    },
    modalMode: "create",
};

const elements = {};
let searchDebounceId = null;

document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    bindEvents();
    initializeView();
});

function cacheElements() {
    Object.assign(elements, {
        notification: document.getElementById("notification"),
        serviceHealth: document.getElementById("serviceHealth"),
        readinessHealth: document.getElementById("readinessHealth"),
        authStateBadge: document.getElementById("authStateBadge"),
        loginForm: document.getElementById("loginForm"),
        usernameInput: document.getElementById("usernameInput"),
        passwordInput: document.getElementById("passwordInput"),
        authActions: document.getElementById("authActions"),
        authUserLabel: document.getElementById("authUserLabel"),
        logoutButton: document.getElementById("logoutButton"),
        totalItemsMetric: document.getElementById("totalItemsMetric"),
        totalUnitsMetric: document.getElementById("totalUnitsMetric"),
        lowStockMetric: document.getElementById("lowStockMetric"),
        locationsMetric: document.getElementById("locationsMetric"),
        openCreateModalButton: document.getElementById("openCreateModalButton"),
        searchInput: document.getElementById("searchInput"),
        categoryFilter: document.getElementById("categoryFilter"),
        locationFilter: document.getElementById("locationFilter"),
        stockFilter: document.getElementById("stockFilter"),
        sortFilter: document.getElementById("sortFilter"),
        directionFilter: document.getElementById("directionFilter"),
        inventoryTableBody: document.getElementById("inventoryTableBody"),
        lowStockList: document.getElementById("lowStockList"),
        historyList: document.getElementById("historyList"),
        refreshDashboardButton: document.getElementById("refreshDashboardButton"),
        refreshHistoryButton: document.getElementById("refreshHistoryButton"),
        clearHistoryButton: document.getElementById("clearHistoryButton"),
        itemModal: document.getElementById("itemModal"),
        modalTitle: document.getElementById("modalTitle"),
        closeModalButton: document.getElementById("closeModalButton"),
        itemForm: document.getElementById("itemForm"),
        itemIdInput: document.getElementById("itemIdInput"),
        itemNameInput: document.getElementById("itemNameInput"),
        itemSkuInput: document.getElementById("itemSkuInput"),
        itemQuantityInput: document.getElementById("itemQuantityInput"),
        itemThresholdInput: document.getElementById("itemThresholdInput"),
        itemLocationInput: document.getElementById("itemLocationInput"),
        itemCategoryInput: document.getElementById("itemCategoryInput"),
    });
}

function bindEvents() {
    elements.loginForm.addEventListener("submit", handleLogin);
    elements.logoutButton.addEventListener("click", handleLogout);
    elements.openCreateModalButton.addEventListener("click", () => openModal("create"));
    elements.closeModalButton.addEventListener("click", closeModal);
    elements.itemModal.addEventListener("click", (event) => {
        if (event.target === elements.itemModal) {
            closeModal();
        }
    });
    elements.itemForm.addEventListener("submit", handleItemSubmit);
    elements.refreshDashboardButton.addEventListener("click", refreshAllData);
    elements.refreshHistoryButton.addEventListener("click", loadHistory);
    elements.clearHistoryButton.addEventListener("click", clearHistory);

    elements.searchInput.addEventListener("input", (event) => {
        window.clearTimeout(searchDebounceId);
        state.filters.search = event.target.value.trim();
        searchDebounceId = window.setTimeout(loadItems, 180);
    });

    for (const [element, filterKey] of [
        [elements.categoryFilter, "category"],
        [elements.locationFilter, "location"],
        [elements.stockFilter, "stock_status"],
        [elements.sortFilter, "sort"],
        [elements.directionFilter, "direction"],
    ]) {
        element.addEventListener("change", (event) => {
            state.filters[filterKey] = event.target.value;
            loadItems();
        });
    }
}

async function initializeView() {
    renderAuthState();
    await Promise.all([checkHealth(), refreshSession()]);
    await refreshAllData();
    window.setInterval(checkHealth, 30000);
}

async function refreshAllData() {
    await Promise.all([loadDashboard(), loadItems(), loadHistory()]);
}

async function api(path, options = {}) {
    const requestOptions = { ...options };
    requestOptions.headers = requestOptions.headers || {};

    if (requestOptions.body && !requestOptions.headers["Content-Type"]) {
        requestOptions.headers["Content-Type"] = "application/json";
    }

    const response = await fetch(path, requestOptions);
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : null;

    if (!response.ok) {
        throw new Error(payload?.message || "Request failed");
    }

    return payload;
}

async function checkHealth() {
    const [health, ready] = await Promise.allSettled([
        api("/healthz"),
        api("/readyz"),
    ]);

    setHealthPill(elements.serviceHealth, health.status === "fulfilled");
    setHealthPill(elements.readinessHealth, ready.status === "fulfilled");
}

function setHealthPill(element, isHealthy) {
    element.textContent = isHealthy ? "Healthy" : "Issue";
    element.className = `status-pill ${isHealthy ? "healthy" : "unhealthy"}`;
}

async function refreshSession() {
    try {
        const sessionData = await api("/api/session");
        state.authenticated = sessionData.authenticated;
        state.username = sessionData.username;
        renderAuthState();
    } catch (_error) {
        state.authenticated = false;
        state.username = null;
        renderAuthState();
    }
}

function renderAuthState() {
    if (state.authenticated) {
        elements.authStateBadge.textContent = "Admin";
        elements.authStateBadge.className = "status-pill healthy";
        elements.loginForm.classList.add("hidden");
        elements.authActions.classList.remove("hidden");
        elements.authUserLabel.textContent = state.username;
    } else {
        elements.authStateBadge.textContent = "Read only";
        elements.authStateBadge.className = "status-pill muted";
        elements.loginForm.classList.remove("hidden");
        elements.authActions.classList.add("hidden");
        elements.authUserLabel.textContent = "";
        closeModal();
    }

    elements.openCreateModalButton.disabled = !state.authenticated;
    elements.clearHistoryButton.disabled = !state.authenticated;
}

async function handleLogin(event) {
    event.preventDefault();

    try {
        const result = await api("/api/login", {
            method: "POST",
            body: JSON.stringify({
                username: elements.usernameInput.value.trim(),
                password: elements.passwordInput.value.trim(),
            }),
        });
        state.authenticated = result.authenticated;
        state.username = result.username;
        elements.passwordInput.value = "";
        renderAuthState();
        notify("Signed in successfully.", "success");
        await refreshAllData();
    } catch (error) {
        notify(error.message, "error");
    }
}

async function handleLogout() {
    try {
        await api("/api/logout", { method: "POST" });
        state.authenticated = false;
        state.username = null;
        renderAuthState();
        notify("Signed out.", "success");
    } catch (error) {
        notify(error.message, "error");
    }
}

async function loadDashboard() {
    try {
        const payload = await api("/api/dashboard");
        const summary = payload.summary;
        state.metadata.categories = uniqueValues([
            ...DEFAULT_CATEGORIES,
            ...(payload.categories || []),
        ]);
        state.metadata.locations = uniqueValues([
            ...DEFAULT_LOCATIONS,
            ...(payload.locations || []),
        ]);

        elements.totalItemsMetric.textContent = String(summary.total_items);
        elements.totalUnitsMetric.textContent = String(summary.total_units);
        elements.lowStockMetric.textContent = String(summary.low_stock_count);
        elements.locationsMetric.textContent = String(summary.locations);

        renderFilterOptions(elements.categoryFilter, "All categories", state.metadata.categories);
        renderFilterOptions(elements.locationFilter, "All locations", state.metadata.locations);
        renderSelectOptions(elements.itemCategoryInput, state.metadata.categories);
        renderSelectOptions(elements.itemLocationInput, state.metadata.locations);
        renderLowStockList(payload.low_stock_items || []);
    } catch (error) {
        notify(error.message, "error");
    }
}

async function loadItems() {
    const params = new URLSearchParams();
    Object.entries(state.filters).forEach(([key, value]) => {
        if (value) {
            params.set(key, value);
        }
    });

    try {
        const payload = await api(`/api/items?${params.toString()}`);
        renderInventoryTable(payload.items || []);
    } catch (error) {
        notify(error.message, "error");
    }
}

async function loadHistory() {
    try {
        const payload = await api("/api/history?limit=20");
        renderHistory(payload.history || []);
    } catch (error) {
        notify(error.message, "error");
    }
}

function renderFilterOptions(selectElement, defaultLabel, values) {
    const currentValue = selectElement.value;
    selectElement.innerHTML = "";

    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = defaultLabel;
    selectElement.appendChild(defaultOption);

    values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        selectElement.appendChild(option);
    });

    selectElement.value = values.includes(currentValue) ? currentValue : "";
    state.filters[selectElement.id === "categoryFilter" ? "category" : "location"] = selectElement.value;
}

function renderSelectOptions(selectElement, values) {
    const currentValue = selectElement.value;
    selectElement.innerHTML = "";

    values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        selectElement.appendChild(option);
    });

    if (values.includes(currentValue)) {
        selectElement.value = currentValue;
    } else if (values.length) {
        selectElement.value = values[0];
    }
}

function renderInventoryTable(items) {
    elements.inventoryTableBody.innerHTML = "";

    if (!items.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 8;
        cell.textContent = "No inventory items match the current filters.";
        row.appendChild(cell);
        elements.inventoryTableBody.appendChild(row);
        return;
    }

    items.forEach((item) => {
        const row = document.createElement("tr");
        row.appendChild(createCellWithMarkup(item.name, item.category));
        row.appendChild(createTextCell(item.sku));
        row.appendChild(createStockCell(item.quantity, item.is_low_stock));
        row.appendChild(createTextCell(item.location));
        row.appendChild(createTextCell(item.category));
        row.appendChild(createTextCell(String(item.low_stock_threshold)));
        row.appendChild(createTextCell(formatDate(item.updated_at)));
        row.appendChild(createActionCell(item));
        elements.inventoryTableBody.appendChild(row);
    });
}

function createCellWithMarkup(primary, secondary) {
    const cell = document.createElement("td");
    const title = document.createElement("span");
    title.className = "item-name";
    title.textContent = primary;
    const subtitle = document.createElement("span");
    subtitle.className = "subtle";
    subtitle.textContent = secondary;
    cell.appendChild(title);
    cell.appendChild(subtitle);
    return cell;
}

function createTextCell(value) {
    const cell = document.createElement("td");
    cell.textContent = value;
    return cell;
}

function createStockCell(quantity, isLowStock) {
    const cell = document.createElement("td");
    const pill = document.createElement("span");
    pill.className = `stock-pill ${isLowStock ? "low" : "healthy"}`;
    pill.textContent = `${quantity} ${isLowStock ? "At risk" : "Healthy"}`;
    cell.appendChild(pill);
    return cell;
}

function createActionCell(item) {
    const cell = document.createElement("td");
    const wrapper = document.createElement("div");
    wrapper.className = "row-actions";

    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.textContent = "Edit";
    editButton.disabled = !state.authenticated;
    editButton.addEventListener("click", () => openModal("edit", item));

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "danger-ghost";
    deleteButton.textContent = "Delete";
    deleteButton.disabled = !state.authenticated;
    deleteButton.addEventListener("click", () => handleDelete(item));

    wrapper.appendChild(editButton);
    wrapper.appendChild(deleteButton);
    cell.appendChild(wrapper);
    return cell;
}

function renderLowStockList(items) {
    elements.lowStockList.innerHTML = "";

    if (!items.length) {
        const entry = document.createElement("li");
        entry.textContent = "No low-stock alerts right now.";
        elements.lowStockList.appendChild(entry);
        return;
    }

    items.forEach((item) => {
        const entry = document.createElement("li");
        const title = document.createElement("div");
        title.className = "alert-title";
        title.textContent = `${item.name} (${item.sku})`;
        const meta = document.createElement("div");
        meta.className = "alert-meta";
        meta.textContent = `${item.quantity} units at ${item.location} | threshold ${item.low_stock_threshold}`;
        entry.appendChild(title);
        entry.appendChild(meta);
        elements.lowStockList.appendChild(entry);
    });
}

function renderHistory(entries) {
    elements.historyList.innerHTML = "";

    if (!entries.length) {
        const entry = document.createElement("li");
        entry.textContent = "No history yet.";
        elements.historyList.appendChild(entry);
        return;
    }

    entries.forEach((historyEntry) => {
        const item = document.createElement("li");
        const title = document.createElement("div");
        title.className = "history-title";

        const badge = document.createElement("span");
        badge.className = `history-badge ${historyEntry.action}`;
        badge.textContent = historyEntry.action;

        title.appendChild(badge);
        title.append(document.createTextNode(historyEntry.item));

        const meta = document.createElement("div");
        meta.className = "history-meta";
        meta.textContent = `${formatHistoryDetails(historyEntry.details)} | ${formatDate(historyEntry.timestamp)}`;

        item.appendChild(title);
        item.appendChild(meta);
        elements.historyList.appendChild(item);
    });
}

function formatHistoryDetails(details) {
    if (!details) {
        return "Recorded event";
    }

    if (details.message) {
        return details.message;
    }

    if (details.quantity) {
        return `Qty ${details.quantity.from} -> ${details.quantity.to}`;
    }

    const keys = Object.keys(details);
    if (!keys.length) {
        return "Recorded event";
    }

    return keys
        .slice(0, 2)
        .map((key) => `${key}: ${details[key].from} -> ${details[key].to}`)
        .join(", ");
}

function openModal(mode, item = null) {
    if (!state.authenticated) {
        notify("Sign in as admin to modify inventory.", "error");
        return;
    }

    state.modalMode = mode;
    elements.modalTitle.textContent = mode === "create" ? "Add Item" : "Edit Item";
    elements.itemForm.reset();

    if (item) {
        elements.itemIdInput.value = item.id;
        elements.itemNameInput.value = item.name;
        elements.itemSkuInput.value = item.sku;
        elements.itemQuantityInput.value = item.quantity;
        elements.itemThresholdInput.value = item.low_stock_threshold;
        renderSelectOptions(elements.itemLocationInput, uniqueValues([...state.metadata.locations, item.location]));
        renderSelectOptions(elements.itemCategoryInput, uniqueValues([...state.metadata.categories, item.category]));
        elements.itemLocationInput.value = item.location;
        elements.itemCategoryInput.value = item.category;
    } else {
        elements.itemIdInput.value = "";
        elements.itemQuantityInput.value = "0";
        elements.itemThresholdInput.value = "0";
        renderSelectOptions(elements.itemLocationInput, state.metadata.locations);
        renderSelectOptions(elements.itemCategoryInput, state.metadata.categories);
    }

    elements.itemModal.classList.remove("hidden");
}

function closeModal() {
    elements.itemModal.classList.add("hidden");
}

async function handleItemSubmit(event) {
    event.preventDefault();

    const payload = {
        name: elements.itemNameInput.value.trim(),
        sku: elements.itemSkuInput.value.trim().toUpperCase(),
        quantity: Number(elements.itemQuantityInput.value),
        low_stock_threshold: Number(elements.itemThresholdInput.value),
        location: elements.itemLocationInput.value.trim(),
        category: elements.itemCategoryInput.value.trim(),
    };

    try {
        if (state.modalMode === "create") {
            await api("/api/items", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            resetInventoryFilters();
            notify("Inventory item created.", "success");
        } else {
            await api(`/api/items/${elements.itemIdInput.value}`, {
                method: "PUT",
                body: JSON.stringify(payload),
            });
            notify("Inventory item updated.", "success");
        }

        closeModal();
        await refreshAllData();
    } catch (error) {
        notify(error.message, "error");
    }
}

function resetInventoryFilters() {
    state.filters.search = "";
    state.filters.category = "";
    state.filters.location = "";
    state.filters.stock_status = "all";
    state.filters.sort = "updated_at";
    state.filters.direction = "desc";

    elements.searchInput.value = "";
    elements.categoryFilter.value = "";
    elements.locationFilter.value = "";
    elements.stockFilter.value = "all";
    elements.sortFilter.value = "updated_at";
    elements.directionFilter.value = "desc";
}

async function handleDelete(item) {
    if (!state.authenticated) {
        notify("Sign in as admin to delete inventory.", "error");
        return;
    }

    if (!window.confirm(`Delete ${item.name} (${item.sku})?`)) {
        return;
    }

    try {
        await api(`/api/items/${item.id}`, { method: "DELETE" });
        notify("Inventory item deleted.", "success");
        await refreshAllData();
    } catch (error) {
        notify(error.message, "error");
    }
}

async function clearHistory() {
    if (!state.authenticated) {
        notify("Sign in as admin to clear history.", "error");
        return;
    }

    if (!window.confirm("Clear the full history log?")) {
        return;
    }

    try {
        await api("/api/history/clear", { method: "POST" });
        notify("History cleared.", "success");
        await loadHistory();
    } catch (error) {
        notify(error.message, "error");
    }
}

function notify(message, type) {
    elements.notification.textContent = message;
    elements.notification.className = `notification ${type}`;
    window.clearTimeout(elements.notification.hideTimer);
    elements.notification.hideTimer = window.setTimeout(() => {
        elements.notification.className = "notification hidden";
    }, 3400);
}

function formatDate(isoString) {
    if (!isoString) {
        return "Unknown";
    }

    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) {
        return isoString;
    }

    return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    }).format(date);
}

function uniqueValues(values) {
    return [...new Set(values.filter(Boolean))];
}
