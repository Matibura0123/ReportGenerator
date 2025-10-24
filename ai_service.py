import os
import json
import requests
from google import genai
from google.genai.errors import APIError
import logger_service 
import base64
from io import BytesIO
from PIL import Image
from typing import Optional, Tuple, Dict, Any, List
from google.api_core.exceptions import DeadlineExceeded
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
logger_service.initialize_firebase_logger()

# ★ クライアントの初期化 (SDKを使用)
client = None
try:
    if API_KEY and API_KEY != 'YOUR_API_KEY_HERE':
        client = genai.Client(api_key=API_KEY)
except Exception as e:
    # APIキーが無効な場合やSDK初期化エラー
    client = None
    print(f"警告: Gemini Clientの初期化に失敗しました。詳細: {e}")

# def process_report_request(prompt: str, previous_content: str = None, file_paths: list[str] = None, request_type: str = 'initial_generation') -> tuple[str, dict]:

# process_report_requestの引数とロジックを修正
def process_report_request(
    initial_prompt: str, mode="general_report",
    previous_content: Optional[str] = None, 
    image_data_base64: Optional[str] = None
) -> Tuple[str, str,Dict[str, Any]]:
    print(previous_content)
    """
    Gemini APIを呼び出して、レポートを生成または精製し、ログ用メタデータを返します。
    ファイルパスの代わりにBase64エンコードされた画像を直接処理します。

    Args:
        initial_prompt (str): ユーザーからの指示（初回生成プロンプトまたは精製指示）。
        previous_content (str): 精製対象のレポート内容 (Noneの場合は初回生成)。
        image_data_base64 (str): Base64エンコードされた画像データ（接頭辞なし）。

    Returns:
        tuple[str, dict]: (生成または精製されたレポートテキスト、ログ用メタデータ辞書)
    """
    
    # ★ 内部で使用する変数の定義と初期化
    # 1. request_type: previous_contentの有無で判断
    request_type = 'refinement' if previous_content is not None else 'initial_generation'
    
    # 2. prompt: 処理で使用するプロンプトを initial_prompt に設定 (名前を統一)
    prompt = initial_prompt
    
    # 3. file_paths: Base64処理に移行するため、利用しない（またはBase64をパーツとして扱う）
    files_attached = bool(image_data_base64)

    meta_data: Dict[str, Any] = {
        'model_name': MODEL_NAME,
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'safety_rating': None,
    }

    if not client:
        return "エラー: Gemini Clientが初期化されていません。APIキーが正しく設定されているか確認してください。", meta_data

    # ファイルのアップロードと参照の準備
    uploaded_files: List[Any] = [] # Gemini Fileオブジェクトを格納
    contents: List[Any] = [] # APIリクエストに渡すコンテンツパーツ

    # --- 処理開始ログ ---
    # request_type, prompt, files_attached 変数を使用
    logger_service.log_to_firestore('INFO', 
                                    'Report generation/refinement started', 
                                    request_type, 
                                    prompt, 
                                    previous_content_exists=bool(previous_content),
                                    files_attached=files_attached)
    # --------------------
    
    # ★ Base64画像の処理ロジック
    if image_data_base64:
        try:
            # Base64デコード
            img_data = base64.b64decode(image_data_base64)
            img = Image.open(BytesIO(img_data))
            
            # 一時ファイルとして保存し、Gemini APIにアップロード
            # 注: クリーンアップが必要なため、一時ファイルを使用する
            temp_file_path = "temp_image.png"
            img.save(temp_file_path)

            file = client.files.upload(file=temp_file_path)
            uploaded_files.append(file)
            contents.append(file)
            
            # 一時ファイルを削除
            os.remove(temp_file_path)
            
        except Exception as e:
            error_msg = f"画像のBase64デコードまたはアップロードに失敗しました: {e}"
            logger_service.log_to_firestore('ERROR', 
                                            error_msg, 
                                            request_type, 
                                            prompt, 
                                            error_detail=str(e),
                                            **meta_data)
            return f"エラー: {error_msg}", meta_data
    
    # システム命令の設定
    if mode=="general_report":
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
                "あなたはプロのレポート作成者です。依頼されたテーマと提供された画像（もしあれば）に基づいて、読みやすく、構造化された、詳細なレポートを日本語で作成してください。見出しにはMarkdown記法を使用してください。"
            )
            user_query = prompt
    elif mode=="book_report":
        if previous_content:
            # 精製モードの場合
            if image_data_base64:
                system_instruction_text = (
                    "あなたはプロの編集者兼読書感想文作成者です。提供された読書感想文の内容（PREVIOUS REPORT）を、"
                    "新しい指示（REFINEMENT PROMPT）に従って完全に修正し、新しい読書感想文全文をMarkdown形式で出力してください。 "
                    "出力は新しい修正後のレポートのみとし、指示やコメントは含めないでください。"
                )
                # ユーザープロンプト：過去の内容と新しい指示を結合
                user_query = (
                    f"--- PREVIOUS REPORT ---\n{previous_content}\n\n"
                    f"--- REFINEMENT PROMPT ---\n{prompt}\n\n"
                    f"上記の読書感想文を精製（修正・加筆）してください。"
                )
            else:
                error_msg = "エラー: 参照元となる文章が提供されていません。"
                logger_service.log_to_firestore('ERROR', 
                                        error_msg, 
                                        request_type, 
                                        initial_prompt, 
                                        error_detail="Empty prompt provided.",
                                        **meta_data)
                return error_msg, meta_data
        else:
            # 初回生成モードの場合
            # 
            if image_data_base64:
                system_instruction_text = (
                    "あなたはプロの読書感想文作成者です。提供された画像（もしあれば）に基づいて、読みやすく、構造化された、詳細な読書感想文を日本語で作成してください。見出しにはMarkdown記法を使用してください。"
                )
                user_query = prompt
            else:
                error_msg = "エラー: 参照元となる文章が提供されていません。"
                logger_service.log_to_firestore('ERROR', 
                                        error_msg, 
                                        request_type, 
                                        initial_prompt, 
                                        error_detail="Empty prompt provided.",
                                        **meta_data)
                return error_msg, meta_data

    # コンテンツリストにテキストプロンプトを追加
    contents.append(user_query)

    # API呼び出し
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents, # ファイル（またはBase64画像）とテキストプロンプトの両方を含む
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
        print("成功")
        # ----------------
        
        return generated_text, meta_data
    except DeadlineExceeded:
        print("エラー: AIサービスからの応答がタイムアウトしました。")
        return "エラー: AIサービスからの応答がタイムアウトしました。", None

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
