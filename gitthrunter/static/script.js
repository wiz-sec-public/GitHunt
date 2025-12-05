document.addEventListener('DOMContentLoaded', function() {
    const toggleDeleteEvents = document.getElementById('toggleDeleteEvents');
    const tableBody = document.querySelector('#attacksTable tbody');
    let allAttacks = []; // Store all fetched data

    function renderTable(dataToRender) {
        tableBody.innerHTML = ''; // Clear existing rows
        dataToRender.forEach(attack => {
            const row = tableBody.insertRow();

            const createdAtCell = row.insertCell();
            createdAtCell.className = 'whitespace-nowrap px-4 py-2 text-gray-700 dark:text-gray-200';
            createdAtCell.textContent = attack.created_at;

            const eventTypeCell = row.insertCell();
            eventTypeCell.className = 'whitespace-nowrap px-4 py-2 text-gray-700 dark:text-gray-200';
            eventTypeCell.textContent = attack.event_type;

            const actorLoginCell = row.insertCell();
            actorLoginCell.className = 'whitespace-nowrap px-4 py-2 text-gray-700 dark:text-gray-200';
            actorLoginCell.textContent = attack.actor_login;

            const repoNameCell = row.insertCell();
            repoNameCell.className = 'px-4 py-2 text-gray-700 dark:text-gray-200 break-words';
            repoNameCell.style.maxWidth = '200px';
            repoNameCell.textContent = attack.repo_name;

            const titleCell = row.insertCell();
            titleCell.className = 'px-4 py-2 text-gray-700 dark:text-gray-200 break-words';
            titleCell.style.maxWidth = '300px';
            titleCell.textContent = attack.title;

            const refOrHeadRef = attack.ref || attack.head_ref;
            const refCell = row.insertCell();
            refCell.className = 'px-4 py-2 text-gray-700 dark:text-gray-200 break-words';
            refCell.style.maxWidth = '300px';
            refCell.textContent = refOrHeadRef;
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