import ai_service
import sys
import os
import logger_service

def main():
    """
    ai_service.pyのレポート生成/精製機能をテストするためのメイン関数。
    コマンドラインから対話形式でプロンプトを受け取り、結果を表示します。
    """
    print("--- レポート生成テストランナー ---")
    
    # 1. APIキーのチェック
    api_key_status = ai_service.get_api_key_status()
    if api_key_status == 'missing':
        print("\n[警告] APIキーが設定されていません。ai_service.py内の 'HARDCODED_API_KEY' を確認・設定してください。")
        # キーがない場合は終了
        sys.exit(1)
    
    logger_service.initialize_firebase_logger() 

    print(f"[設定] 使用モデル: {ai_service.get_model_name()}")
    print("-" * 30)

    # 2. 初回プロンプトの取得と生成
    initial_prompt = input("レポートのテーマを入力してください (例: 地方創生におけるAIの活用): ")
    if not initial_prompt:
        print("テーマが入力されなかったため、終了します。")
        return

    print("\n>>> レポートを生成中...しばらくお待ちください。")
    
    # 初回生成 (previous_content=None)
    request_type = 'initial_generation'
    current_report_content, meta_data = ai_service.process_report_request(initial_prompt, 
                                                                         previous_content=None,
                                                                         request_type=request_type)
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

        # 精製実行 (previous_contentに現在のレポート内容を渡す)
        request_type = 'refinement'
        refined_report_content, meta_data = ai_service.process_report_request(
            refinement_prompt, 
            previous_content=current_report_content,
            request_type=request_type
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
            
if __name__ == '__main__':
    main()
