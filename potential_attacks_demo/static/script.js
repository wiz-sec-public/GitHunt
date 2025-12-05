document.addEventListener('DOMContentLoaded', function() {
    const toggleDeleteEvents = document.getElementById('toggleDeleteEvents');
    const tableBody = document.querySelector('#attacksTable tbody');
    let allAttacks = []; // Store all fetched data

    function renderTable(dataToRender) {
        tableBody.innerHTML = ''; // Clear existing rows
        dataToRender.forEach(attack => {
            const row = tableBody.insertRow();
            row.insertCell().textContent = attack.created_at;
            row.insertCell().textContent = attack.event_type;
            row.insertCell().textContent = attack.actor_login;
            row.insertCell().textContent = attack.repo_name;
            row.insertCell().textContent = attack.title;
            const refOrHeadRef = attack.ref || attack.head_ref;
            row.insertCell().textContent = refOrHeadRef;
        });
    }

    function filterAndRender() {
        let filteredData = allAttacks;
        if (toggleDeleteEvents.checked) {
            filteredData = allAttacks.filter(attack => attack.event_type !== 'DeleteEvent');
        }
        renderTable(filteredData);
    }

    fetch('/api/potential_attacks')
        .then(response => response.json())
        .then(data => {
            // Sort data by created_at in descending order
            data.sort((a, b) => {
                return new Date(b.created_at) - new Date(a.created_at);
            });
            allAttacks = data; // Store all data
            filterAndRender(); // Initial render
        })
        .catch(error => console.error('Error fetching data:', error));

    toggleDeleteEvents.addEventListener('change', filterAndRender);
});