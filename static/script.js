// DOM要素の取得
const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const reportDisplay = document.getElementById('report-display');
const charCount = document.getElementById('char-count');
const downloadButton = document.getElementById('download-button');
const uploadButton = document.getElementById('upload-button');
const fileInput = document.getElementById('file-input');
const attachedFilesContainer = document.getElementById('attached-files'); 
const chatArea = document.getElementById('chat-area'); 

// DataTransferオブジェクトを使用して、fileInput.filesを管理する
let filesToUpload = new DataTransfer(); 

// --- 初期化処理 ---
document.addEventListener('DOMContentLoaded', () => {
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
    
    // 初期モード設定を適用
    const initialCheckedMode = document.querySelector('input[name="creation_mode"]:checked');
    if (initialCheckedMode) {
        handleModeChange(initialCheckedMode.value, true); // true: 初期ロード
    }
});


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
uploadButton.addEventListener('click', () => { fileInput.click(); }); 

fileInput.addEventListener('change', handleFileSelection); 

// モード切り替えイベントの監視
document.querySelectorAll('input[name="creation_mode"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        handleModeChange(e.target.value);
    });
});

// --- 関数定義: モード/ファイル関連 ---

/**
 * 作成モードが変更されたときの処理
 * @param {string} mode 'general_report' または 'book_report'
 * @param {boolean} isInitialLoad ページロード時かどうか
 */
function handleModeChange(mode, isInitialLoad = false) {
    if (chatArea) chatArea.setAttribute('data-mode', mode);
    
    // 既存のファイル選択状態をクリア
    filesToUpload = new DataTransfer();
    fileInput.value = '';
    renderAttachedFiles();
    
    // チャット履歴のクリアと初期メッセージ表示
    if (!isInitialLoad) {
        chatHistory.innerHTML = ''; 
    }
    
    const fileHint = document.getElementById('file-hint');
    const reportFilename = document.getElementById('report-filename');
    const initialMessageDiv = document.createElement('div');
    initialMessageDiv.className = 'ai-message';

    fileInput.removeAttribute('multiple'); 

    if (mode === 'book_report') {
        fileInput.accept = '.pdf, .epub, .txt';
        if (fileHint) fileHint.textContent = '(PDF, EPUB, TXTファイルを1つ)';
        if (reportFilename) reportFilename.textContent = '感想文.md';
        initialMessageDiv.innerHTML = `読書感想文モードです。書籍をアップロードし、感想文の要件を指示してください。`;
    } else {
        fileInput.accept = 'image/*';
        if (fileHint) fileHint.textContent = '(画像ファイルを1つ)'; 
        if (reportFilename) reportFilename.textContent = 'レポート.md';
        initialMessageDiv.innerHTML = `レポート作成モードです。テーマや指示を入力し、必要に応じて画像を添付してください。`;
    }
    
    // 初期ロード時またはモード変更時にメッセージを追加
    if (isInitialLoad || chatHistory.children.length === 0 || !isInitialLoad) {
        chatHistory.appendChild(initialMessageDiv);
        scrollToBottom();
    }
}


// ファイル選択時の処理 (最初の1ファイルのみを採用)
function handleFileSelection() {
    const newFiles = fileInput.files;

    filesToUpload = new DataTransfer();
    if (newFiles.length > 0) {
        filesToUpload.items.add(newFiles[0]); 
    }
    
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
    filesToUpload = newFiles; 
    renderAttachedFiles(); 
}


// ファイルが選択されたとき、または削除されたときにUIを更新する関数
function renderAttachedFiles() {
    const files = filesToUpload.files;
    
    if (!attachedFilesContainer) return;

    attachedFilesContainer.innerHTML = '';

    if (files.length > 0) {
        attachedFilesContainer.style.display = 'flex';

        Array.from(files).forEach((file, index) => {
            const chip = document.createElement('div');
            chip.className = 'file-chip';
            
            const nameSpan = document.createElement('span');
            nameSpan.className = 'file-chip-name';
            nameSpan.textContent = file.name;
            chip.appendChild(nameSpan);

            const removeButton = document.createElement('button');
            removeButton.className = 'remove-file-button';
            removeButton.innerHTML = '&times;';
            removeButton.addEventListener('click', (e) => {
                e.stopPropagation(); 
                removeFile(index); // ファイルを削除
            });
            
            chip.appendChild(removeButton);
            attachedFilesContainer.appendChild(chip);
        });
        
    } else {
        attachedFilesContainer.style.display = 'none';
    }
}


// --- 関数定義: チャット・レポート機能 ---

function getReportContent() {
    return reportDisplay ? reportDisplay.innerText.trim() : '';
}

function displayReport(content) {
    if (reportDisplay) {
        const safeContent = content || '';
        
        // TODO: ここでMarkdownレンダリングを実装すると見栄えが向上 (例: marked.jsなどを使用)
        reportDisplay.innerText = safeContent;
        reportDisplay.scrollTop = 0; 
        
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
    
    if (sender === 'ai') {
        displayContent = displayContent.replace(/^(AI:|処理に失敗しました:)\s*/, '').trim();
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

    // MIMEタイプを text/plain;charset=utf-8 に維持 (互換性のため)
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


// --- 関数定義: メイン送信処理 ---

async function handleSendMessage() {
    const message = userInput.value.trim();
    const files = filesToUpload.files;
    const currentMode = chatArea ? chatArea.getAttribute('data-mode') : 'general_report';
    const currentContent = getReportContent();
    const isBookReportMode = currentMode === 'book_report';

    if (message === '' && files.length === 0 && currentContent === '') {
        return;
    }
    
    // 初回生成時の必須チェック
    if (currentContent === '' && message === '' && files.length === 0) {
        const requiredMsg = isBookReportMode 
            ? "AI: 読書感想文を作成するには、書籍ファイルを添付し、必要に応じてプロンプトを入力してください。"
            : "AI: プロンプト（質問・指示）を入力するか、ファイルを添付してください。";
        displayMessage(requiredMsg, 'ai');
        return;
    }


    // 1. ユーザーメッセージを画面に表示
    displayMessage(message, 'user');

    // 2. UIの無効化（UX改善）
    userInput.value = '';
    sendButton.disabled = true;
    userInput.disabled = true; // 入力欄を無効化

    // 3. AIからの応答を待つローディングメッセージを表示
    const action = currentContent === '' ? 'generate' : 'refine';
    const typeText = isBookReportMode ? '感想文' : 'レポート';
    const actionText = action === 'generate' ? `${typeText}作成の準備中です` : `${typeText}精製の準備中です`;
    const loadingMessage = displayMessage(`AI: ...AIが${actionText}...`, 'ai');
    
    // 4. FormDataの準備
    const formData = new FormData();
    formData.append('initial_prompt', message); 
    formData.append('mode', currentMode); 
    
    // ファイルを添付 (generator.pyに合わせてfiles[0]のみを送信)
    if (files.length > 0) {
        const fileKey = isBookReportMode ? 'book_file' : 'image_file';
        formData.append(fileKey, files[0]); 
    }
    
    // 5. API呼び出しとタイムアウト処理
    const timeoutDuration = 60000; // 60秒
    const controller = new AbortController();
    const signal = controller.signal;
    
    const timeoutId = setTimeout(() => {
        controller.abort(); 
    }, timeoutDuration);

    try {
        const response = await fetch('/', {
            method: 'POST',
            body: formData,
            signal: signal ,
            credentials: 'include'
        });
        
        clearTimeout(timeoutId);

        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            const errorText = await response.text();
            throw new Error(`サーバーから予期しない応答形式が返されました (Content-Type: ${contentType}).`);
        }
        
        const responseJson = await response.json();

        // 6. ローディングメッセージを削除
        if (loadingMessage && chatHistory.contains(loadingMessage)) {
            chatHistory.removeChild(loadingMessage);
        }
        
        if (responseJson.status === 'success') {
            const newContent = responseJson.report_content;
            const successMessage = responseJson.message;

            // レポート表示を更新
            displayReport(newContent);
            
            // チャット履歴にAIの応答を表示
            displayMessage(successMessage, 'ai');
            
        } else {
            // エラー時の処理 
            const errorMessage = responseJson.message || '不明なエラーが発生しました。';
            displayMessage(errorMessage, 'ai');
            
            // レポート内容がエラーでクリアされた場合に対応
            if (responseJson.report_content === null) {
                displayReport('エラーによりレポート内容はリセットされました。'); 
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
            const errorMessage = error.message.includes("HTMLが返されている可能性があります") 
                                 ? "サーバー内部でエラーが発生し、HTMLページが返されました。ログを確認してください。"
                                 : error.message;

            displayMessage(`処理中にエラーが発生しました: ${errorMessage}`, 'ai');
        }
        
    } finally {
        // 7. 通信が完了したら、ボタンと入力欄を有効化
        sendButton.disabled = false;
        userInput.disabled = false;
        
        // 8. ファイル入力をクリア（成功・失敗に関わらず）
        filesToUpload = new DataTransfer(); 
        fileInput.value = ''; 
        renderAttachedFiles();
    }
}