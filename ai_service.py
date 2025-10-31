# ファイル名: ai_service.py

import os
import json
from google import genai
from google.genai.errors import APIError
# logger_service は外部ファイルとして存在するものと想定します
import logger_service 
import base64
from io import BytesIO
from PIL import Image
from typing import Optional, Tuple, Dict, Any, List
from google.api_core.exceptions import DeadlineExceeded

# --- 設定 ---
# 実際のキーに置き換えてください。本番環境では環境変数を使用することを推奨します。
HARDCODED_API_KEY = "AIzaSyAnWQR85rRFZzMxMnOwkmNgmNoi8YxM4rE" 

API_KEY = os.getenv('GEMINI_API_KEY') or HARDCODED_API_KEY
MODEL_NAME = "gemini-2.5-flash"

# クライアントの初期化
client = None
client_status = 'missing'
try:
    client = genai.Client(api_key=API_KEY)
    client_status = 'ok'
except Exception as e:
    client = None
    client_status = 'error'
    print(f"致命的な警告: Gemini Clientの初期化に失敗しました。詳細: {e}")

# --- ユーティリティ関数: ファイルデコードの堅牢化 ---
def decode_uploaded_text(file_bytes: bytes, file_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    バイトデータをUTF-8、CP932の順にデコードし、成功したテキストとエラーメッセージを返す。
    """
    for encoding in ['utf-8', 'cp932', 'shift_jis']: # 複数のエンコーディングを試行
        try:
            return file_bytes.decode(encoding), None
        except UnicodeDecodeError:
            continue
        except Exception as e:
            # その他の予期せぬデコードエラー
            return None, f"予期せぬデコードエラーが発生しました: {type(e).__name__}"
    
    # すべて失敗
    return None, f"ファイル '{file_name}' のデコードに失敗しました（UTF-8, CP932などを試行）。"


def process_report_request(
    initial_prompt: str,
    mode="general_report",
    previous_content: Optional[str] = None,
    image_data_base64: Optional[str] = None,
    uploaded_file_data: Optional[Tuple[bytes, str]] = None
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """
    レポート生成または精製を実行する。
    戻り値: (生成テキスト, エラーメッセージ, メタデータ)
    """
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
        return None, "Gemini Clientが初期化されていません。APIキーが正しく設定されているか確認してください。", meta_data

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
            # logger_service.log_to_firestore('ERROR', error_msg, prompt, error_detail=str(e), **meta_data)
            return None, error_msg, meta_data

    # --- アップロードされたテキストファイルの処理 ---
    if uploaded_file_data:
        file_bytes, file_name = uploaded_file_data
        
        file_text, decode_error = decode_uploaded_text(file_bytes, file_name)
        
        if decode_error:
            # logger_service.log_to_firestore('ERROR', decode_error, prompt, error_detail=decode_error, **meta_data)
            return None, decode_error, meta_data
            
        full_text_content += f"--- 参照元ファイル: {file_name} ---\n{file_text}\n--- 参照元ファイル 終了 ---\n\n"

    # --- システム命令構築 ---
    system_instruction_text = ""
    user_query = ""
    
    # レポートモード
    if mode == "general_report":
        if previous_content:
            system_instruction_text = (
                "あなたはプロの編集者兼レポート作成者です。提供されたレポートの内容（PREVIOUS REPORT）を、"
                "新しい指示（REFINEMENT PROMPT）に従って完全に修正し、新しいレポート全文をMarkdown形式で出力してください。"
                "**出力は新しい修正後のレポート全文のみとし、指示、コメント、再入力を求めるメッセージは厳禁です。**"
            )
            user_query = (
                f"--- PREVIOUS REPORT ---\n{previous_content}\n\n--- REFINEMENT PROMPT ---\n{prompt}\n\n"
                f"上記のレポートを精製（修正・加筆）してください。"
            )
        else:
            system_instruction_text = (
                "あなたはプロのレポート作成者です。依頼されたテーマと提供された情報（画像やテキスト）に基づいて、"
                "構造化された日本語レポート全文をMarkdown形式で作成してください。"
            )
            user_query = prompt
            
    # 感想文モード
    elif mode=="book_report":
        if previous_content:
            system_instruction_text = (
                "あなたはプロの編集者兼読書感想文作成者です。提供された読書感想文の内容（PREVIOUS REPORT）を、"
                "新しい指示（REFINEMENT PROMPT）に従って完全に修正し、新しい読書感想文全文をMarkdown形式で出力してください。 "
                "**出力は新しい修正後のレポート全文のみとし、指示、コメント、再入力を求めるメッセージは厳禁です。**"
            )
            user_query = (
                f"--- PREVIOUS REPORT ---\n{previous_content}\n\n"
                f"--- REFINEMENT PROMPT ---\n{prompt}\n\n"
                f"上記の読書感想文を精製（修正・加筆）してください。"
            )
        else:
            system_instruction_text = (
                "あなたはプロの読書感想文作成者です。提供された参照元（文章または画像）と、"
                "要約・感想文の指示（USER PROMPT）に基づき、依頼された内容を出力してください。見出しにはMarkdown記法を使用してください。感想文の形式で記述してください。"
            )
            user_query = f"--- USER PROMPT ---\n{prompt}\n\n上記の参照元に対する処理（要約または感想文作成）を実行してください。"
    
    # 最終プロンプトの構築
    final_text_prompt = full_text_content + user_query
    if final_text_prompt:
        contents.append(final_text_prompt)

    # --- API呼び出しとログ ---
    # logger_service.log_to_firestore('INFO', 'API call initiated', ...)
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

        # logger_service.log_to_firestore('INFO', 'API call successful', ...)
        # 成功時は (テキスト, エラーメッセージ=None, メタデータ) を返す
        return generated_text, None, meta_data

    except DeadlineExceeded:
        error_msg = "AIサービスからの応答がタイムアウトしました。"
        # logger_service.log_to_firestore('ERROR', error_msg, prompt, **meta_data)
        return None, error_msg, meta_data

    except APIError as e:
        error_msg = f"Gemini API呼び出し中にエラーが発生しました: {e}"
        # logger_service.log_to_firestore('ERROR', error_msg, prompt, error_detail=str(e), **meta_data)
        return None, error_msg, meta_data

    except Exception as e:
        error_msg = f"予期せぬエラーが発生しました: {e}"
        # logger_service.log_to_firestore('ERROR', error_msg, prompt, error_detail=str(e), **meta_data)
        return None, error_msg, meta_data


def get_api_key_status() -> str:
    return client_status

def get_model_name() -> str:
    return MODEL_NAME