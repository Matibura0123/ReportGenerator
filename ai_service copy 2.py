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
# ---------------------------------------------------------------
# ↓↓↓ここにAPIキーを直接記述してください↓↓↓
HARDCODED_API_KEY = "AIzaSyAnWQR85rRFZzMxMnOwkmNgmNoi8YxM4rE"
# ---------------------------------------------------------------

# 環境変数が設定されていればそれを使い、なければハードコードされたキーを使用
API_KEY = os.getenv('GEMINI_API_KEY') or HARDCODED_API_KEY
MODEL_NAME = "gemini-2.5-flash"

# ロガー初期化
logger_service.initialize_firebase_logger()

# ★ クライアントの初期化 (SDKを使用)
client = None
client_status = 'missing'
try:
    client = genai.Client(api_key=API_KEY)
    client_status = 'ok'
except Exception as e:
    client = None
    client_status = 'error'
    print(f"致命的な警告: Gemini Clientの初期化に失敗しました。詳細: {e}")


def process_report_request(
    initial_prompt: str,
    mode="general_report",
    previous_content: Optional[str] = None,
    image_data_base64: Optional[str] = None,
    uploaded_file_data: Optional[Tuple[bytes, str]] = None
) -> Tuple[str, Dict[str, Any]]:

    request_type = 'refinement' if previous_content is not None else 'initial_generation'
    prompt = initial_prompt

    meta_data: Dict[str, Any] = {
        'model_name': MODEL_NAME,
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'safety_rating': None,
        'request_type': request_type,
    }

    if not client:
        return "エラー: Gemini Clientが初期化されていません。APIキーが正しく設定されているか確認してください。", meta_data

    contents: List[Any] = []
    full_text_content = ""

    # --- Base64画像の処理 ---
    if image_data_base64:
        try:
            img_data = base64.b64decode(image_data_base64)
            img = Image.open(BytesIO(img_data))
            contents.append(img)
        except Exception as e:
            error_msg = f"画像のBase64デコードまたは処理に失敗しました: {e}"
            logger_service.log_to_firestore('ERROR', error_msg, request_type, prompt, error_detail=str(e), **meta_data)
            return f"エラー: {error_msg}", meta_data

    # --- ファイル処理 ---
    if uploaded_file_data:
        file_bytes, file_name = uploaded_file_data
        try:
            file_text = file_bytes.decode('cp932')
            full_text_content += f"--- 参照元ファイル: {file_name} ---\n{file_text}\n--- 参照元ファイル 終了 ---\n\n"
        except UnicodeDecodeError as e:
            error_msg = f"ファイルのデコードに失敗しました: {e}"
            logger_service.log_to_firestore('ERROR', error_msg, request_type, prompt, error_detail=str(e), **meta_data)
            return f"エラー: {error_msg}", meta_data

    # --- システム命令構築 ---
    if mode == "general_report":
        if previous_content:
            system_instruction_text = (
                "あなたはプロの編集者兼レポート作成者です。提供されたレポートの内容（PREVIOUS REPORT）を、"
                "新しい指示（REFINEMENT PROMPT）に従って完全に修正し、新しいレポート全文をMarkdown形式で出力してください。"
            )
            user_query = (
                f"--- PREVIOUS REPORT ---\n{previous_content}\n\n--- REFINEMENT PROMPT ---\n{prompt}\n\n"
                f"上記のレポートを精製（修正・加筆）してください。"
            )
        else:
            system_instruction_text = (
                "あなたはプロのレポート作成者です。依頼されたテーマと提供された画像（もしあれば）に基づいて、構造化された日本語レポートを作成してください。"
            )
            user_query = prompt
    else:
        system_instruction_text = "あなたはプロの編集者です。"
        user_query = prompt

    final_text_prompt = full_text_content + user_query
    if final_text_prompt:
        contents.append(final_text_prompt)

    # --- API呼び出しとログ ---
    logger_service.log_to_firestore(
        'INFO',
        'API call initiated',
        request_type,
        prompt,
        previous_content_exists=bool(previous_content),
        files_attached=bool(image_data_base64)
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={
                "system_instruction": system_instruction_text,
                "temperature": 0.7
            }
        )

        generated_text = response.text
        usage_metadata = response.usage_metadata
        if usage_metadata:
            meta_data['input_tokens'] = usage_metadata.prompt_token_count
            meta_data['output_tokens'] = usage_metadata.candidates_token_count
            meta_data['total_tokens'] = usage_metadata.total_token_count

        logger_service.log_to_firestore(
            'INFO',
            'API call successful',
            request_type,
            prompt,
            response_content=generated_text,
            **meta_data
        )
        return generated_text, meta_data

    except DeadlineExceeded:
        error_msg = "エラー: AIサービスからの応答がタイムアウトしました。"
        logger_service.log_to_firestore('ERROR', error_msg, request_type, prompt, **meta_data)
        return error_msg, meta_data

    except APIError as e:
        error_msg = f"Gemini API呼び出し中にエラーが発生しました: {e}"
        logger_service.log_to_firestore('ERROR', error_msg, request_type, prompt, error_detail=str(e), **meta_data)
        return f"エラー: {error_msg}", meta_data

    except Exception as e:
        error_msg = f"予期せぬエラーが発生しました: {e}"
        logger_service.log_to_firestore('ERROR', error_msg, request_type, prompt, error_detail=str(e), **meta_data)
        return f"エラー: {error_msg}", meta_data


def get_api_key_status() -> str:
    if client_status == 'ok':
        return 'ok'
    return 'missing'


def get_model_name() -> str:
    return MODEL_NAME