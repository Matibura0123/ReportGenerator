// script.js の完全版 (ファイル添付リスト機能付き)

// DOM要素の取得
const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const reportDisplay = document.getElementById('report-display');
const charCount = document.getElementById('char-count');
const downloadButton = document.getElementById('download-button');
const uploadButton = document.getElementById('upload-button');
const fileInput = document.getElementById('file-input');
const attachedFilesContainer = document.getElementById('attached-files'); // 新規: ファイルチップコンテナ

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
fileInput.addEventListener('change', handleFileSelection);           // ファイル選択時の処理

// 初期状態
downloadButton.disabled = true;

// --- 関数定義: ファイル関連 ---

// ファイルが選択されたとき、または削除されたときにUIを更新する関数
function renderAttachedFiles() {
    const files = fileInput.files;
    
    // コンテナをクリア
    attachedFilesContainer.innerHTML = '';

    if (files.length > 0) {
        // ファイルがある場合、コンテナを表示
        attachedFilesContainer.style.display = 'flex';

        // 各ファイルに対してチップを作成
        Array.from(files).forEach((file, index) => {
            const chip = document.createElement('div');
            chip.className = 'file-chip';
            chip.setAttribute('data-index', index); 

            // ファイル名
            const nameSpan = document.createElement('span');
            nameSpan.className = 'file-chip-name';
            nameSpan.textContent = file.name;
            chip.appendChild(nameSpan);

            // 削除ボタン
            const removeButton = document.createElement('button');
            removeButton.className = 'remove-file-button';
            removeButton.innerHTML = '&times;'; // '×'記号
            
            // 削除ボタンのクリックイベント
            removeButton.addEventListener('click', () => removeFile(index));
            
            chip.appendChild(removeButton);
            attachedFilesContainer.appendChild(chip);
        });
        
        // チャットに通知
        const fileNames = Array.from(files).map(f => f.name).join(', ');
        displayMessage(`ファイルを添付しました: ${fileNames}`, 'user');
        
    } else {
        // ファイルがない場合、コンテナを非表示
        attachedFilesContainer.style.display = 'none';
    }
}

// ファイル選択時の処理
function handleFileSelection() {
    // 新しい選択内容に基づいてUIを再描画
    renderAttachedFiles();
}

// ファイルをリストから削除する関数
function removeFile(indexToRemove) {
    const files = Array.from(fileInput.files);
    
    // 指定されたインデックスのファイルを削除
    files.splice(indexToRemove, 1);
    
    // DataTransferオブジェクトを使用して、fileInput.filesを更新
    const dataTransfer = new DataTransfer();
    files.forEach(file => dataTransfer.items.add(file));
    fileInput.files = dataTransfer.files;

    // UIを再描画
    renderAttachedFiles();
}


// --- 関数定義: チャット・レポート機能 ---

function displayMessage(message, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add(`${sender}-message`);
    
    let displayContent = message;
    if (sender === 'ai' && displayContent.startsWith('AI: ')) {
        displayContent = displayContent.substring(4); 
    }

    const formattedMessage = displayContent.replace(/\n/g, '<br>');
    messageDiv.innerHTML = formattedMessage;
    chatHistory.appendChild(messageDiv);
    scrollToBottom();
    
    return messageDiv;
}

function scrollToBottom() {
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function displayReport(content) {
    // TODO: ここでMarkdownレンダリングを実装すると見栄えが向上
    reportDisplay.innerText = content;
    reportDisplay.scrollTop = 0; 
    downloadButton.disabled = false;
    updateCharCount(content.length);
}

function updateCharCount(count) {
    charCount.textContent = `${count} 文字`;
}

function handleDownloadReport() {
    const reportContent = reportDisplay.innerText;
    if (reportContent === '' || reportContent === 'ここにレポートの内容が表示されます') {
        alert('ダウンロードできるレポートがありません。');
        return;
    }

    const blob = new Blob([reportContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = 'レポート.txt'; 
    
    document.body.appendChild(a);
    a.click();
    
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}


// --- 関数定義: メイン送信処理 ---

async function handleSendMessage() {
    const message = userInput.value.trim();
    const attachedFiles = fileInput.files;

    if (message === '' && attachedFiles.length === 0) {
        return; 
    }
    
    // 1. ユーザーメッセージを画面に表示
    if (message !== '') {
        displayMessage(message, 'user');
    }
    
    // 2. 入力欄とファイルをクリア
    userInput.value = '';
    fileInput.value = ''; // ファイル入力欄をリセット
    renderAttachedFiles(); // ファイルチップ表示をクリア

    // 3. AIからの応答を待つダミー処理
    const loadingMessage = displayMessage('...AIがレポート作成の準備中です...', 'ai');
    
    // TODO: 送信ボタンを無効化する処理 (UX改善)

    try {
        // ★★★ TODO: ここをバックエンド（Python）への fetch() 処理に置き換える ★★★

        setTimeout(() => {
            const aiResponse = `AI: 「${message}」と添付ファイル（${attachedFiles.length}個）について承知しました。レポートを生成しました。`;
            const reportContent = `【入力内容とファイル】\n入力: ${message}\nファイル数: ${attachedFiles.length}\n\n## AI生成レポート\n\n- レポートの本文はここに表示されます。`;

            chatHistory.removeChild(loadingMessage);
            displayMessage(aiResponse, 'ai');
            displayReport(reportContent); 
        }, 3000);

    } catch (error) {
        console.error('通信エラー:', error);
        chatHistory.removeChild(loadingMessage);
        displayMessage('AI: エラーが発生しました。時間を置いて再度お試しください。', 'ai');
    }
    
    // TODO: 通信完了後、送信ボタンを有効化する処理 (UX改善)
}