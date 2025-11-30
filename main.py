import streamlit as st
import datetime as dt
from typing import Optional, List, Dict, Tuple
import urllib.parse
import requests
import math

# google API client
try:
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
except ImportError:
    build = None
    service_account = None


# ==================== 설정 ====================

# 🔹 반드시 네 구글 캘린더(사람 계정)의 이메일로 바꿔줘야 함
CALENDAR_ID = "dlspike520@gmail.com"

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# 간단한 반응형 + 카드 스타일
st.markdown(
    """
<style>
.main .block-container {
    max-width: 900px;
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
}

.app-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #179c92;
    margin-bottom: 0.3rem;
}
.app-subtitle {
    font-size: 0.9rem;
    color: #666;
    margin-bottom: 1.2rem;
}

/* 카드 컨테이너 */
.section-card {
    padding: 1.2rem 1.2rem;
    border-radius: 14px;
    background: #ffffff;
    border: 1px solid #e7f4f3;
    box-shadow: 0 4px 12px rgba(0,0,0,0.04);
    margin-bottom: 1.3rem;
}

/* 버튼 */
.stButton > button {
    background-color: #36cfc9;
    color: white;
    border-radius: 12px;
    border: none;
    padding: 0.5rem 1.3rem;
    font-weight: 600;
    width: 100%;
    font-size: 1.0rem;
}
.stButton > button:hover {
    background-color: #5ee4de;
    color: #004443;
}

/* 입력창 모서리 */
.stTextInput > div > div > input,
.stTextArea > div > textarea,
.stDateInput > div > input,
.stTimeInput > div > input {
    border-radius: 10px !important;
}

/* 모바일 대응 */
@media (max-width: 640px) {
    .app-title { font-size: 1.3rem; }
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


# ==================== 공용 함수 ====================

def get_maps_api_key() -> Optional[str]:
    """secrets.toml 에 [google_maps].api_key"""
    try:
        return st.secrets["google_maps"]["api_key"]
    except Exception:
        return None


def get_tmap_app_key() -> Optional[str]:
    """secrets.toml 에 [tmap].app_key"""
    try:
        return st.secrets["tmap"]["app_key"]
    except Exception:
        return None


# ---- Google Calendar ----
def get_calendar_service():
    if build is None or service_account is None:
        return None, "google-api-python-client, google-auth 설치 필요"

    try:
        info = st.secrets["google_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        service = build("calendar", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"서비스 계정 인증 오류: {e}"


def fetch_google_events(service, calendar_id: str = CALENDAR_ID, max_results: int = 50):
    """오늘(한국시간) 이후 일정만 조회"""
    today_kst = dt.datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_utc = today_kst - dt.timedelta(hours=9)
    time_min = today_utc.isoformat() + "Z"

    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
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


# ---- 날짜/시간 ----
def parse_iso_or_date(s: str) -> dt.datetime:
    if not s:
        raise ValueError("empty")

    s = s.strip()
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")

    try:
        return dt.datetime.fromisoformat(s)
    except Exception:
        d = dt.date.fromisoformat(s)
        return dt.datetime.combine(d, dt.time.min)


def format_event_time_str(start_raw: str, end_raw: str) -> str:
    try:
        s = parse_iso_or_date(start_raw)
        e = parse_iso_or_date(end_raw)
        if s.date() == e.date():
            return f"{s.strftime('%Y-%m-%d %H:%M')} ~ {e.strftime('%H:%M')}"
        else:
            return f"{s.strftime('%Y-%m-%d %H:%M')} ~ {e.strftime('%Y-%m-%d %H:%M')}"
    except Exception:
        return f"{start_raw} → {end_raw}"


# ---- Google Geocoding ----
def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    문자열 주소 -> (lon, lat)
    Google Geocoding 사용 (Tmap은 경로계산만 사용).
    """
    key = get_maps_api_key()
    if not key or not address.strip():
        if not key:
            st.caption("⚠ Google Maps API 키가 없어 주소 좌표를 찾을 수 없습니다.")
        return None

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": key,
        "language": "ko",
        "region": "kr",
    }
    try:
        data = requests.get(url, params=params, timeout=5).json()
        status = data.get("status")
        if status != "OK" or not data.get("results"):
            st.caption(f"지오코딩 상태: {status} (주소 좌표를 찾지 못했습니다.)")
            return None
        loc = data["results"][0]["geometry"]["location"]
        return float(loc["lng"]), float(loc["lat"])
    except Exception as e:
        st.caption(f"지오코딩 요청 중 오류: {e}")
        return None


# ---- Places 자동완성 (Google) ----
def places_autocomplete(text: str):
    key = get_maps_api_key()
    if not key or not text.strip():
        if not key:
            st.warning("⚠ Google Maps API 키가 없습니다. secrets에 google_maps.api_key를 확인해 주세요.")
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
        status = data.get("status")
        if status != "OK":
            msg = data.get("error_message", "")
            st.caption(f"자동완성 API 상태: {status} {(' - ' + msg) if msg else ''}")
            return []
        return [
            {
                "description": p.get("description", ""),
                "place_id": p.get("place_id"),
            }
            for p in data.get("predictions", [])
        ]
    except Exception as e:
        st.caption(f"자동완성 요청 중 오류: {e}")
        return []


# ---- Google Distance Matrix (fallback 용) ----
def get_google_travel_time_minutes(origin: str, dest: str, mode: str) -> Optional[float]:
    """
    최후 fallback: Google Distance Matrix.
    여기서는 절대로 직선거리 근사 안 쓰고,
    응답이 없으면 그냥 None 반환.
    """
    key = get_maps_api_key()
    if not key:
        return None

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": dest,
        "mode": mode,
        "units": "metric",
        "language": "ko",
        "region": "kr",
        "key": key,
    }
    if mode == "transit":
        params["departure_time"] = "now"

    try:
        data = requests.get(url, params=params, timeout=5).json()
        status = data.get("status")
        if status != "OK":
            msg = data.get("error_message", "")
            st.caption(f"Distance Matrix API 상태: {status} {(' - ' + msg) if msg else ''}")
            return None

        row = data.get("rows", [{}])[0]
        el = row.get("elements", [{}])[0]
        if el.get("status") != "OK":
            st.caption(f"Distance Matrix element 상태: {el.get('status')}")
            return None

        return el["duration"]["value"] / 60.0
    except Exception as e:
        st.caption(f"Distance Matrix 요청 중 오류: {e}")
        return None


# ---- Tmap 경로 시간 ----
def _extract_tmap_total_time_sec(features: List[Dict]) -> Optional[float]:
    """
    Tmap GeoJSON features 배열에서 properties.totalTime(sec) 찾아서 반환
    """
    for f in features or []:
        props = f.get("properties", {})
        if "totalTime" in props:
            try:
                return float(props["totalTime"])
            except Exception:
                continue
    return None


def get_tmap_travel_time_minutes(origin: str, dest: str, mode: str) -> Optional[float]:
    """
    mode: 'driving', 'walking', 'bicycling'
    - 좌표는 Google Geocoding으로 가져오고
    - 경로/시간은 Tmap OpenAPI 사용
    - 자전거는 보행자 totalTime에서 속도 보정 (대략 0.4배) 근사
      (도로를 따라간다는 점에서 직선거리보다는 훨씬 현실적)
    """
    app_key = get_tmap_app_key()
    if not app_key:
        st.caption("⚠ Tmap appKey가 없어 Tmap 경로 API를 사용할 수 없습니다.")
        return None

    # 주소 -> 좌표
    start = geocode_address(origin)
    end = geocode_address(dest)
    if not start or not end:
        return None

    start_x, start_y = start  # lon, lat
    end_x, end_y = end

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "appKey": app_key,
    }

    try:
        if mode in ("walking", "bicycling"):
            # 보행자 경로 안내
            url = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1"
            payload = {
                "startX": start_x,
                "startY": start_y,
                "endX": end_x,
                "endY": end_y,
                "startName": urllib.parse.quote(origin),
                "endName": urllib.parse.quote(dest),
                "reqCoordType": "WGS84GEO",
                "resCoordType": "WGS84GEO",
                "searchOption": "0",
                "sort": "index",
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=7)
            if resp.status_code != 200:
                st.caption(f"Tmap 보행자 경로 API 상태: HTTP {resp.status_code}")
                return None
            data = resp.json()
            total_sec = _extract_tmap_total_time_sec(data.get("features", []))
            if total_sec is None:
                st.caption("Tmap 보행자 응답에 totalTime 정보가 없습니다.")
                return None

            walk_min = total_sec / 60.0
            if mode == "walking":
                return walk_min
            else:
                # 자전거: 보행 속도의 대략 2.5배 정도로 가정해서 0.4배 근사
                return walk_min * 0.4

        elif mode == "driving":
            # 자동차 경로 안내
            # (경로 URL은 환경에 따라 '/tmap/routes' 또는 '/routes' 일 수 있어서 필요하면 바꿔줘)
            url = "https://apis.openapi.sk.com/tmap/routes?version=1&format=json"
            payload = {
                "startX": start_x,
                "startY": start_y,
                "endX": end_x,
                "endY": end_y,
                "reqCoordType": "WGS84GEO",
                "resCoordType": "WGS84GEO",
                "sort": "index",
                "carType": 0,
                "searchOption": 0,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=7)
            if resp.status_code != 200:
                st.caption(f"Tmap 자동차 경로 API 상태: HTTP {resp.status_code}")
                return None
            data = resp.json()
            total_sec = _extract_tmap_total_time_sec(data.get("features", []))
            if total_sec is None:
                st.caption("Tmap 자동차 응답에 totalTime 정보가 없습니다.")
                return None
            return total_sec / 60.0

        else:
            return None
    except Exception as e:
        st.caption(f"Tmap 경로 요청 중 오류: {e}")
        return None


# ---- 통합 이동시간 함수 ----
def get_travel_time_minutes(origin: str, dest: str, mode: str = "transit") -> Optional[float]:
    """
    1순위: 자동차/도보/자전거는 Tmap 경로 API
    2순위: 실패 시 Google Distance Matrix
    - 직선거리 근사는 절대 사용 안 함
    """
    # 1) Tmap 우선 시도
    if mode in ("driving", "walking", "bicycling"):
        tmap_min = get_tmap_travel_time_minutes(origin, dest, mode)
        if tmap_min is not None:
            return tmap_min

    # 2) Google Distance Matrix fallback
    if mode == "transit":
        return get_google_travel_time_minutes(origin, dest, "transit")
    elif mode == "driving":
        return get_google_travel_time_minutes(origin, dest, "driving")
    elif mode == "walking":
        return get_google_travel_time_minutes(origin, dest, "walking")
    elif mode == "bicycling":
        return get_google_travel_time_minutes(origin, dest, "bicycling")

    return None


# ---- 지도 Embed (Google Maps) ----
def render_place_map(query: str, height: int = 320):
    key = get_maps_api_key()
    if not key:
        return
    q = urllib.parse.quote(query)
    src = f"https://www.google.com/maps/embed/v1/place?key={key}&q={q}"
    st.markdown(
        f"""
        <iframe
            width="100%"
            height="{height}"
            style="border:0; border-radius: 14px;"
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade"
            src="{src}">
        </iframe>
        """,
        unsafe_allow_html=True,
    )


def render_directions_map(origin: str, dest: str, mode: str = "transit", height: int = 320):
    key = get_maps_api_key()
    if not key:
        return
    o = urllib.parse.quote(origin)
    d = urllib.parse.quote(dest)
    src = (
        f"https://www.google.com/maps/embed/v1/directions"
        f"?key={key}&origin={o}&destination={d}&mode={mode}"
    )
    st.markdown(
        f"""
        <iframe
            width="100%"
            height="{height}"
            style="border:0; border-radius: 14px;"
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade"
            src="{src}">
        </iframe>
        """,
        unsafe_allow_html=True,
    )


# ---- 새 일정 시간 미루기 ----
def shift_last_event(minutes: int):
    """화면 내부에 저장된 마지막 새 일정(start/end)을 minutes만큼 뒤로 미룸."""
    ev = st.session_state.last_added_event
    if not ev:
        return

    start_dt = dt.datetime.combine(ev["date"], ev["start_time"])
    end_dt = dt.datetime.combine(ev["date"], ev["end_time"])

    delta = dt.timedelta(minutes=minutes)
    new_start = start_dt + delta
    new_end = end_dt + delta

    ev["date"] = new_start.date()
    ev["start_time"] = new_start.time()
    ev["end_time"] = new_end.time()

    st.session_state.last_added_event = ev


# ==================== UI ====================

st.markdown('<div class="app-title">📅 일정? 바로잡 GO!</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-subtitle">Google Calendar 일정과 새 일정을 비교해서 이동시간·간격을 확인합니다.</div>',
    unsafe_allow_html=True,
)

today = dt.date.today()

# ---------- 1. Google Calendar 불러오기 ----------
with st.container():
    st.markdown('<div class="section-card">', unsafe_allow_html=True)

    st.markdown("### 1. Google Calendar 불러오기")

    if st.button("오늘 이후 일정 불러오기", key="load_calendar"):
        service, err = get_calendar_service()
        if err:
            st.error(err)
        elif not service:
            st.error("캘린더 service 생성 실패")
        else:
            try:
                st.session_state.google_events = fetch_google_events(service)
                st.success(f"오늘 이후 일정 {len(st.session_state.google_events)}개 불러왔습니다.")
            except Exception as e:
                st.error(f"캘린더 일정 불러오는 중 오류가 발생했습니다: {e}")

    selected_date = st.date_input("날짜별 일정 보기", value=today, key="calendar_date")

    day_events: List[Dict] = []
    for ev in st.session_state.google_events:
        try:
            start_dt = parse_iso_or_date(ev["start_raw"])
            if start_dt.date() == selected_date:
                day_events.append(ev)
        except Exception:
            pass

    custom_day_events: List[Dict] = [
        ev for ev in st.session_state.custom_events if ev["date"] == selected_date
    ]

    if day_events or custom_day_events:
        st.markdown("**선택한 날짜의 일정**")

        if day_events:
            st.markdown("📆 **Google Calendar 일정**")
            for ev in day_events:
                text = f"- **{ev['summary']}**  \n"
                text += f"  ⏰ {format_event_time_str(ev['start_raw'], ev['end_raw'])}"
                if ev.get("location"):
                    text += f"  \n  📍 {ev['location']}"
                st.markdown(text)

        if custom_day_events:
            st.markdown("📝 **화면 내에서 추가한 일정**")
            for ev in custom_day_events:
                text = (
                    f"- **{ev['summary']}**  \n"
                    f"  ⏰ {ev['date']} {ev['start_time'].strftime('%H:%M')} ~ {ev['end_time'].strftime('%H:%M')}"
                )
                if ev.get("location"):
                    text += f"  \n  📍 {ev['location']}"
                st.markdown(text)
    else:
        st.caption("선택한 날짜에 표시할 일정이 없습니다.")

    if st.session_state.google_events:
        with st.expander("오늘 이후 전체 일정 목록 보기"):
            for ev in st.session_state.google_events:
                text = f"**{ev['summary']}**  \n"
                text += f"⏰ {format_event_time_str(ev['start_raw'], ev['end_raw'])}"
                if ev.get("location"):
                    text += f"  \n📍 {ev['location']}"
                st.markdown(text)
    else:
        st.info("아직 불러온 일정이 없습니다. 위 버튼을 눌러 주세요.")

    st.markdown("</div>", unsafe_allow_html=True)

# ---------- 2. 새 일정 입력 ----------
with st.container():
    st.markdown('<div class="section-card">', unsafe_allow_html=True)

    st.markdown("### 2. 새 일정 입력 (주소 자동완성 포함)")

    with st.form("add_event_form"):
        title = st.text_input("일정 제목", placeholder="예) 동아리 모임, 학원 수업 등")
        date = st.date_input("날짜", value=today, key="new_event_date")
        start_time = st.time_input("시작 시간", value=dt.time(15, 0), key="new_event_start")
        end_time = st.time_input("끝나는 시간", value=dt.time(16, 0), key="new_event_end")

        loc_input = st.text_input(
            "일정 장소",
            placeholder="예) 서울시청, 강남역 2번출구 등",
            key="new_event_location",
        )

        autocomplete_results: List[Dict] = []
        chosen_idx: Optional[int] = None
        chosen_desc: Optional[str] = None
        chosen_place_id: Optional[str] = None

        if loc_input.strip():
            autocomplete_results = places_autocomplete(loc_input.strip())
            if autocomplete_results:
                chosen_idx = st.radio(
                    "주소 자동완성 결과",
                    options=list(range(len(autocomplete_results))),
                    format_func=lambda i: autocomplete_results[i]["description"],
                    key="autocomplete_choice",
                )
                chosen_desc = autocomplete_results[chosen_idx]["description"]
                chosen_place_id = autocomplete_results[chosen_idx]["place_id"]
                st.caption(f"선택된 주소: {chosen_desc}")
            else:
                st.caption("자동완성 결과가 없습니다. 주소를 조금 더 구체적으로 입력해 보세요.")

        memo = st.text_area("메모 (선택)", placeholder="간단한 메모를 적을 수 있어요.")

        submitted_event = st.form_submit_button("➕ 이 일정 화면에 추가")

        if submitted_event:
            if not title.strip():
                st.warning("일정 제목은 반드시 입력해 주세요.")
            else:
                final_location = chosen_desc if chosen_desc else loc_input.strip()
                new_event = {
                    "summary": title.strip(),
                    "date": date,
                    "start_time": start_time,
                    "end_time": end_time,
                    "location": final_location,
                    "place_id": chosen_place_id,
                    "memo": memo.strip(),
                }
                st.session_state.custom_events.append(new_event)
                st.session_state.last_added_event = new_event
                st.success("새 일정을 화면 내 목록에 추가했습니다. (Google Calendar에는 쓰지 않습니다.)")

    if st.session_state.last_added_event and st.session_state.last_added_event.get("location"):
        st.markdown("#### 🗺 방금 추가한 일정 위치")
        loc = st.session_state.last_added_event["location"]
        st.write(f"📍 {loc}")
        render_place_map(loc)
    else:
        st.caption("위에서 일정을 추가하면 이곳에 지도가 표시됩니다.")

    st.markdown("</div>", unsafe_allow_html=True)

# ---------- 3. 기존 일정 ↔ 새 일정 비교 ----------
with st.container():
    st.markdown('<div class="section-card">', unsafe_allow_html=True)

    st.markdown("### 3. 기존 일정 ↔ 새 일정 거리·시간 비교")

    calendar_events_with_loc = [
        ev for ev in st.session_state.google_events if ev.get("location")
    ]

    if not calendar_events_with_loc:
        st.info("위치 정보가 있는 Google Calendar 일정이 없습니다.")
    else:
        left, right = st.columns(2)

        with left:
            base_event = st.selectbox(
                "기준이 될 캘린더 일정 선택",
                options=calendar_events_with_loc,
                format_func=lambda ev: f"{ev['summary']} | {format_event_time_str(ev['start_raw'], ev['end_raw'])} | {ev['location']}",
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

        with right:
            ne = st.session_state.last_added_event
            if ne:
                st.markdown(
                    f"""
                    <div>
                    <b>새 일정</b><br/>
                    제목: {ne['summary']}<br/>
                    날짜: {ne['date']}<br/>
                    시간: {ne['start_time'].strftime('%H:%M')} ~ {ne['end_time'].strftime('%H:%M')}<br/>
                    장소: {ne['location'] or '(입력 없음)'}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.info("아직 새 일정이 없습니다. 위에서 일정을 하나 추가해 주세요.")

        if st.session_state.last_added_event and base_event:
            base_loc_text = base_event["location"]
            new_loc_text = st.session_state.last_added_event["location"]

            if not new_loc_text:
                st.warning("새 일정에 장소가 입력되어 있어야 이동경로를 계산할 수 있습니다.")
            else:
                st.markdown("#### 🗺 이동 경로 지도")
                render_directions_map(base_loc_text, new_loc_text, mode=mode_value)

                # Distance/ETA 계산
                origin_param = base_loc_text
                dest_param = new_loc_text
                travel_min = get_travel_time_minutes(origin_param, dest_param, mode=mode_value)

                # 일정 간 간격 계산
                try:
                    base_end_dt = parse_iso_or_date(base_event["end_raw"])
                    new_start_dt = dt.datetime.combine(
                        st.session_state.last_added_event["date"],
                        st.session_state.last_added_event["start_time"],
                    )

                    if base_end_dt.tzinfo is not None:
                        base_end_dt_naive = base_end_dt.replace(tzinfo=None)
                    else:
                        base_end_dt_naive = base_end_dt

                    gap_min = (new_start_dt - base_end_dt_naive).total_seconds() / 60.0
                except Exception:
                    gap_min = None

                st.markdown("#### ⏱ 이동 시간 vs 일정 간 간격")

                if travel_min is not None:
                    st.write(f"- 예상 이동 시간: **약 {travel_min:.0f}분**")
                else:
                    st.write("- 이동 시간을 계산할 수 없습니다.")

                if gap_min is not None:
                    st.write(
                        f"- 기존 일정 종료 → 새 일정 시작 사이 간격: **약 {gap_min:.0f}분**"
                    )
                else:
                    st.write("- 일정 간 간격을 계산할 수 없습니다.")

                delay_min_recommend: Optional[int] = None

                # ✅ 버퍼: 30분으로 축소
                if (travel_min is not None) and (gap_min is not None):
                    total_required = travel_min + 30  # 이동 + 30분 버퍼
                    if gap_min >= total_required:
                        st.success(
                            "이동 시간과 30분 여유를 고려했을 때 일정 간 간격이 충분합니다. "
                            "현재 시간대로 진행해도 무리가 없을 것 같아요."
                        )
                        delay_min_recommend = 0
                    else:
                        need = total_required - gap_min
                        delay_min_recommend = max(1, math.ceil(need))
                        st.warning(
                            f"이동 시간에 비해 일정 간 간격이 부족해 보입니다.  \n"
                            f"30분 여유까지 고려하면 새 일정을 **최소 {delay_min_recommend}분 이상** "
                            f"뒤로 미루는 게 안전해요."
                        )
                else:
                    st.info("이동 시간 또는 일정 간 간격 정보를 충분히 얻지 못해, 텍스트 추천은 생략합니다.")

                # ---- 시간 미루기 버튼들 ----
                if st.session_state.last_added_event and (delay_min_recommend is not None):
                    col1, col2 = st.columns(2)

                    with col1:
                        if delay_min_recommend > 0:
                            if st.button(
                                f"⏩ 추천({delay_min_recommend}분)만큼 미루기",
                                key="btn_shift_recommend",
                            ):
                                shift_last_event(delay_min_recommend)
                                st.success(
                                    f"새 일정이 추천대로 {delay_min_recommend}분 뒤로 미뤄졌습니다."
                                )
                                st.experimental_rerun()
                        else:
                            st.caption("이미 30분 여유 이상 확보되어 있어 추가로 미룰 필요는 없어요.")

                    with col2:
                        if st.button("⏰ 30분 뒤로 미루기", key="btn_shift_30"):
                            shift_last_event(30)
                            st.success("새 일정이 30분 뒤로 미뤄졌습니다.")
                            st.experimental_rerun()

    st.markdown("</div>", unsafe_allow_html=True)
