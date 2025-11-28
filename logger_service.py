from typing import Optional
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin import storage # Storage機能
import datetime
import os
import sys
import json # JSONのパース用にインポートを追加

# PyInstaller関連の関数はそのまま残します (ローカル実行時の互換性のため)
def resource_path(relative_path):
    """
    PyInstallerでバンドルされた環境で、リソースファイルの絶対パスを取得する
    """
    try:
        # PyInstallerがリソースを格納する一時フォルダのパス
        base_path = sys._MEIPASS
    except Exception:
        # スクリプトとして実行されている場合 (開発環境)
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- 設定 ---
# ★【重要】GCPコンソールで作成した「実際のバケット名」に書き換えてください
# 例: "tanii-report-gen-files"
YOUR_BUCKET_NAME = "repo-gen-storage" 
# ローカルファイルパス (Renderでは使用されない)
json_file_path = resource_path('static/repo-gen.json') 

# 環境変数 (Render Secret Files または Environment Variables で設定するキー名)
SECRET_ENV_KEY = 'FIREBASE_CREDENTIALS_JSON'
env_value = os.environ.get(SECRET_ENV_KEY)
# ---------------------------------------------------------------
#確認用
print(f"環境変数の値: {env_value}")

db = None
is_logger_enabled = False

def initialize_firebase_logger():
    """
    Firebase Admin SDKを初期化し、FirestoreおよびStorageクライアントを準備する。
    Render環境では環境変数から、ローカル環境ではファイルから認証情報を取得する。
    """
    global db, is_logger_enabled
    if is_logger_enabled:
        return True
    
    # 1. Renderの環境変数からJSON文字列を取得
    secret_json_str = os.environ.get(SECRET_ENV_KEY)
    
    if secret_json_str:
        # 認証情報をJSON文字列から読み込む (Renderでのデプロイ環境)
        try:
            cred_json = json.loads(secret_json_str)
            cred = credentials.Certificate(cred_json)
            print(f"\n[設定] Firebase認証情報: 環境変数 '{SECRET_ENV_KEY}' から読み込みました。")
        except Exception as e:
            print(f"\n[エラー] 環境変数から認証情報JSONをパース中にエラーが発生しました: {e}")
            return False
    else:
        # 2. 環境変数がなければ、ローカルファイルから認証情報を読み込む (ローカル開発/PyInstaller環境)
        absolute_credential_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), json_file_path)

        if not os.path.exists(absolute_credential_path):
            print(f"\n[警告] Firebaseサービスアカウントキー '{absolute_credential_path}' が見つかりません。ログ機能は無効です。")
            is_logger_enabled = False
            return False
        
        try:
            cred = credentials.Certificate(absolute_credential_path)
            print(f"\n[設定] Firebase認証情報: ローカルファイル '{json_file_path}' から読み込みました。")
        except Exception as e:
            print(f"\n[エラー] ローカルファイルからの認証情報読み込み中にエラーが発生しました: {e}")
            return False

    # 3. Firebaseを初期化
    try:
        if not firebase_admin._apps:
            # Storageバケットを設定に追加
            firebase_admin.initialize_app(cred, {
                'storageBucket': YOUR_BUCKET_NAME
            })
        
        db = firestore.client()
        is_logger_enabled = True
        print(f"[設定] Firebase Firestoreロガー有効 (Bucket: {YOUR_BUCKET_NAME})")
        return True
    except Exception as e:
        print(f"\n[エラー] Firebase初期化中にエラーが発生しました: {e}")
        is_logger_enabled = False
        return False

def save_report_to_storage(content: str, user_id: str, workspace_id: str) -> Optional[str]:
    """
    AIが生成したテキストコンテンツをCloud Storageにアップロードし、署名付きURLを返します。
    """
    if not is_logger_enabled:
        print("[Storage] ロガーが無効なため、Storageに保存できません。")
        return None
        
    try:
        bucket = storage.bucket()
        
        # 保存パス: reports/user_id/workspace_id_timestamp.txt
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        file_path = f"reports/{user_id}/{workspace_id}_{timestamp_str}.txt"

        blob = bucket.blob(file_path)
        blob.upload_from_string(
            content, 
            content_type='text/plain; charset=utf-8'
        )
        
        # 有効期限付きの署名付きURLを生成 (最大7日間)
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(days=7), # 7日に設定
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
    user_id: str, 
    workspace_id: str,
    response_content: Optional[str] = None, 
    error_detail: Optional[str] = None, 
    **kwargs
):
    """
    構造化されたログデータをFirestoreの 'app_logs' コレクションに書き込む。
    """
    if not is_logger_enabled:
        return

    # 長すぎるテキストは要約 (Storage URLがある場合はそちらが優先保存されるため短くなる)
    response_summary = response_content[:500] + "..." if response_content and len(response_content) > 500 else response_content

    log_data = {
        'timestamp': datetime.datetime.now(datetime.timezone.utc),
        'level': log_level,
        'message': message,
        'user_id': user_id, 
        'workspace_id': workspace_id,
        'user_prompt': user_prompt,
        'response_summary': response_summary,
        'error_detail': error_detail,
        **kwargs 
    }
    
    try:
        db.collection('app_logs').add(log_data)
    except Exception as e:
        print(f"警告: ログをFirestoreに書き込めませんでした: {e}")


