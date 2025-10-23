from datetime import timedelta
import ai_service
from io import BytesIO
from typing import Optional
import os
import base64
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, make_response

# --- アプリケーション設定 ---
app = Flask(__name__)
# セッションを使用するためのシークレットキー。本番環境では安全な値に設定してください。
app.config['SECRET_KEY'] = 'your_very_secret_and_long_key_for_session'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# ★★★ セッションの有効期限を延長する設定（例: 30日間） ★★★
app.permanent_session_lifetime = timedelta(days=30)

# --- ユーティリティ関数 (ファイルパスではなくアップロードされたファイルオブジェクトを処理) ---

def get_base64_image_data_from_upload(file) -> Optional[str]:
    """
    アップロードされたファイルオブジェクトからBase64エンコードされたデータを取得します。
    """
    if file.filename == '':
        return None
    
    try:
        # ファイルの内容をメモリ上で読み込み、Base64エンコード
        image_data = file.read()
        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"[エラー] 画像ファイルの読み込み中にエラーが発生しました: {e}")
        return None

# --- Flask ルート定義 ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    レポートの生成と精製を処理するメインルート。
    GETリクエストに対してはHTMLを返し、POSTリクエストに対してはJSONを返します。
    """
    api_key_status = ai_service.get_api_key_status()
    if api_key_status == 'missing':
        # APIキーエラーはテンプレートに渡して表示（GET時のみ）
        if request.method == 'GET':
            return render_template('index.html', error_message="APIキーが設定されていません。ai_service.pyを確認してください。")
        else:
            return jsonify({'status': 'error', 'message': "APIキーが設定されていません。"}), 500

    # セッションから現在のレポート内容を取得
    current_report_content = session.get('report_content', None)
    
    # ★★★ 追加/変更: リクエスト開始時のセッション状態をログに出力 ★★★
    # セッションから現在のレポート内容を取得
    current_report_content = session.get('report_content', None)
    error_message = None
    if request.method == 'POST':
        if current_report_content:
            length = len(current_report_content)
            print(f"DEBUG: POST Request received. Session is ACTIVE. Content length: {length}.")
        else:
            print("DEBUG: POST Request received. Session is EMPTY (None/Reset).")
    
    if request.method == 'GET':
        # URLに ?clear=true が含まれていればセッションをクリア
        if 'clear' in request.args:
            session.pop('report_content', None)
            
            # クリア後、クエリパラメータを削除したページにリダイレクト
            # url_for('index') は '/' を指す
            return redirect(url_for('index')) # <--- ここでリダイレクトを確定させる
        
        # セッションクリア後の current_report_content を再取得（リダイレクトがなければ実行）
        current_report_content = session.get('report_content', None)
    
    # POSTリクエスト（AJAX/Fetch APIから）
    if request.method == 'POST':
        action = request.form.get('action')
        
        # 応答用の変数
        new_report_content = current_report_content
        
        # if current_report_content and action == 'generate':
        #     print("WARNING: Client sent 'generate' but session has content. Forcing 'refine'.")
        #     action = 'refine' 
        
        # # セッションにレポート内容がないにもかかわらず、クライアントが 'refine' を送ってきた場合は 'generate' に強制
        if not current_report_content and action == 'refine':
            print("WARNING: Client sent 'refine' but session is empty. Forcing 'generate'.")
            action = 'generate'
        
        # --- 1. 初回レポート生成 ---
        print(action)
        if action == 'generate':
            initial_prompt = request.form.get('initial_prompt')
            image_file = request.files.get('image_file')

            if not initial_prompt:
                error_message = "テーマを入力してください。"
            else:
                image_data_base64 = get_base64_image_data_from_upload(image_file) if image_file else None
                
                print(">>> レポートを生成中...")
                report_text, meta_data = ai_service.process_report_request( # <--- ここでAI応答を待つ
                    initial_prompt, 
                    previous_content=None, 
                    image_data_base64=image_data_base64
                )


                # ★修正点: report_textに対して処理を行う
                if report_text.startswith("エラー:"):
                    error_message = report_text
                    new_report_content = None # エラー時はレポート内容をクリア
                else:
                    new_report_content = report_text
                    
        # --- 2. レポート精製 ---
        elif action == 'refine' and current_report_content:
            refinement_prompt = request.form.get('initial_prompt')

            if not refinement_prompt:
                error_message = "ブラッシュアップの指示を入力してください。"
            else:
                print(">>> レポートを精製中...")

                # ★修正点: タプルを分解して refined_report_content と meta_data で受け取る
                refined_text, meta_data = ai_service.process_report_request(
                    refinement_prompt, 
                    previous_content=current_report_content,
                    image_data_base64=None 
                )

                # ★修正点: refined_textに対して処理を行う
                if not refined_text.startswith("エラー:"):
                    new_report_content = refined_text
                else:
                    error_message = refined_text
        
        # 処理後のレポート内容をセッションに保存
        session['report_content'] = new_report_content
        saved_content = session.get('report_content')
        if saved_content:
            # 成功した場合: 内容の長さと最初の50文字を出力
            print(f"DEBUG: Session 'report_content' saved successfully.")
            print(f"DEBUG: Length: {len(saved_content)} chars.")
            print(f"DEBUG: Start: {saved_content[:50].replace('\n', ' ')}...")
        else:
            # 失敗した場合: None または空として保存されたことを示す
            print(f"DEBUG: WARNING! Session 'report_content' is None or empty after saving.")

        # ★修正点: リダイレクトを削除し、JSONを返す
        response_data = {
            'status': 'success' if not error_message else 'error',
            'report_content': new_report_content,
            'message': error_message or 'レポートが正常に生成されました。',
            'meta_data': meta_data if 'meta_data' in locals() else None, # meta_dataがあれば含める
            'action_type': action
        }
        
        # エラー時はHTTP 400 Bad Requestとして返す
        status_code = 200 if response_data['status'] == 'success' else 400
        return jsonify(response_data), status_code


    # GETリクエストに対する応答
    return render_template(
        'index.html',
        report_content=current_report_content,
        error_message=error_message,
        model_name=ai_service.get_model_name()
    )

@app.route('/clear_session', methods=['POST'])
def clear_session():
    """
    セッションをクリアし、新しいレポート作成を開始するためのルート。
    """
    session.pop('report_content', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    # デバッグモードを有効にして実行 (本番環境では無効にしてください)
    app.run(debug=True)