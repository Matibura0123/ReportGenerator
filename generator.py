import ai_service
from io import BytesIO
from typing import Optional, Tuple
import os
import base64
from flask import Flask, render_template, request, session, jsonify, redirect, url_for

# --- アプリケーション設定 ---
app = Flask(__name__)
# セッションを使用するためのシークレットキー。
# 【重要】本番環境では、os.environなどから安全に取得し、外部から設定してください。
app.config['SECRET_KEY'] = os.urandom(24) 

# --- ユーティリティ関数 ---

def get_base64_image_data_from_upload(file) -> Optional[str]:
    """
    アップロードされた画像ファイルオブジェクトからBase64エンコードされたデータを取得します。
    """
    # ファイルオブジェクトがNoneでないこと、ファイル名があることを確認
    if not file or not file.filename:
        return None

    try:
        # ファイルの内容をメモリ上で読み込み、Base64エンコード
        image_data = file.read()
        
        # 【修正】読み込み後、ファイルポインタを先頭に戻す (再読み込みに備えて)
        file.seek(0)
        
        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"[エラー] 画像ファイルの読み込み中にエラーが発生しました: {e}")
        return None

def get_uploaded_file_bytes(file) -> Optional[Tuple[bytes, str]]:
    """
    アップロードされたファイルオブジェクトからバイトデータとファイル名を返します。
    （主に書籍ファイルなど、Base64エンコードが不要なバイナリデータ用）
    """
    # ファイルオブジェクトがNoneでないこと、ファイル名があることを確認
    if not file or not file.filename:
        return None
    
    try:
        # ファイルの内容をメモリ上で読み込み
        file_bytes = file.read()
        file_name = file.filename
        
        # 【修正】読み込み後、ファイルポインタを先頭に戻す (再読み込みに備えて)
        file.seek(0)
        
        return file_bytes, file_name
    except Exception as e:
        print(f"[エラー] ファイルの読み込み中にエラーが発生しました: {e}")
        return None


# --- Flask ルート定義 ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    レポートの生成と精製を処理するメインルート。
    """
    # AIキーのステータスチェック（GET/POST共通）
    api_key_status = ai_service.get_api_key_status()
    if api_key_status == 'missing':
        error_msg = "APIキーが設定されていません。ai_service.pyを確認してください。"
        if request.method == 'GET':
            # GETリクエストの場合、HTMLテンプレートでエラーを表示
            return render_template('index.html', error_message=error_msg)
        else:
            # POSTリクエストの場合、JSONでエラーを返す
            return jsonify({'status': 'error', 'message': error_msg, 'report_content': None}), 500

    # セッションから現在のレポート内容を取得
    current_report_content = session.get('report_content', None)
    error_message = None
    
    if request.method == 'GET':
        # セッションクリア処理（/clear_sessionルートがあるため、この処理は冗長かもしれませんが残しておきます）
        if 'clear' in request.args:
            session.pop('report_content', None)
            current_report_content = None
            
        return render_template(
            'index.html',
            report_content=current_report_content,
            error_message=error_message,
            model_name=ai_service.get_model_name()
        )
    
    # POSTリクエスト（AJAX/Fetch APIから）
    if request.method == 'POST':
        
        # POSTリクエスト全体をtry-exceptで囲み、HTML応答を防ぐ
        try:
            # 現在のレポート内容の有無に基づいて 'generate' または 'refine' を決定
            action = 'refine' if current_report_content else 'generate'
            
            # 応答用の変数
            new_report_content = current_report_content
            meta_data = None 
            
            # フォームデータからプロンプトとアップロードファイルを取得
            initial_prompt = request.form.get('initial_prompt')
            image_file = request.files.get('image_file') # 一般レポート用
            book_file = request.files.get('book_file')   # 感想文用
            
            # 感想文モードの判定
            is_book_report_mode = request.form.get('mode') == 'book_report'

            # --- 1. レポート/感想文 生成 ---
            if action == 'generate':
                if not initial_prompt and not (is_book_report_mode and book_file and book_file.filename) and not (not is_book_report_mode and image_file and image_file.filename):
                    error_message = "テーマ、またはファイルを入力/アップロードしてください。"
                else:
                    image_data_base64 = None
                    uploaded_file_data = None
                    file_error = None

                    # ファイル処理の排他制御
                    if is_book_report_mode and book_file and book_file.filename:
                        # 書籍ファイルがアップロードされた場合
                        uploaded_file_data = get_uploaded_file_bytes(book_file)
                        if uploaded_file_data is None:
                            file_error = "書籍ファイルの読み込みに失敗しました。"

                    elif not is_book_report_mode and image_file and image_file.filename:
                        # 画像ファイルがアップロードされた場合
                        image_data_base64 = get_base64_image_data_from_upload(image_file)
                        if image_data_base64 is None:
                            file_error = "画像ファイルの読み込みに失敗しました。"
                    
                    if file_error:
                        error_message = file_error
                        
                    elif not error_message: # エラーがない場合のみAI処理を実行
                        print(f">>> {request.form.get('mode')}を生成中...")
                        
                        # ai_service.process_report_requestを呼び出し
                        report_text, meta_data = ai_service.process_report_request( 
                            initial_prompt=initial_prompt, 
                            previous_content=None, 
                            image_data_base64=image_data_base64,
                            uploaded_file_data=uploaded_file_data, # (bytes, filename) または None
                            mode=request.form.get('mode') 
                        )

                        if report_text and report_text.startswith("エラー:"):
                            error_message = report_text.replace("エラー:", "").strip() # エラーメッセージからプレフィックスを除去
                            new_report_content = None
                        else:
                            new_report_content = report_text
                        
            # --- 2. レポート/感想文 精製 ---
            elif action == 'refine' and current_report_content:
                refinement_prompt = request.form.get('initial_prompt')

                if not refinement_prompt:
                    error_message = "ブラッシュアップの指示を入力してください。"
                else:
                    print(f">>> {request.form.get('mode')}を精製中...")

                    refined_text, meta_data = ai_service.process_report_request(
                        initial_prompt=refinement_prompt, 
                        previous_content=current_report_content,
                        image_data_base64=None,
                        uploaded_file_data=None, 
                        mode=request.form.get('mode') # モードを引き継ぐ
                    )

                    if refined_text and not refined_text.startswith("エラー:"):
                        new_report_content = refined_text
                    else:
                        error_message = refined_text.replace("エラー:", "").strip()
            
            # 処理後のレポート内容をセッションに保存
            session['report_content'] = new_report_content

            # JSONを返す
            response_data = {
                'status': 'success' if not error_message else 'error',
                'report_content': new_report_content,
                'message': error_message or ('感想文が正常に生成されました。' if is_book_report_mode else 'レポートが正常に生成されました。'),
                'meta_data': meta_data,
                'action_type': action
            }
            
            status_code = 200 if response_data['status'] == 'success' else 400
            return jsonify(response_data), status_code

        # 例外処理ブロック
        except Exception as e:
            # サーバー側で予期せぬエラーが発生した場合
            print(f"[クリティカルエラー] POSTリクエスト処理中に予期せぬエラーが発生しました: {type(e).__name__}: {e}")
            
            # HTMLではなく、必ずJSONでエラーを返す（HTTP 500）
            return jsonify({
                'status': 'error',
                'report_content': None, # レポート内容をクリア
                'message': f"サーバー内部エラーが発生しました。ログを確認してください: {type(e).__name__}"
            }), 500


@app.route('/clear_session', methods=['POST'])
def clear_session():
    """
    セッションをクリアし、新しいレポート作成を開始するためのルート。
    """
    session.pop('report_content', None)
    return jsonify({'status': 'success', 'message': 'セッションをクリアしました'}), 200

if __name__ == '__main__':
    # デバッグモードを有効にして実行 (本番環境では無効にしてください)
    app.run(debug=True)

