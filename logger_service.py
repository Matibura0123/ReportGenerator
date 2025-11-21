import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin import storage  # ★追加: Storage機能
import datetime
import os
import sys
from typing import Optional

# --- 設定 ---
# ★ GCPで作成したバケット名 (例: "tanii-report-gen-files")
YOUR_BUCKET_NAME = "repo-gen-storage" 

# サービスアカウントキーのパス
CREDENTIAL_PATH = os.environ.get('FIREBASE_CREDENTIALS_PATH', 'repo-gen.json')
# ---------------------------------------------------------------

db = None
is_logger_enabled = False

def initialize_firebase_logger():
    """
    Firebase Admin SDKを初期化し、FirestoreおよびStorageクライアントを準備する。
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
        # Firebaseプロジェクト名が設定されていない場合、初期化
        if not firebase_admin._apps:
            cred = credentials.Certificate(absolute_credential_path)
            # ★変更: storageBucket を設定に追加
            firebase_admin.initialize_app(cred, {
                'storageBucket': YOUR_BUCKET_NAME
            })
        
        db = firestore.client()
        is_logger_enabled = True
        print("\n[設定] Firebase FirestoreロガーおよびStorageが有効になりました。")
        return True
    except Exception as e:
        print(f"\n[エラー] Firebase初期化中にエラーが発生しました: {e}")
        is_logger_enabled = False
        return False

def save_report_to_storage(content: str, user_id: str, workspace_id: str) -> Optional[str]:
    """
    【新規追加】
    AIが生成したテキストコンテンツをCloud Storageにファイルとしてアップロードし、
    アクセス可能なURLを返します。
    """
    if not is_logger_enabled:
        print("[Storage] ロガーが無効なため、Storageに保存できません。")
        return None
        
    try:
        # 1. バケツを取得 (initialize_appで設定済み)
        bucket = storage.bucket()
        
        # 2. 保存するファイルパスを決定
        # 例: reports/tanii/taniiPC_20251121093000.txt
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        file_path = f"reports/{user_id}/{workspace_id}_{timestamp_str}.txt"

        # 3. Blob作成とアップロード
        blob = bucket.blob(file_path)
        blob.upload_from_string(
            content, 
            content_type='text/plain; charset=utf-8'
        )
        
        # 4. 有効期限付きの署名付きURLを生成 (例: 365日間有効)
        # ※ make_public() は権限エラーになりやすいため、署名付きURLが安全です
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(days=7),
            method="GET"
        )
        
        return url

    except Exception as e:
        print(f"[エラー] Storageへのアップロード中にエラー: {e}")
        return None

def log_to_firestore(
    log_level: str, 
    message: str, 
    user_prompt: str, 
    # ユーザー認識情報 (必須)
    user_id: str, 
    # デバイス/ワークスペース認識情報 (必須)
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
    # (Storage URLが渡された場合は短いのでそのまま保存されます)
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
    except Exception as e:
        # ログ書き込みエラーはアプリの主要なロジックを止めない
        print(f"警告: ログをFirestoreに書き込めませんでした: {e}")