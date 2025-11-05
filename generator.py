import ai_service
import logger_service # ★Firebaseロガーをインポート
from firebase_admin import firestore # ★Firestoreクエリのためにインポート
from typing import Optional, Tuple, Dict, Any
import os
import base64
from flask import Flask, render_template, request, jsonify, redirect, url_for
from threading import Lock 
from io import BytesIO

# --- アプリケーション設定 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_and_fixed_key_for_dev_only_2'

# --- データベースシミュレータ（delete_report_from_db のみで使用） ---
# ※ getとsaveはFirestoreロジックに置き換えられました。
REPORT_DB_SIMULATOR: Dict[str, str] = {}
DB_LOCK = Lock()

def get_report_from_db(user_id: str, workspace_id: str) -> Optional[str]:
    """
    【Firestore変更】app_logsから最新の有効なレポート内容を取得します。
    """
    if not logger_service.is_logger_enabled:
        print("[DB] Logger disabled, cannot get report from logs.")
        return None
        
    try:
        db = logger_service.db
        
        # ユーザーの指示通りのクエリ
        query = db.collection('app_logs') \
                  .where('user_id', '==', user_id) \
                  .where('workspace_id', '==', workspace_id) \
                  .where('response_summary', '!=', None) \
                  .order_by('timestamp', direction=firestore.Query.DESCENDING) \
                  .limit(1)
                  
        results = query.stream()
        
        # 最初のドキュメントを取得
        first_doc = next(results, None)
        
        if first_doc:
            content = first_doc.to_dict().get('response_summary')
            print(f"[DB GET] Found log for key='{user_id}:{workspace_id}'. Content length: {len(content if content else 0)}")
            return content
        else:
            print(f"[DB GET] No log found for key='{user_id}:{workspace_id}'.")
            return None
            
    except Exception as e:
        print(f"[エラー] Firestoreからのログ取得中にエラー: {e}")
        return None

def save_report_to_db(user_id: str, workspace_id: str, content: str, prompt: str = "N/A", mode: str = "N/A") -> None:
    """
    【Firestore変更】処理結果をapp_logsに記録します。
    """
    if not logger_service.is_logger_enabled:
        print("[DB] Logger disabled, cannot save report to logs.")
        return

    try:
        logger_service.log_to_firestore(
            log_level='INFO',
            message='レポート保存/更新',
            user_prompt=prompt,
            response_content=content, # response_summaryはロガー内部で処理される
            user_id=user_id,
            workspace_id=workspace_id,
            mode=mode
        )
        print(f"[DB SAVE] Logged report for key='{user_id}:{workspace_id}'. Content length: {len(content)}")
    except Exception as e:
        print(f"[エラー] Firestoreへのログ保存中にエラー: {e}")


def delete_report_from_db(user_id: str, workspace_id: str) -> bool:
    """
    【Firestore変更】ログは削除しないため、この操作は常に成功を返します。
    クライアントが新しいIDを生成できるようにします。
    """
    print(f"[DB DELETE] Log-based system. Deletion skipped for key='{user_id}:{workspace_id}'.")
    return True


# --- ユーティリティ関数 (変更なし) ---

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
    """
    
    # ----------------------------------------------------
    # GETリクエストの場合 (初期表示)
    # ----------------------------------------------------
    if request.method == 'GET':
        # ★ご要望通り、GETの時は前回のデータを参照しない
        api_key_status = ai_service.get_api_key_status()
        if api_key_status == 'missing':
            error_msg = "APIキーが設定されていません。ai_service.pyを確認してください。"
            return render_template('index.html', error_message=error_msg)
            
        return render_template(
            'index.html',
            report_content=None, # 初期値としてNoneを渡す
            error_message=None,
            model_name=ai_service.get_model_name()
        )
    
    # ----------------------------------------------------
    # POSTリクエスト（AJAX/Fetch APIから）
    # ----------------------------------------------------
    if request.method == 'POST':
        
        # ★ご要望に基づき、ユーザーIDとワークスペースIDをハードコード
        user_id = 'tanii'
        workspace_id = 'taniiPC'

        try:
            # フォームから渡されるworkspace_idは使用しない (ログ出力用には取得)
            workspace_id_from_form = request.form.get('workspace_id')
            print(f"Processing for Hardcoded IDs: User='{user_id}', Workspace='{workspace_id}' (Form ID ignored: '{workspace_id_from_form}')")

            # ★Firestoreのログから現在のレポート内容を取得
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
                    # (ファイル処理ロジック ... 変更なし)
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

            # --- ★【重要】Firestoreログへの保存処理 ---
            if new_report_content and not error_message:
                save_report_to_db(
                    user_id=user_id, 
                    workspace_id=workspace_id, 
                    content=new_report_content,
                    prompt=initial_prompt, # ログ用にプロンプトを渡す
                    mode=request.form.get('mode') # ログ用にモードを渡す
                )
            elif error_message:
                 # ★エラーが発生した場合もログに残す
                logger_service.log_to_firestore(
                    log_level='ERROR',
                    message=f"レポート {action} 失敗",
                    user_prompt=initial_prompt,
                    error_detail=error_message,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    mode=request.form.get('mode')
                )


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
            # ★例外エラーもログに残す
            logger_service.log_to_firestore(
                log_level='CRITICAL',
                message="POST処理中に予期せぬ例外",
                user_prompt=request.form.get('initial_prompt', 'N/A'),
                error_detail=str(e),
                user_id=user_id,
                workspace_id=workspace_id,
                mode=request.form.get('mode', 'N/A')
            )
            return jsonify({
                'status': 'error',
                'report_content': None, 
                'message': f"サーバー内部エラーが発生しました。ログを確認してください: {type(e).__name__}"
            }), 500


@app.route('/clear_session', methods=['POST'])
def clear_session():
    """
    DBのワークスペースIDデータを削除する処理（シミュレーション）。
    """
    # ★ハードコードされたIDを使用
    user_id = 'tanii'
    workspace_id = 'taniiPC' # クライアントから送られてきたIDは無視
    
    # ログは削除しない (delete_report_from_db が True を返す)
    if delete_report_from_db(user_id, workspace_id):
        return jsonify({'status': 'success', 'message': 'レポートを削除し、新規ワークスペースを開始します'}), 200
    else:
         return jsonify({'status': 'success', 'message': 'クリア対象のレポートはありませんでした'}), 200
    

if __name__ == '__main__':
    # ★Firebaseロガーを初期化
    logger_service.initialize_logger_service()
    app.run(debug=True)