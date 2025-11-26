import streamlit as st
import datetime as dt
import calendar
from typing import List, Dict, Optional
import urllib.parse
import requests
import streamlit.components.v1 as components

# google-api-python-client이 아직 설치 안 되어 있어도 에러 안 나게 처리
try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

# 서비스 계정 인증용
try:
    from google.oauth2 import service_account
except ImportError:
    service_account = None

# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ==================== CSS (반응형 + 스타일) ====================
st.markdown("""
<style>
/* 메인 컨테이너 */
.main .block-container {
    max-width: 900px;
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
}

/* 제목 폰트 조금 줄이기 */
.main .block-container h1 {
    font-size: 1.7rem;
}

/* 버튼 스타일 */
.stButton > button {
    border-radius: 999px;
    padding: 0.4rem 1.4rem;
    font-weight: 600;
    border: 1px solid #ddd;
}

/* 구글 로그인 버튼 전용 스타일 */
.google-login-btn > button {
    background: white;
    border-radius: 999px;
    padding: 0.5rem 1.6rem;
    font-weight: 600;
    border: 1px solid #ccc;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

/* 작은 안내 텍스트 */
.subtle {
    font-size: 0.85rem;
    color: #666666;
}

/* 카드 박스 */
.card {
    padding: 1rem 1.2rem;
    border-radius: 0.8rem;
    border: 1px solid #e5e5e5;
    background: #fafafa;
    margin-bottom: 1rem;
}

/* 폼 안의 라벨 간격 조정 */
.stForm label {
    font-size: 0.9rem !important;
}
</style>
""", unsafe_allow_html=True)

# ==================== 세션 상태 초기화 ====================
today = dt.date.today()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "google_events" not in st.session_state:
    st.session_state.google_events = []

if "custom_events" not in st.session_state:
    st.session_state.custom_events = []  # 사용자가 화면에서 추가한 일정 (로컬용)


# ==================== Google Calendar 연동 함수 ====================
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

def get_calendar_service():
    """서비스 계정 + google-api-python-client 로 캘린더 service 생성"""
    if build is None or service_account is None:
        return None, "google-api-python-client 또는 google-auth 라이브러리가 설치되어 있지 않아요."

    try:
        # secrets.toml 의 [google_service_account] 사용
        info = st.secrets["google_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=SCOPES,
        )
        service = build("calendar", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"서비스 계정 인증 중 오류: {e}"

def fetch_google_events(service, calendar_id: str = "primary", max_results: int = 20):
    """Google Calendar에서 다가오는 일정 불러오기 (읽기 전용)"""
    now = dt.datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = events_result.get("items", [])
    parsed = []
    for e in events:
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date")
        end = e.get("end", {}).get("dateTime") or e.get("end", {}).get("date")
        parsed.append(
            {
                "summary": e.get("summary", "(제목 없음)"),
                "start": start,
                "end": end,
                "location": e.get("location", ""),
            }
        )
    return parsed


# ==================== UI 시작 ====================
st.title("📅 일정? 바로잡 GO!")

st.markdown(
    "<p class='subtle'>Google Calendar에 연동해서 오늘·다가오는 일정을 확인하고, "
    "화면 안에서 추가 일정도 함께 관리할 수 있어요.</p>",
    unsafe_allow_html=True,
)

# ---------- 1. 구글 로그인(서비스 계정 기반) ----------
st.markdown("### 1. Google 계정 연동")

col_login, col_info = st.columns([1, 2])

with col_login:
    # 👇 여기가 "구글로 로그인" 버튼 부분
    with st.container():
        login_btn = st.button("🔐 Google로 로그인", key="google_login_btn")
        # 버튼을 구글 스타일로 보이게 하기 위해 클래스 부여
        st.markdown(
            """
            <script>
            const btns = window.parent.document.querySelectorAll('button[kind="secondary"]');
            </script>
            """,
            unsafe_allow_html=True,
        )

    if login_btn:
        service, err = get_calendar_service()
        if err:
            st.error(err)
        elif not service:
            st.error("캘린더 service를 만들 수 없어요.")
        else:
            try:
                # 👉 calendar_id는 기본적으로 "primary" 사용
                # 개인 캘린더를 서비스 계정에 공유했다면 primary로도 접근 가능
                events = fetch_google_events(service, calendar_id="primary")
                st.session_state.google_events = events
                st.session_state.logged_in = True
                st.success("Google Calendar 연동에 성공했어요! 아래에서 일정을 확인해 주세요.")
            except Exception as e:
                st.error(f"캘린더 이벤트를 불러오는 중 오류가 발생했습니다: {e}")

with col_info:
    if not st.session_state.logged_in:
        st.markdown(
            """
            <div class='card'>
            <b>로그인 안내</b><br/>
            • 이 버튼은 서비스 계정을 통해 네 캘린더에 접근해요.<br/>
            • Google Calendar 설정에서, 이 서비스 계정 이메일을 <b>공유</b>에 추가해야 해요.<br/>
            • 공유가 되어 있으면, ‘primary’ 캘린더의 다가오는 일정이 자동으로 불러와집니다.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='card'><b>로그인 완료!</b><br/>이제 아래에서 Google 일정과 "
            "직접 입력한 일정을 함께 볼 수 있어요.</div>",
            unsafe_allow_html=True,
        )

st.markdown("---")

# ---------- 2. 일정 추가 폼 ----------
st.markdown("### 2. 지금 일정 추가하기 (화면 내 관리용)")

with st.form(key="add_schedule_form"):
    title = st.text_input("일정 제목", placeholder="예) 수학 시험, 친구랑 약속")
    date = st.date_input("날짜 선택", value=today)
    start_time = st.time_input("시작 시간", value=dt.time(9, 0))
    end_time = st.time_input("종료 시간", value=dt.time(10, 0))
    location = st.text_input("장소 (선택)", placeholder="예) 학교, 카페, Zoom 링크 등")
    memo = st.text_area("메모 (선택)", placeholder="추가로 적고 싶은 내용을 자유롭게 써 주세요.")

    submitted = st.form_submit_button("➕ 이 일정 추가하기")

    if submitted:
        if not title.strip():
            st.warning("일정 제목은 반드시 입력해 주세요.")
        else:
            st.session_state.custom_events.append(
                {
                    "summary": title.strip(),
                    "date": date,
                    "start_time": start_time,
                    "end_time": end_time,
                    "location": location.strip(),
                    "memo": memo.strip(),
                }
            )
            st.success("화면 내 일정 목록에 추가했어요! (Google Calendar에는 아직 쓰지 않아요.)")

st.markdown("---")

# ---------- 3. 오늘 & 다가오는 일정 보기 ----------
st.markdown("### 3. 오늘 & 다가오는 일정 한눈에 보기")

def format_time_range(date, start_time: Optional[dt.time], end_time: Optional[dt.time]) -> str:
    if start_time and end_time:
        return f"{date} {start_time.strftime('%H:%M')}–{end_time.strftime('%H:%M')}"
    elif start_time:
        return f"{date} {start_time.strftime('%H:%M')}"
    else:
        return str(date)

# (1) Google Calendar에서 가져온 일정
if st.session_state.logged_in and st.session_state.google_events:
    with st.expander("📆 Google Calendar에서 불러온 일정 보기", expanded=True):
        for ev in st.session_state.google_events:
            st.markdown(
                f"- **{ev['summary']}**  "
                f"({ev['start']} → {ev['end']})"
                + (f" @ {ev['location']}" if ev.get("location") else "")
            )
else:
    st.info("아직 Google Calendar 일정이 없거나, 로그인 후 일정이 불러와지지 않았어요.")

# (2) 화면 내에서 추가한 커스텀 일정
st.markdown("#### ✍ 내가 이 화면에서 직접 추가한 일정들")

if st.session_state.custom_events:
    for ev in sorted(st.session_state.custom_events, key=lambda x: (x["date"], x["start_time"])):
        time_str = format_time_range(ev["date"], ev["start_time"], ev["end_time"])
        st.markdown(
            f"- **{ev['summary']}**  \n"
            f"  ⏰ {time_str}"
            + (f"  \n  📍 {ev['location']}" if ev["location"] else "")
            + (f"  \n  📝 {ev['memo']}" if ev["memo"] else "")
        )
else:
    st.write("아직 화면 내에 추가한 일정이 없어요. 위 폼에서 일정을 하나 추가해 볼까요?")

# ==================== 끝 ====================
