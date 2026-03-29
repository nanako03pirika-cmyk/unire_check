import os
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from playwright.sync_api import sync_playwright

# --- 設定 ---
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")
TO_EMAILS_STR = os.getenv("TO_EMAIL", "")
TO_EMAILS_LIST = [e.strip() for e in TO_EMAILS_STR.split(",") if e.strip()]

AUTH_FILE = "auth.json"
LAST_TITLE_FILE = "last_title.txt" # 前回のタイトルを保存するファイル
UNIRE_URL = "https://unire.hokudai.ac.jp/"

def send_email_bcc(articles, screenshot_path, is_new):
    """BCC方式で送信。is_new=Falseならスクショのみ"""
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)

            for recipient in TO_EMAILS_LIST:
                msg = MIMEMultipart()
                msg['From'] = GMAIL_USER
                msg['To'] = recipient

                if is_new:
                    msg['Subject'] = f"✨【新着あり】UNIRE通知: {articles[0]['title'][:15]}..."
                    # サマリーと詳細を作成（3件分）
                    summary = "📋 【最新3件のタイトル一覧】\n" + "\n".join([f"{i+1}. 📌 {a['title']}" for i, a in enumerate(articles)])
                    details = "\n\n" + "="*45 + "\n\n📖 【各記事の詳細内容】\n"
                    for i, art in enumerate(articles, 1):
                        details += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n【第 {i} 件】 {art['category']}\n"
                        details += f"📌 タイトル: {art['title']}\n🕒 投稿時期: {art['time']}\n🏢 担当: {art['dept']}\n\n本文:\n{art['body']}\n\n"
                    msg.attach(MIMEText(summary + details, 'plain'))
                else:
                    msg['Subject'] = "🔎【更新なし】UNIRE定期生存確認"
                    msg.attach(MIMEText("UNIREに新しい記事はありませんでした。現在のスクリーンショットをお送りします。", 'plain'))

                if os.path.exists(screenshot_path):
                    with open(screenshot_path, 'rb') as f:
                        msg.attach(MIMEImage(f.read(), name="unire_capture.png"))

                server.send_message(msg)
            print(f"✉️ {len(TO_EMAILS_LIST)} 名に送信完了 (新着: {is_new})")
    except Exception as e:
        print(f"❌ メール送信失敗: {e}")

def run_notifier():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=AUTH_FILE, viewport={'width': 1280, 'height': 3000}, locale='ja-JP')
        page = context.new_page()
        try:
            page.goto(UNIRE_URL)
            page.wait_for_load_state("networkidle")
            page.locator('flt-semantics-placeholder[aria-label="Enable accessibility"]').dispatch_event("click")
            page.wait_for_timeout(10000)
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(3000)

            screenshot_path = "unire_capture.png"
            page.screenshot(path=screenshot_path)

            raw_text = page.locator("flt-semantics-host").inner_text()
            raw_articles = re.split(r'詳細を表示|Show Detail|詳細を閉じる|Hide Detail', raw_text)
            
            final_articles = []
            for part in raw_articles:
                lines = [l.strip() for l in part.replace("|", "").split("\n") if l.strip()]
                if len(lines) >= 4:
                    if any(x in lines[0] for x in ["マイホーム", "My home", "検索", "Search", "お知らせ"]): continue
                    final_articles.append({ "category": lines[0], "title": lines[1], "dept": lines[2], "time": lines[3], "body": "\n".join(lines[4:]) })
                if len(final_articles) >= 3: break # 今回は3件

            # --- 更新チェックロジック ---
            current_top_title = final_articles[0]['title'] if final_articles else ""
            last_top_title = ""
            if os.path.exists(LAST_TITLE_FILE):
                with open(LAST_TITLE_FILE, "r", encoding="utf-8") as f:
                    last_top_title = f.read().strip()

            if current_top_title != last_top_title:
                # 新着あり
                send_email_bcc(final_articles, screenshot_path, is_new=True)
                # 新しいタイトルを保存
                with open(LAST_TITLE_FILE, "w", encoding="utf-8") as f:
                    f.write(current_top_title)
            else:
                # 新着なし
                send_email_bcc([], screenshot_path, is_new=False)

        except Exception as e:
            print(f"⚠️ エラー: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run_notifier()
