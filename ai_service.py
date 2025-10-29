import os
import json
import requests
from google import genai
from google.genai.errors import APIError
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
# 注: この値はデモ用のダミーキーです。実際のAPIキーに置き換えてください。
HARDCODED_API_KEY = "AIzaSyAnWQR85rRFZzMxMnOwkmNgmNoi8YxM4rE"
# ---------------------------------------------------------------

# 環境変数が設定されていればそれを使い、なければハードコードされたキーを使用
API_KEY = os.getenv('GEMINI_API_KEY') or HARDCODED_API_KEY
MODEL_NAME = "gemini-2.5-flash" # 最新の推奨モデル名に変更
# ----------------

# ★ クライアントの初期化 (SDKを使用)
client = None
client_status = 'missing'
try:
    if API_KEY and not API_KEY.startswith('AIzaSyA'):
        client_status = 'dummy_key'
        print("警告: ダミーのAPIキーが使用されています。APIキーを設定してください。")
    elif API_KEY and API_KEY.startswith('AIzaSyA'):
        client = genai.Client(api_key=API_KEY)
        client_status = 'ok'
    else:
        client_status = 'missing'
except Exception as e:
    client = None
    client_status = 'error'
    print(f"致命的な警告: Gemini Clientの初期化に失敗しました。詳細: {e}")

# process_report_requestの引数とロジックを修正
def process_report_request(
    initial_prompt: str, mode="general_report",
    previous_content: Optional[str] = None, 
    image_data_base64: Optional[str] = None,
    uploaded_file_data: Optional[Tuple[bytes, str]]=None
) -> Tuple[str, Dict[str, Any]]:
    
    print(f"--- リクエスト詳細 ---")
    print(f"モード: {mode}")
    print(f"画像添付 (image_data_base64): {bool(image_data_base64)}")
    if uploaded_file_data:
        file_bytes, file_name = uploaded_file_data
        print(f"ファイル添付 (uploaded_file_data): True ({file_name}, {len(file_bytes)} bytes)")
    else:
        print(f"ファイル添付 (uploaded_file_data): False")
    print(f"----------------------")
    
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

    # クライアントがNoneの場合、ここでエラーを返す (API呼び出しが不可能なため)
    if not client:
        if client_status == 'dummy_key':
             return "エラー: APIキーがダミー値のままです。`ai_service.py` の `HARDCODED_API_KEY` を有効なキーに置き換えてください。", meta_data
        return "エラー: Gemini Clientが初期化されていません。APIキーが正しく設定されているか確認してください。", meta_data

    contents: List[Any] = [] # APIリクエストに渡すコンテンツパーツ (画像/ファイル/テキスト)
    full_text_content = "" # すべてのテキストコンテンツ（ファイル内容＋プロンプト）を格納

    
    # --- Base64画像の処理ロジック ---
    if image_data_base64:
        print("画像をコンテンツに追加中...")
        try:
            img_data = base64.b64decode(image_data_base64)
            img = Image.open(BytesIO(img_data))
            contents.append(img) 
            print("画像が正常に処理されました。")
        except Exception as e:
            error_msg = f"画像のBase64デコードまたは処理に失敗しました: {e}"
            print(error_msg)
            return f"エラー: {error_msg}", meta_data
            
    # --- 書籍ファイル（バイトデータ）の処理ロジック (File APIを使わずテキストとして処理) ---
    if uploaded_file_data:
        file_bytes, file_name = uploaded_file_data
        print(f"ファイル '{file_name}' の内容をテキストとして抽出中...")
        
        try:
            # バイトデータをUTF-8でデコードし、テキストコンテンツに組み込む
            # NOTE: ファイルが他のエンコーディング（例: Shift-JIS）の場合は、ここで適切なエンコーディングを指定する必要があります。
            file_text = file_bytes.decode('cp932')
            
            full_text_content += f"--- 参照元ファイル: {file_name} ---\n"
            full_text_content += file_text
            full_text_content += "\n--- 参照元ファイル 終了 ---\n\n"
            print(f"ファイルの内容 ({len(file_text)} 文字) をプロンプトに組み込みました。")
            
        except UnicodeDecodeError as e:
            error_msg = f"ファイルのデコードに失敗しました。エンコーディングがUTF-8ではない可能性があります。: {e}"
            print(error_msg)
            return f"エラー: {error_msg}", meta_data
        except Exception as e:
            error_msg = f"ファイルの内容抽出中に予期せぬエラーが発生しました: {type(e).__name__}: {e}"
            print(error_msg)
            return f"エラー: {error_msg}", meta_data

    # --- システム命令の設定とユーザープロンプトの構築 ---
    system_instruction_text = ""
    user_query = ""
    
    # テキストプロンプトとファイル内容の結合
    if mode=="general_report":
        # ... (中略: general_reportモードのロジックは前回と同じ)
        if previous_content:
            system_instruction_text = (
                "あなたはプロの編集者兼レポート作成者です。提供されたレポートの内容（PREVIOUS REPORT）を、"
                "新しい指示（REFINEMENT PROMPT）に従って完全に修正し、新しいレポート全文をMarkdown形式で出力してください。 "
                "出力は新しい修正後のレポートのみとし、指示やコメントは含めないでください。"
            )
            user_query = (
                f"--- PREVIOUS REPORT ---\n{previous_content}\n\n"
                f"--- REFINEMENT PROMPT ---\n{prompt}\n\n"
                f"上記のレポートを精製（修正・加筆）してください。"
            )
        else:
            system_instruction_text = (
                "あなたはプロのレポート作成者です。依頼されたテーマと提供された画像（もしあれば）に基づいて、読みやすく、構造化された、詳細なレポートを日本語で作成してください。見出しにはMarkdown記法を使用してください。"
            )
            user_query = prompt
            
    elif mode=="book_report":
        # ... (中略: book_reportモードのロジックは前回と同じ)
        if previous_content:
            system_instruction_text = (
                "あなたはプロの編集者兼読書感想文作成者です。提供された読書感想文の内容（PREVIOUS REPORT）を、"
                "新しい指示（REFINEMENT PROMPT）に従って完全に修正し、新しい読書感想文全文をMarkdown形式で出力してください。 "
                "出力は新しい修正後のレポートのみとし、指示やコメントは含めないでください。"
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
    
    # ファイル内容があれば、それをユーザープロンプトの前に結合
    final_text_prompt = full_text_content + user_query

    # コンテンツリストに最終的なテキストプロンプトを追加
    if final_text_prompt:
        contents.append(final_text_prompt)
        
    if not contents:
        return "エラー: AIに渡すコンテンツ（プロンプトやファイル）が空です。", meta_data

    print("API呼び出しを実行中...")
    # API呼び出し
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents, 
            config={
                "system_instruction": system_instruction_text,
                "temperature": 0.7
            }
            # timeout=60.0 は非互換性の問題を避けるため削除
        )
        
        generated_text = response.text
        
        # --- メタデータの抽出と更新 ---
        usage_metadata = response.usage_metadata
        if usage_metadata:
            meta_data['input_tokens'] = usage_metadata.prompt_token_count
            meta_data['output_tokens'] = usage_metadata.candidates_token_count
            meta_data['total_tokens'] = usage_metadata.total_token_count
        
        print("API呼び出し成功")
        
        return generated_text, meta_data
        
    except DeadlineExceeded:
        # タイムアウト時のエラー処理
        print("エラー: AIサービスからの応答がタイムアウトしました。（約2分以上の待機が発生した可能性）")
        return "エラー: AIサービスからの応答がタイムアウトしました。リクエストが複雑すぎる可能性があります。", meta_data

    except APIError as e:
        error_msg = f"Gemini API呼び出し中にエラーが発生しました: {e}"
        if "API_KEY_INVALID" in str(e) or "API key is not valid" in str(e):
             error_msg += " -> APIキーが不正または無効です。キーを再確認してください。"
        print(f"APIリクエストエラー (SDK): {e}")
        return f"エラー: {error_msg}", meta_data
        
    except Exception as e:
        error_msg = f"予期せぬエラーが発生しました: {e}"
        print(f"予期せぬエラー: {e}")
        return f"エラー: {error_msg}", meta_data
        
    finally:
        # File APIは使用しないため、クリーンアップロジックは不要
        pass


def get_api_key_status() -> str:
    """
    APIキーが設定されているかどうかのステータスを返します。
    """
    global client_status
    if client_status == 'ok':
        return 'ok'
    return 'missing'


def get_model_name() -> str:
    """
    使用モデル名を取得します。
    """
    return MODEL_NAME
