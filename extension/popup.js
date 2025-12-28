
document.addEventListener('DOMContentLoaded', restoreOptions);
document.getElementById('save').addEventListener('click', saveOptions);

function saveOptions() {
  const backendUrl = document.getElementById('backend_url').value;
  const useLlm = document.getElementById('use_llm').checked;
  const sensitivity = document.getElementById('sensitivity').value;

  chrome.storage.sync.set({
    backend_url: backendUrl,
    use_llm: useLlm,
    sensitivity: sensitivity
  }, function () {
    const status = document.getElementById('status');
    status.textContent = 'Options saved.';
    setTimeout(function () {
      status.textContent = '';
    }, 750);
  });
}

function restoreOptions() {
  chrome.storage.sync.get({
    backend_url: 'http://127.0.0.1:8000',
    use_llm: false,
    sensitivity: 0.5
  }, function (items) {
    document.getElementById('backend_url').value = items.backend_url;
    document.getElementById('use_llm').checked = items.use_llm;
    document.getElementById('sensitivity').value = items.sensitivity;
  });
}

// Test Connection
document.getElementById('test-connection').addEventListener('click', async () => {
  const backendUrl = document.getElementById('backend_url').value;
  const status = document.getElementById('status');
  status.textContent = 'Testing...';
  status.style.color = '#888';

  try {
    const res = await fetch(backendUrl + '/health');
    if (res.ok) {
      const data = await res.json();
      status.textContent = `Backend: Online (OpenAI: ${data.openai_configured ? 'Yes' : 'No'})`;
      status.style.color = '#0f0';
    } else {
      status.textContent = 'Backend: Error ' + res.status;
      status.style.color = '#f00';
    }
  } catch (e) {
    status.textContent = 'Backend: Unreachable';
    status.style.color = '#f00';
  }
});
