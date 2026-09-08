document.addEventListener('DOMContentLoaded', () => {
  const instanceBadge = document.getElementById('instance-name');
  const pingBtn = document.getElementById('ping-btn');
  const refreshBtn = document.getElementById('refresh-btn');
  const createForm = document.getElementById('create-campaign-form');
  const campaignsTbody = document.getElementById('campaigns-tbody');
  const campaignCount = document.getElementById('campaign-count');
  const requestLog = document.getElementById('request-log');
  const clearLogsBtn = document.getElementById('clear-logs-btn');
  const toast = document.getElementById('toast');

  function showToast(message, isError = false) {
    toast.textContent = message;
    toast.style.borderColor = isError ? '#ef4444' : '#10b981';
    toast.style.display = 'block';
    setTimeout(() => {
      toast.style.display = 'none';
    }, 3500);
  }

  function addLogEntry(method, url, status, durationMs, instance) {
    const emptyMsg = requestLog.querySelector('.empty-log');
    if (emptyMsg) {
      requestLog.innerHTML = '';
    }

    const entry = document.createElement('div');
    const isSuccess = status >= 200 && status < 300;
    entry.className = `log-entry ${isSuccess ? 'status-2xx' : 'status-4xx'}`;

    const time = new Date().toLocaleTimeString();
    entry.innerHTML = `
      <div>
        <strong>${method}</strong> ${url} 
        <span style="color: ${isSuccess ? '#34d399' : '#f87171'}">[${status}]</span>
        ${instance ? `<span style="color: #94a3b8">(${instance})</span>` : ''}
      </div>
      <div>
        <span>${durationMs}ms</span> &bull; 
        <span style="color: #94a3b8">${time}</span>
      </div>
    `;

    requestLog.prepend(entry);
    while (requestLog.children.length > 20) {
      requestLog.removeChild(requestLog.lastChild);
    }
  }

  async function apiFetch(url, options = {}) {
    const start = performance.now();
    const method = options.method || 'GET';
    try {
      const response = await fetch(url, options);
      const duration = Math.round(performance.now() - start);
      const instance = response.headers.get('X-Instance-ID') || '';
      addLogEntry(method, url, response.status, duration, instance);
      return response;
    } catch (err) {
      const duration = Math.round(performance.now() - start);
      addLogEntry(method, url, 'ERR', duration, '');
      throw err;
    }
  }

  async function updateHealth() {
    try {
      const res = await apiFetch('/health');
      if (res.ok) {
        const data = await res.json();
        instanceBadge.textContent = data.instance || 'healthy';
      } else {
        instanceBadge.textContent = 'degraded';
      }
    } catch (err) {
      instanceBadge.textContent = 'offline';
    }
  }

  async function loadCampaigns() {
    try {
      const res = await apiFetch('/campaigns');
      if (!res.ok) throw new Error('Failed to fetch campaigns');
      const json = await res.json();
      const campaigns = json.data || [];

      campaignCount.textContent = `${campaigns.length} campaign${campaigns.length === 1 ? '' : 's'} found`;

      if (campaigns.length === 0) {
        campaignsTbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No campaigns found. Create one above!</td></tr>';
        return;
      }

      campaignsTbody.innerHTML = '';
      campaigns.forEach(c => {
        const tr = document.createElement('tr');
        const due = c.due_date ? new Date(c.due_date).toLocaleString() : '—';
        const created = c.created_at ? new Date(c.created_at).toLocaleString() : '—';

        tr.innerHTML = `
          <td><strong>#${c.campaign_id}</strong></td>
          <td>${c.name}</td>
          <td>${due}</td>
          <td>${created}</td>
          <td>
            <button class="btn btn-danger-sm delete-btn" data-id="${c.campaign_id}">Delete</button>
          </td>
        `;
        campaignsTbody.appendChild(tr);
      });

      // Attach delete listeners
      campaignsTbody.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          const id = e.target.getAttribute('data-id');
          await deleteCampaign(id);
        });
      });
    } catch (err) {
      campaignsTbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Error loading campaigns: ${err.message}</td></tr>`;
      showToast(err.message, true);
    }
  }

  async function createCampaign(e) {
    e.preventDefault();
    const nameInput = document.getElementById('campaign-name');
    const dueInput = document.getElementById('campaign-due');
    const name = nameInput.value.trim();
    const dueDate = dueInput.value ? new Date(dueInput.value).toISOString() : null;

    if (!name) return;

    try {
      const res = await apiFetch('/campaigns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, due_date: dueDate })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Could not create campaign');
      }

      nameInput.value = '';
      dueInput.value = '';
      showToast('Campaign created successfully!');
      await loadCampaigns();
    } catch (err) {
      showToast(err.message, true);
    }
  }

  async function deleteCampaign(id) {
    if (!confirm(`Are you sure you want to delete campaign #${id}?`)) return;
    try {
      const res = await apiFetch(`/campaigns/${id}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 204) {
        throw new Error('Failed to delete campaign');
      }
      showToast(`Campaign #${id} deleted.`);
      await loadCampaigns();
    } catch (err) {
      showToast(err.message, true);
    }
  }

  async function testRoundRobin() {
    pingBtn.disabled = true;
    pingBtn.textContent = 'Pinging (6x)...';
    const instancesFound = new Set();

    const promises = Array.from({ length: 6 }).map(async () => {
      try {
        const res = await apiFetch('/health');
        if (res.ok) {
          const data = await res.json();
          if (data.instance) instancesFound.add(data.instance);
        }
      } catch (_) {}
    });

    await Promise.all(promises);
    pingBtn.disabled = false;
    pingBtn.textContent = 'Test Round Robin';

    const arr = Array.from(instancesFound);
    if (arr.length > 1) {
      showToast(`Load balanced across ${arr.length} instances: ${arr.join(', ')}`);
      instanceBadge.textContent = `${arr.join(' | ')}`;
    } else if (arr.length === 1) {
      showToast(`Responded by: ${arr[0]}`);
      instanceBadge.textContent = arr[0];
    }
  }

  // Event Listeners
  createForm.addEventListener('submit', createCampaign);
  refreshBtn.addEventListener('click', () => {
    loadCampaigns();
    updateHealth();
  });
  pingBtn.addEventListener('click', testRoundRobin);
  clearLogsBtn.addEventListener('click', () => {
    requestLog.innerHTML = '<div class="empty-log">Log cleared. Make requests to view telemetry events.</div>';
  });

  // Initial Load
  updateHealth();
  loadCampaigns();
});
