document.addEventListener('DOMContentLoaded', () => {
    // Navigation Handling
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.section');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(nav => nav.classList.remove('active'));
            sections.forEach(sec => sec.classList.remove('active'));
            item.classList.add('active');
            const targetId = item.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });

    // --- SIMULATED DATABASE (LocalStorage) ---
    const DB_KEY = 'sovereign_db';
    function getDB() {
        return JSON.parse(localStorage.getItem(DB_KEY) || '{}');
    }
    function saveToDB(id, data) {
        const db = getDB();
        db[id] = data;
        localStorage.setItem(DB_KEY, JSON.stringify(db));
    }
    function getFromDB(id) {
        return getDB()[id];
    }

    const AVATAR_KEY = 'avatar_cfg';
    function getAvatarCfg() {
        return JSON.parse(localStorage.getItem(AVATAR_KEY) || '{}');
    }
    function setAvatarCfg(cfg) {
        localStorage.setItem(AVATAR_KEY, JSON.stringify(cfg));
    }

    // --- API BASE ---
    const API_BASE = window.location.origin;

    function getAdminToken() {
        return (document.getElementById('html_token') || {}).value || '';
    }

    // --- QUICK ACTION HANDLER ---
    const quickBtn = document.getElementById('quickActionBtn');
    if (quickBtn) {
        quickBtn.addEventListener('click', () => {
            const input = document.getElementById('quickInput').value.trim();
            if (!input) return;

            // Switch to Editor Tab
            navItems.forEach(nav => nav.classList.remove('active'));
            sections.forEach(sec => sec.classList.remove('active'));
            
            const editorNav = document.querySelector('[data-target="editor"]');
            const editorSec = document.getElementById('editor');
            
            if (editorNav && editorSec) {
                editorNav.classList.add('active');
                editorSec.classList.add('active');
                
                // Pre-fill and click decrypt
                document.getElementById('edit_urlInput').value = input;
                document.getElementById('decryptBtn').click();
            }
        });
    }

    // =====================================================
    // --- HTML PAGES MANAGER ---
    // =====================================================

    const htmlKeyInput = document.getElementById('html_key');
    const htmlPreviewUrl = document.getElementById('html_preview_url');
    const htmlFileInput = document.getElementById('html_file');
    const htmlFilename = document.getElementById('html_filename');
    const htmlDropzone = document.getElementById('html_dropzone');

    // Live preview of the blank link URL as user types the key
    if (htmlKeyInput && htmlPreviewUrl) {
        htmlKeyInput.addEventListener('input', () => {
            const k = htmlKeyInput.value.trim();
            htmlPreviewUrl.textContent = k ? `${API_BASE}/r/${encodeURIComponent(k)}` : '/r/<key>';
        });
    }

    // File input display
    if (htmlFileInput && htmlFilename) {
        htmlFileInput.addEventListener('change', () => {
            if (htmlFileInput.files[0]) {
                const f = htmlFileInput.files[0];
                htmlFilename.textContent = `${f.name} (${(f.size / 1024).toFixed(1)} KB)`;
            } else {
                htmlFilename.textContent = '';
            }
        });
    }

    // Drag & drop support
    if (htmlDropzone && htmlFileInput) {
        htmlDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            htmlDropzone.style.borderColor = 'var(--primary)';
            htmlDropzone.style.background = 'rgba(0,242,234,0.08)';
        });
        htmlDropzone.addEventListener('dragleave', () => {
            htmlDropzone.style.borderColor = 'rgba(0,242,234,0.3)';
            htmlDropzone.style.background = '';
        });
        htmlDropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            htmlDropzone.style.borderColor = 'rgba(0,242,234,0.3)';
            htmlDropzone.style.background = '';
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const f = files[0];
                if (f.name.match(/\.html?$/i)) {
                    // Assign to file input via DataTransfer
                    const dt = new DataTransfer();
                    dt.items.add(f);
                    htmlFileInput.files = dt.files;
                    htmlFilename.textContent = `${f.name} (${(f.size / 1024).toFixed(1)} KB)`;
                } else {
                    showHtmlResult('error', 'Please drop an HTML (.html or .htm) file.');
                }
            }
        });
    }

    function showHtmlResult(type, message, extra) {
        const el = document.getElementById('html_result');
        if (!el) return;
        const colors = { success: '#00ff7f', error: '#ff0055', info: '#00f2ea' };
        const icons = { success: 'fa-check-circle', error: 'fa-triangle-exclamation', info: 'fa-circle-info' };
        const color = colors[type] || '#ccc';
        const icon = icons[type] || 'fa-circle-info';
        el.innerHTML = `
            <div style="background: rgba(${type==='success'?'0,255,127':type==='error'?'255,0,85':'0,242,234'},0.08); padding: 1rem; border-radius: 8px; border: 1px solid ${color};">
                <p style="color: ${color}; margin-bottom: ${extra ? '8px' : '0'}; font-weight: bold;">
                    <i class="fa-solid ${icon}"></i> ${message}
                </p>
                ${extra || ''}
            </div>`;
    }

    // Publish button
    const htmlPublishBtn = document.getElementById('html_publishBtn');
    if (htmlPublishBtn) {
        htmlPublishBtn.addEventListener('click', async () => {
            const key = (document.getElementById('html_key').value || '').trim();
            const title = (document.getElementById('html_title').value || '').trim();
            const token = getAdminToken();
            const file = htmlFileInput && htmlFileInput.files[0];

            if (!key) { showHtmlResult('error', 'Please enter a blank link key.'); return; }
            if (!/^[A-Za-z0-9_\-]{1,128}$/.test(key)) {
                showHtmlResult('error', 'Key must be letters, numbers, dashes, or underscores (max 128 chars).');
                return;
            }
            if (!file) { showHtmlResult('error', 'Please choose an HTML file to upload.'); return; }
            if (!token) { showHtmlResult('error', 'Please enter your admin token.'); return; }

            htmlPublishBtn.disabled = true;
            htmlPublishBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Publishing...';

            const fd = new FormData();
            fd.append('key', key);
            fd.append('title', title);
            fd.append('file', file);

            try {
                const res = await fetch(`${API_BASE}/api/links/upload-html`, {
                    method: 'POST',
                    headers: { 'X-Admin-Token': token },
                    body: fd
                });
                const json = await res.json();
                if (json.ok) {
                    const link = `${API_BASE}/r/${encodeURIComponent(key)}`;
                    showHtmlResult('success', 'HTML page published successfully!', `
                        <p style="color: #ccc; margin-bottom: 6px;">Your blank link:</p>
                        <a href="${link}" target="_blank" style="color: #00ff7f; word-break: break-all; font-size: 1rem;">${link}</a>
                        <button onclick="navigator.clipboard.writeText('${link}').then(()=>this.textContent='Copied!').catch(()=>{})"
                            style="margin-left: 10px; background: rgba(0,255,127,0.15); color: #00ff7f; border: 1px solid #00ff7f; border-radius: 4px; padding: 2px 10px; cursor: pointer; font-size: 0.8rem;">
                            <i class="fa-solid fa-copy"></i> Copy
                        </button>
                    `);
                    logToTerminal(`HTML page published: /r/${key} → ${file.name}`);
                    // Auto-refresh pages list
                    loadHtmlPages(token);
                    loadDashboardHtmlCount(token);
                } else {
                    showHtmlResult('error', `Error: ${json.error || 'Unknown error'}${json.detail ? ' – ' + json.detail : ''}`);
                    logToTerminal(`HTML upload failed: ${json.error}`, 'error');
                }
            } catch (e) {
                showHtmlResult('error', `Network error: ${e.message}`);
                logToTerminal(`HTML upload error: ${e.message}`, 'error');
            } finally {
                htmlPublishBtn.disabled = false;
                htmlPublishBtn.innerHTML = '<i class="fa-solid fa-rocket"></i> Publish HTML Page';
            }
        });
    }

    // Load HTML pages list
    async function loadHtmlPages(token) {
        const listEl = document.getElementById('html_pages_list');
        if (!listEl) return;
        if (!token) {
            listEl.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 2rem;">
                <i class="fa-solid fa-circle-info"></i> Enter your admin token above and click Refresh to see published pages.
            </div>`;
            return;
        }
        listEl.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 1.5rem;">
            <i class="fa-solid fa-spinner fa-spin"></i> Loading pages...
        </div>`;
        try {
            const res = await fetch(`${API_BASE}/api/links/list-html`, {
                headers: { 'X-Admin-Token': token }
            });
            const json = await res.json();
            if (json.ok) {
                renderHtmlPagesList(json.pages, token);
            } else {
                listEl.innerHTML = `<div style="color:#ff0055; padding:1rem;"><i class="fa-solid fa-triangle-exclamation"></i> ${json.error || 'Failed to load'}</div>`;
            }
        } catch (e) {
            listEl.innerHTML = `<div style="color:#ff0055; padding:1rem;"><i class="fa-solid fa-triangle-exclamation"></i> Network error: ${e.message}</div>`;
        }
    }

    function renderHtmlPagesList(pages, token) {
        const listEl = document.getElementById('html_pages_list');
        if (!pages || pages.length === 0) {
            listEl.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 2rem;">
                <i class="fa-solid fa-inbox" style="font-size:2rem; display:block; margin-bottom:0.5rem;"></i>
                No HTML pages published yet. Upload one above!
            </div>`;
            return;
        }
        const rows = pages.map(p => {
            const link = `${API_BASE}/r/${encodeURIComponent(p.key)}`;
            const sizeStr = p.size > 0 ? `${(p.size / 1024).toFixed(1)} KB` : 'unknown size';
            const statusIcon = p.has_file
                ? `<span style="color:#00ff7f;" title="File stored"><i class="fa-solid fa-circle-check"></i></span>`
                : `<span style="color:#ff0055;" title="File missing"><i class="fa-solid fa-circle-xmark"></i></span>`;
            return `
            <div style="border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; background: rgba(255,255,255,0.03);">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
                    <div style="flex:1; min-width:0;">
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                            ${statusIcon}
                            <span style="color:var(--primary); font-weight:bold; font-size:1rem;">/r/${escHtml(p.key)}</span>
                            ${p.title ? `<span style="color:#aaa; font-size:0.85rem;">– ${escHtml(p.title)}</span>` : ''}
                        </div>
                        <div style="color:var(--text-muted); font-size:0.8rem; margin-bottom:6px;">
                            <i class="fa-solid fa-file-code"></i> HTML file (${sizeStr})
                        </div>
                        <a href="${escHtml(link)}" target="_blank" style="color:#66b3ff; font-size:0.85rem; word-break:break-all;">${escHtml(link)}</a>
                    </div>
                    <div style="display:flex; gap:6px; flex-shrink:0;">
                        <button data-action="preview" data-link="${escHtml(link)}"
                            style="background: rgba(0,242,234,0.1); color:var(--primary); border:1px solid var(--primary); border-radius:4px; padding:5px 10px; cursor:pointer; font-size:0.8rem;" title="Preview">
                            <i class="fa-solid fa-eye"></i>
                        </button>
                        <button data-action="copy" data-link="${escHtml(link)}"
                            style="background: rgba(0,255,127,0.1); color:#00ff7f; border:1px solid #00ff7f; border-radius:4px; padding:5px 10px; cursor:pointer; font-size:0.8rem;" title="Copy link">
                            <i class="fa-solid fa-copy"></i>
                        </button>
                        <button data-action="delete" data-key="${escHtml(p.key)}"
                            style="background: rgba(255,0,85,0.1); color:#ff0055; border:1px solid #ff0055; border-radius:4px; padding:5px 10px; cursor:pointer; font-size:0.8rem;" title="Delete">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>`;
        }).join('');
        listEl.innerHTML = rows;
        // Attach event listeners via delegation (safe – no inline JS, no string escaping of sensitive values)
        listEl.querySelectorAll('button[data-action]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const action = btn.getAttribute('data-action');
                if (action === 'preview') {
                    window.open(btn.getAttribute('data-link'), '_blank');
                } else if (action === 'copy') {
                    const lnk = btn.getAttribute('data-link');
                    try {
                        await navigator.clipboard.writeText(lnk);
                        btn.innerHTML = '<i class="fa-solid fa-check"></i>';
                        setTimeout(() => { btn.innerHTML = '<i class="fa-solid fa-copy"></i>'; }, 1200);
                    } catch (e) {}
                } else if (action === 'delete') {
                    const key = btn.getAttribute('data-key');
                    if (!confirm(`Delete HTML page "/r/${key}"? This cannot be undone.`)) return;
                    btn.disabled = true;
                    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                    try {
                        const res = await fetch(`${API_BASE}/api/links/delete-html`, {
                            method: 'POST',
                            headers: { 'X-Admin-Token': token, 'Content-Type': 'application/json' },
                            body: JSON.stringify({ key })
                        });
                        const json = await res.json();
                        if (json.ok) {
                            logToTerminal(`HTML page deleted: /r/${key}`);
                            loadHtmlPages(token);
                            loadDashboardHtmlCount(token);
                        } else {
                            btn.disabled = false;
                            btn.innerHTML = '<i class="fa-solid fa-trash"></i>';
                            alert(`Delete failed: ${json.error || 'Unknown error'}`);
                        }
                    } catch (e) {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fa-solid fa-trash"></i>';
                        alert(`Network error: ${e.message}`);
                    }
                }
            });
        });
    }

    function escHtml(s) {
        return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    }

    async function loadDashboardHtmlCount(token) {
        if (!token) return;
        try {
            const res = await fetch(`${API_BASE}/api/links/list-html`, {
                headers: { 'X-Admin-Token': token }
            });
            const json = await res.json();
            const countEl = document.getElementById('dashHtmlCountVal');
            if (countEl && json.ok) {
                countEl.textContent = json.pages.length;
            }
        } catch (e) {}
    }

    // Refresh button
    const htmlRefreshBtn = document.getElementById('html_refreshBtn');
    if (htmlRefreshBtn) {
        htmlRefreshBtn.addEventListener('click', () => {
            const token = getAdminToken();
            loadHtmlPages(token);
        });
    }

    // Auto-load pages when switching to HTML section
    document.querySelector('[data-target="html-pages"]') && document.querySelector('[data-target="html-pages"]').addEventListener('click', () => {
        const token = getAdminToken();
        if (token) loadHtmlPages(token);
    });

    // =====================================================
    // --- LINK GENERATOR LOGIC ---
    // =====================================================
    const generateBtn = document.getElementById('generateBtn');
    if (generateBtn) {
        generateBtn.addEventListener('click', () => {
            const data = {
                ref: document.getElementById('gen_ref').value,
                passport: document.getElementById('gen_passport').value,
                name: document.getElementById('gen_name').value,
                father: document.getElementById('gen_father').value,
                village: document.getElementById('gen_village').value,
                po: document.getElementById('gen_po').value,
                district: document.getElementById('gen_district').value,
                place: document.getElementById('gen_place').value,
                issueDate: document.getElementById('gen_issueDate').value,
                address: document.getElementById('gen_address').value,
                code: "0000"
            };

            const pdfFile = document.getElementById('gen_pdf').files[0];

            if (!data.passport || !data.name) {
                logToTerminal('Error: Missing required fields (Passport/Name)', 'error');
                return;
            }

            if (pdfFile) {
                logToTerminal(`Uploading PDF: ${pdfFile.name} (Size: ${(pdfFile.size/1024).toFixed(2)} KB)...`);
                // Simulate Upload
                setTimeout(() => {
                    logToTerminal('PDF Uploaded Successfully to Secure Storage.');
                }, 500);
            } else {
                logToTerminal('Warning: No PDF attached. Generating link with metadata only.', 'warning');
            }

            logToTerminal(`Generating Link for ${data.passport}...`);
            
            // DB Based Generation
            const uniqueId = 'ID_' + Date.now().toString(36); // Simple ID
            saveToDB(uniqueId, data);

            // Encode Data (Hybrid: ID + Token for redundancy, or just ID?)
            // For now, let's keep token but ALSO support ID lookup
            const token = btoa(JSON.stringify(data));
            const base = window.location.origin;
            const link = `${base}/ords/f?p=500:50:::NO:RP:P50_TOKEN_ID:${token}&ref_id=${uniqueId}`;
            
            document.getElementById('resultArea').innerHTML = `
                <div style="background: rgba(0,255,0,0.1); padding: 1rem; border-radius: 5px; border: 1px solid #00ff7f;">
                    <p style="color: #ccc; margin-bottom: 5px;">New Secure Link (Database Synced):</p>
                    <a href="${link}" target="_blank" style="color: #00ff7f; word-break: break-all;">${link}</a>
                </div>
            `;
            logToTerminal(`Link generated. ID: ${uniqueId} saved to Secure Database.`);
        });
    }

    // --- LINK EDITOR/DECODER LOGIC ---
    const decryptBtn = document.getElementById('decryptBtn');
    if (decryptBtn) {
        decryptBtn.addEventListener('click', () => {
            const url = document.getElementById('edit_urlInput').value;
            try {
                let data = null;
                let currentId = null;
                let originalOrigin = '';

                // Try Database Lookup first (if ref_id exists)
                if (url.includes('ref_id=')) {
                    currentId = url.split('ref_id=')[1].split('&')[0];
                    const dbData = getFromDB(currentId);
                    if (dbData) {
                        data = dbData;
                        logToTerminal(`Found Record in Database (ID: ${currentId}). Loading...`);
                    }
                }

                // Fallback to Token Decoding
                if (!data) {
                     // Extract Token
                    let token = "";
                    if (url.includes('P50_TOKEN_ID:')) {
                        token = url.split('P50_TOKEN_ID:')[1];
                    } else if (url.includes('P50_TOKEN_ID=')) {
                        token = url.split('P50_TOKEN_ID=')[1];
                    } else {
                        token = url;
                    }
                    token = token.split('&')[0].split('#')[0];
                    data = JSON.parse(atob(token));
                    logToTerminal('Link Decrypted from Token (No DB Record Found).');
                }

                // Populate Form
                document.getElementById('edit_ref').value = data.ref || '';
                document.getElementById('edit_passport').value = data.passport || '';
                document.getElementById('edit_name').value = data.name || '';
                document.getElementById('edit_father').value = data.father || '';
                document.getElementById('edit_village').value = data.village || '';
                document.getElementById('edit_po').value = data.po || '';
                document.getElementById('edit_district').value = data.district || '';
                document.getElementById('edit_place').value = data.place || '';
                document.getElementById('edit_issueDate').value = data.issueDate || '';
                document.getElementById('edit_address').value = data.address || '';
                
                // Store ID for update
                document.getElementById('updateLinkBtn').setAttribute('data-current-id', currentId || '');

                try { originalOrigin = new URL(url).origin } catch (e) { originalOrigin = window.location.origin }

                // Show Form
                document.getElementById('editorForm').style.display = 'block';

                const token = btoa(JSON.stringify(data));
                const base = originalOrigin;
                const fixed = `${base}/ords/f?p=500:50:::NO:RP:P50_TOKEN_ID:${token}${currentId?`&ref_id=${currentId}`:''}`;
                const area = document.getElementById('editResultArea');
                if (area) {
                    area.innerHTML = `
                        <div style="background: rgba(0,136,255,0.1); padding: 1rem; border-radius: 5px; border: 1px solid #0088ff;">
                            <p style="color: #ccc; margin-bottom: 5px;">Fixed Link (Current Domain):</p>
                            <a href="${fixed}" target="_blank" style="color: #66b3ff; word-break: break-all;">${fixed}</a>
                        </div>
                    `;
                }

                document.getElementById('updateLinkBtn').setAttribute('data-origin', originalOrigin);

            } catch (e) {
                logToTerminal('Error Decrypting Link: ' + e.message, 'error');
                alert('Invalid Link or Token Format!');
            }
        });
    }

    // Update Button Logic
    const updateLinkBtn = document.getElementById('updateLinkBtn');
    if (updateLinkBtn) {
        updateLinkBtn.addEventListener('click', () => {
            const currentId = updateLinkBtn.getAttribute('data-current-id');
            const base = updateLinkBtn.getAttribute('data-origin') || window.location.origin;
            
            const data = {
                ref: document.getElementById('edit_ref').value,
                passport: document.getElementById('edit_passport').value,
                name: document.getElementById('edit_name').value,
                father: document.getElementById('edit_father').value,
                village: document.getElementById('edit_village').value,
                po: document.getElementById('edit_po').value,
                district: document.getElementById('edit_district').value,
                place: document.getElementById('edit_place').value,
                issueDate: document.getElementById('edit_issueDate').value,
                address: document.getElementById('edit_address').value,
                code: "0000"
            };

            if (currentId) {
                // Update Existing DB Record
                saveToDB(currentId, data);
                
                // The link REMAINS THE SAME because it points to ref_id
                // We just re-generate it to show the user, but the URL itself (the ref_id part) is constant.
                // NOTE: We also update the token in the URL just in case, but if the system relies on DB, the ID is enough.
                const token = btoa(JSON.stringify(data));
                const link = `${base}/ords/f?p=500:50:::NO:RP:P50_TOKEN_ID:${token}&ref_id=${currentId}`;

                document.getElementById('editResultArea').innerHTML = `
                    <div style="background: rgba(0,255,127,0.1); padding: 1rem; border-radius: 5px; border: 1px solid #00ff7f;">
                        <p style="color: #00ff7f; margin-bottom: 5px; font-weight: bold;"><i class="fa-solid fa-check-circle"></i> Database Updated Successfully!</p>
                        <p style="color: #ccc; font-size: 0.9rem;">The existing link with ID <b>${currentId}</b> will now show this new information.</p>
                        <p style="margin-top: 10px; color: #aaa;">(Optional) Updated Full Link:</p>
                        <a href="${link}" target="_blank" style="color: #00ff7f; word-break: break-all;">${link}</a>
                    </div>
                `;
                logToTerminal(`Database Record ${currentId} UPDATED. Link content changed silently.`);
            } else {
                // No ID (was a raw token link), so must generate NEW link
                const uniqueId = 'ID_' + Date.now().toString(36);
                saveToDB(uniqueId, data);
                const token = btoa(JSON.stringify(data));
                const link = `${base}/ords/f?p=500:50:::NO:RP:P50_TOKEN_ID:${token}&ref_id=${uniqueId}`;
                
                document.getElementById('editResultArea').innerHTML = `
                    <div style="background: rgba(255,200,0,0.1); padding: 1rem; border-radius: 5px; border: 1px solid #ffcc00;">
                        <p style="color: #ffcc00; margin-bottom: 5px;">Link Converted to Database Record!</p>
                        <p style="color: #ccc;">This was an old link. A NEW Database-Synced link has been created.</p>
                        <a href="${link}" target="_blank" style="color: #ffcc00; word-break: break-all;">${link}</a>
                    </div>
                `;
                logToTerminal('Old Token Link converted to Database Record.');
            }
        });
    }

    const bulkBtn = document.getElementById('bulk_processBtn');
    if (bulkBtn) {
        bulkBtn.addEventListener('click', () => {
            const raw = (document.getElementById('bulk_input').value || '').split(/\n|\r/).map(s => s.trim()).filter(Boolean);
            if (!raw.length) return;
            const results = [];
            for (const url of raw) {
                try {
                    let data = null;
                    let currentId = null;
                    let originalOrigin = '';
                    if (url.includes('ref_id=')) {
                        currentId = url.split('ref_id=')[1].split('&')[0];
                        const d = getFromDB(currentId);
                        if (d) data = d;
                    }
                    if (!data) {
                        let token = '';
                        if (url.includes('P50_TOKEN_ID:')) token = url.split('P50_TOKEN_ID:')[1];
                        else if (url.includes('P50_TOKEN_ID=')) token = url.split('P50_TOKEN_ID=')[1];
                        else token = url;
                        token = token.split('&')[0].split('#')[0];
                        data = JSON.parse(atob(token));
                    }
                    try { originalOrigin = new URL(url).origin } catch (e) { originalOrigin = window.location.origin }
                    if (currentId) {
                        saveToDB(currentId, data);
                    } else {
                        currentId = 'ID_' + Date.now().toString(36) + Math.random().toString(36).slice(2,6);
                        saveToDB(currentId, data);
                    }
                    const token = btoa(JSON.stringify(data));
                    const link = `${originalOrigin}/ords/f?p=500:50:::NO:RP:P50_TOKEN_ID:${token}&ref_id=${currentId}`;
                    results.push(link);
                    logToTerminal(`Processed ${currentId}`);
                } catch (e) {
                    logToTerminal('Bulk process error: ' + e.message, 'error');
                }
            }
            const area = document.getElementById('bulkResultArea');
            if (area) {
                area.innerHTML = `
                    <div style="background: rgba(0,136,255,0.1); padding: 1rem; border-radius: 5px; border: 1px solid #0088ff;">
                        <p style="color: #ccc; margin-bottom: 8px;">Processed Links:</p>
                        ${results.map(l => `<div style="margin: 6px 0;"><a href="${l}" target="_blank" style="color: #66b3ff; word-break: break-all;">${l}</a></div>`).join('')}
                    </div>
                `;
            }
        });
    }

    // Initial Logs
    logToTerminal('Sovereign Guardian AI System Initialized...');
    logToTerminal('Connected to Server Node: VPS');
    logToTerminal('HTML Pages Manager: READY');
    logToTerminal('System Status: OPERATIONAL');

    const providerSel = document.getElementById('avatarProvider');
    const apiKeyInput = document.getElementById('avatarApiKey');
    const saveBtn = document.getElementById('saveAvatarApi');
    const testBtn = document.getElementById('testAvatarApi');
    const statusEl = document.getElementById('avatarStatus');
    const currentCfg = getAvatarCfg();
    if (providerSel && apiKeyInput) {
        providerSel.value = currentCfg.provider || 'heygen';
        apiKeyInput.value = currentCfg.key || '';
    }
    if (saveBtn) {
        saveBtn.addEventListener('click', () => {
            const cfg = { provider: providerSel.value, key: apiKeyInput.value.trim() };
            if (!cfg.key) { statusEl.textContent = 'API Key required'; return; }
            setAvatarCfg(cfg);
            statusEl.textContent = 'Saved';
        });
    }
    async function testHeyGen(key) {
        try {
            const r = await fetch('https://api.heygen.com/v1/avatars', { headers: { Authorization: 'Bearer ' + key } });
            return r.ok;
        } catch (e) { return false; }
    }
    async function testDID(key) {
        try {
            const r = await fetch('https://api.d-id.com/v1/avatars', { headers: { Authorization: 'Bearer ' + key } });
            return r.ok;
        } catch (e) { return false; }
    }
    if (testBtn) {
        testBtn.addEventListener('click', async () => {
            const cfg = getAvatarCfg();
            statusEl.textContent = 'Testing via secure proxy...';
            let ok = false;
            try {
                const r = await fetch(`/api/avatar/test?provider=${(cfg.provider||'heygen')}`);
                const j = await r.json();
                ok = !!j.ok;
                if (!ok && j.error && j.error.includes('Missing API key')) {
                    statusEl.textContent = 'Add environment variable in Pages: HEYGEN_API_KEY or DID_API_KEY';
                    return;
                }
            } catch (e) {}

            if (!ok) {
                statusEl.textContent = 'Proxy failed, testing direct API...';
                if (cfg.provider === 'did') ok = await testDID(cfg.key);
                else ok = await testHeyGen(cfg.key);
            }
            statusEl.textContent = ok ? 'API reachable' : 'Failed (check key or env variables)';
        });
    }
});

function logToTerminal(message, type = 'info') {
    const terminal = document.getElementById('terminalLogs');
    if (!terminal) return;
    const time = new Date().toLocaleTimeString();
    const color = type === 'error' ? '#ff0055' : type === 'warning' ? '#ffcc00' : '#00ff7f';
    
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="timestamp">[${time}]</span> <span style="color: ${color}">${message}</span>`;
    
    terminal.appendChild(entry);
    terminal.scrollTop = terminal.scrollHeight;
}
