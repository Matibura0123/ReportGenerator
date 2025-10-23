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
const attachedFilesContainer = document.getElementById('attached-files'); // ファイルチップコンテナ

// ページロード時に既存のレポート内容に基づいてダウンロードボタンを初期化
if (reportDisplay && reportDisplay.innerText.trim() !== '' && reportDisplay.innerText.trim() !== 'ここにレポートの内容が表示されます') {
    downloadButton.disabled = false;
    updateCharCount(reportDisplay.innerText.length);
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
fileInput.addEventListener('change', handleFileSelection);           // ファイル選択時の処理

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
        
        // チャットに通知（初回生成時のみ）
        if (getReportContent() === '') {
            const fileNames = Array.from(files).map(f => f.name).join(', ');
            displayMessage(`ファイルを添付しました: ${fileNames}`, 'system'); // systemメッセージとして表示
        }
        
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

function getReportContent() {
    return reportDisplay ? reportDisplay.innerText.trim() : '';
}

// ★ 修正箇所: displayReport
function displayReport(content) {
    if (reportDisplay) {
        // null/undefinedの場合は空文字列に変換し、安全に処理する
        const safeContent = content || '';
        
        // TODO: ここでMarkdownレンダリングを実装すると見栄えが向上
        reportDisplay.innerText = safeContent;
        reportDisplay.scrollTop = 0; 
        
        // 空文字列の場合はダウンロードボタンを無効化
        downloadButton.disabled = (safeContent === ''); 
        
        // safeContentに対して.lengthを呼び出す
        updateCharCount(safeContent.length);
    }
}
// ★ 修正箇所ここまで

function updateCharCount(count) {
    if (charCount) {
        charCount.textContent = `${count} 文字`;
    }
}

function displayMessage(message, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add(`${sender}-message`);
    
    let displayContent = message;
    
    // エラーメッセージの装飾を解除
    if (displayContent.startsWith("エラー:")) {
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

function handleDownloadReport() {
    const reportContent = getReportContent();
    if (reportContent === '' || reportContent === 'ここにレポートの内容が表示されます') {
        // alertの代わりにカスタムメッセージボックスを使用することが推奨されますが、ここでは簡略化
        console.error('ダウンロードできるレポートがありません。');
        return;
    }

    const blob = new Blob([reportContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = 'レポート.md'; // Markdown形式としてダウンロード
    
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
    const userActionType = getReportContent() === '' ? 'generate' : 'refine';
    displayMessage(message, 'user');

    // 2. 入力欄をクリア
    userInput.value = '';
    
    // 3. 送信ボタンの無効化（UX改善）
    sendButton.disabled = true;

    // 4. AIからの応答を待つローディングメッセージを表示
    const actionText = userActionType === 'generate' ? 'レポート作成の準備中です' : 'レポート精製の準備中です';
    const loadingMessage = displayMessage(`...AIが${actionText}...`, 'ai');
    
    // 5. FormDataの準備
    const formData = new FormData();
    formData.append('action', userActionType); // 初回生成 or 精製
    formData.append('initial_prompt', message); // 両方のケースでプロンプトとして利用
    
    // 初回生成の場合のみファイルを添付
    if (userActionType === 'generate' && attachedFiles.length > 0) {
        // 'image_file' は Flask の request.files.get('image_file') に対応
        // 複数ファイルに対応する場合、バックエンドのロジックを修正する必要があります。ここでは最初のファイルのみを送信。
        formData.append('image_file', attachedFiles[0]); 
    }
    
    // ★★★ タイムアウト処理の追記開始 ★★★
    const timeoutDuration = 60000; // 30秒
    const controller = new AbortController();
    const signal = controller.signal;
    
    // 指定時間後にリクエストを中止するためのタイマーを設定
    const timeoutId = setTimeout(() => {
        controller.abort(); // リクエストを中止
    }, timeoutDuration);
    // ★★★ タイムアウト処理の追記終了 ★★★

    try {
        const response = await fetch('/', {
            method: 'POST',
            body: formData,
            // ★ AbortControllerのsignalをfetchオプションに追加 ★
            signal: signal ,
            credentials: 'include'
        });
        
        // ★ 成功またはエラー処理前に、必ずタイマーを解除 ★
        clearTimeout(timeoutId);

        // 応答がJSONであることを確認
        if (response.status === 204 || response.headers.get('content-length') === '0') {
            // コンテンツがない場合はエラーとして扱う
            throw new Error('サーバーからの応答データがありません。');
        }
        
        const responseJson = await response.json();

        // 6. ローディングメッセージを削除
        chatHistory.removeChild(loadingMessage);
        
        if (response.ok && responseJson.status === 'success') {
            const newContent = responseJson.report_content;
            const successMessage = responseJson.message;

            // レポート表示を更新
            displayReport(newContent);
            
            // チャット履歴にAIの応答を表示
            const responseAction = responseJson.action_type === 'generate' ? 'レポートを生成しました' : 'レポートを精製しました';
            displayMessage(`AI: ${responseAction}。${successMessage}`, 'ai');
            
        } else {
            // エラー時の処理 
            const errorMessage = responseJson.message || '不明なエラーが発生しました。';
            displayMessage(`AI: ${errorMessage}`, 'ai');
            
            // レポート内容がエラーでクリアされた場合に対応
            if (responseJson.report_content === null) {
                displayReport(''); // 明示的に空文字列を渡し、表示をクリア
            }
        }
    
    } catch (error) {
        console.error('通信エラー:', error);
        
        // ★ エラーが発生した場合もタイマーを解除し、ローディングメッセージを削除 ★
        clearTimeout(timeoutId); 
        if (chatHistory.contains(loadingMessage)) {
            chatHistory.removeChild(loadingMessage);
        }

        // タイムアウトエラー（AbortError）の処理
        if (error.name === 'AbortError') {
            displayMessage(`AI: 処理がタイムアウトしました。`, 'ai');
        } else {
            // その他の通信エラー
            displayMessage(`AI: 処理中にエラーが発生しました: ${error.message}`, 'ai');
        }
        
    } finally {
        // 7. 通信が完了したら、ボタンを有効化
        sendButton.disabled = false;
        
        // 8. ファイル入力をクリア（成功・失敗に関わらず）
        fileInput.value = ''; 
        renderAttachedFiles();
    }
}
