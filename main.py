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
