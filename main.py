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
CALENDAR_ID = "dlspike520@gmail.com"   # ← 반드시 Gmail 주소로 변경

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


# ==================== Streamlit UI 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

st.markdown("""
<style>
.main .block-container {
    max-width: 900px;
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
}
.stButton > button {
    border-radius: 999px;
    padding: 0.4rem 1.4rem;
    font-weight: 600;
    border: 1px solid #ddd;
}
.card {
    padding: 1rem 1.2rem;
    border-radius: 0.8rem;
    border: 1px solid #e5e5e5;
    background: #fafafa;
    margin-bottom: 1rem;
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
        service = build("calendar", "v3", credentials=creds)
        return service, None
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
    if not s:
        raise ValueError()

    s = s.strip()
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")

    try:
        return dt.datetime.fromisoformat(s)
    except:
        pass

    try:
        d = dt.date.fromisoformat(s)
        return dt.datetime.combine(d, dt.time.min)
    except:
        raise ValueError("지원하지 않는 날짜 형식")


def format_event_time_str(start_raw, end_raw):
    s = parse_iso_or_date(start_raw)
    e = parse_iso_or_date(end_raw)
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

    try:
        data = requests.get(url, params=params, timeout=5).json()
        if data.get("status") != "OK":
            return []
        return [
            {
                "description": p.get("description", ""),
                "place_id": p.get("place_id"),
            }
            for p in data.get("predictions", [])
        ]
    except:
        return []


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
        data = requests.get(url, params=params, timeout=5).json()
        elements = data.get("rows", [{}])[0].get("elements", [{}])
        el = elements[0]
        if el.get("status") != "OK":
            return None
        return el["duration"]["value"] / 60.0
    except:
        return None


# ==================== 지도 Embed ====================
def render_place_map(query, height=320):
    key = get_maps_api_key()
    if not key:
        return
    q = urllib.parse.quote(query)
    src = f"https://www.google.com/maps/embed/v1/place?key={key}&q={q}"

    st.markdown(f"""
        <iframe width="100%" height="{height}"
        style="border:0; border-radius:12px;"
        loading="lazy"
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
        <iframe width="100%" height="320"
        style="border:0; border-radius:12px;"
        loading="lazy"
        src="{src}">
        </iframe>
    """, unsafe_allow_html=True)


# ==================== UI 시작 ====================
st.title("📅 일정? 바로잡 GO!")

st.markdown(
    "Google Calendar 일정과 내가 입력한 새 일정의 <b>거리·이동시간·간격</b>을 비교합니다.",
    unsafe_allow_html=True
)
# ---------- 1. Google Calendar 불러오기 ----------
st.markdown("### 1. Google Calendar 불러오기 (오늘 이후 일정)")

today = dt.date.today()

if st.button("🔄 캘린더에서 다가오는 일정 불러오기", use_container_width=True):
    service, err = get_calendar_service()
    if err:
        st.error(err)
    elif not service:
        st.error("캘린더 인증 실패")
    else:
        try:
            events = fetch_google_events(service)
            st.session_state.google_events = events
            st.success(f"오늘 이후 일정 {len(events)}개 불러옴")
        except Exception as e:
            st.error(f"불러오기 오류: {e}")


selected_date = st.date_input("날짜별 일정 보기", value=today)

# 선택 날짜 일정 필터링
selected_day_events = []
for ev in st.session_state.google_events:
    try:
        dt_start = parse_iso_or_date(ev["start_raw"])
        if dt_start.date() == selected_date:
            selected_day_events.append(ev)
    except:
        pass

if selected_day_events:
    st.markdown("#### 📅 선택 날짜 일정")
    for ev in selected_day_events:
        st.markdown(
            f"- **{ev['summary']}**  \n"
            f"  ⏰ {format_event_time_str(ev['start_raw'], ev['end_raw'])}"
            + (f"  \n📍 {ev['location']}" if ev.get("location") else "")
        )
else:
    st.markdown("_선택한 날짜에는 일정이 없습니다._")

# 전체 일정 보기
if st.session_state.google_events:
    with st.expander("오늘 이후 전체 일정 보기"):
        for ev in st.session_state.google_events:
            line = f"**{ev['summary']}**  \n"
            line += f"⏰ {format_event_time_str(ev['start_raw'], ev['end_raw'])}"
            if ev.get("location"):
                line += f"  \n📍 {ev['location']}"
            st.markdown(line)
else:
    st.info("캘린더 일정이 없습니다. 먼저 불러오세요.")

st.markdown("---")


# ---------- 2. 새 일정 입력 ----------
st.markdown("### 2. 새 일정 추가 (주소 자동완성)")

with st.form("add_event_form"):
    title = st.text_input("일정 제목", placeholder="예: 과외, 학원, 스터디 등")

    date = st.date_input("날짜", value=today, key="new_event_date")

    start_time = st.time_input("시작 시간", value=dt.time(9, 0))
    end_time = st.time_input("종료 시간", value=dt.time(10, 0))

    loc_input = st.text_input(
        "장소 입력 (자동완성 지원)", placeholder="예: 서울시청, 강남역 2번출구"
    )

    # 자동완성 (DEBUG 제거 버전)
    auto_results = []
    chosen_idx = None
    chosen_place_id = None
    chosen_desc = None

    if loc_input.strip():
        auto_results = places_autocomplete(loc_input)

        if auto_results:
            chosen_idx = st.radio(
                "주소 자동완성 결과",
                options=list(range(len(auto_results))),
                format_func=lambda i: auto_results[i]["description"],
            )
            chosen_place_id = auto_results[chosen_idx]["place_id"]
            chosen_desc = auto_results[chosen_idx]["description"]
        else:
            st.caption("자동완성 결과 없음")

    memo = st.text_area("메모 (선택)", placeholder="선택 입력")

    submitted = st.form_submit_button("➕ 새 일정 추가")

    if submitted:
        if not title.strip():
            st.warning("제목을 반드시 입력하세요.")
        else:
            final_loc = chosen_desc if chosen_desc else loc_input.strip()
            final_place = chosen_place_id if chosen_place_id else None

            new_event = {
                "summary": title.strip(),
                "date": date,
                "start_time": start_time,
                "end_time": end_time,
                "location": final_loc,
                "place_id": final_place,
                "memo": memo.strip(),
            }

            st.session_state.custom_events.append(new_event)
            st.session_state.last_added_event = new_event
            st.success("새 일정이 화면에 추가되었습니다!")


# 지도 표시
if st.session_state.last_added_event and st.session_state.last_added_event["location"]:
    st.markdown("#### 🗺 새 일정 위치")
    render_place_map(st.session_state.last_added_event["location"])

st.markdown("---")


# ---------- 3. 거리·이동시간·간격 계산 ----------
st.markdown("### 3. 기존 일정 ↔ 새 일정 비교")

calendar_loc_events = [
    e for e in st.session_state.google_events if e.get("location")
]

if not calendar_loc_events:
    st.info("위치가 있는 캘린더 일정이 없습니다.")
else:
    col1, col2 = st.columns(2)

    with col1:
        base_event = st.selectbox(
            "기준(출발지) 캘린더 일정 선택",
            options=calendar_loc_events,
            format_func=lambda e: f"{e['summary']} | {format_event_time_str(e['start_raw'], e['end_raw'])} | {e['location']}",
        )

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

    with col2:
        ne = st.session_state.last_added_event
        if ne:
            st.markdown(
                f"""
                <div class="card">
                <b>새 일정</b><br/>
                제목: {ne['summary']}<br/>
                날짜: {ne['date']}<br/>
                시간: {ne['start_time'].strftime('%H:%M')} ~ {ne['end_time'].strftime('%H:%M')}<br/>
                장소: {ne['location']}
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.info("새 일정을 먼저 추가하세요.")

    if st.session_state.last_added_event and base_event:
        base_loc = base_event["location"]
        new_loc = st.session_state.last_added_event["location"]

        if not new_loc:
            st.warning("새 일정의 장소가 필요합니다.")
        else:
            st.markdown("#### 🚏 이동 경로 지도")
            render_directions_map(base_loc, new_loc, mode=mode_value)

            # Distance Matrix
            origin = base_loc
            dest = new_loc

            if st.session_state.last_added_event.get("place_id"):
                dest = "place_id:" + st.session_state.last_added_event["place_id"]

            travel_min = get_travel_time_minutes(origin, dest, mode=mode_value)

            # 시간 간격 계산
            try:
                base_end = parse_iso_or_date(base_event["end_raw"])
                new_start = dt.datetime.combine(
                    st.session_state.last_added_event["date"],
                    st.session_state.last_added_event["start_time"],
                )

                # tzinfo만 제거 (시간은 유지)
                if base_end.tzinfo:
                    base_end_naive = base_end.replace(tzinfo=None)
                else:
                    base_end_naive = base_end

                gap_min = (new_start - base_end_naive).total_seconds() / 60.0
            except:
                gap_min = None

            st.markdown("#### ⏱ 이동 시간 · 일정 간격 분석")

            if travel_min is not None:
                st.write(f"- 🚗 예상 이동 시간: **{travel_min:.0f}분**")
            else:
                st.write("- 이동시간을 계산할 수 없습니다.")

            if gap_min is not None:
                st.write(
                    f"- 🕒 기존 일정 종료 → 새 일정 시작 간격: **{gap_min:.0f}분**"
                )

            # 추천 로직
            if travel_min is not None and gap_min is not None:
                buffer = gap_min - travel_min
                need_extra = 60 - buffer

                if buffer >= 60:
                    st.success("일정 간 간격이 충분해요! 그대로 진행해도 괜찮습니다.")
                else:
                    delay = max(0, int(need_extra))
                    st.warning(
                        f"간격이 부족해요. 새 일정을 **약 {delay}분 뒤로 미루는 것**을 추천합니다."
                    )
            else:
                st.info("데이터가 부족해 추천을 제공할 수 없습니다.")
