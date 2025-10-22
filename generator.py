from flask import Flask, render_template, request, redirect, url_for, session
import ai_service
import base64
import os
from io import BytesIO
from typing import Optional

# --- アプリケーション設定 ---
app = Flask(__name__)
# セッションを使用するためのシークレットキー。本番環境では安全な値に設定してください。
app.config['SECRET_KEY'] = 'your_very_secret_key_for_flask_session' 

# --- ユーティリティ関数 (ファイルパスではなくアップロードされたファイルオブジェクトを処理) ---

def get_base64_image_data_from_upload(file) -> Optional[str]:
    """
    アップロードされたファイルオブジェクトからBase64エンコードされたデータを取得します。
    """
    if file.filename == '':
        return None
    
    try:
        # ファイルの内容をメモリ上で読み込み、Base64エンコード
        image_data = file.read()
        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"[エラー] 画像ファイルの読み込み中にエラーが発生しました: {e}")
        return None

# --- Flask ルート定義 ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    レポートの生成と精製を処理するメインルート。
    """
    print("test1")
    api_key_status = ai_service.get_api_key_status()
    if api_key_status == 'missing':
        # APIキーエラーはテンプレートに渡して表示
        return render_template('index.html', error_message="APIキーが設定されていません。ai_service.pyを確認してください。")

    # セッションから現在のレポート内容を取得（初回アクセス時はNone）
    current_report_content = session.get('report_content', None)
    error_message = None

    if request.method == 'POST':
        # フォームから送信されたアクションを識別
        action = request.form.get('action')
        
        if action == 'generate':
            # --- 1. 初回レポート生成 ---
            initial_prompt = request.form.get('initial_prompt')
            image_file = request.files.get('image_file')

            if not initial_prompt:
                error_message = "テーマを入力してください。"
            else:
                image_data_base64 = get_base64_image_data_from_upload(image_file) if image_file else None
                
                print(">>> レポートを生成中...")

                current_report_content = ai_service.process_report_request(
                    initial_prompt, 
                    previous_content=None,
                    image_data_base64=image_data_base64
                )
                
                if current_report_content.startswith("エラー:"):
                    error_message = current_report_content
                    current_report_content = None # エラー時はレポート内容をクリア
                
        elif action == 'refine' and current_report_content:
            # --- 2. レポート精製 ---
            refinement_prompt = request.form.get('refinement_prompt')

            if not refinement_prompt:
                error_message = "ブラッシュアップの指示を入力してください。"
            else:
                print(">>> レポートを精製中...")

                refined_report_content = ai_service.process_report_request(
                    refinement_prompt, 
                    previous_content=current_report_content,
                    image_data_base64=None # 精製時には画像は使用しない
                )

                if not refined_report_content.startswith("エラー:"):
                    current_report_content = refined_report_content
                else:
                    error_message = refined_report_content
                    
        # 処理後のレポート内容をセッションに保存
        session['report_content'] = current_report_content

        # フォーム送信後はGETリクエストにリダイレクトし、二重送信を防ぐ
        return redirect(url_for('index'))

    # GETリクエスト、またはPOSTリクエスト後の表示
    return render_template(
        'index.html',
        report_content=current_report_content,
        error_message=error_message,
        model_name=ai_service.get_model_name()
    )

@app.route('/clear_session', methods=['POST'])
def clear_session():
    """
    セッションをクリアし、新しいレポート作成を開始するためのルート。
    """
    session.pop('report_content', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    # デバッグモードを有効にして実行 (本番環境では無効にしてください)
    app.run(debug=True)