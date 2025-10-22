import ai_service
import sys
import os
import base64
from typing import Optional

# --- ユーティリティ関数 ---

def get_base64_image_data(file_path: str) -> Optional[str]:
    """
    指定された画像ファイルパスからBase64エンコードされたデータを取得します。
    ファイルが存在しない、または読み込みエラーが発生した場合はNoneを返します。
    """
    if not os.path.exists(file_path):
        print(f"[エラー] 画像ファイルが見つかりません: {file_path}")
        return None
    
    try:
        # 画像ファイルをバイナリモードで読み込み、Base64エンコード
        with open(file_path, "rb") as f:
            image_data = f.read()
            # Base64データを返す
            return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"[エラー] 画像ファイルの読み込み中にエラーが発生しました: {e}")
        return None

def save_report_to_file(content: str, filename: str) -> bool:
    """
    レポート内容をMarkdownファイルとして保存します。
    """
    try:
        # 拡張子がなければ自動で .md を追加
        if not filename.lower().endswith('.md'):
            filename = f"{filename}.md"
            
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n[成功] レポートをファイル '{filename}' に保存しました。")
        return True
    except Exception as e:
        print(f"\n[エラー] ファイルの保存中にエラーが発生しました: {e}")
        return False

# --- メインロジック ---

def main():
    """
    ai_service.pyのレポート生成/精製機能をテストするためのメイン関数。
    """
    print("--- AIレポート作成・ブラッシュアップツール ---")
    
    # 1. APIキーのチェック
    api_key_status = ai_service.get_api_key_status()
    if api_key_status == 'missing':
        print("\n[警告] APIキーが設定されていません。ai_service.py内の 'HARDCODED_API_KEY' を確認・設定してください。")
        sys.exit(1)

    print(f"[設定] 使用モデル: {ai_service.get_model_name()}")
    print("-" * 30)

    # 2. 初回プロンプト（テーマと画像パス）の取得と生成
    
    print("\n--- 初回レポート生成 ---")
    
    # 画像パスの入力
    image_path = input("レポートに使用する画像ファイルパスを入力してください (オプション、スキップする場合はEnter): ")
    image_data_base64 = None
    if image_path:
        image_data_base64 = get_base64_image_data(image_path)
        if not image_data_base64:
            print("[注意] 画像の読み込みに失敗したため、テキストのみでレポートを生成します。")

    # テーマの入力と終了コマンドチェック
    initial_prompt = input("レポートのテーマを入力してください (終了するには 'exit' または 'q' を入力): ")
    
    if initial_prompt.lower() in ['exit', 'q']:
        print("実行を終了します。")
        return

    if not initial_prompt:
        print("テーマが入力されなかったため、終了します。")
        return

    print("\n>>> レポートを生成中...しばらくお待ちください。")
    
    # 初回生成 (画像データを含めてai_serviceを呼び出す)
    current_report_content = ai_service.process_report_request(
        initial_prompt, 
        previous_content=None,
        image_data_base64=image_data_base64
    )
    
    # 結果の表示
    print("\n" + "=" * 60)
    print("<<< 初回生成されたレポート（Markdown形式） >>>")
    print("-" * 60)
    print(current_report_content)
    print("=" * 60 + "\n")

    # エラーが発生した場合は精製ループに進まない
    if current_report_content.startswith("エラー:"):
        print("エラーが発生したため、アプリケーションを終了します。")
        return

    # 3. レポート精製ループ
    print("--- レポート精製モード ---")
    print("追加の指示を入力して、レポートをブラッシュアップできます。")
    print("終了するには 'exit' または 'q' を入力してください。")
    
    while True:
        refinement_prompt = input("\nブラッシュアップの指示を入力してください: ")
        
        if refinement_prompt.lower() in ['exit', 'q']:
            print("\nレポート精製を終了します。")
            break
        
        if not refinement_prompt:
            continue

        print("\n>>> レポートを精製中...しばらくお待ちください。")

        # 精製実行 (previous_contentに現在のレポート内容を渡す。精製時には画像は使用しない)
        refined_report_content = ai_service.process_report_request(
            refinement_prompt, 
            previous_content=current_report_content,
            image_data_base64=None
        )
        
        # 結果の表示
        print("\n" + "=" * 60)
        print("<<< 精製後のレポート（Markdown形式） >>>")
        print("-" * 60)
        print(refined_report_content)
        print("=" * 60 + "\n")
        
        # 精製が成功した場合のみ、現在のレポートを更新
        if not refined_report_content.startswith("エラー:"):
            current_report_content = refined_report_content
        else:
            print("精製中にエラーが発生しました。現在のレポートは更新されていません。")
            
    # 4. ダウンロード（保存）処理
    # エラーが発生しておらず、内容が存在する場合に保存を促す
    if current_report_content and not current_report_content.startswith("エラー:"):
        print("\n" + "=" * 60)
        save_choice = input("最終レポートをファイルに保存しますか？ (y/n, デフォルト: n): ").lower()

        if save_choice == 'y':
            default_filename = "generated_report"
            print(f"\n[ヒント] ファイルはMarkdown形式 (*.md) で保存されます。")
            save_filename = input(f"保存するファイル名を入力してください (デフォルト: {default_filename}.md): ") or default_filename
            
            # ファイル保存処理を実行
            save_report_to_file(current_report_content, save_filename)
        else:
            print("レポートの保存をスキップしました。")
        print("=" * 60)
        
if __name__ == '__main__':
    main()