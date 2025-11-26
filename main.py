import streamlit as st
import datetime as dt
from typing import Optional, List, Dict

import urllib.parse
import requests

# google-api-python-client, google-auth 관련 (없어도 앱 안 죽게 처리)
try:
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
except ImportError:
    build = None
    service_account = None


# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

st.markdown(
    """
<style>
.main .block-container {
    max-width: 900px;
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
}
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

/* 카드 */
.card {
    padding: 1rem 1.2rem;
    border-radius: 0.8rem;
    border: 1px solid #e5e5e5;
    background: #fafafa;
    margin-bottom: 1rem;
}

/* 작은 글씨 */
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

# ==================== 세션 상태 초기화 ====================
if "google_events" not in st.session_state:
    st.session_state.google_events: List[Dict] = []

if "custom_events" not in st.session_state:
    st.session_state.custom_events: List[Dict] = []

if "last_added_event" not in st.session_state:
    st.session_state.last_added_event: Optional[Dict] = None

if "autocomplete_results" not in st.session_state:
    st.session_state.autocomplete_results: List[Dict] = []

if "selected_location_text" not in st.session_state:
    st.session_state.selected_location_text: str = ""

if "selected_location_place_id" not in st.session_state:
    st.session_state.selected_location_place_id: Optional[str] = None


# ==================== 공통: Maps API Key ====================
def get_maps_api_key() -> Optional[str]:
    try:
        key = st.secrets["google_maps"]["api_key"]
        return key
    except Exception as e:
        st.error(f"[DEBUG] google_maps.api_key 설정을 읽을 수 없습니다: {e}")
        return None


# ==================== Google Calendar (서비스 계정) ====================
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

def get_calendar_service():
    """서비스 계정으로 Google Calendar service 생성"""
    if build is None or service_account is None:
        return None, "google-api-python-client / google-auth 라이브러리가 설치되어 있지 않습니다. pip install google-api-python-client google-auth 를 실행해 주세요."

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

def fetch_google_events(service, calendar_id: str = "primary", max_results: int = 10):
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
                "location": e.get("location", ""),  # 문자열
            }
        )
    return parsed


# ==================== 시간/날짜 처리 ====================
def parse_iso_or_date(s: str) -> dt.datetime:
    """Google Calendar의 dateTime 또는 date 문자열을 datetime으로 변환"""
    if "T" in s:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    else:
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


# ==================== Places API (자동완성 + 좌표) ====================
def places_autocomplete(input_text: str, language: str = "ko") -> List[Dict]:
    """Places Autocomplete API로 주소 자동완성 후보를 가져옴"""
    api_key = get_maps_api_key()
    if not api_key or not input_text.strip():
        return []

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": input_text,
        "key": api_key,
        "language": language,
        "components": "country:kr",  # 한국 한정 (원하면 제거)
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        status = data.get("status")
        if status != "OK":
            # 너무 시끄럽지 않게, 디버그 용으로만 표시
            st.info(f"[DEBUG] Places Autocomplete 상태: {status}")
            return []
        preds = data.get("predictions", [])
        results = [
            {
                "description": p.get("description", ""),
                "place_id": p.get("place_id"),
            }
            for p in preds
        ]
        return results
    except Exception as e:
        st.info(f"[DEBUG] Places Autocomplete 요청 중 오류: {e}")
        return []

def place_details(place_id: str) -> Optional[Dict]:
    """Places Details API로 place_id의 좌표/정식 주소 조회"""
    api_key = get_maps_api_key()
    if not api_key or not place_id:
        return None

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "key": api_key,
        "language": "ko",
        "fields": "geometry/location,formatted_address",
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        if data.get("status") != "OK":
            st.info(f"[DEBUG] Place Details 상태: {data.get('status')}")
            return None
        result = data.get("result", {})
        loc = result.get("geometry", {}).get("location", {})
        return {
            "formatted_address": result.get("formatted_address", ""),
            "lat": loc.get("lat"),
            "lng": loc.get("lng"),
        }
    except Exception as e:
        st.info(f"[DEBUG] Place Details 요청 중 오류: {e}")
        return None


# ==================== Distance Matrix (이동시간) ====================
def get_travel_time_minutes(origin: str, destination: str, mode: str = "transit") -> Optional[float]:
    """Distance Matrix API로 이동 시간(분) 계산. origin/destination은 주소 또는 'place_id:...' 형식."""
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
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        rows = data.get("rows", [])
        if not rows:
            return None
        elements = rows[0].get("elements", [])
        if not elements:
            return None
        el = elements[0]
        if el.get("status") != "OK":
            st.info(f"[DEBUG] Distance Matrix element status: {el.get('status')}")
            return None
        seconds = el["duration"]["value"]
        return seconds / 60.0
    except Exception as e:
        st.info(f"[DEBUG] Distance Matrix 요청 중 오류: {e}")
        return None


# ==================== 지도 표시 (Maps Embed) ====================
def render_place_map_from_query(query: str, height: int = 320):
    """검색어 기반 place 지도"""
    api_key = get_maps_api_key()
    if not api_key:
        st.warning("Google Maps API Key가 설정되어 있지 않습니다.")
        return

    q = urllib.parse.quote(query)
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
    """두 지점 사이 길찾기 지도"""
    api_key = get_maps_api_key()
    if not api_key:
        st.warning("Google Maps API Key가 설정되어 있지 않습니다.")
        return

    o = urllib.parse.quote(origin)
    d = urllib.parse.quote(destination)
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


# ==================== UI 시작 ====================
st.title("📅 일정? 바로잡 GO!")
st.markdown(
    "<p class='subtle'>Google Calendar의 일정 위치와 내가 새로 추가한 일정의 위치를 비교해서, "
    "실제로 이동 가능한지 지도와 시간으로 확인해 봅니다. 주소 자동완성(Places)도 함께 사용합니다.</p>",
    unsafe_allow_html=True,
)


# ---------- 1. 캘린더 일정 불러오기 ----------
st.markdown("### 1. Google Calendar 일정 불러오기 (서비스 계정)")

col_btn, col_help = st.columns([1, 2])

with col_btn:
    if st.button("🔄 캘린더에서 다가오는 일정 불러오기", use_container_width=True):
        service, err = get_calendar_service()
        if err:
            st.error(err)
        elif not service:
            st.error("캘린더 service 객체를 만들 수 없습니다.")
        else:
            try:
                events = fetch_google_events(service, calendar_id="primary")
                st.session_state.google_events = events
                st.success(f"다가오는 일정 {len(events)}개를 불러왔습니다.")
            except Exception as e:
                st.error(f"캘린더 이벤트를 불러오는 중 오류가 발생했습니다: {e}")

with col_help:
    st.markdown(
        """
        <div class="card">
        <b>서비스 계정 연동 체크리스트</b><br/>
        • Google Cloud에서 서비스 계정 JSON을 발급해서 secrets.toml에 넣었나요?<br/>
        • Google Calendar 설정 &gt; 특정 사용자와 공유에 서비스 계정 이메일을 추가했나요?<br/>
        • Google Calendar API를 같은 프로젝트에서 '사용'으로 켰나요?<br/>
        </div>
        """,
        unsafe_allow_html=True,
    )

if st.session_state.google_events:
    with st.expander("📆 불러온 일정 목록 보기", expanded=True):
        for ev in st.session_state.google_events:
            line = f"**{ev['summary']}**  \n"
            line += f"⏰ {format_event_time_str(ev['start_raw'], ev['end_raw'])}"
            if ev.get("location"):
                line += f"  \n📍 {ev['location']}"
            st.markdown(line)
else:
    st.info("아직 불러온 일정이 없습니다. 위 버튼을 눌러 주세요.")

st.markdown("---")


# ---------- 2. 주소 자동완성 (Places API) ----------
st.markdown("### 2. 새 일정 장소 검색 (주소 자동완성)")

with st.form("autocomplete_form"):
    query = st.text_input("검색할 장소(예: 서울시청, 강남역 등)", value="", key="autocomplete_query")
    submitted_search = st.form_submit_button("🔍 주소 자동완성 검색")

    if submitted_search and query.strip():
        results = places_autocomplete(query.strip())
        st.session_state.autocomplete_results = results
        if not results:
            st.warning("검색 결과가 없거나, Places API 상태를 확인해야 합니다.")

if st.session_state.autocomplete_results:
    idx = st.selectbox(
        "검색 결과에서 선택",
        options=list(range(len(st.session_state.autocomplete_results))),
        format_func=lambda i: st.session_state.autocomplete_results[i]["description"],
    )
    chosen = st.session_state.autocomplete_results[idx]
    if st.button("이 주소를 새 일정 장소로 사용하기"):
        st.session_state.selected_location_text = chosen["description"]
        st.session_state.selected_location_place_id = chosen["place_id"]
        st.success(f"선택한 주소를 새 일정에 사용할 준비가 되었습니다: {chosen['description']}")

st.markdown("---")


# ---------- 3. 새 일정 입력 + 위치 지도 ----------
st.markdown("### 3. 새 일정 입력 + 위치 확인")

today = dt.date.today()
default_loc = st.session_state.selected_location_text or ""

with st.form("add_event_form"):
    title = st.text_input("일정 제목", placeholder="예) 동아리 모임, 학원 수업 등")
    date = st.date_input("날짜", value=today)
    start_time = st.time_input("시작 시간", value=dt.time(15, 0))
    end_time = st.time_input("끝나는 시간", value=dt.time(16, 0))
    location = st.text_input(
        "일정 장소 (자동완성으로 선택한 주소가 있으면 자동 채워집니다)",
        value=default_loc,
        key="new_event_location",
    )
    memo = st.text_area("메모 (선택)", placeholder="간단한 메모를 적을 수 있어요.")

    submitted_event = st.form_submit_button("➕ 이 일정 화면에 추가")

    if submitted_event:
        if not title.strip():
            st.warning("일정 제목은 반드시 입력해 주세요.")
        else:
            new_event = {
                "summary": title.strip(),
                "date": date,
                "start_time": start_time,
                "end_time": end_time,
                "location": location.strip(),
                # 자동완성으로 선택된 place_id (없으면 None)
                "place_id": st.session_state.selected_location_place_id,
                "memo": memo.strip(),
            }
            st.session_state.custom_events.append(new_event)
            st.session_state.last_added_event = new_event
            st.success("새 일정을 화면 내 목록에 추가했습니다. (캘린더에는 쓰지 않습니다.)")

# 방금 추가한 일정 위치 지도
if st.session_state.last_added_event and st.session_state.last_added_event.get("location"):
    st.markdown("#### 🗺 방금 추가한 일정 위치")
    loc = st.session_state.last_added_event["location"]
    st.write(f"📍 {loc}")
    render_place_map_from_query(loc)
else:
    st.info("위에서 일정을 추가하면 이곳에 지도가 표시됩니다.")

st.markdown("---")


# ---------- 4. 캘린더 일정 vs 새 일정 거리/시간 비교 ----------
st.markdown("### 4. 기존 캘린더 일정 ↔ 새 일정 거리·이동시간 비교")

# 위치가 있는 캘린더 일정만 필터
calendar_events_with_loc = [
    ev for ev in st.session_state.google_events if ev.get("location")
]

if not calendar_events_with_loc:
    st.info("불러온 Google 일정 중 위치 정보가 있는 일정이 없습니다.")
else:
    left, right = st.columns(2)

    with left:
        base_event = st.selectbox(
            "기준이 될 캘린더 일정 선택 (위치 있는 일정만)",
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
        if st.session_state.last_added_event:
            ne = st.session_state.last_added_event
            st.markdown(
                f"""
                <div class="card">
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
            st.markdown("#### 🚏 이동 경로 지도")

            st.write(f"출발(캘린더 일정): {base_loc_text}")
            st.write(f"도착(새 일정): {new_loc_text}")

            # 지도는 텍스트 검색 기반으로 표시
            render_directions_map(base_loc_text, new_loc_text, mode=mode_value)

            # Distance Matrix: place_id 사용 가능하면 'place_id:...' 형식 사용
            origin_param = base_loc_text
            dest_param = new_loc_text

            # 새 일정에 place_id가 있다면 우선 사용
            new_place_id = st.session_state.last_added_event.get("place_id")
            if new_place_id:
                dest_param = f"place_id:{new_place_id}"

            # 캘린더 일정 위치도 place_id로 해석 시도 (실패해도 텍스트로 fallback)
            base_details = places_autocomplete(base_loc_text)
            if base_details:
                pid = base_details[0].get("place_id")
                if pid:
                    origin_param = f"place_id:{pid}"

            travel_min = get_travel_time_minutes(origin_param, dest_param, mode=mode_value)

            # 일정 간 간격 계산
            try:
                base_end_dt = parse_iso_or_date(base_event["end_raw"])
                new_start_dt = dt.datetime.combine(
                    st.session_state.last_added_event["date"],
                    st.session_state.last_added_event["start_time"],
                )
                gap_min = (new_start_dt - base_end_dt).total_seconds() / 60.0
            except Exception:
                gap_min = None

            st.markdown("#### ⏱ 이동 시간 vs 일정 간 간격")

            if travel_min is not None:
                st.write(f"- 예상 이동 시간: **약 {travel_min:.0f}분**")
            else:
                st.write("- 예상 이동 시간을 계산할 수 없습니다.")

            if gap_min is not None:
                st.write(f"- 기존 일정 종료 → 새 일정 시작 사이 간격: **약 {gap_min:.0f}분**")
            else:
                st.write("- 일정 간 간격을 계산할 수 없습니다.")

            if (travel_min is not None) and (gap_min is not None):
                buffer = gap_min - travel_min
                need_extra = 60 - buffer  # 1시간 여유를 위해 더 필요한 시간

                if buffer >= 60:
                    st.success(
                        "이동 시간과 1시간 여유를 고려했을 때 일정 간 간격이 충분합니다. "
                        "현재 시간대로 진행해도 무리가 없을 것 같아요."
                    )
                else:
                    delay_min = max(0, int(need_extra))
                    st.warning(
                        f"이동 시간에 비해 일정 간 간격이 부족해 보입니다. "
                        f"1시간 여유를 확보하려면 새 일정을 **약 {delay_min}분 정도 뒤로 미루는 것**을 추천합니다."
                    )
            else:
                st.info("이동 시간 또는 일정 간 간격 정보를 충분히 얻지 못해, 텍스트 추천은 생략합니다.")
