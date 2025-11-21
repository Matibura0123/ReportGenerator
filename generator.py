import ai_service
import logger_service # ★Firebaseロガー
from firebase_admin import firestore
from typing import Optional, Tuple, Dict, Any
import os
import base64
from flask import Flask, render_template, request, jsonify
from threading import Lock
import requests # ★追加: StorageのURLからテキストを取得するため

# --- アプリケーション設定 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_and_fixed_key_for_dev_only_2'

# --- データベース関連関数 ---

def get_report_from_db(user_id: str, workspace_id: str) -> Optional[str]:
    """
    【修正版】app_logsから最新のレポートを取得します。
    StorageのURLがある場合はそこから本文をダウンロードし、
    なければFirestoreのresponse_summary(テキスト)を返します。
    """
    if not logger_service.is_logger_enabled:
        print("[DB] Logger disabled, cannot get report from logs.")
        return None
        
    try:
        db = logger_service.db
        
        # 最新のログを取得（response_summaryがあるもの）
        query = db.collection('app_logs') \
                  .where('user_id', '==', user_id) \
                  .where('workspace_id', '==', workspace_id) \
                  .where('response_summary', '!=', None) \
                  .order_by('timestamp', direction=firestore.Query.DESCENDING) \
                  .limit(1)
                  
        results = query.stream()
        first_doc = next(results, None)
        
        if first_doc:
            data = first_doc.to_dict()
            
            # ★ パターンA: StorageのURLが記録されている場合 (推奨)
            if 'report_url' in data and data['report_url']:
                report_url = data['report_url']
                print(f"[DB GET] Found Storage URL. Downloading content...")
                try:
                    # URLからテキストをダウンロード
                    response = requests.get(report_url)
                    response.raise_for_status() # エラーなら例外発生
                    content = response.text
                    print(f"[DB GET] Download successful. Length: {len(content)}")
                    return content
                except Exception as e:
                    print(f"[エラー] Storageからのダウンロードに失敗: {e}")
                    # ダウンロード失敗時は、Firestore内のサマリーで妥協するか、Noneを返す
                    return data.get('response_summary')

            # ★ パターンB: URLがなく、直接テキストが入っている場合 (旧仕様/短いテキスト)
            else:
                content = data.get('response_summary')
                print(f"[DB GET] Found text log. Content length: {len(content if content else 0)}")
                return content
        else:
            print(f"[DB GET] No log found for key='{user_id}:{workspace_id}'.")
            return None
            
    except Exception as e:
        print(f"[エラー] Firestoreからのログ取得中にエラー: {e}")
        return None

def save_report_to_db(user_id: str, workspace_id: str, content: str, prompt: str = "N/A", mode: str = "N/A") -> None:
    """
    【修正版】
    1. コンテンツをCloud Storageに保存
    2. 取得したURLをFirestoreのログに記録
    """
    if not logger_service.is_logger_enabled:
        print("[DB] Logger disabled, cannot save report to logs.")
        return

    try:
        report_url = None
        
        # ★ 1. Cloud Storageに保存を試みる
        if content and len(content) > 0:
            report_url = logger_service.save_report_to_storage(content, user_id, workspace_id)
        
        # ★ 2. ログ出力 (Storage URLを含める)
        logger_service.log_to_firestore(
            log_level='INFO',
            message='レポート保存/更新 (Storage)',
            user_prompt=prompt,
            
            # response_contentには生データを渡さない (Storage URLがあれば不要、なければ要約される)
            response_content=content if not report_url else None, 
            
            # URLがある場合はresponse_summaryの代わりにURLを入れておく(可読性のため)
            response_summary=report_url if report_url else None,
            
            user_id=user_id,
            workspace_id=workspace_id,
            mode=mode,
            
            # ★ カスタムフィールドとしてURLを保存
            report_url=report_url 
        )
        
        location = "Storage" if report_url else "Firestore(Truncated)"
        print(f"[DB SAVE] Report saved to {location}. Length: {len(content)}")

    except Exception as e:
        print(f"[エラー] DB保存プロセス中にエラー: {e}")


def delete_report_from_db(user_id: str, workspace_id: str) -> bool:
    """
    ログベースのため物理削除はしない。
    """
    print(f"[DB DELETE] Log-based system. Deletion skipped for key='{user_id}:{workspace_id}'.")
    return True


# --- ユーティリティ関数 (変更なし) ---

def get_base64_image_data_from_upload(file) -> Optional[str]:
    if not file or not file.filename:
        return None
    try:
        image_data = file.read()
        file.seek(0)
        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"[エラー] 画像ファイルの読み込み中にエラー: {e}")
        return None

def get_uploaded_file_bytes(file) -> Optional[Tuple[bytes, str]]:
    if not file or not file.filename:
        return None
    try:
        file_bytes = file.read()
        file_name = file.filename
        file.seek(0)
        return file_bytes, file_name
    except Exception as e:
        print(f"[エラー] ファイルの読み込み中にエラー: {e}")
        return None


# --- Flask ルート定義 ---

@app.route('/', methods=['GET', 'POST'])
def index():
    # テスト用デフォルトID (GET時など)
    default_user_id = 'tanii'
    default_workspace_id = 'taniiPC'

    # --- GETリクエスト ---
    if request.method == 'GET':
        api_key_status = ai_service.get_api_key_status()
        if api_key_status == 'missing':
            return render_template('index.html', error_message="APIキー未設定")
        
        # ページリセット時は空の状態を記録
        save_report_to_db(
            user_id=default_user_id, 
            workspace_id=default_workspace_id, 
            content="　",
            prompt="GET(PageReset)",
            mode='general_report'
        )

        return render_template(
            'index.html',
            report_content=None,
            error_message=None,
            model_name=ai_service.get_model_name()
        )
    
    # --- POSTリクエスト ---
    if request.method == 'POST':
        try:
            # クライアントからIDを取得 (なければデフォルト)
            workspace_id = request.form.get('workspace_id', default_workspace_id)
            user_id = default_user_id # ユーザーIDは今回は固定
            
            print(f"Processing for Workspace ID: '{workspace_id}'")

            # ★ DB(Storage)から現状を取得
            current_report_content = get_report_from_db(user_id, workspace_id)
            
            # アクション決定
            if current_report_content is None or current_report_content == "　":
                action = 'generate'
            else:
                action = 'refine'
            
            # 変数初期化
            error_message = None
            new_report_content = current_report_content
            meta_data = None 
            
            initial_prompt = request.form.get('initial_prompt')
            image_file = request.files.get('image_file') 
            book_file = request.files.get('book_file') 
            mode = request.form.get('mode')
            is_book_report_mode = (mode == 'book_report')

            # --- 生成/精製ロジック ---
            if action == 'generate':
                # 入力チェック
                has_prompt = bool(initial_prompt)
                has_book = bool(is_book_report_mode and book_file and book_file.filename)
                has_image = bool(not is_book_report_mode and image_file and image_file.filename)

                if not (has_prompt or has_book or has_image):
                    error_message = "テーマ、またはファイルを入力/アップロードしてください。"
                else:
                    # ファイル処理
                    image_data_base64 = None
                    uploaded_file_data = None
                    
                    if has_book:
                        uploaded_file_data = get_uploaded_file_bytes(book_file)
                        if not uploaded_file_data: error_message = "書籍ファイル読込失敗"
                    elif has_image:
                        image_data_base64 = get_base64_image_data_from_upload(image_file)
                        if not image_data_base64: error_message = "画像ファイル読込失敗"
                    
                    if not error_message:
                        print(f">>> {mode}を生成中...")
                        # ★修正箇所: user_id と workspace_id を引数に追加
                        report_text, meta_data = ai_service.process_report_request(
                            initial_prompt=initial_prompt,
                            user_id=user_id,             # 追加
                            workspace_id=workspace_id,   # 追加
                            previous_content=None,
                            image_data_base64=image_data_base64,
                            uploaded_file_data=uploaded_file_data,
                            mode=mode
                        )
                        if report_text.startswith("エラー:"):
                            error_message = report_text.replace("エラー:", "").strip()
                        else:
                            new_report_content = report_text

            elif action == 'refine':
                if not initial_prompt:
                    error_message = "ブラッシュアップの指示を入力してください。"
                else:
                    print(f">>> {mode}を精製中...")
                    # ★修正箇所: user_id と workspace_id を引数に追加
                    refined_text, meta_data = ai_service.process_report_request(
                        initial_prompt=initial_prompt,
                        user_id=user_id,             # 追加
                        workspace_id=workspace_id,   # 追加
                        previous_content=current_report_content, 
                        mode=mode
                    )
                    if refined_text.startswith("エラー:"):
                        error_message = refined_text.replace("エラー:", "").strip()
                    else:
                        new_report_content = refined_text

            # --- 結果の保存 ---
            if new_report_content and not error_message:
                # ★ Storageへの保存を含む新しい関数を呼ぶ
                save_report_to_db(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    content=new_report_content,
                    prompt=initial_prompt,
                    mode=mode
                )
            elif error_message:
                logger_service.log_to_firestore(
                    log_level='ERROR',
                    message=f"レポート {action} 失敗",
                    user_prompt=initial_prompt,
                    error_detail=error_message,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    mode=mode
                )

            # レスポンス
            response_data = {
                'status': 'success' if not error_message else 'error',
                'report_content': new_report_content,
                'message': error_message or ('処理が完了しました。'),
                'meta_data': meta_data,
                'action_type': action
            }
            status_code = 200 if response_data['status'] == 'success' else 400
            return jsonify(response_data), status_code

        except Exception as e:
            print(f"[Critical Error] {e}")
            logger_service.log_to_firestore(
                log_level='CRITICAL',
                message="POST処理中に例外",
                user_prompt=request.form.get('initial_prompt', 'N/A'),
                error_detail=str(e),
                user_id=user_id,
                workspace_id=workspace_id
            )
            return jsonify({'status': 'error', 'message': 'サーバー内部エラー'}), 500


@app.route('/clear_session', methods=['POST'])
def clear_session():
    try:
        # JSONボディからIDを取得
        data = request.get_json() or {}
        user_id = 'tanii'
        workspace_id = data.get('workspace_id', 'taniiPC')

        if delete_report_from_db(user_id, workspace_id):
            return jsonify({'status': 'success', 'message': 'セッションクリア'}), 200
        else:
            return jsonify({'status': 'success', 'message': '対象なし'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    logger_service.initialize_firebase_logger()
    app.run(debug=True)