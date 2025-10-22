import os
import json
import requests
# base64エンコーディングに必要なライブラリをインポート
import base64
from typing import Optional, List, Dict, Any

# ↓↓↓ここにAPIキーを直接記述してください↓↓↓
HARDCODED_API_KEY = "AIzaSyAnWQR85rRFZzMxMnOwkmNgmNoi8YxM4rE" # <-- ここを実際のAPIキーに置き換える

# 環境変数が設定されていればそれを使い、なければハードコードされたキーを使用
API_KEY = os.getenv('GEMINI_API_KEY') or HARDCODED_API_KEY
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
MODEL_NAME = "gemini-2.5-flash-preview-05-20"

# MIMEタイプは一般的なJPEGとして扱います（必要に応じてPNGなどに変更可）
DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"

def process_report_request(prompt: str, previous_content: Optional[str] = None, image_data_base64: Optional[str] = None) -> str:
    """
    Gemini APIを呼び出して、レポートを生成または精製します。
    previous_contentが提供された場合、promptは精製の指示として扱われます。
    image_data_base64が提供された場合、画像もコンテキストとして含めます。

    Args:
        prompt (str): 初回はレポート生成のテーマ。精製時は追加の指示（例：指定文字数、修正点）。
        previous_content (str): 精製対象となる、以前に生成されたレポートテキスト。
        image_data_base64 (str): Base64エンコードされた画像データ。

    Returns:
        str: 生成または精製されたMarkdown形式のレポートテキスト、またはエラーメッセージ。
    """
    # APIキーの存在チェック
    if API_KEY == 'YOUR_API_KEY_HERE' or not API_KEY:
        return "エラー: APIキーが設定されていません。ai_service.pyのHARDCODED_API_KEYを実際のキーに置き換えてください。"

    # システム命令の設定とコンテンツ部品の準備
    contents_parts: List[Dict[str, Any]]
    
    if previous_content:
        # **精製モードの場合:** 画像は精製指示には含めず、テキストのみを扱う
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
        contents_parts = [{"text": user_query}]
    else:
        # **初回生成モードの場合:** 画像データがあればテキストと同時にAPIに渡す
        system_instruction_text = (
            "あなたはプロのレポート作成者です。依頼されたテーマについて、読みやすく、構造化された、詳細なレポートを日本語で作成してください。"
            "もし画像が提供されている場合、その画像を分析し、レポートの内容に組み込んでください。見出しにはMarkdown記法を使用してください。"
        )
        user_query = prompt
        
        contents_parts = []
        
        # 1. 画像データが存在すればインラインデータとして追加
        if image_data_base64:
            contents_parts.append({
                "inlineData": {
                    "mimeType": DEFAULT_IMAGE_MIME_TYPE,
                    "data": image_data_base64
                }
            })
            # 画像の後にプロンプト（テーマ）をテキストとして追加
            contents_parts.append({"text": user_query})
        else:
            # 画像がない場合、プロンプトのみをテキストとして追加
            contents_parts.append({"text": user_query})


    # APIリクエストのペイロードを構築
    payload: Dict[str, Any] = {
        "contents": [{"parts": contents_parts}],
        "systemInstruction": {
            "parts": [{"text": system_instruction_text}]
        },
        "generationConfig": {
            "temperature": 0.7
        }
    }

    headers = {
        "Content-Type": "application/json"
    }

    # API呼び出し
    try:
        # APIキーをURLパラメータとして付与してリクエストを送信
        response = requests.post(
            f"{API_URL}?key={API_KEY}",
            headers=headers,
            data=json.dumps(payload),
            timeout=60 # タイムアウト設定
        )
        
        # エラーコードを詳細に表示するためのカスタムエラーハンドリング (変更なし)
        if response.status_code != 200:
            
            try:
                error_response_json = response.json()
                error_details = error_response_json.get('error', {}).get('message', '詳細不明')
                print("\n--- APIエラーレスポンス (JSON) ---")
                print(json.dumps(error_response_json, indent=2, ensure_ascii=False))
                print("----------------------------------\n")
            except Exception:
                error_details = "応答JSONの解析に失敗しました。"
            
            print(f"APIリクエストエラー (HTTP {response.status_code}): {error_details}")

            if response.status_code in [400, 403]:
                return f"エラー: HTTP {response.status_code} Bad Request/Forbidden。APIキー（{API_KEY[:5]}...）が無効、またはAPIが有効になっていない可能性があります。コンソールに詳細なエラーメッセージが出力されています。"
            
            response.raise_for_status() 

        result = response.json()
        
        # 応答から生成されたテキストを抽出
        generated_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'レポートの生成に失敗しました。')
        
        # 成功した場合、Markdown形式のテキストを返します
        return generated_text

    except requests.exceptions.RequestException as e:
        print(f"APIリクエストエラー: {e}")
        return f"APIリクエスト中にエラーが発生しました: {e}"
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        return f"予期せぬエラーが発生しました: {e}"

def get_api_key_status() -> str:
    """
    APIキーが設定されているかどうかのステータスを返します。
    """
    return 'ok' if API_KEY and API_KEY != 'YOUR_API_KEY_HERE' else 'missing'


def get_model_name() -> str:
    """
    使用モデル名を取得します。
    """
    return MODEL_NAME