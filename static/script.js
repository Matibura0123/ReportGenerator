// DOM要素の取得
const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const reportDisplay = document.getElementById('report-display');
const charCount = document.getElementById('char-count');
const downloadButton = document.getElementById('download-button');
const uploadButton = document.getElementById('upload-button');
const fileInput = document.getElementById('file-input');
const attachedFilesContainer = document.getElementById('attached-files'); // ファイルチップコンテナ
const chatArea = document.getElementById('chat-area'); // モード取得用

// --- 【重要】ワークスペースIDの管理 ---
const WORKSPACE_ID_KEY = 'report_workspace_id';
let workspaceId;

/**
 * ワークスペースIDを取得または新規生成します。
 */
function getOrCreateWorkspaceId() {
    let id = localStorage.getItem(WORKSPACE_ID_KEY);
    if (!id || id === 'null' || id === 'undefined') {
        // 新しいUUIDを生成 (簡易版)
        id = crypto.randomUUID(); 
        localStorage.setItem(WORKSPACE_ID_KEY, id);
        console.log(`[Workspace] New Workspace ID generated and saved: ${id}`);
    } else {
        console.log(`[Workspace] Existing Workspace ID loaded: ${id}`);
    }
    return id;
}

/**
 * ワークスペースをクリアし、新しいIDを生成します。
 */
function clearWorkspaceAndGenerateNewId() {
    localStorage.removeItem(WORKSPACE_ID_KEY);
    workspaceId = getOrCreateWorkspaceId();
    // サーバー側のDBからも古いデータを削除するAPIを呼び出す（後述）
    
    // UIを初期化
    displayReport('');
    // メッセージ履歴をクリア
    if (chatHistory) chatHistory.innerHTML = ''; 
    displayMessage("AI: 新しいレポート作成を開始します。テーマを入力してください。", 'ai');

    // サーバー側の古いレポートデータを削除
    clearServerReportData(workspaceId);
}

// ページロード時にワークスペースIDを初期化
workspaceId = getOrCreateWorkspaceId();


// DataTransferオブジェクトを使用して、fileInput.filesを管理する
let filesToUpload = new DataTransfer(); 

// ページロード時に既存のレポート内容に基づいてダウンロードボタンを初期化
if (reportDisplay) {
    const initialContent = reportDisplay.innerText.trim();
    const isInitialPlaceholder = initialContent === '' || initialContent === 'ここにレポートの内容が表示されます';

    downloadButton.disabled = isInitialPlaceholder;
    updateCharCount(isInitialPlaceholder ? 0 : initialContent.length);
} else {
    downloadButton.disabled = true;
    updateCharCount(0);
}

// --- イベントリスナーの設定 ---
sendButton.addEventListener('click', handleSendMessage);

// Enterキーで送信（Shift+Enterでは改行）
userInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault(); 
        handleSendMessage();
    }
});

downloadButton.addEventListener('click', handleDownloadReport);
uploadButton.addEventListener('click', () => { fileInput.click(); }); // ファイルボタン発火

// fileInputの変更イベントは、一旦選択内容をfilesToUploadに統合するために使用する
fileInput.addEventListener('change', handleFileSelection); 

// モード切り替えイベントの監視
document.querySelectorAll('input[name="creation_mode"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        handleModeChange(e.target.value);
    });
});

// 新しいレポート作成ボタン (UIに追加されていると仮定)
const newReportButton = document.getElementById('new-report-button');
if(newReportButton) {
    newReportButton.addEventListener('click', clearWorkspaceAndGenerateNewId);
} else {
    // 既存のUIにボタンがない場合、初期生成後にメッセージを表示
    setTimeout(() => {
        if (getReportContent() === '') {
            displayMessage("AI: レポート作成を開始します。テーマを入力してください。", 'ai');
            // ここで clearWorkspaceAndGenerateNewId() を呼ぶと、IDがリフレッシュされる
        }
    }, 100);
}


// 初期モード設定
const initialCheckedMode = document.querySelector('input[name="creation_mode"]:checked');
if (initialCheckedMode) {
    handleModeChange(initialCheckedMode.value);
}

// --- 関数定義: モード/ファイル関連 (変更なし) ---
// ... (handleModeChange, handleFileSelection, removeFile, renderAttachedFiles は元のコードを維持)

/**
 * 作成モードが変更されたときの処理
 * @param {string} mode 'general_report' または 'book_report'
 */
function handleModeChange(mode) {
    // chatArea (またはメインコンテナ) に現在のモードを設定
    if (chatArea) chatArea.setAttribute('data-mode', mode);
    
    // 既存のファイル選択状態をクリア（モードが異なるとファイルタイプが異なるため）
    filesToUpload = new DataTransfer();
    fileInput.value = '';
    renderAttachedFiles();
    
    // UIのヒントとfileInputのaccept属性を更新
    const fileHint = document.getElementById('file-hint');
    const reportFilename = document.getElementById('report-filename');
    const uploadText = document.getElementById('upload-text');
    
    // ★修正点1: 両モードで単一ファイル選択に統一
    fileInput.removeAttribute('multiple'); 

    if (mode === 'book_report') {
        fileInput.accept = '.pdf, .epub, .txt';
        if (fileHint) fileHint.textContent = '(PDF, EPUB, TXTファイルを1つ)';
        if (reportFilename) reportFilename.textContent = '感想文.md';
        if (uploadText) uploadText.textContent = '書籍ファイル添付';
    } else {
        // general_report
        fileInput.accept = 'image/*';
        // ★修正点2: ヒントも単一ファイルに修正
        if (fileHint) fileHint.textContent = '(画像ファイルを1つ)'; 
        if (reportFilename) reportFilename.textContent = 'レポート.md';
        if (uploadText) uploadText.textContent = '画像ファイル添付';
    }
}


// ファイル選択時の処理 (filesToUploadに追加/上書き)
function handleFileSelection() {
    const newFiles = fileInput.files;

    // ★修正点3: 両モードで最初の1ファイルのみを採用するロジックに統一
    // バックエンドが1ファイルのみを受け付けるため、UIとロジックを統一
    filesToUpload = new DataTransfer();
    if (newFiles.length > 0) {
        // 最初の1つのみを採用
        filesToUpload.items.add(newFiles[0]); 
    }
    
    // fileInput自体のFilesリストは操作しないため、空にする（DataTransferで管理）
    fileInput.value = ''; 
    renderAttachedFiles();
}


// ファイルをリストから削除する関数
function removeFile(indexToRemove) {
    const newFiles = new DataTransfer();
    Array.from(filesToUpload.files).forEach((file, i) => {
        if (i !== indexToRemove) {
            newFiles.items.add(file);
        }
    });
    filesToUpload = newFiles; // 更新
    renderAttachedFiles(); // UIを再描画
}


// ファイルが選択されたとき、または削除されたときにUIを更新する関数
function renderAttachedFiles() {
    const files = filesToUpload.files;
    
    // コンテナをクリア
    if (!attachedFilesContainer) return;

    attachedFilesContainer.innerHTML = '';

    if (files.length > 0) {
        attachedFilesContainer.style.display = 'flex';

        Array.from(files).forEach((file, index) => {
            const chip = document.createElement('div');
            chip.className = 'file-chip';
            chip.setAttribute('data-index', index); 

            const nameSpan = document.createElement('span');
            nameSpan.className = 'file-chip-name';
            nameSpan.textContent = file.name;
            chip.appendChild(nameSpan);

            const removeButton = document.createElement('button');
            removeButton.className = 'remove-file-button';
            removeButton.innerHTML = '&times;';
            // indexをキャプチャするためにクロージャを使用
            removeButton.addEventListener('click', (function(i) {
                return function(e) {
                    e.stopPropagation(); // ボタンクリックが親要素に伝播しないように
                    removeFile(i);
                };
            })(index));
            
            chip.appendChild(removeButton);
            attachedFilesContainer.appendChild(chip);
        });
        
    } else {
        attachedFilesContainer.style.display = 'none';
    }
}


// --- 関数定義: チャット・レポート機能 (変更なし) ---

function getReportContent() {
    return reportDisplay ? reportDisplay.innerText.trim() : '';
}

function displayReport(content) {
    if (reportDisplay) {
        const safeContent = content || '';
        
        // TODO: ここでMarkdownレンダリングを実装すると見栄えが向上 (例: marked.jsなどを使用)
        reportDisplay.innerText = safeContent;
        reportDisplay.scrollTop = 0; 
        
        // 空文字列の場合はダウンロードボタンを無効化
        downloadButton.disabled = (safeContent === ''); 
        
        updateCharCount(safeContent.length);
    }
}

function updateCharCount(count) {
    if (charCount) {
        charCount.textContent = `${count} 文字`;
    }
}

function displayMessage(message, sender) {
    if (!chatHistory) return null;

    const messageDiv = document.createElement('div');
    messageDiv.classList.add(`${sender}-message`);
    
    let displayContent = message;
    
    // AIからの応答をチャット履歴用に装飾
    if (sender === 'ai') {
        // エラーメッセージの装飾を解除
        displayContent = displayContent.replace(/^(エラー:|AI:)\s*/, '').trim();
        // 応答テキストが空でなければ 'AI: ' プレフィックスを付ける
        if (displayContent !== '') {
            displayContent = `AI: ${displayContent}`;
        }
    }
    
    const formattedMessage = displayContent.replace(/\n/g, '<br>');
    messageDiv.innerHTML = formattedMessage;
    chatHistory.appendChild(messageDiv);
    scrollToBottom();
    
    return messageDiv;
}

function scrollToBottom() {
    if (chatHistory) {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
}

function handleDownloadReport() {
    const reportContent = getReportContent();
    if (reportContent === '' || reportContent === 'ここにレポートの内容が表示されます') {
        console.error('ダウンロードできるレポートがありません。');
        return;
    }

    const currentMode = chatArea ? chatArea.getAttribute('data-mode') : 'general_report';
    const filename = currentMode === 'book_report' ? '感想文.md' : 'レポート.md';

    const blob = new Blob([reportContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = filename; 
    
    document.body.appendChild(a);
    a.click();
    
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// サーバー側の古いレポートデータを削除する関数
async function clearServerReportData(currentWorkspaceId) {
    try {
        await fetch('/clear_session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ workspace_id: currentWorkspaceId }),
            credentials: 'include'
        });
        // 成功しても失敗しても、ローカルのIDはクリア済みなので特に何もしない
    } catch (error) {
        console.error('サーバー側レポート削除時にエラーが発生しました:', error);
    }
}


// --- 関数定義: メイン送信処理 ---

async function handleSendMessage() {
    const message = userInput.value.trim();
    const files = filesToUpload.files;
    const currentMode = chatArea ? chatArea.getAttribute('data-mode') : 'general_report';
    const currentContent = getReportContent();

    if (message === '' && files.length === 0 && currentContent === '') {
        return;
    }
    
    // 初回生成時の必須チェック
    if (currentContent === '') {
        if (currentMode === 'book_report' && (files.length === 0 && message === '')) {
             displayMessage("AI: 読書感想文を作成するには、書籍ファイルを添付し、必要に応じてプロンプトを入力してください。", 'ai');
             return;
        }
        if (currentMode === 'general_report' && message === '' && files.length === 0) {
            displayMessage("AI: プロンプト（質問・指示）を入力するか、ファイルを添付してください。", 'ai');
            return;
        }
    }

    // 1. ユーザーメッセージを画面に表示
    const userActionType = currentContent === '' ? 'generate' : 'refine';
    displayMessage(message, 'user');

    // 2. 入力欄をクリア
    userInput.value = '';
    
    // 3. 送信ボタンの無効化（UX改善）
    sendButton.disabled = true;

    // 4. AIからの応答を待つローディングメッセージを表示
    const typeText = currentMode === 'book_report' ? '感想文' : 'レポート';
    const actionText = userActionType === 'generate' ? `${typeText}作成の準備中です` : `${typeText}精製の準備中です`;
    const loadingMessage = displayMessage(`AI: ...AIが${actionText}...`, 'ai');
    
    // 5. FormDataの準備
    const formData = new FormData();
    formData.append('initial_prompt', message); 
    formData.append('mode', currentMode); 
    
    // 【重要】ワークスペースIDを追加
    formData.append('workspace_id', workspaceId); 
    
    // ファイルを添付 (generator.pyに合わせてfiles[0]のみを送信)
    if (files.length > 0) {
        if (currentMode === 'book_report') {
            formData.append('book_file', files[0]); 
        } else {
            formData.append('image_file', files[0]); 
        }
    }
    
    // ★★★ タイムアウト処理 ★★★
    const timeoutDuration = 60000; // 60秒
    const controller = new AbortController();
    const signal = controller.signal;
    
    const timeoutId = setTimeout(() => {
        controller.abort(); 
    }, timeoutDuration);
    // ★★★ タイムアウト処理終了 ★★★

    try {
        const response = await fetch('/', {
            method: 'POST',
            body: formData,
            signal: signal ,
            credentials: 'include'
        });
        
        clearTimeout(timeoutId);

        // 応答がJSONであることを確認
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            const errorText = await response.text();
            throw new Error(`サーバーから予期しない応答形式が返されました (Content-Type: ${contentType}). HTMLが返されている可能性があります。`);
        }
        
        const responseJson = await response.json();

        // 6. ローディングメッセージを削除
        if (loadingMessage && chatHistory.contains(loadingMessage)) {
            chatHistory.removeChild(loadingMessage);
        }
        
        if (response.ok && responseJson.status === 'success') {
            const newContent = responseJson.report_content;
            const successMessage = responseJson.message;

            // レポート表示を更新
            displayReport(newContent);
            
            // チャット履歴にAIの応答を表示
            const responseAction = responseJson.action_type === 'generate' ? 'を生成しました' : 'を精製しました';
            displayMessage(`${typeText}${responseAction}。${successMessage}`, 'ai');
            
        } else {
            // エラー時の処理 
            const errorMessage = responseJson.message || '不明なエラーが発生しました。';
            displayMessage(`エラーが発生しました: ${errorMessage}`, 'ai');
            
            // レポート内容がエラーでクリアされた場合に対応
            if (responseJson.report_content === null) {
                displayReport(''); 
            }
        }
    
    } catch (error) {
        console.error('通信エラー:', error);
        
        clearTimeout(timeoutId); 
        if (loadingMessage && chatHistory.contains(loadingMessage)) {
            chatHistory.removeChild(loadingMessage);
        }

        if (error.name === 'AbortError') {
            displayMessage(`処理がタイムアウトしました。(${timeoutDuration/1000}秒)`, 'ai');
        } else {
            // その他の通信エラー。特に 'Unexpected token <' はここで捕捉されることが多い。
            const errorMessage = error.message.includes("HTMLが返されている可能性があります") 
                                 ? "サーバー内部でエラーが発生し、HTMLページが返されました。Flaskのログを確認してください。"
                                 : error.message;

            displayMessage(`処理中にエラーが発生しました: ${errorMessage}`, 'ai');
        }
        
    } finally {
        // 7. 通信が完了したら、ボタンを有効化
        sendButton.disabled = false;
        
        // 8. ファイル入力をクリア（成功・失敗に関わらず）
        filesToUpload = new DataTransfer(); 
        fileInput.value = ''; 
        renderAttachedFiles();
    }
}