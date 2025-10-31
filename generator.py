# ファイル名: generator.py (Flaskアプリケーション本体として動作)

# ai_service.py（AIコアロジック）をインポート
import ai_service 
from io import BytesIO
from typing import Optional, Tuple
import os
import base64
from flask import Flask, render_template, request, session, jsonify, redirect, url_for
# logger_service は外部ファイルとして存在するものと想定します
# import logger_service 

# --- アプリケーション設定 ---
app = Flask(__name__)
# 【重要】本番環境では、os.environなどから安全に取得し、外部から設定してください。
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# --- ユーティリティ関数 ---
def get_base64_image_data_from_upload(file) -> Optional[str]:
    """アップロードされた画像ファイルオブジェクトからBase64エンコードされたデータを取得"""
    if not file or not file.filename: return None
    try:
        image_data = file.read()
        file.seek(0)
        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"[エラー] 画像ファイルの読み込み中にエラーが発生しました: {e}"); return None

def get_uploaded_file_bytes(file) -> Optional[Tuple[bytes, str]]:
    """アップロードされたファイルオブジェクトからバイトデータとファイル名を返します。"""
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

    current_report_content = session.get('report_content', None)
    error_message = None
    
    if request.method == 'GET':
        if 'clear' in request.args:
            session.pop('report_content', None)
            current_report_content = None
            
        return render_template(
            'index.html',
            report_content=current_report_content,
            error_message=error_message,
            model_name=ai_service.get_model_name()
        )
    
    # POSTリクエスト（AJAX/Fetch APIから）
    if request.method == 'POST':
        try:
            # action = 'refine' or 'generate'
            action = 'refine' if current_report_content else 'generate'
            new_report_content = current_report_content # エラー時に維持するため、初期値は現在の内容
            meta_data = None 
            
            initial_prompt = request.form.get('initial_prompt')
            image_file = request.files.get('image_file') 
            book_file = request.files.get('book_file')
            is_book_report_mode = request.form.get('mode') == 'book_report'

            # --- 1. 入力チェックとファイル処理 ---
            image_data_base64 = None
            uploaded_file_data = None
            file_error = None
            
            if action == 'generate':
                if not initial_prompt and not (is_book_report_mode and book_file and book_file.filename) and not (not is_book_report_mode and image_file and image_file.filename):
                    error_message = "テーマ、またはファイルを入力/アップロードしてください。"
                else:
                    # ファイル処理（generate時のみ実行）
                    if is_book_report_mode and book_file and book_file.filename:
                        uploaded_file_data = get_uploaded_file_bytes(book_file)
                        if uploaded_file_data is None: file_error = "書籍ファイルの読み込みに失敗しました。"
                    elif not is_book_report_mode and image_file and image_file.filename:
                        image_data_base64 = get_base64_image_data_from_upload(image_file)
                        if image_data_base64 is None: file_error = "画像ファイルの読み込みに失敗しました。"
            
            # ブラッシュアップの指示チェック（refine時のみ）
            elif action == 'refine':
                 if not initial_prompt:
                    error_message = "ブラッシュアップの指示を入力してください。"
            
            # ファイル処理でエラーがあった場合
            if file_error:
                error_message = file_error

            # --- 2. AIコアロジック呼び出し（エラーがない場合のみ） ---
            if not error_message: 
                print(f">>> {request.form.get('mode')}を{action}中...")

                # ai_service.process_report_requestを呼び出し
                # (report_text, ai_error, meta_data) を受け取る
                report_text, ai_error, meta_data = ai_service.process_report_request( 
                    initial_prompt=initial_prompt, 
                    previous_content=current_report_content if action == 'refine' else None, 
                    image_data_base64=image_data_base64 if action == 'generate' else None,
                    uploaded_file_data=uploaded_file_data if action == 'generate' else None,
                    mode=request.form.get('mode') 
                )
                
                # ai_error の有無で判定
                if ai_error:
                    error_message = ai_error
                    # 生成エラー時: new_report_content = None (レポートをクリア)
                    if action == 'generate':
                        new_report_content = None
                    # 精製エラー時: new_report_content は current_report_content のまま維持される
                else:
                    new_report_content = report_text # 成功時は新しいレポート内容で上書き
            
            # 処理後のレポート内容をセッションに保存
            session['report_content'] = new_report_content

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
                    # 精製時の成功メッセージ
                    message = 'ご要望に基づいて修正が完了しました。レポート内容をご確認ください。' 
            
            response_data = {
                'status': status,
                'report_content': new_report_content, 
                'message': message,
                'meta_data': meta_data,
                'action_type': action
            }
            
            return jsonify(response_data), status_code

        # 例外処理ブロック
        except Exception as e:
            print(f"[クリティカルエラー] POSTリクエスト処理中に予期せぬエラーが発生しました: {type(e).__name__}: {e}")
            
            return jsonify({
                'status': 'error',
                'report_content': current_report_content, 
                'message': f"サーバー内部エラーが発生しました。ログを確認してください: {type(e).__name__}"
            }), 500


@app.route('/clear_session', methods=['POST'])
def clear_session():
    session.pop('report_content', None)
    return jsonify({'status': 'success', 'message': 'セッションをクリアしました'}), 200

if __name__ == '__main__':
    # Flaskアプリ起動時に logger_service の初期化を一度だけ実行することが推奨されます。
    # logger_service.initialize_firebase_logger() 
    app.run(debug=True)