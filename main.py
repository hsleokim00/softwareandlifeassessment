import streamlit as st
import datetime as dt
import calendar

# ==== (1) 구글 캘린더용 라이브러리 ====
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 구글 캘린더에서 읽기/쓰기 권한 (필요한 범위만 사용)
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    # 일정 생성까지 할 거면 아래 주석 해제
    # "https://www.googleapis.com/auth/calendar.events"
]


# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)


# ==================== 세션 상태 ====================
today = dt.date.today()

if "google_service" not in st.session_state:
    st.session_state.google_service = None  # 구글 캘린더 서비스 핸들
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# 달력용 상태
if "cal_year" not in st.session_state:
    st.session_state.cal_year = today.year
if "cal_month" not in st.session_state:
    st.session_state.cal_month = today.month
if "selected_date" not in st.session_state:
    st.session_state.selected_date = today


# ==================== 스타일 ====================
st.markdown(
    """
    <style>
    .title-text {
        font-size: 2rem;
        font-weight: 800;
        color: #f5f5f5;
        margin: 0.8rem 0 0.5rem 0;
    }
    .pill-input > div > input {
        border-radius: 999px !important;
    }
    .pill-button > button {
        border-radius: 999px !important;
        font-weight: 600;
        padding: 0.6rem 2.0rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==================== 구글 캘린더 연동 함수 ====================
def get_google_service():
    """
    credentials.json / token.json 을 사용해서
    구글 캘린더 service 객체를 생성.
    - 실제 서비스에서는 OAuth redirect URL 등을 따로 설정해야 함.
    - 수행평가용/로컬 테스트용 구조라고 보면 됨.
    """
    creds = None

    # 1) token.json이 있으면 거기서 토큰 로드
    try:
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    except Exception:
        creds = None

    # 2) 없거나 만료됐으면 새로 인증
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # 새로고침
            try:
                creds.refresh_request  # type: ignore[attr-defined]
            except Exception:
                pass
        else:
            # 여기서 InstalledAppFlow를 사용해서 로컬/서버에서 OAuth 수행
            # Streamlit Cloud에서는 이 부분을 환경에 맞게 조정해야 할 수 있음
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            # 로컬에서 돌린다면 아래처럼 사용 (브라우저 열림)
            creds = flow.run_local_server(port=0)

        # 3) 새 토큰 저장 (다음 실행 시 사용)
        with open("token.json", "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    return service


def fetch_month_event_days(service, year: int, month: int):
    """
    해당 연/월에 일정이 있는 '날짜(day 숫자)'들의 집합 반환.
    달력에 점(•) 표시하는 용도.
    """
    from datetime import datetime, timezone

    start = dt.date(year, month, 1)
    if month == 12:
        end = dt.date(year + 1, 1, 1)
    else:
        end = dt.date(year, month + 1, 1)

    time_min = datetime.combine(start, dt.time(0, 0, 0), tzinfo=timezone.utc).isoformat()
    time_max = datetime.combine(end, dt.time(0, 0, 0), tzinfo=timezone.utc).isoformat()

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    items = events_result.get("items", [])
    days_with_events = set()

    for event in items:
        start_info = event.get("start", {})
        # 종일 일정은 'date', 일반 일정은 'dateTime'
        date_str = start_info.get("date") or start_info.get("dateTime")
        if not date_str:
            continue
        # "2025-11-24" or "2025-11-24T10:00:00+09:00" 형태 → 앞의 날짜 부분만 사용
        date_only = date_str[:10]
        try:
            y, m, d = map(int, date_only.split("-"))
            days_with_events.add(d)
        except Exception:
            continue

    return days_with_events


# ==================== 상단: 제목 + 로그인 ====================
top_left, top_right = st.columns([4, 1])

with top_left:
    st.markdown('<div class="title-text">일정? 바로잡 GO!</div>', unsafe_allow_html=True)

with top_right:
    if st.session_state.google_service is not None:
        st.session_state.logged_in = True

    if st.session_state.logged_in:
        st.success("구글 로그인 완료 ✅")
    else:
        login_clicked = st.button("구글로 로그인")
        if login_clicked:
            try:
                service = get_google_service()
                st.session_state.google_service = service
                st.session_state.logged_in = True
                st.success("구글 로그인 완료 ✅")
            except Exception as e:
                st.error(
                    "구글 캘린더 연동에 실패했습니다. "
                    "credentials.json / token.json 파일이 있는지 확인하세요."
                )
                st.write(e)

st.write("")

# ==================== 가운데: 항상 펼쳐진 달력 + 구글 일정 점 표시 ====================
st.subheader("캘린더")

if not st.session_state.logged_in:
    st.caption("구글 로그인 전에는 날짜만 선택 가능한 일반적인 캘린더입니다.")
else:
    st.caption("구글 캘린더와 연동된 일정이 있는 날에는 ● 표시가 나타납니다.")

year = st.session_state.cal_year
month = st.session_state.cal_month

# ---- 월 이동 헤더 ----
cal_top_left, cal_top_mid, cal_top_right = st.columns([1, 3, 1])

with cal_top_left:
    if st.button("◀ 이전달"):
        if month == 1:
            st.session_state.cal_month = 12
            st.session_state.cal_year -= 1
        else:
            st.session_state.cal_month -= 1

with cal_top_mid:
    st.markdown(f"### {year}년 {month}월")

with cal_top_right:
    if st.button("다음달 ▶"):
        if month == 12:
            st.session_state.cal_month = 1
            st.session_state.cal_year += 1
        else:
            st.session_state.cal_month += 1

# 버튼으로 인해 값이 바뀌었을 수 있으니 다시 읽기
year = st.session_state.cal_year
month = st.session_state.cal_month

# ---- 이 달의 구글 일정 있는 날짜 집합 구하기 ----
days_with_events = set()
if st.session_state.logged_in and st.session_state.google_service is not None:
    try:
        days_with_events = fetch_month_event_days(
            st.session_state.google_service, year, month
        )
    except Exception as e:
        st.warning("구글 일정 정보를 가져오는 데 문제가 발생했습니다.")
        st.write(e)

# ---- 요일 헤더 ----
weekday_cols = st.columns(7)
weekdays = ["일", "월", "화", "수", "목", "금", "토"]
for i, wd in enumerate(weekdays):
    with weekday_cols[i]:
        st.markdown(f"**{wd}**")

# ---- 달력 그리드 (항상 펼쳐진 형태) ----
cal = calendar.Calendar(firstweekday=6)  # 6: 일요일부터
weeks = cal.monthdayscalendar(year, month)

for week in weeks:
    cols = st.columns(7)
    for i, day in enumerate(week):
        with cols[i]:
            if day == 0:
                st.write("")  # 빈 칸
            else:
                date_obj = dt.date(year, month, day)
                selected_date = st.session_state.selected_date

                # 기본 라벨: 날짜 숫자
                label = f"{day}"

                # 선택된 날짜면 []로 감싸서 강조
                if date_obj == selected_date:
                    label = f"[{label}]"

                # 구글 캘린더에 일정이 있으면 ● 점 추가
                if day in days_with_events:
                    label = f"{label} ●"

                if st.button(label, key=f"day-{year}-{month}-{day}"):
                    st.session_state.selected_date = date_obj

st.write("---")

# ==================== 아래: 새 일정 입력 ====================
st.markdown("#### 새 일정 입력")

selected_date = st.session_state.selected_date
st.write(f"선택한 날짜: **{selected_date}**")

c1, c2, c3, c4 = st.columns(4)

with c1:
    title = st.text_input("일정명", key="title", placeholder="예: 수학 학원")

with c2:
    st.markdown('<div class="pill-input">', unsafe_allow_html=True)
    place = st.text_input("장소", key="place", placeholder="예: OO학원")
    st.markdown('</div>', unsafe_allow_html=True)

with c3:
    start_time = st.time_input("시작시간", value=dt.time(18, 0))

with c4:
    end_time = st.time_input("종료시간", value=dt.time(19, 0))

st.write("")

btn_col = st.columns([1, 2, 1])[1]
with btn_col:
    clicked = st.button(
        "입력",
        key="submit",
        disabled=not st.session_state.logged_in,
        help="구글 로그인 후 사용 가능합니다.",
    )

if clicked and st.session_state.logged_in:
    st.success(
        f"새 일정이 준비되었습니다: "
        f"{selected_date} {start_time.strftime('%H:%M')}~{end_time.strftime('%H:%M')} "
        f"/ {title} @ {place}"
    )
    # TODO:
    # 여기에서:
    # 1) selected_date 주변 기존 일정 + 교통/동선 체크
    # 2) 이상 없으면 service.events().insert(...)로 구글 캘린더에 일정 생성
