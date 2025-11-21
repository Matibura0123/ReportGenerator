import ai_service
import logger_service
from firebase_admin import firestore
from typing import Optional, Tuple
import base64
from flask import Flask, render_template, request, jsonify
import requests # pip install requests が必要

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev_key_fixed_for_demo'

# --- DB関数 ---
def get_report_from_db(user_id: str, workspace_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    app_logsから最新レポートとモードを取得。Storage URLがあればDLする。
    戻り値: (content, mode)
    """
    if not logger_service.is_logger_enabled:
        return None, None
        
    try:
        db = logger_service.db
        # timestampの降順で最新1件を取得
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
            log_mode = data.get('mode')
            
            # Storage URLがある場合
            if 'report_url' in data and data['report_url']:
                try:
                    resp = requests.get(data['report_url'])
                    resp.raise_for_status()
                    return resp.text, log_mode
                except Exception as e:
                    print(f"[Error] Storage DL failed: {e}")
                    return data.get('response_summary'), log_mode
            else:
                return data.get('response_summary'), log_mode
        return None, None
    except Exception as e:
        print(f"[Error] DB Get failed: {e}")
        return None, None

def save_report_to_db(user_id: str, workspace_id: str, content: str, prompt: str, mode: str) -> None:
    if not logger_service.is_logger_enabled: return
    try:
        report_url = None
        # 空文字でなければStorageへ保存
        if content and len(content) > 0 and content != "　":
            report_url = logger_service.save_report_to_storage(content, user_id, workspace_id)
        
        logger_service.log_to_firestore(
            log_level='INFO',
            message='レポート保存/更新',
            user_prompt=prompt,
            response_content=content if not report_url else None,
            response_summary=report_url if report_url else None,
            user_id=user_id,
            workspace_id=workspace_id,
            mode=mode,
            report_url=report_url
        )
    except Exception as e:
        print(f"[Error] DB Save failed: {e}")

def delete_report_from_db(user_id, workspace_id):
    return True

# --- Utils ---
def get_uploaded_file_bytes(file):
    if not file or not file.filename: return None
    try:
        f_bytes = file.read(); file.seek(0)
        return f_bytes, file.filename
    except: return None

def get_base64_image_data_from_upload(file):
    if not file or not file.filename: return None
    try:
        img_data = file.read(); file.seek(0)
        return base64.b64encode(img_data).decode("utf-8")
    except: return None

# --- Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    user_id = 'tanii' 
    # GET時のデフォルトIDはPOSTでは使われないため、リセットには影響しません
    
    if request.method == 'GET':
        if ai_service.get_api_key_status() == 'missing':
            return render_template('index.html', error_message="APIキー未設定")
        
        # ★修正: GET時はDB操作をせず、単にHTMLを返すだけにする
        # JS側で新しいIDが生成されるため、サーバー側でのリセットログ書き込みは不要
        return render_template('index.html', report_content=None, model_name=ai_service.get_model_name())

    if request.method == 'POST':
        try:
            # JSから送られてきた動的なIDを使用
            ws_id = request.form.get('workspace_id', 'default_error_ws')
            current_mode = request.form.get('mode')
            
            # DBから直前の状態を取得
            fetched_content, last_mode = get_report_from_db(user_id, ws_id)
            
            # ★ モード変更検知ロジック ★
            # 1. 履歴がない -> 新規
            # 2. 前回のモードと今回のモードが違う -> コンテキストリセット(新規)
            if not fetched_content or fetched_content == "　":
                current_content = None
            elif last_mode != current_mode:
                print(f"[Info] Mode changed ({last_mode}->{current_mode}). Resetting context.")
                current_content = None # これにより ai_service に previous_content=None が渡る
            else:
                current_content = fetched_content

            action = 'generate' if current_content is None else 'refine'
            
            prompt = request.form.get('initial_prompt')
            img_file = request.files.get('image_file')
            book_file = request.files.get('book_file')
            
            new_content = current_content
            error_msg = None
            meta = None

            if action == 'generate':
                has_input = prompt or (img_file and img_file.filename) or (book_file and book_file.filename)
                if not has_input:
                    error_msg = "入力が必要です。"
                else:
                    img_b64 = get_base64_image_data_from_upload(img_file)
                    book_data = get_uploaded_file_bytes(book_file)
                    
                    # generateなので previous_content=None で呼ぶ
                    text, meta = ai_service.process_report_request(
                        prompt, user_id, ws_id,
                        mode=current_mode, 
                        image_data_base64=img_b64, 
                        uploaded_file_data=book_data,
                        previous_content=None 
                    )
                    if text.startswith("エラー:"): error_msg = text
                    else: new_content = text
            
            elif action == 'refine':
                if not prompt: error_msg = "指示が必要です。"
                else:
                    text, meta = ai_service.process_report_request(
                        prompt, user_id, ws_id,
                        mode=current_mode,
                        previous_content=current_content # 履歴を引き継ぐ
                    )
                    if text.startswith("エラー:"): error_msg = text
                    else: new_content = text

            if new_content and not error_msg:
                save_report_to_db(user_id, ws_id, new_content, prompt, current_mode)
            elif error_msg:
                logger_service.log_to_firestore('ERROR', '処理失敗', prompt, user_id, ws_id, error_detail=error_msg)

            return jsonify({
                'status': 'success' if not error_msg else 'error',
                'report_content': new_content,
                'message': error_msg or "完了",
                'action_type': action
            })

        except Exception as e:
            print(f"[Critical] {e}")
            logger_service.log_to_firestore('CRITICAL', '例外発生', request.form.get('initial_prompt'), user_id, ws_id, error_detail=str(e))
            return jsonify({'status': 'error', 'message': 'サーバーエラー'}), 500

@app.route('/clear_session', methods=['POST'])
def clear_session():
    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    logger_service.initialize_firebase_logger()
    app.run(debug=True)