import os
import json
import requests
from google import genai
from google.genai.errors import APIError
import logger_service 

# --- 設定 ---
# 警告: セキュリティ上の理由から、本番環境ではこの方法でAPIキーを直接記述しないでください。
# 環境変数よりもコード内記述を優先します。
# ---------------------------------------------------------------
# ↓↓↓ここにAPIキーを直接記述してください↓↓↓
HARDCODED_API_KEY = "AIzaSyAnWQR85rRFZzMxMnOwkmNgmNoi8YxM4rE"  # <-- ここを実際のAPIキーに置き換える
# ---------------------------------------------------------------

# 環境変数が設定されていればそれを使い、なければハードコードされたキーを使用
API_KEY = os.getenv('GEMINI_API_KEY') or HARDCODED_API_KEY
# API_URL は SDK 使用のため不要になりますが、ここでは互換性のため残します
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
MODEL_NAME = "gemini-2.5-flash-preview-05-20"
# ----------------

# ★ クライアントの初期化 (SDKを使用)
client = None
try:
    if API_KEY and API_KEY != 'YOUR_API_KEY_HERE':
        client = genai.Client(api_key=API_KEY)
except Exception as e:
    # APIキーが無効な場合やSDK初期化エラー
    client = None
    print(f"警告: Gemini Clientの初期化に失敗しました。詳細: {e}")

def process_report_request(prompt: str, previous_content: str = None, file_paths: list[str] = None, request_type: str = 'initial_generation') -> tuple[str, dict]:
    """
    Gemini APIを呼び出して、レポートを生成または精製し、ログ用メタデータを返します。

    Args:
        prompt (str): ユーザーからの指示。
        previous_content (str): 精製対象のレポート内容。
        file_paths (list[str]): アップロードされたローカルファイルのパスのリスト。
        request_type (str): リクエストの種類 ('initial_generation' または 'refinement').

    Returns:
        tuple[str, dict]: (生成または精製されたレポートテキスト、ログ用メタデータ辞書)
    """
    meta_data = {
        'model_name': MODEL_NAME,
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'safety_rating': None,
    }

    if not client:
        return "エラー: Gemini Clientが初期化されていません。APIキーが正しく設定されているか確認してください。", meta_data

    # ファイルのアップロードと参照の準備
    uploaded_files = []
    contents = []
    
    # --- 処理開始ログ ---
    logger_service.log_to_firestore('INFO', 
                                    'Report generation/refinement started', 
                                    request_type, 
                                    prompt, 
                                    previous_content_exists=bool(previous_content),
                                    files_attached=len(file_paths) if file_paths else 0)
    # --------------------
    
    if file_paths:
        for path in file_paths:
            try:
                # ファイルをアップロードし、Fileオブジェクトを取得
                file = client.files.upload(file=path)
                uploaded_files.append(file)
                # コンテンツリストにFileオブジェクトを追加
                contents.append(file)
            except Exception as e:
                # アップロード失敗時も後でファイルをクリーンアップするためリストに追加
                print(f"ファイル {path} のアップロードに失敗しました: {e}")
                # ログを記録して処理を終了
                error_msg = f"ファイルのアップロード中に問題が発生しました ({os.path.basename(path)})"
                logger_service.log_to_firestore('ERROR', 
                                                error_msg, 
                                                request_type, 
                                                prompt, 
                                                error_detail=str(e),
                                                **meta_data)
                return f"エラー: {error_msg}", meta_data
    
    # システム命令の設定
    if previous_content:
        # 精製モードの場合
        system_instruction_text = (
            "あなたはプロの編集者兼レポート作成者です。提供されたレポートの内容（PREVIOUS REPORT）を、"
            "新しい指示（REFINEMENT PROMPT）に従って完全に修正し、新しいレポート全文をMarkdown形式で出力してください。 "
            "出力は新しい修正後のレポートのみとし、指示やコメントは含めないでください。"
        )
        # ユーザープロンプト：過去の内容と新しい指示を結合
        user_query = (
            f"--- PREVIOUS REPORT ---\n{previous_content}\n\n"
            f"--- REFINEMENT PROMPT ---\n{prompt}\n\n"
            f"上記のレポートを精製（修正・加筆）してください。"
        )
    else:
        # 初回生成モードの場合
        system_instruction_text = (
            "あなたはプロのレポート作成者です。依頼されたテーマと提供されたファイル（もしあれば）に基づいて、読みやすく、構造化された、詳細なレポートを日本語で作成してください。見出しにはMarkdown記法を使用してください。"
        )
        user_query = prompt

    # コンテンツリストにテキストプロンプトを追加
    contents.append(user_query)

    # API呼び出し
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents, # ファイルとテキストプロンプトの両方を含む
            config={
                "system_instruction": system_instruction_text,
                "temperature": 0.7
            }
        )
        
        # 応答から生成されたテキストを抽出
        generated_text = response.text
        
        # --- メタデータの抽出と更新 ---
        usage_metadata = response.usage_metadata
        if usage_metadata:
            meta_data['input_tokens'] = usage_metadata.prompt_token_count
            meta_data['output_tokens'] = usage_metadata.candidates_token_count
            meta_data['total_tokens'] = usage_metadata.total_token_count
        
        # --- 成功ログ ---
        logger_service.log_to_firestore('INFO', 
                                        'API call successful', 
                                        request_type, 
                                        prompt, 
                                        response_content=generated_text,
                                        **meta_data)
        # ----------------
        
        return generated_text, meta_data

    except APIError as e:
        print(f"APIリクエストエラー (SDK): {e}")
        error_msg = f"Gemini API呼び出し中にエラーが発生しました: {e}"
        # --- エラーログ ---
        logger_service.log_to_firestore('ERROR', 
                                        'API call failed', 
                                        request_type, 
                                        prompt, 
                                        error_detail=str(e),
                                        **meta_data)
        # ------------------
        return f"エラー: {error_msg}", meta_data
        
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        error_msg = f"予期せぬエラーが発生しました: {e}"
        # --- エラーログ ---
        logger_service.log_to_firestore('ERROR', 
                                        'Unexpected error occurred', 
                                        request_type, 
                                        prompt, 
                                        error_detail=str(e),
                                        **meta_data)
        # ------------------
        return f"エラー: {error_msg}", meta_data
        
    finally:
        # ★ アップロードしたファイルをクリーンアップ (重要!)
        for file in uploaded_files:
            try:
                client.files.delete(name=file.name)
            except Exception as e:
                print(f"ファイル {file.name} の削除に失敗しました: {e}")


def get_api_key_status() -> str:
    """
    APIキーが設定されているかどうかのステータスを返します。
    """
    # HARDCODED_API_KEYをチェック
    if 'AIzaSy' in API_KEY and len(API_KEY) > 20: # 実際のキー形式をチェック
        return 'ok'
    return 'missing' # 安全のため、キー形式が不正な場合は 'missing' を返す


def get_model_name() -> str:
    """
    使用モデル名を取得します。
    """
    return MODEL_NAME
