const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const reportDisplay = document.getElementById('report-display');
const fileInput = document.getElementById('file-input');
const attachedFilesContainer = document.getElementById('attached-files');
const chatArea = document.getElementById('chat-area');

// --- ワークスペースID管理 ---
// ★修正: localStorageを使わず、ページ読み込みのたびに新規IDを発行してリセット状態にする
const workspaceId = crypto.randomUUID();
console.log(`New Session Started: ${workspaceId}`);

let filesToUpload = new DataTransfer();

// --- Event Listeners ---
sendButton.addEventListener('click', handleSendMessage);
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendMessage(); }
});
fileInput.addEventListener('change', handleFileSelection);
document.querySelectorAll('input[name="creation_mode"]').forEach(r => {
    r.addEventListener('change', (e) => handleModeChange(e.target.value));
});

// --- Logic ---
function handleModeChange(mode) {
    if (chatArea) chatArea.setAttribute('data-mode', mode);
    
    // ★修正: モードを変えたら、添付ファイルと「表示中のレポート」をクリアする（視覚的リセット）
    filesToUpload = new DataTransfer();
    fileInput.value = '';
    renderAttachedFiles();
    fileInput.removeAttribute('multiple');
    
    if (reportDisplay) {
        reportDisplay.innerText = ""; // 画面クリア
    }
    
    // モードに応じたファイル制限
    if (mode === 'book_report') {
        fileInput.accept = '.pdf, .epub, .txt';
    } else {
        fileInput.accept = 'image/*';
    }
}

function handleFileSelection() {
    if (fileInput.files.length > 0) {
        filesToUpload = new DataTransfer();
        filesToUpload.items.add(fileInput.files[0]);
    }
    fileInput.value = '';
    renderAttachedFiles();
}

function renderAttachedFiles() {
    attachedFilesContainer.innerHTML = '';
    if (filesToUpload.files.length > 0) {
        const f = filesToUpload.files[0];
        const chip = document.createElement('div');
        chip.className = 'file-chip';
        chip.textContent = f.name;
        const btn = document.createElement('button');
        btn.textContent = '×';
        btn.onclick = () => { filesToUpload = new DataTransfer(); renderAttachedFiles(); };
        chip.appendChild(btn);
        attachedFilesContainer.appendChild(chip);
    }
}

function displayMessage(msg, sender) {
    const div = document.createElement('div');
    div.className = `${sender}-message`;
    div.innerText = sender === 'ai' ? `AI: ${msg}` : msg;
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return div;
}

async function handleSendMessage() {
    const msg = userInput.value.trim();
    const files = filesToUpload.files;
    const mode = chatArea ? chatArea.getAttribute('data-mode') : 'general_report';
    
    if (!msg && files.length === 0) return;

    displayMessage(msg, 'user');
    userInput.value = '';
    sendButton.disabled = true;
    const loading = displayMessage("...考え中...", 'ai');

    const formData = new FormData();
    formData.append('initial_prompt', msg);
    formData.append('mode', mode);
    formData.append('workspace_id', workspaceId);
    if (files.length > 0) {
        formData.append(mode === 'book_report' ? 'book_file' : 'image_file', files[0]);
    }

    try {
        const res = await fetch('/', { method: 'POST', body: formData });
        const json = await res.json();
        
        chatHistory.removeChild(loading);
        
        if (json.status === 'success') {
            if (reportDisplay) reportDisplay.innerText = json.report_content;
            displayMessage(json.message, 'ai');
        } else {
            displayMessage(`エラー: ${json.message}`, 'ai');
        }
    } catch (e) {
        chatHistory.removeChild(loading);
        displayMessage(`通信エラー: ${e.message}`, 'ai');
    } finally {
        sendButton.disabled = false;
        filesToUpload = new DataTransfer();
        renderAttachedFiles();
    }
}

// Init
const initialMode = document.querySelector('input[name="creation_mode"]:checked');
if (initialMode) {
    // 初期ロード時は画面クリアを行わないよう、属性セットだけ行う簡易処理
    if (chatArea) chatArea.setAttribute('data-mode', initialMode.value);
}