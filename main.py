import streamlit as st
import datetime as dt
from typing import Optional, List, Dict

# 외부 라이브러리들 (설치 안 되어 있으면 안내만)
try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

try:
    from google.oauth2 import service_account
except ImportError:
    service_account = None

import urllib.parse
import requests

# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ==================== CSS (반응형 + 스타일) ====================
st.markdown(
    """
<style>
.main .block-container {
    max-width: 900px;
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
}

/* 제목 크기 조정 */
.main .block-container h1 {
    font-size: 1.7rem;
}

/* 버튼 공통 스타일 */
.stButton > button {
    border-radius: 999px;
    padding: 0.4rem 1.4rem;
    font-weight: 600;
    border: 1px solid #ddd;
}

/* 카드 */
.card {
    padding: 1rem 1.2rem;
    border-radius: 0.8rem;
    border: 1px solid #e5e5e5;
    background: #fafafa;
    margin-bottom: 1rem;
}

/* 작은 안내 텍스트 */
.subtle {
    font-size: 0.85rem;
    color: #666666;
}

/* 폼 라벨 */
.stForm label {
    font-size: 0.9rem !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ==================== 세션 상태 ====================
if "google_events" not in st.session_state:
    st.session_state.google_events: List[Dict] = []

if "custom_events" not in st.session_state:
    st.session_state.custom_events: List[Dict] = []

if "last_added_event" not in st.session_state:
    st.session_state.last_added_event: Optional[Dict] = None

# ==================== Google Calendar (서비스 계정) ====================
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

def get_calendar_service():
    """서비스 계정 정보로 Google Calendar service 생성"""
    if build is None or service_account is None:
        return None, "google-api-python-client 또는 google-auth 라이브러리가 설치되어 있지 않아요. pip install google-api-python-client google-auth-oauthlib google-auth 를 실행해 주세요."

    try:
        info = st.secrets["google_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=SCOPES,
        )
        service = build("calendar", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"서비스 계정 인증 중 오류가 발생했습니다: {e}"

def fetch_google_events(service, calendar_id: str = "primary", max_results: int = 15):
    """다가오는 Google Calendar 일정 불러오기"""
    now = dt.datetime.utcnow().isoformat() + "Z"
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
    items = events_result.get("items", [])
    parsed = []
    for e in items:
        start_raw = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date")
        end_raw = e.get("end", {}).get("dateTime") or e.get("end", {}).get("date")

        parsed.append(
            {
                "id": e.get("id"),
                "summary": e.get("summary", "(제목 없음)"),
                "start_raw": start_raw,
                "end_raw": end_raw,
                "location": e.get("location", ""),
            }
        )
    return parsed

# ==================== Google Maps Embed / Distance Matrix ====================
def get_maps_api_key() -> Optional[str]:
    try:
        return st.secrets["google_maps"]["api_key"]
    except Exception:
        return None

def render_place_map(location: str, height: int = 300):
    """장소 문자열로 Google Maps Embed (place 검색)"""
    api_key = get_maps_api_key()
    if not api_key:
        st.warning("Google Maps API Key가 secrets.toml의 [google_maps]에 설정되어 있지 않아요.")
        return

    q = urllib.parse.quote(location)
    src = f"https://www.google.com/maps/embed/v1/place?key={api_key}&q={q}"

    st.markdown(
        f"""
        <iframe
            width="100%"
            height="{height}"
            style="border:0; border-radius: 12px;"
            loading="lazy"
            allowfullscreen
            referrerpolicy="no-referrer-when-downgrade"
            src="{src}">
        </iframe>
        """,
        unsafe_allow_html=True,
    )

def render_directions_map(origin: str, destination: str, mode: str = "transit", height: int = 320):
    """두 장소 사이의 길찾기 지도를 Embed API로 표시"""
    api_key = get_maps_api_key()
    if not api_key:
        st.warning("Google Maps API Key가 secrets.toml의 [google_maps]에 설정되어 있지 않아요.")
        return

    o = urllib.parse.quote(origin)
    d = urllib.parse.quote(destination)
    mode = mode or "transit"

    src = f"https://www.google.com/maps/embed/v1/directions?key={api_key}&origin={o}&destination={d}&mode={mode}"

    st.markdown(
        f"""
        <iframe
            width="100%"
            height="{height}"
            style="border:0; border-radius: 12px;"
            loading="lazy"
            allowfullscreen
            referrerpolicy="no-referrer-when-downgrade"
            src="{src}">
        </iframe>
        """,
        unsafe_allow_html=True,
    )

def get_travel_time_minutes(origin: str, destination: str, mode: str = "transit") -> Optional[float]:
    """Google Distance Matrix API로 이동 시간(분)을 계산"""
    api_key = get_maps_api_key()
    if not api_key:
        return None

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "mode": mode,
        "units": "metric",
        "key": api_key,
    }

    try:
        resp = requests.get(url, params=params)
        data = resp.json()
        rows = data.get("rows", [])
        if not rows:
            return None
        elements = rows[0].get("elements", [])
        if not elements:
            return None
        el = elements[0]
        if el.get("status") != "OK":
            return None
        seconds = el["duration"]["value"]
        return seconds / 60.0
    except Exception:
        return None

# ==================== 날짜/시간 포맷 ====================
def parse_iso_or_date(s: str) -> dt.datetime:
    """Google Calendar의 dateTime 또는 date 문자열을 datetime으로 변환"""
    if "T" in s:
        # dateTime
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    else:
        # date only → 하루의 시작으로 가정
        d = dt.date.fromisoformat(s)
        return dt.datetime.combine(d, dt.time.min)

def format_event_time_str(start_raw: str, end_raw: str) -> str:
    try:
        start_dt = parse_iso_or_date(start_raw)
        end_dt = parse_iso_or_date(end_raw)
        if start_dt.date() == end_dt.date():
            return f"{start_dt.strftime('%Y-%m-%d %H:%M')} ~ {end_dt.strftime('%H:%M')}"
        else:
            return f"{start_dt.strftime('%Y-%m-%d %H:%M')} ~ {end_dt.strftime('%Y-%m-%d %H:%M')}"
    except Exception:
        return f"{start_raw} → {end_raw}"

# ==================== UI 시작 ====================
st.title("📅 일정? 바로잡 GO!")
st.markdown(
    "<p class='subtle'>Google Calendar와 Google Maps를 함께 써서, "
    "내 일정 사이의 이동 가능 시간과 동선을 직관적으로 확인해 봅니다.</p>",
    unsafe_allow_html=True,
)

# ---------- 1. Google Calendar 불러오기 ----------
st.markdown("### 1. Google Calendar 연동 (서비스 계정)")

col_btn, col_help = st.columns([1, 2])

with col_btn:
    if st.button("🔄 Google Calendar 일정 불러오기", use_container_width=True):
        service, err = get_calendar_service()
        if err:
            st.error(err)
        elif not service:
            st.error("캘린더 service를 만들 수 없어요.")
        else:
            try:
                events = fetch_google_events(service, calendar_id="primary")
                st.session_state.google_events = events
                if events:
                    st.success(f"다가오는 일정 {len(events)}개를 불러왔어요.")
                else:
                    st.info("다가오는 일정이 없습니다.")
            except Exception as e:
                st.error(f"캘린더 이벤트를 불러오는 중 오류: {e}")

with col_help:
    st.markdown(
        """
        <div class="card">
        <b>서비스 계정 방식 안내</b><br/>
        • 이 앱은 미리 등록된 <b>서비스 계정</b>으로 캘린더에 접근해요.<br/>
        • Google Calendar 설정 > 공유에서 이 서비스 계정 이메일에
          <b>읽기 권한</b>을 주면, 해당 계정의 일정이 여기로 가져와집니다.<br/>
        • 시연용으로 안정적이고, 별도의 로그인 팝업이 뜨지 않아요.
        </div>
        """,
        unsafe_allow_html=True,
    )

if st.session_state.google_events:
    with st.expander("📆 불러온 Google Calendar 일정 목록", expanded=True):
        for ev in st.session_state.google_events:
            line = f"**{ev['summary']}**  \n"
            line += f"⏰ {format_event_time_str(ev['start_raw'], ev['end_raw'])}"
            if ev.get("location"):
                line += f"  \n📍 {ev['location']}"
            st.markdown(line)
else:
    st.info("아직 불러온 Google 일정이 없어요. 위 버튼을 눌러 가져와 주세요.")

st.markdown("---")

# ---------- 2. 지금 추가할 일정 입력 + 지도 ----------
st.markdown("### 2. 새 일정 입력 + 위치 지도 보기")

today = dt.date.today()

with st.form("add_event_form"):
    title = st.text_input("일정 제목", placeholder="예) 학원 수업, 동아리 모임 등")
    date = st.date_input("날짜", value=today)
    start_time = st.time_input("시작 시간", value=dt.time(15, 0))
    end_time = st.time_input("끝나는 시간", value=dt.time(16, 0))
    location = st.text_input("일정 장소 (지도에 표시됩니다)", placeholder="예) 서울역, 강남역 2호선, 학교 이름 등")
    memo = st.text_area("메모 (선택)", placeholder="간단한 메모를 적을 수 있어요.")

    submitted = st.form_submit_button("➕ 이 일정 화면에 추가")

    if submitted:
        if not title.strip():
            st.warning("일정 제목은 반드시 입력해 주세요.")
        else:
            new_event = {
                "summary": title.strip(),
                "date": date,
                "start_time": start_time,
                "end_time": end_time,
                "location": location.strip(),
                "memo": memo.strip(),
            }
            st.session_state.custom_events.append(new_event)
            st.session_state.last_added_event = new_event
            st.success("새 일정을 화면 내 목록에 추가했어요. (Google Calendar에는 직접 쓰지 않습니다.)")

# 입력한 위치가 있다면 바로 아래에 지도 표시
if st.session_state.last_added_event and st.session_state.last_added_event.get("location"):
    st.markdown("#### 🗺 방금 추가한 일정 위치")
    loc = st.session_state.last_added_event["location"]
    st.write(f"📍 {loc}")
    render_place_map(loc)
else:
    st.info("위 폼에서 장소를 입력하고 일정을 추가하면 여기에 지도가 표시됩니다.")

st.markdown("---")

# ---------- 3. 기존 일정과 새 일정 사이 동선/이동시간 확인 ----------
st.markdown("### 3. 기존 일정 ↔ 새 일정 동선·이동시간 확인")

google_events_with_location = [
    ev for ev in st.session_state.google_events if ev.get("location")
]

if not google_events_with_location:
    st.info("위에서 불러온 Google 일정 중에 위치 정보가 있는 일정이 없어요.")
else:
    left, right = st.columns(2)
    with left:
        base_event_label = st.selectbox(
            "기준이 될 기존 일정 선택 (위치 정보 있는 일정만 표시)",
            options=google_events_with_location,
            format_func=lambda ev: f"{ev['summary']} | {format_event_time_str(ev['start_raw'], ev['end_raw'])}",
        )

        mode = st.selectbox(
            "이동 수단(모드)",
            options=[
                ("대중교통", "transit"),
                ("자동차", "driving"),
                ("도보", "walking"),
                ("자전거", "bicycling"),
            ],
            format_func=lambda x: x[0],
        )
        mode_value = mode[1]

    with right:
        if st.session_state.last_added_event:
            new_ev = st.session_state.last_added_event
            st.markdown(
                f"""
                <div class="card">
                <b>새 일정</b><br/>
                제목: {new_ev['summary']}<br/>
                날짜: {new_ev['date']}<br/>
                시간: {new_ev['start_time'].strftime('%H:%M')} ~ {new_ev['end_time'].strftime('%H:%M')}<br/>
                장소: {new_ev['location'] or '(입력 없음)'}
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.info("아직 새 일정이 없습니다. 위에서 일정을 하나 추가해 주세요.")

    if st.session_state.last_added_event and base_event_label:
        base_loc = base_event_label["location"]
        new_loc = st.session_state.last_added_event["location"]

        if not new_loc:
            st.warning("새 일정에 장소가 입력되어 있어야 이동경로를 계산할 수 있어요.")
        else:
            st.markdown("#### 🚏 이동 경로 지도")
            st.write(f"출발: {base_loc}")
            st.write(f"도착: {new_loc}")
            render_directions_map(base_loc, new_loc, mode=mode_value)

            # 이동 시간 계산 + 일정 간 간격 비교
            travel_min = get_travel_time_minutes(base_loc, new_loc, mode=mode_value)

            try:
                base_end_dt = parse_iso_or_date(base_event_label["end_raw"])
                new_start_dt = dt.datetime.combine(
                    st.session_state.last_added_event["date"],
                    st.session_state.last_added_event["start_time"],
                )
                gap_min = (new_start_dt - base_end_dt).total_seconds() / 60.0
            except Exception:
                gap_min = None

            if travel_min is not None and gap_min is not None:
                st.markdown("#### ⏱ 이동 시간 vs 일정 간격")

                st.write(f"- 예상 이동 시간: **약 {travel_min:.0f}분**")
                st.write(f"- 기존 일정 종료 → 새 일정 시작 사이 간격: **약 {gap_min:.0f}분**")

                # 1시간 여유를 기준으로 추천
                buffer = gap_min - travel_min
                need_extra = 60 - buffer  # 1시간 여유를 확보하기 위해 더 필요한 시간

                if buffer >= 60:
                    st.success(
                        "이동 시간과 1시간 여유를 고려했을 때, 일정 간 간격이 충분해 보여요. "
                        "현재 시간대로 진행해도 무리가 없을 것 같아요."
                    )
                else:
                    delay_min = max(0, int(need_extra))
                    st.warning(
                        f"이동 시간에 비해 일정 간 간격이 부족해 보여요. "
                        f"1시간 여유를 확보하려면 새 일정을 **약 {delay_min}분 정도 뒤로 미루는 것**을 추천합니다."
                    )
            else:
                st.info("이동 시간 또는 일정 간 간격을 계산할 수 없어서, 텍스트 추천은 생략했어요.")
