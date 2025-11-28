import os
import json
from google import genai
from google.genai.errors import APIError
import logger_service
import base64
from io import BytesIO
from PIL import Image
from typing import Optional, Tuple, Dict, Any, List
from google.api_core.exceptions import DeadlineExceeded

# --- 設定 ---
GEMINI_API_KEY= "sample_api_key"#←ここをAPIキーに変える
# ---------------------------------------------------------------

API_KEY = os.getenv('GEMINI_API_KEY') or GEMINI_API_KEY
MODEL_NAME = "gemini-2.5-flash"

# ロガー初期化
logger_service.initialize_firebase_logger()

# クライアント初期化
client = None
client_status = 'missing'
try:
    client = genai.Client(api_key=API_KEY)
    client_status = 'ok'
except Exception as e:
    client = None
    client_status = 'error'
    print(f"Gemini Client初期化失敗: {e}")


def process_report_request(
    initial_prompt: str,
    user_id: str,
    workspace_id: str,
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
        'request_type': request_type,
    }

    if not client:
        return "エラー: Gemini Client未初期化 (APIキーを確認してください)", meta_data

    contents: List[Any] = []
    full_text_content = ""

    # 画像処理
    if image_data_base64:
        try:
            img_data = base64.b64decode(image_data_base64)
            img = Image.open(BytesIO(img_data))
            contents.append(img)
        except Exception as e:
            error_msg = f"画像処理失敗: {e}"
            logger_service.log_to_firestore('ERROR', error_msg, prompt, user_id, workspace_id, error_detail=str(e), **meta_data)
            return f"エラー: {error_msg}", meta_data

    # ファイル処理
    if uploaded_file_data:
        file_bytes, file_name = uploaded_file_data
        try:
            file_text = file_bytes.decode('cp932')
            full_text_content += f"--- 参照元ファイル: {file_name} ---\n{file_text}\n--- 参照元ファイル 終了 ---\n\n"
        except UnicodeDecodeError as e:
            error_msg = f"ファイルデコード失敗: {e}"
            logger_service.log_to_firestore('ERROR', error_msg, prompt, user_id, workspace_id, error_detail=str(e), **meta_data)
            return f"エラー: {error_msg}", meta_data

    # システム命令
    system_instruction_text = ""
    user_query = ""
    
    if mode == "general_report":
        if previous_content:
            system_instruction_text = "あなたはプロの編集者兼レポート作成者です。提供されたレポートを指示に従って修正し、Markdownで出力してください。"
            user_query = f"--- PREVIOUS REPORT ---\n{previous_content}\n\n--- REFINEMENT PROMPT ---\n{prompt}\n\n修正してください。"
        else:
            system_instruction_text = "あなたはプロのレポート作成者です。テーマと画像に基づき構造化されたレポートを作成してください。"
            user_query = prompt
    elif mode == "book_report":
        if previous_content:
            system_instruction_text = "あなたはプロの編集者兼読書感想文作成者です。提供された感想文を指示に従って修正し、Markdownで出力してください。"
            user_query = f"--- PREVIOUS REPORT ---\n{previous_content}\n\n--- REFINEMENT PROMPT ---\n{prompt}\n\n修正してください。"
        else:
            system_instruction_text = "あなたはプロの読書感想文作成者です。参照元と指示に基づき感想文を作成してください。"
            user_query = f"--- USER PROMPT ---\n{prompt}\n\n感想文を作成してください。"
    
    final_text_prompt = full_text_content + user_query
    if final_text_prompt:
        contents.append(final_text_prompt)

    # ★削除: API呼び出し開始時のログ (user_prompt送信時) を削除
    # logger_service.log_to_firestore('INFO', 'API call initiated', ...) 
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={"system_instruction": system_instruction_text, "temperature": 0.7}
        )
        generated_text = response.text
        if response.usage_metadata:
            meta_data['total_tokens'] = response.usage_metadata.total_token_count
            meta_data['input_tokens'] = response.usage_metadata.prompt_token_count
            meta_data['output_tokens'] = response.usage_metadata.candidates_token_count

        # ★削除: API成功直後の生テキストログを削除
        # ここでログを出さないことで、app.pyでのStorage保存後のログのみが残ります
        
        return generated_text, meta_data

    except DeadlineExceeded:
        error_msg = "エラー: AI応答タイムアウト"
        logger_service.log_to_firestore('ERROR', error_msg, prompt, user_id, workspace_id, **meta_data)
        return error_msg, meta_data
    except APIError as e:
        error_msg = f"Gemini APIエラー: {e}"
        logger_service.log_to_firestore('ERROR', error_msg, prompt, user_id, workspace_id, error_detail=str(e), **meta_data)
        return f"エラー: {error_msg}", meta_data
    except Exception as e:
        error_msg = f"エラー発生: {e}"
        logger_service.log_to_firestore('ERROR', error_msg, prompt, user_id, workspace_id, error_detail=str(e), **meta_data)
        return error_msg, meta_data

def get_api_key_status() -> str:
    if client_status == 'ok': return 'ok'
    return 'missing'

def get_model_name() -> str:

    return MODEL_NAME

