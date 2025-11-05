import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import datetime
import os
import sys
from typing import Optional

# --- 設定 ---
CREDENTIAL_PATH = os.environ.get('FIREBASE_CREDENTIALS_PATH', 'repo-gen.json')
# ---------------------------------------------------------------

db = None
is_logger_enabled = False

def initialize_firebase_logger():
    """
    Firebase Admin SDKを初期化し、Firestoreクライアントを準備する。
    初期化に失敗した場合、ログ機能は無効になる。
    """
    global db, is_logger_enabled
    if is_logger_enabled:
        return True

    # スクリプトファイルからの相対パスを確実に解決
    absolute_credential_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CREDENTIAL_PATH)

    if not os.path.exists(absolute_credential_path):
        print(f"\n[警告] Firebaseサービスアカウントキー '{absolute_credential_path}' が見つかりません。ログ機能は無効です。")
        is_logger_enabled = False
        return False

    try:
        # Firebaseプロジェクト名が設定されていない場合、デフォルトのアプリ名で初期化
        if not firebase_admin._apps:
            # 絶対パスを使用して認証
            cred = credentials.Certificate(absolute_credential_path)
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        is_logger_enabled = True
        print("\n[設定] Firebase Firestoreロガーが有効になりました。")
        return True
    except Exception as e:
        print(f"\n[エラー] Firebase初期化中にエラーが発生しました: {e}")
        is_logger_enabled = False
        return False

def log_to_firestore(
    log_level: str, 
    message: str, 
    user_prompt: str, 
    # 【追加】ユーザー認識情報 (必須)
    user_id: str, 
    # 【追加】デバイス/ワークスペース認識情報 (必須)
    workspace_id: str,
    response_content: Optional[str] = None, 
    error_detail: Optional[str] = None, 
    **kwargs
):
    """
    構造化されたログデータをFirestoreの 'app_logs' コレクションに書き込む。
    ユーザーIDとワークスペースIDを含める。
    """
    if not is_logger_enabled:
        return

    # 応答内容が長すぎる場合、最初の500文字に切り詰めてログのサイズを抑える
    response_summary = response_content[:500] + "..." if response_content and len(response_content) > 500 else response_content

    log_data = {
        'timestamp': datetime.datetime.now(datetime.timezone.utc),
        'level': log_level,
        'message': message,
        # --- 認識情報 ---
        'user_id': user_id, 
        'workspace_id': workspace_id,
        # ----------------
        'user_prompt': user_prompt,
        'response_summary': response_summary,
        'error_detail': error_detail,
        **kwargs 
    }
    
    try:
        # 'app_logs' コレクションにドキュメントを追加
        db.collection('app_logs').add(log_data)
        # print(f"ログをFirestoreに書き込みました (Level: {log_level}, User: {user_id})") # デバッグ用
    except Exception as e:
        # ログ書き込みエラーはアプリの主要なロジックを止めない
        print(f"警告: ログをFirestoreに書き込めませんでした: {e}")