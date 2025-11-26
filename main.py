import streamlit as st
import datetime as dt
from typing import Optional, List, Dict
import urllib.parse
import requests

# google API client
try:
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
except ImportError:
    build = None
    service_account = None


# ==================== 캘린더 ID ====================
CALENDAR_ID = "YOUR_GMAIL_ADDRESS_HERE"   # ← Gmail로 변경

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


# ==================== Streamlit 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ==================== 네이티브 앱 스타일 CSS ====================
st.markdown("""
<style>

:root {
    --mint: #36CFC9;
    --mint-light: #8ef0ec;
    --text-dark: #222;
    --bg-light: #f8fffe;
}

/* 전체 배경 */
body {
    background-color: var(--bg-light);
}

/* 상단 AppBar */
.appbar {
    position: sticky;
    top: 0;
    background-color: white;
    padding: 0.9rem 1.2rem;
    font-size: 1.3rem;
    font-weight: 600;
    color: var(--mint);
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
    z-index: 50;
    border-bottom: 2px solid var(--mint-light);
    border-radius: 0 0 14px 14px;
}

/* Section Sheet */
.sheet {
    margin-top: 1.2rem;
    padding: 1.4rem 1.4rem;
    background: white;
    border-radius: 14px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}

/* 버튼 */
.stButton > button {
    background-color: var(--mint);
    color: white;
    border-radius: 14px;
    border: none;
    padding: 0.7rem 1.5rem;
    font-weight: 600;
    width: 100%;
    font-size: 1.05rem;
    transition: 0.15s ease-in-out;
}

.stButton > button:hover {
    background-color: var(--mint-light);
    color: #004443;
}

/* 입력창 */
.stTextInput > div > div > input,
.stTextArea > div > textarea,
.stDateInput > div > input,
.stTimeInput > div > input {
    border-radius: 12px !important;
    border: 1.8px solid #d6d6d6 !important;
}

.stTextInput > div > div > input:focus-visible {
    border-color: var(--mint) !important;
}

/* 지도 iframe 반응형 */
.mapframe {
    width: 100%;
    border-radius: 14px;
    border: none;
}

/* 모바일 최적화 */
@media (max-width: 640px) {
    .sheet {
        padding: 1.0rem 1.0rem;
    }
    .appbar {
        font-size: 1.2rem;
    }
    iframe {
        height: 260px !important;
    }
}

</style>
""", unsafe_allow_html=True)


# ==================== 세션 상태 ====================
if "google_events" not in st.session_state:
    st.session_state.google_events: List[Dict] = []

if "custom_events" not in st.session_state:
    st.session_state.custom_events: List[Dict] = []

if "last_added_event" not in st.session_state:
    st.session_state.last_added_event: Optional[Dict] = None


# ==================== API 키 ====================
def get_maps_api_key() -> Optional[str]:
    try:
        return st.secrets["google_maps"]["api_key"]
    except:
        return None


# ==================== Google Calendar ====================
def get_calendar_service():
    if build is None:
        return None, "google-api-python-client 설치 필요"

    try:
        info = st.secrets["google_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        return build("calendar", "v3", credentials=creds), None
    except Exception as e:
        return None, f"Calendar 인증 오류: {e}"


def fetch_google_events(service, calendar_id=CALENDAR_ID, max_results=50):
    today_kst = dt.datetime.now().replace(hour=0, minute=0, second=0)
    today_utc = today_kst - dt.timedelta(hours=9)
    time_min = today_utc.isoformat() + "Z"

    items = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )

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


# ==================== 날짜 처리 ====================
def parse_iso_or_date(s: str) -> dt.datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")

    try:
        return dt.datetime.fromisoformat(s)
    except:
        d = dt.date.fromisoformat(s)
        return dt.datetime.combine(d, dt.time.min)


def format_event_time_str(start, end):
    s = parse_iso_or_date(start)
    e = parse_iso_or_date(end)
    if s.date() == e.date():
        return f"{s.strftime('%Y-%m-%d %H:%M')} ~ {e.strftime('%H:%M')}"
    return f"{s.strftime('%Y-%m-%d %H:%M')} ~ {e.strftime('%Y-%m-%d %H:%M')}"


# ==================== Places API ====================
def places_autocomplete(text: str):
    key = get_maps_api_key()
    if not key or not text.strip():
        return []

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": text,
        "key": key,
        "language": "ko",
        "components": "country:kr",
    }
    data = requests.get(url, params=params).json()
    if data.get("status") != "OK":
        return []
    return [
        {"description": p.get("description"), "place_id": p.get("place_id")}
        for p in data.get("predictions", [])
    ]


# ==================== Distance Matrix ====================
def get_travel_time_minutes(origin, dest, mode="transit"):
    key = get_maps_api_key()
    if not key:
        return None

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": dest,
        "mode": mode,
        "units": "metric",
        "key": key,
    }
    try:
        data = requests.get(url, params=params).json()
        row = data.get("rows", [{}])[0]
        element = row.get("elements", [{}])[0]
        if element.get("status") != "OK":
            return None
        return element["duration"]["value"] / 60.0
    except:
        return None


# ==================== 지도 Embed ====================
def render_place_map(query, height_mobile=260, height_pc=360):
    key = get_maps_api_key()
    if not key:
        return
    q = urllib.parse.quote(query)
    src = f"https://www.google.com/maps/embed/v1/place?key={key}&q={q}"

    st.markdown(f"""
        <iframe class="mapframe"
        height="{height_pc}"
        src="{src}">
        </iframe>
    """, unsafe_allow_html=True)


def render_directions_map(origin, dest, mode="transit"):
    key = get_maps_api_key()
    if not key:
        return
    o = urllib.parse.quote(origin)
    d = urllib.parse.quote(dest)
    src = f"https://www.google.com/maps/embed/v1/directions?key={key}&origin={o}&destination={d}&mode={mode}"

    st.markdown(f"""
        <iframe class="mapframe"
        height="360"
        src="{src}">
        </iframe>
    """, unsafe_allow_html=True)


# ==================== UI ====================

st.markdown('<div class="appbar">📅 일정? 바로잡 GO!</div>', unsafe_allow_html=True)

# ---------- 1. 캘린더 불러오기 ----------
with st.container():
    st.markdown('<div class="sheet">', unsafe_allow_html=True)

    st.markdown("### 🔄 Google Calendar 불러오기")

    if st.button("오늘 이후 일정 불러오기"):
        service, err = get_calendar_service()
        if err:
            st.error(err)
        else:
            st.session_state.google_events = fetch_google_events(service)
            st.success(f"{len(st.session_state.google_events)}개 불러옴")

    today = dt.date.today()
    selected_date = st.date_input("날짜별 일정 보기", value=today)

    # 날짜별 일정 출력
    day_events = []
    for ev in st.session_state.google_events:
        try:
            if parse_iso_or_date(ev["start_raw"]).date() == selected_date:
                day_events.append(ev)
        except:
            pass

    if day_events:
        for ev in day_events:
            st.markdown(
                f"- **{ev['summary']}**  \n"
                f"  ⏰ {format_event_time_str(ev['start_raw'], ev['end_raw'])}"
                + (f"  \n📍 {ev['location']}" if ev["location"] else "")
            )
    else:
        st.markdown("선택 날짜 일정 없음")

    st.markdown("</div>", unsafe_allow_html=True)


# ---------- 2. 새 일정 입력 ----------
with st.container():
    st.markdown('<div class="sheet">', unsafe_allow_html=True)

    st.markdown("### ➕ 새 일정 추가")

    with st.form("addevent"):
        title = st.text_input("제목")
        date = st.date_input("날짜", value=today)
        start = st.time_input("시작", value=dt.time(9, 0))
        end = st.time_input("종료", value=dt.time(10, 0))

        loc = st.text_input("장소 입력 (자동완성 지원)")
        auto = places_autocomplete(loc) if loc else []

        chosen_place = None
        chosen_desc = None

        if auto:
            idx = st.radio(
                "자동완성 결과",
                options=list(range(len(auto))),
                format_func=lambda i: auto[i]["description"],
            )
            chosen_place = auto[idx]["place_id"]
            chosen_desc = auto[idx]["description"]

        memo = st.text_area("메모", placeholder="선택 입력")

        submit_new = st.form_submit_button("추가하기")

        if submit_new:
            final_loc = chosen_desc if chosen_desc else loc
            st.session_state.last_added_event = {
                "summary": title,
                "date": date,
                "start_time": start,
                "end_time": end,
                "location": final_loc,
                "place_id": chosen_place,
                "memo": memo,
            }
            st.success("새 일정 추가됨!")

    # 지도 표시
    if st.session_state.last_added_event:
        if st.session_state.last_added_event["location"]:
            st.markdown("#### 🗺 새 일정 위치")
            render_place_map(st.session_state.last_added_event["location"])

    st.markdown("</div>", unsafe_allow_html=True)


# ---------- 3. 기존 일정 ↔ 새 일정 비교 ----------
with st.container():
    st.markdown('<div class="sheet">', unsafe_allow_html=True)
    st.markdown("### 🚏 기존 일정 ↔ 새 일정 비교")

    base_candidates = [ev for ev in st.session_state.google_events if ev["location"]]

    if not base_candidates:
        st.info("위치가 있는 기존 일정 없음")
    else:
        base_ev = st.selectbox(
            "기준 일정 선택",
            options=base_candidates,
            format_func=lambda e: f"{e['summary']} | {format_event_time_str(e['start_raw'], e['end_raw'])}",
        )

        ne = st.session_state.last_added_event
        if not ne:
            st.info("새 일정을 먼저 추가하세요")
        else:
            mode_label, mode_value = st.selectbox(
                "이동 수단",
                options=[
                    ("대중교통", "transit"),
                    ("자동차", "driving"),
                    ("도보", "walking"),
                    ("자전거", "bicycling"),
                ],
                format_func=lambda x: x[0],
            )

            # 지도
            st.markdown("#### 🗺 이동 경로")
            render_directions_map(base_ev["location"], ne["location"], mode=mode_value)

            # 이동시간
            dest_param = (
                f"place_id:{ne['place_id']}"
                if ne.get("place_id")
                else ne["location"]
            )

            travel = get_travel_time_minutes(
                base_ev["location"], dest_param, mode_value
            )

            # 시간 간격 계산
            base_end = parse_iso_or_date(base_ev["end_raw"])
            new_start = dt.datetime.combine(ne["date"], ne["start_time"])

            if base_end.tzinfo:
                base_end_naive = base_end.replace(tzinfo=None)
            else:
                base_end_naive = base_end

            gap = (new_start - base_end_naive).total_seconds() / 60.0

            st.markdown("#### 🕒 시간 비교 결과")

            if travel is not None:
                st.write(f"- 이동 시간: **{travel:.0f}분**")
            else:
                st.write("- 이동 시간 계산 불가")

            st.write(f"- 일정 간 간격: **{gap:.0f}분**")

            # 추천
            if travel is not None:
                buffer = gap - travel
                need_extra = 60 - buffer
                if buffer >= 60:
                    st.success("충분한 간격! 그대로 진행해도 좋아요.")
                else:
                    st.warning(
                        f"간격이 부족해요. 새 일정을 **약 {int(need_extra)}분 뒤로 미루는 것**을 추천합니다."
                    )

    st.markdown("</div>", unsafe_allow_html=True)
