# ファイル名: generator.py (Flaskアプリケーション本体として動作)

import ai_service # ai_service.py（AIコアロジック）をインポート
from io import BytesIO
from typing import Optional, Tuple
import os
import base64
from flask import Flask, render_template, request, session, jsonify, redirect, url_for

# --- アプリケーション設定 ---
app = Flask(__name__)
# 環境変数FLASK_SECRET_KEYがない場合はランダムなキーを使用
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# --- ユーティリティ関数 ---
def get_base64_image_data_from_upload(file) -> Optional[str]:
    # ... (変更なし) ...
    if not file or not file.filename: return None
    try:
        image_data = file.read()
        file.seek(0)
        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"[エラー] 画像ファイルの読み込み中にエラーが発生しました: {e}"); return None

def get_uploaded_file_bytes(file) -> Optional[Tuple[bytes, str]]:
    # ... (変更なし) ...
    if not file or not file.filename: return None
    try:
        file_bytes = file.read()
        file_name = file.filename
        file.seek(0)
        return file_bytes, file_name
    except Exception as e:
        print(f"[エラー] ファイルの読み込み中にエラーが発生しました: {e}"); return None


# --- Flask ルート定義 ---

@app.route('/', methods=['GET', 'POST'])
def index():
    api_key_status = ai_service.get_api_key_status()
    if api_key_status == 'missing':
        error_msg = "APIキーが設定されていません。ai_service.pyを確認してください。"
        if request.method == 'GET':
            return render_template('index.html', error_message=error_msg)
        else:
            return jsonify({'status': 'error', 'message': error_msg, 'report_content': None}), 500

    # ★修正点: 現在のモードを取得し、セッションキーを決定する★
    # GET/POST/セッションのいずれかから現在のモードを取得
    current_mode = request.form.get('mode') or request.args.get('mode') or session.get('mode', 'general_report')
    content_key = f'report_content_{current_mode}' # 例: 'report_content_book'
    
    current_report_content = session.get(content_key, None) # モードに応じたレポート内容を取得
    session['mode'] = current_mode # 現在のモードをセッションに保存
    error_message = None
    
    if request.method == 'GET':
        # GETリクエストの場合、モード切り替え時も履歴が保持される
        if 'clear' in request.args:
            # ★修正点: モードに関係なく、現在のモードの履歴のみをクリアする★
            session.pop(content_key, None)
            current_report_content = None
        
        return render_template(
            'index.html',
            report_content=current_report_content, # 取得した履歴を表示
            error_message=error_message,
            model_name=ai_service.get_model_name(),
            current_mode=current_mode # 現在のモードをHTMLに渡す
        )
    
    # POSTリクエスト（AJAX/Fetch APIから）
    if request.method == 'POST':
        try:
            # POSTリクエストのフォームから取得した 'mode' を利用
            action = 'refine' if current_report_content else 'generate'
            new_report_content = current_report_content 
            meta_data = None 
            
            initial_prompt = request.form.get('initial_prompt')
            image_file = request.files.get('image_file') 
            book_file = request.files.get('book_file')
            is_book_report_mode = current_mode == 'book_report' # セッションから取得したcurrent_modeで判定

            # --- 1. 入力チェックとファイル処理 ---
            # ... (中略：入力チェックロジックは変更なし) ...
            image_data_base64 = None
            uploaded_file_data = None
            file_error = None
            
            if action == 'generate':
                if not initial_prompt and not (is_book_report_mode and book_file and book_file.filename) and not (not is_book_report_mode and image_file and image_file.filename):
                    error_message = "テーマ、またはファイルを入力/アップロードしてください。"
                else:
                    if is_book_report_mode and book_file and book_file.filename:
                        uploaded_file_data = get_uploaded_file_bytes(book_file)
                        if uploaded_file_data is None: file_error = "書籍ファイルの読み込みに失敗しました。"
                    elif not is_book_report_mode and image_file and image_file.filename:
                        image_data_base64 = get_base64_image_data_from_upload(image_file)
                        if image_data_base64 is None: file_error = "画像ファイルの読み込みに失敗しました。"
            
            elif action == 'refine':
                 if not initial_prompt:
                    error_message = "ブラッシュアップの指示を入力してください。"
            
            if file_error:
                error_message = file_error

            # --- 2. AIコアロジック呼び出し ---
            if not error_message: 
                print(f">>> {current_mode}を{action}中...")

                report_text, ai_error, meta_data = ai_service.process_report_request( 
                    initial_prompt=initial_prompt, 
                    previous_content=current_report_content if action == 'refine' else None, 
                    image_data_base64=image_data_base64 if action == 'generate' else None,
                    uploaded_file_data=uploaded_file_data if action == 'generate' else None,
                    mode=current_mode # 現在のモードを渡す
                )
                
                if ai_error:
                    error_message = ai_error
                    if action == 'generate':
                        new_report_content = None # 生成エラー時はクリア
                    # 精製エラー時はcurrent_report_contentのまま維持
                else:
                    new_report_content = report_text 
            
            # ★修正点: モードに応じたセッションキーに保存★
            session[content_key] = new_report_content

            # JSONを返す
            if error_message:
                message = f"処理に失敗しました: {error_message}"
                status = 'error'
                status_code = 400
            else:
                status = 'success'
                status_code = 200
                if action == 'generate':
                    message = '感想文が正常に生成されました。' if is_book_report_mode else 'レポートが正常に生成されました。'
                else:
                    message = 'ご要望に基づいて修正が完了しました。レポート内容をご確認ください。' 
            
            response_data = {
                'status': status,
                'report_content': new_report_content, 
                'message': message,
                'meta_data': meta_data,
                'action_type': action
            }
            
            return jsonify(response_data), status_code

        except Exception as e:
            print(f"[クリティカルエラー] POSTリクエスト処理中に予期せぬエラーが発生しました: {type(e).__name__}: {e}")
            
            return jsonify({
                'status': 'error',
                'report_content': current_report_content, 
                'message': f"サーバー内部エラーが発生しました。ログを確認してください: {type(e).__name__}"
            }), 500


@app.route('/clear_session', methods=['POST'])
def clear_session():
    # ★修正点: 全セッションキーをクリアするのではなく、リセットする★
    # これにより、ユーザーが意図的にクリア操作をした場合のみ履歴が消える
    session.pop('report_content_general', None)
    session.pop('report_content_book', None)
    session['mode'] = 'general_report'
    
    return jsonify({'status': 'success', 'message': 'セッションをクリアしました'}), 200

if __name__ == '__main__':
    app.run(debug=True)