import requests
import feedparser
import google.generativeai as genai
import smtplib
import urllib3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import os

# SSL 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- [설정 영역] ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
receiver_raw = os.environ.get('RECEIVER_EMAIL', '')
receiver_list = [email.strip() for email in receiver_raw.replace(';', ',').split(',') if email.strip()]

# 2. 이메일 설정 (Gmail 권장)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# 가장 안정적인 뉴스 소스로 변경
NEWS_SOURCES = {
    "국내 주요 과학 소식 (Google News)": "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=ko&gl=KR&ceid=KR:ko",
    "해외 과학 (ScienceDaily)": "https://www.sciencedaily.com/rss/all.xml"
}


# ------------------------------------------

def fetch_news():
    """안정적으로 뉴스 데이터를 가져오는 함수"""
    all_news = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}

    for source_name, url in NEWS_SOURCES.items():
        try:
            print(f"[*] {source_name} 수집 중...")
            response = requests.get(url, headers=headers, timeout=15, verify=False)

            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                articles = []
                for entry in feed.entries[:3]:  # 각 소스별 최신 3건
                    articles.append({
                        "title": entry.title,
                        "link": entry.link,
                        "desc": entry.get('summary', entry.get('description', '내용 없음'))[:300]
                    })
                all_news[source_name] = articles
            else:
                print(f"[!] {source_name} 접속 실패 (Status: {response.status_code})")
        except Exception as e:
            print(f"[!] {source_name} 오류 발생: {e}")

    return all_news


def get_ai_summary(news_data):
    """Gemini AI를 통한 핵심 요약 생성"""
    print("[*] AI 요약 생성 중...")
    genai.configure(api_key=GEMINI_API_KEY)
    # model = genai.GenerativeModel('gemini-1.5-flash')  # 속도가 빠른 flash 모델 권장
    model = genai.GenerativeModel('gemini-2.5-flash')  # 속도가 빠른 flash 모델 권장


    summarized_data = {}
    for category, articles in news_data.items():
        summarized_articles = []
        for art in articles:
            prompt = f"다음 뉴스 기사를 읽고 2문장(한국어)로 핵심만 요약해줘.\n제목: {art['title']}\n내용: {art['desc']}"
            # try:
            #     response = model.generate_content(prompt)
            #     art['ai_summary'] = response.text.strip()
            # except:
            #     art['ai_summary'] = "요약을 생성하지 못했습니다. 링크를 참조해 주세요."
            try:
                time.sleep(1)
                response = model.generate_content(prompt)
                # art['ai_summary'] = response.text.strip()
                if response.candidates and response.candidates[0].content.parts:
                    art['ai_summary'] = response.text.strip()
                else:
                    # 3. 만약 차단되었다면 이유 확인 (선택 사항)
                    reason = response.prompt_feedback.block_reason
                    art['ai_summary'] = f"AI 정책에 의해 요약이 제한되었습니다. (사유: {reason})"
            except Exception as e:
                print(f"Error for '{art['title']}': {e}")
                art['ai_summary'] = "요약을 생성하지 못했습니다. 링크를 참조해 주세요."            
            summarized_articles.append(art)
        summarized_data[category] = summarized_articles
    return summarized_data


def build_html_template(data):
    """세련된 뉴스레터 양식 생성"""
    today = datetime.now().strftime("%Y-%m-%d")

    html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 10px; overflow: hidden; color: #333;">
        <div style="background-color: #002d5b; color: #ffffff; padding: 30px 20px; text-align: center;">
            <h2 style="margin: 0; font-size: 24px;">SCIENCE MORNING</h2>
            <p style="margin: 5px 0 0; opacity: 0.7;">{today} 오늘의 과학 이슈 브리핑</p>
        </div>
        <div style="padding: 20px; background-color: #ffffff;">
    """

    for category, articles in data.items():
        html += f"<h3 style='color: #002d5b; border-bottom: 2px solid #002d5b; padding-bottom: 5px; margin-top: 25px;'>{category}</h3>"
        for art in articles:
            html += f"""
            <div style="margin-bottom: 20px; border-bottom: 1px solid #f0f0f0; padding-bottom: 15px;">
                <a href="{art['link']}" style="font-size: 16px; font-weight: bold; color: #0056b3; text-decoration: none;">{art['title']}</a>
                <p style="font-size: 14px; color: #555; line-height: 1.5; margin-top: 8px; padding: 10px; background-color: #f9f9f9; border-radius: 5px;">
                    <b>💡 핵심 요약:</b> {art['ai_summary']}
                </p>
            </div>
            """

    html += """
        </div>
        <div style="background-color: #f4f4f4; padding: 15px; text-align: center; font-size: 12px; color: #888;">
            본 메일은 Python과 Gemini AI에 의해 생성된 자동 뉴스레터입니다.
        </div>
    </div>
    """
    return html


def send_email(html_body):
    """최종 메일 발송"""
    msg = MIMEMultipart()
    msg['Subject'] = f"🔬 오늘의 과학 리포트 ({datetime.now().strftime('%m/%d')})"
    msg['From'] = SENDER_EMAIL
    msg['To'] = ", ".join(receiver_list)
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg, to_addrs=receiver_list)
        print(f"[+] 총 {len(receiver_list)}명에게 발송 성공!")
    except Exception as e:
        print(f"[!] 메일 발송 실패: {e}")


if __name__ == "__main__":
    raw_news = fetch_news()
    if raw_news:
        final_data = get_ai_summary(raw_news)
        email_content = build_html_template(final_data)
        send_email(email_content)
    else:
        print("[!] 수집된 뉴스 데이터가 없어 발송을 중단합니다.")


