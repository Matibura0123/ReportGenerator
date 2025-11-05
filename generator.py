import ai_service
from typing import Optional, Tuple, Dict, Any
import os
import base64
from flask import Flask, render_template, request, jsonify, redirect, url_for
from threading import Lock 
from io import BytesIO

# --- アプリケーション設定 ---
app = Flask(__name__)

# 【注意】Flaskセッションは使用しませんが、Flaskのデバッグモード警告を回避するために設定を残します。
app.config['SECRET_KEY'] = 'a_very_secret_and_fixed_key_for_dev_only_2'

# 【重要】認証済みのユーザーIDをシミュレート
# 実際にはFirebase Authなどから取得する必要があります。
DEFAULT_USER_ID = 'default_user_123' 

# --- データベースシミュレータ（実際はFirestoreに置き換える部分） ---
# キー: "userId:workspaceId" で、特定のユーザーの特定のデバイスでの作業を一意に識別します。
REPORT_DB_SIMULATOR: Dict[str, str] = {}
DB_LOCK = Lock() # スレッドセーフのためのロック

def get_report_from_db(user_id: str, workspace_id: str) -> Optional[str]:
    """
    【DB処理シミュレーション】Firestoreから特定のワークスペースIDのレポートを取得します。
    """
    key = f"{user_id}:{workspace_id}"
    with DB_LOCK:
        report = REPORT_DB_SIMULATOR.get(key)
        # 実際はFirestore: doc(db, 'artifacts', appId, 'users', userId, 'reports', workspaceId).get().data().get('content')
        print(f"[DB SIM] GET key='{key}'. Content exists: {report is not None}")
        return report

def save_report_to_db(user_id: str, workspace_id: str, content: str) -> None:
    """
    【DB処理シミュレーション】Firestoreにレポートを保存または更新します。
    """
    key = f"{user_id}:{workspace_id}"
    with DB_LOCK:
        REPORT_DB_SIMULATOR[key] = content
        # 実際はFirestore: setDoc(doc(db, 'artifacts', appId, 'users', userId, 'reports', workspaceId), {content: content, timestamp: serverTimestamp()})
        print(f"[DB SIM] SAVE key='{key}'. Content length: {len(content)}")

def delete_report_from_db(user_id: str, workspace_id: str) -> bool:
    """
    【DB処理シミュレーション】Firestoreから特定のワークスペースIDのレポートを削除します。
    """
    key = f"{user_id}:{workspace_id}"
    with DB_LOCK:
        if key in REPORT_DB_SIMULATOR:
            del REPORT_DB_SIMULATOR[key]
            print(f"[DB SIM] DELETED key='{key}'.")
            return True
        return False


# --- ユーティリティ関数 ---

def get_base64_image_data_from_upload(file) -> Optional[str]:
    """
    アップロードされた画像ファイルオブジェクトからBase64エンコードされたデータを取得します。
    """
    if not file or not file.filename:
        return None

    try:
        image_data = file.read()
        file.seek(0)
        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"[エラー] 画像ファイルの読み込み中にエラーが発生しました: {e}")
        return None

def get_uploaded_file_bytes(file) -> Optional[Tuple[bytes, str]]:
    """
    アップロードされたファイルオブジェクトからバイトデータとファイル名を返します。
    """
    if not file or not file.filename:
        return None
    
    try:
        file_bytes = file.read()
        file_name = file.filename
        file.seek(0)
        return file_bytes, file_name
    except Exception as e:
        print(f"[エラー] ファイルの読み込み中にエラーが発生しました: {e}")
        return None


# --- Flask ルート定義 ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    レポートの生成と精製を処理するメインルート。
    Flaskセッションの代わりに、クライアントから渡されるworkspace_idを使用します。
    """
    # 【重要】ユーザー認証ID
    user_id = DEFAULT_USER_ID 

    # ----------------------------------------------------
    # GETリクエストの場合 (初期表示)
    # ----------------------------------------------------
    if request.method == 'GET':
        api_key_status = ai_service.get_api_key_status()
        if api_key_status == 'missing':
            error_msg = "APIキーが設定されていません。ai_service.pyを確認してください。"
            return render_template('index.html', error_message=error_msg)
            
        # GET時には、DBからレポートは取得せず、クライアントサイドでworkspaceIdが設定されるのを待つ
        current_report_content = None

        return render_template(
            'index.html',
            report_content=current_report_content, # 初期値としてNoneを渡す
            error_message=None,
            model_name=ai_service.get_model_name()
        )
    
    # ----------------------------------------------------
    # POSTリクエスト（AJAX/Fetch APIから）
    # ----------------------------------------------------
    if request.method == 'POST':
        try:
            # 【重要】フォームデータからワークスペースIDを取得
            workspace_id = request.form.get('workspace_id')
            if not workspace_id:
                # workspace_idがない場合、データの取り違えを防ぐため処理を拒否
                return jsonify({'status': 'error', 'message': 'ワークスペースIDがリクエストに含まれていません。', 'report_content': None}), 400

            # データベースから現在のレポート内容を取得
            current_report_content = get_report_from_db(user_id, workspace_id)
            
            # レポート内容の有無に基づいて 'generate' または 'refine' を決定
            action = 'refine' if current_report_content else 'generate'
            
            error_message = None
            new_report_content = current_report_content
            meta_data = None 
            
            initial_prompt = request.form.get('initial_prompt')
            image_file = request.files.get('image_file') 
            book_file = request.files.get('book_file') 
            is_book_report_mode = request.form.get('mode') == 'book_report'

            # --- 1. レポート/感想文 生成 ---
            if action == 'generate':
                if not initial_prompt and not (is_book_report_mode and book_file and book_file.filename) and not (not is_book_report_mode and image_file and image_file.filename):
                    error_message = "テーマ、またはファイルを入力/アップロードしてください。"
                else:
                    image_data_base64 = None
                    uploaded_file_data = None
                    file_error = None

                    if is_book_report_mode and book_file and book_file.filename:
                        uploaded_file_data = get_uploaded_file_bytes(book_file)
                        if uploaded_file_data is None:
                            file_error = "書籍ファイルの読み込みに失敗しました。"

                    elif not is_book_report_mode and image_file and image_file.filename:
                        image_data_base64 = get_base64_image_data_from_upload(image_file)
                        if image_data_base64 is None:
                            file_error = "画像ファイルの読み込みに失敗しました。"
                    
                    if file_error:
                        error_message = file_error
                        
                    elif not error_message: 
                        print(f">>> {request.form.get('mode')}を生成中...")
                        
                        report_text, meta_data = ai_service.process_report_request( 
                            initial_prompt=initial_prompt, 
                            previous_content=None, 
                            image_data_base64=image_data_base64,
                            uploaded_file_data=uploaded_file_data, 
                            mode=request.form.get('mode') 
                        )

                        if report_text and report_text.startswith("エラー:"):
                            error_message = report_text.replace("エラー:", "").strip() 
                            new_report_content = None
                        else:
                            new_report_content = report_text
                        
            # --- 2. レポート/感想文 精製 ---
            elif action == 'refine' and current_report_content:
                refinement_prompt = request.form.get('initial_prompt')

                if not refinement_prompt:
                    error_message = "ブラッシュアップの指示を入力してください。"
                else:
                    print(f">>> {request.form.get('mode')}を精製中...")
                    
                    refined_text, meta_data = ai_service.process_report_request(
                        initial_prompt=refinement_prompt, 
                        previous_content=current_report_content,
                        image_data_base64=None,
                        uploaded_file_data=None, 
                        mode=request.form.get('mode')
                    )

                    if refined_text and not refined_text.startswith("エラー:"):
                        new_report_content = refined_text
                    else:
                        error_message = refined_text.replace("エラー:", "").strip()

            # --- 【重要】DBへの保存処理 (セッションへの保存から置き換え) ---
            if new_report_content:
                save_report_to_db(user_id, workspace_id, new_report_content)

            # JSONを返す
            response_data = {
                'status': 'success' if not error_message else 'error',
                'report_content': new_report_content,
                'message': error_message or ('感想文が正常に生成されました。' if is_book_report_mode else 'レポートが正常に生成されました。'),
                'meta_data': meta_data,
                'action_type': action
            }
            
            status_code = 200 if response_data['status'] == 'success' else 400
            return jsonify(response_data), status_code

        # 例外処理ブロック
        except Exception as e:
            print(f"[クリティカルエラー] POST処理中に予期せぬエラー: {type(e).__name__}: {e}")
            return jsonify({
                'status': 'error',
                'report_content': None, 
                'message': f"サーバー内部エラーが発生しました。ログを確認してください: {type(e).__name__}"
            }), 500


@app.route('/clear_session', methods=['POST'])
def clear_session():
    """
    【修正】DBのワークスペースIDデータを削除する処理に置き換え。
    """
    user_id = DEFAULT_USER_ID
    
    # クライアントから送信されたworkspace_idを取得
    data = request.get_json(silent=True)
    workspace_id = data.get('workspace_id') if data else None

    if workspace_id:
        if delete_report_from_db(user_id, workspace_id):
            return jsonify({'status': 'success', 'message': 'レポートを削除し、新規ワークスペースを開始します'}), 200
        else:
             # データがDBになかった場合でも成功として扱う
             return jsonify({'status': 'success', 'message': 'クリア対象のレポートはありませんでした'}), 200
    
    return jsonify({'status': 'error', 'message': 'ワークスペースIDがリクエストに含まれていません'}), 400

if __name__ == '__main__':
    app.run(debug=True)