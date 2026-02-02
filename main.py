import time
from datetime import datetime, timedelta, timezone
import requests
import feedparser
import google.generativeai as genai
import smtplib
import urllib3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
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
    "해외 과학 (ScienceDaily)": "https://www.sciencedaily.com/rss/all.xml",
    # --- 새로 추가할 핫 이슈 소스 ---
    "글로벌 이슈 (Nature)": "https://www.nature.com/nature.rss",
    "IT/AI 트렌드 (MIT Tech Review)": "https://www.technologyreview.com/feed/"
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


def build_html_template(data):
    """세련된 뉴스레터 양식 생성"""
    # today = datetime.now().strftime("%Y-%m-%d")
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime("%Y-%m-%d")
    
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


def get_ai_summary(news_data):
    print("[*] AI 배치 요약 시작...")
    genai.configure(api_key=GEMINI_API_KEY)

    # 1. 모델 명칭 설정 (아까 확인된 2.5-flash를 사용하되, 앞에 'models/'를 떼고 입력해 보세요)
    # 만약 계속 NotFound가 뜨면 list_models에서 나온 전체 이름(models/...)을 넣어보세요.
    # MODEL_NAME = 'gemini-2.5-flash'
    MODEL_NAME = 'gemini-3-flash-preview'

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        safety_settings=safety_settings,
        generation_config={"response_mime_type": "application/json"},
        # system_instruction="전문 과학 뉴스 요약가로서, 뉴스 리스트를 JSON 형식으로 요약해라. 반드시 {'summaries': [{'id': 0, 'summary': '...'}]} 구조를 지켜라."
        system_instruction="전문 과학 뉴스 요약가로서 생명공학, 인공지능, 우주과학 분야의 기사를 우선순위로 두고, 전문 용어는 주석을 달거나 쉬운 표현으로 풀어서 요약해라, 뉴스 리스트를 JSON 형식으로 요약해라. 반드시 {'summaries': [{'id': 0, 'summary': '...'}]} 구조를 지켜라."
    )

    summarized_data = {}
    for category, articles in news_data.items():
        if not articles: continue

        print(f"[*] '{category}' 요약 요청 중 (ID 매칭 방식)...")

        # 기사들을 하나의 텍스트로 결합
        batch_prompt = "다음 뉴스들을 각각 2문장 내외의 한국어로 요약해서 JSON으로 줘:\n"
        for i, art in enumerate(articles):
            batch_prompt += f"[ID: {i}] 제목: {art['title']}\n내용: {art.get('desc', '')[:400]}\n\n"

        try:
            # [중요] 429 에러 방지: 호출 전 15초 대기 (무료 티어 분당 5회 제한 준수)
            time.sleep(15)
            response = model.generate_content(batch_prompt)

            # AI 응답이 정상인지 확인
            if response.text:
                result_json = json.loads(response.text.strip())
                summaries_list = result_json.get('summaries', [])

                # 결과 매칭
                for item in summaries_list:
                    idx = item.get('id')
                    if idx is not None and idx < len(articles):
                        articles[idx]['ai_summary'] = item.get('summary', "요약 내용 없음")

            # 매칭되지 않은 기사 처리
            for art in articles:
                if 'ai_summary' not in art:
                    art['ai_summary'] = "요약을 가져오지 못했습니다. 원문을 참고하세요."

        except Exception as e:
            print(f"[!] 에러 발생: {str(e)}")
            # 에러 발생 시 모든 기사에 에러 메시지 할당
            for art in articles:
                art['ai_summary'] = f"요약 생성 중 오류 ({MODEL_NAME} 환경 체크 필요)"

        summarized_data[category] = articles

    return summarized_data


def send_email(html_body):
    # 한국 시간대(UTC+9) 정의
    KST = timezone(timedelta(hours=9))
    today_str = datetime.now(KST).strftime("%m/%d")
    
    """최종 메일 발송"""
    msg = MIMEMultipart()
    msg['Subject'] = f"🔬 오늘의 과학 리포트 ({today_str})"
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





