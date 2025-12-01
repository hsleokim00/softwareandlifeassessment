import streamlit as st
import datetime as dt
from typing import Optional, List, Dict, Tuple
import urllib.parse
import requests
import math
import streamlit.components.v1 as components

# google API client
try:
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
except ImportError:
    build = None
    service_account = None


# ==================== 설정 ====================

CALENDAR_ID = "dlspike520@gmail.com"
# 🔁 읽기 전용 → 쓰기까지 가능한 권한으로 변경
SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_BASE_LOCATION = "하나고등학교"  # 날짜 다를 때 기본 출발 위치
MAX_PLACE_SUGGESTIONS = 15             # 주소 추천 최대 개수 (상한용)

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
    st.session_state.google_events = []

if "custom_events" not in st.session_state:
    st.session_state.custom_events = []

if "last_added_event" not in st.session_state:
    st.session_state.last_added_event = None

# 🔢 주소 자동완성 페이지 상태 (1 ~ 3)
if "autocomplete_page" not in st.session_state:
    st.session_state.autocomplete_page = 1

if "autocomplete_total_pages" not in st.session_state:
    st.session_state.autocomplete_total_pages = 1

if "last_loc_input" not in st.session_state:
    st.session_state.last_loc_input = ""


# ==================== 공용 함수 ====================

def get_maps_api_key() -> Optional[str]:
    try:
        return st.secrets["google_maps"]["api_key"]
    except Exception:
        return None


def get_tmap_app_key() -> Optional[str]:
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


def create_google_event_from_custom(service, custom_ev: Dict) -> Optional[str]:
    """화면에서 입력한 custom_ev를 Google Calendar에 실제 이벤트로 생성"""
    try:
        start_dt = dt.datetime.combine(
            custom_ev["date"],
            custom_ev["start_time"],
            tzinfo=dt.timezone(dt.timedelta(hours=9)),
        )
        end_dt = dt.datetime.combine(
            custom_ev["date"],
            custom_ev["end_time"],
            tzinfo=dt.timezone(dt.timedelta(hours=9)),
        )

        body = {
            "summary": custom_ev["summary"],
            "location": custom_ev.get("location") or "",
            "description": custom_ev.get("memo") or "",
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Asia/Seoul",
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Asia/Seoul",
            },
        }

        ev = (
            service.events()
            .insert(calendarId=CALENDAR_ID, body=body)
            .execute()
        )
        return ev.get("id")
    except Exception as e:
        st.error(f"Google Calendar에 일정 저장 중 오류가 발생했습니다: {e}")
        return None


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
    """문자열 주소 -> (lon, lat), Google Geocoding 사용"""
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


# ==================== Places 자동완성 (거리 정렬 + 페이징) ====================

PLACES_PER_PAGE = 5          # 한 페이지에 5개
MAX_AUTO_PAGES = 3           # 최대 3페이지 → 15개
BASE_ADDRESS_FOR_SORT = "서울특별시 은평구 진관동 연서로 535"

_base_coord_cache: Optional[Tuple[float, float]] = None


def _get_base_coord() -> Optional[Tuple[float, float]]:
    global _base_coord_cache
    if _base_coord_cache is not None:
        return _base_coord_cache
    _base_coord_cache = geocode_address(BASE_ADDRESS_FOR_SORT)
    return _base_coord_cache


def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371.0
    dlon = math.radians(lon2 - lon1)
    dlat = math.radians(lat2 - lat1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def places_autocomplete(text: str) -> List[Dict]:
    """
    입력 문자열을 바탕으로 Google Places Text Search를 이용해
    - 최대 15개(5개 × 3페이지)까지 주소/장소를 추천
    - '서울특별시 은평구 진관동 연서로 535'에서 가까운 순으로 정렬
    - 현재 페이지(st.session_state.autocomplete_page)에 해당하는 5개만 반환
    반환 형태:
      [{ "description": str, "place_id": str }, ...]
    """
    key = get_maps_api_key()
    if not key or not text.strip():
        if not key:
            st.warning("⚠ Google Maps API 키가 없습니다. secrets에 google_maps.api_key를 확인해 주세요.")
        return []

    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": text,
        "key": key,
        "language": "ko",
        "region": "kr",
    }

    try:
        data = requests.get(url, params=params, timeout=5).json()
        status = data.get("status")
        if status != "OK":
            msg = data.get("error_message", "")
            st.caption(f"장소 검색 API 상태: {status} {(' - ' + msg) if msg else ''}")
            return []

        raw = data.get("results", []) or []
        # 최대 15개까지만 사용
        raw = raw[: PLACES_PER_PAGE * MAX_AUTO_PAGES]

        if not raw:
            st.session_state.autocomplete_total_pages = 1
            return []

        base_coord = _get_base_coord()
        enriched = []

        for r in raw:
            name = r.get("name", "")
            addr = r.get("formatted_address", "")
            place_id = r.get("place_id", "")
            geom = r.get("geometry", {}).get("location")

            if not (name or addr):
                continue

            dist = None
            if base_coord and geom:
                try:
                    lon = float(geom["lng"])
                    lat = float(geom["lat"])
                    dist = _haversine(base_coord[0], base_coord[1], lon, lat)
                except Exception:
                    dist = None

            enriched.append(
                {
                    "name": name,
                    "addr": addr,
                    "place_id": place_id,
                    "distance": dist if dist is not None else 1e9,
                }
            )

        # 거리 기준 정렬
        enriched.sort(key=lambda x: x["distance"])

        total_results = len(enriched)
        total_pages = max(1, min(MAX_AUTO_PAGES, math.ceil(total_results / PLACES_PER_PAGE)))
        st.session_state.autocomplete_total_pages = total_pages

        # 현재 페이지 클램프
        page = int(st.session_state.autocomplete_page)
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        st.session_state.autocomplete_page = page

        start = (page - 1) * PLACES_PER_PAGE
        end = start + PLACES_PER_PAGE
        page_results = enriched[start:end]

        suggestions: List[Dict] = []
        for r in page_results:
            if r["name"] and r["addr"]:
                desc = f"{r['name']} ({r['addr']})"
            else:
                desc = r["name"] or r["addr"] or ""
            suggestions.append(
                {
                    "description": desc,
                    "place_id": r["place_id"],
                }
            )

        return suggestions

    except Exception as e:
        st.caption(f"장소 검색 요청 중 오류: {e}")
        return []


# ---- Google Distance Matrix (대중교통용) ----
def get_google_travel_time_minutes(origin: str, dest: str, mode: str) -> Optional[float]:
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


# ---- Tmap 경로에서 시간 + 경로 추출 ----
def _extract_tmap_time_and_path(features: List[Dict]) -> Tuple[Optional[float], List[List[float]]]:
    total_sec: Optional[float] = None
    path: List[List[float]] = []

    for f in features or []:
        props = f.get("properties", {})
        if total_sec is None and "totalTime" in props:
            try:
                total_sec = float(props["totalTime"])
            except Exception:
                pass

        geom = f.get("geometry", {})
        if geom.get("type") == "LineString":
            coords = geom.get("coordinates", [])
            for c in coords:
                if isinstance(c, (list, tuple)) and len(c) >= 2:
                    lon, lat = float(c[0]), float(c[1])
                    path.append([lon, lat])

    return total_sec, path


# ---- Tmap 경로 + 시간 ----
def get_tmap_route(origin: str, dest: str, mode: str) -> Tuple[Optional[float], Optional[List[List[float]]], Optional[Tuple[float, float, float, float]]]:
    app_key = get_tmap_app_key()
    if not app_key:
        st.caption("⚠ Tmap appKey가 없어 Tmap 경로 API를 사용할 수 없습니다.")
        return None, None, None

    start = geocode_address(origin)
    end = geocode_address(dest)
    if not start or not end:
        return None, None, None

    start_x, start_y = start
    end_x, end_y = end

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "appKey": app_key,
    }

    try:
        if mode in ("walking", "bicycling"):
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
                return None, None, (start_x, start_y, end_x, end_y)
            data = resp.json()
            total_sec, path = _extract_tmap_time_and_path(data.get("features", []))
            if total_sec is None:
                st.caption("Tmap 보행자 응답에 totalTime 정보가 없습니다.")
                return None, path, (start_x, start_y, end_x, end_y)

            walk_min = total_sec / 60.0
            if mode == "walking":
                return walk_min, path, (start_x, start_y, end_x, end_y)
            else:
                return walk_min * 0.35, path, (start_x, start_y, end_x, end_y)

        elif mode == "driving":
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
                return None, None, (start_x, start_y, end_x, end_y)
            data = resp.json()
            total_sec, path = _extract_tmap_time_and_path(data.get("features", []))
            if total_sec is None:
                st.caption("Tmap 자동차 응답에 totalTime 정보가 없습니다.")
                return None, path, (start_x, start_y, end_x, end_y)
            return total_sec / 60.0, path, (start_x, start_y, end_x, end_y)
        else:
            return None, None, (start_x, start_y, end_x, end_y)

    except Exception as e:
        st.caption(f"Tmap 경로 요청 중 오류: {e}")
        return None, None, (start_x, start_y, end_x, end_y)


# ---- Tmap JS 지도 embed ----
def render_tmap_route_map(start_x: float, start_y: float, end_x: float, end_y: float, mode: str, height: int = 420):
    app_key = get_tmap_app_key()
    if not app_key:
        st.caption("⚠ Tmap appKey가 없어 경로 지도를 표시할 수 없습니다.")
        return

    if mode in ("walking", "bicycling"):
        route_api = "pedestrian"
        stroke_color = "#0078ff"
    else:
        route_api = "routes"
        stroke_color = "#dd0000"

    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8" />
        <script src="https://code.jquery.com/jquery-3.2.1.min.js"></script>
        <script src="https://apis.openapi.sk.com/tmap/jsv2?version=1&appKey={app_key}"></script>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
            }}
            #map_div {{
                width: 100%;
                height: 100%;
            }}
        </style>
    </head>
    <body>
        <div id="map_div"></div>
        <script>
            var map;
            var routeLine;

            function init() {{
                map = new Tmapv2.Map("map_div", {{
                    center: new Tmapv2.LatLng({start_y}, {start_x}),
                    width: "100%",
                    height: "100%",
                    zoom: 14
                }});

                var marker_s = new Tmapv2.Marker({{
                    position: new Tmapv2.LatLng({start_y}, {start_x}),
                    icon: "/upload/tmap/marker/pin_r_m_s.png",
                    map: map
                }});

                var marker_e = new Tmapv2.Marker({{
                    position: new Tmapv2.LatLng({end_y}, {end_x}),
                    icon: "/upload/tmap/marker/pin_r_m_e.png",
                    map: map
                }});

                drawRoute();
            }}

            function drawRoute() {{
                var url;
                var data;

                if ("{route_api}" === "pedestrian") {{
                    url = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1&format=json&appKey={app_key}";
                    data = {{
                        startX: "{start_x}",
                        startY: "{start_y}",
                        endX: "{end_x}",
                        endY: "{end_y}",
                        reqCoordType: "WGS84GEO",
                        resCoordType: "EPSG3857"
                    }};
                }} else {{
                    url = "https://apis.openapi.sk.com/tmap/routes?version=1&format=json&appKey={app_key}";
                    data = {{
                        startX: "{start_x}",
                        startY: "{start_y}",
                        endX: "{end_x}",
                        endY: "{end_y}",
                        reqCoordType: "WGS84GEO",
                        resCoordType: "EPSG3857",
                        searchOption: 0
                    }};
                }}

                $.ajax({{
                    method: "POST",
                    url: url,
                    data: data,
                    success: function(response) {{
                        var resultData = response.features;
                        var drawInfoArr = [];

                        for (var i = 0; i < resultData.length; i++) {{
                            var geometry = resultData[i].geometry;
                            if (geometry.type === "LineString") {{
                                for (var j = 0; j < geometry.coordinates.length; j++) {{
                                    var pt = new Tmapv2.Point(geometry.coordinates[j][0], geometry.coordinates[j][1]);
                                    var geo = Tmapv2.Projection.convertEPSG3857ToWGS84GEO(pt);
                                    drawInfoArr.push(new Tmapv2.LatLng(geo._lat, geo._lng));
                                }}
                            }}
                        }}

                        if (drawInfoArr.length > 0) {{
                            routeLine = new Tmapv2.Polyline({{
                                path: drawInfoArr,
                                strokeColor: "{stroke_color}",
                                strokeWeight: 6,
                                map: map
                            }});

                            map.setCenter(drawInfoArr[0]);
                        }}
                    }},
                    error: function(request, status, error) {{
                        console.log("Tmap JS 경로 에러:", request.status, request.responseText, error);
                    }}
                }});
            }}

            window.onload = init;
        </script>
    </body>
    </html>
    """

    components.html(html, height=height, scrolling=False)


# ==================== 이동시간/충돌 로직 유틸 ====================

def to_minutes(delta: dt.timedelta) -> int:
    return int(delta.total_seconds() // 60)


def get_travel_minutes_for_logic(origin: str, dest: str, mode: str = "driving") -> int:
    if not origin or not dest:
        return 0

    minutes: Optional[float] = None

    if mode in ("driving", "walking", "bicycling"):
        minutes, _, _ = get_tmap_route(origin, dest, mode)
    else:
        minutes = get_google_travel_time_minutes(origin, dest, "transit")

    if minutes is None:
        return 0
    return int(math.ceil(minutes))


BUFFER_MIN = 30  # 이동 후 여유 시간(분)


def evaluate_time_gap(move_min: float, gap_min: float, label: str = "선행 일정") -> Dict[str, object]:
    if gap_min < 0:
        overlap = abs(gap_min)
        msg = (
            f"{label} 종료 시각과 새 일정 시작 시각이 이미 {overlap:.0f}분만큼 겹쳐 있어요. "
            f"실제로 시간이 겹치는 상태라, 최소 {overlap:.0f}분 이상은 일정을 조정해야 해요."
        )
        return {"level": 2, "shortage": overlap, "msg": msg}

    if move_min > gap_min:
        shortage = move_min - gap_min
        msg = (
            f"{label} 종료 → 새 일정 시작 사이 간격은 {gap_min:.0f}분인데, "
            f"이동 시간이 {move_min:.0f}분이라 실제로 시간이 겹쳐요. "
            f"최소 {shortage:.0f}분 이상 일정을 미루어야 해요."
        )
        return {"level": 2, "shortage": shortage, "msg": msg}

    if move_min + BUFFER_MIN > gap_min:
        shortage = (move_min + BUFFER_MIN) - gap_min
        msg = (
            f"{label} 종료 → 새 일정 시작 사이 간격은 {gap_min:.0f}분, "
            f"이동 시간은 {move_min:.0f}분이에요. 이동은 가능하지만, "
            f"이동 후 여유 {BUFFER_MIN}분까지 생각하면 "
            f"{shortage:.0f}분 정도 일정을 미루면 더 여유롭겠어요."
        )
        return {"level": 1, "shortage": shortage, "msg": msg}

    msg = (
        f"{label} 종료 → 새 일정 시작 사이 간격은 {gap_min:.0f}분, "
        f"이동 시간은 {move_min:.0f}분이라 여유 {BUFFER_MIN}분까지 포함해도 충분해요."
    )
    return {"level": 0, "shortage": 0, "msg": msg}


def compare_two_events_logic(new_ev: Dict, other: Dict, mode: str = "driving") -> Optional[Dict]:
    """새 일정(new_ev)과 기존 일정(other)을 비교"""
    start_new: dt.datetime = new_ev["start"]
    end_new: dt.datetime = new_ev["end"]
    start_o: dt.datetime = other["start"]
    end_o: dt.datetime = other["end"]

    if start_new.date() != start_o.date():
        return None

    if (start_new < end_o) and (start_o < end_new):
        overlap_start = max(start_new, start_o)
        overlap_end = min(end_new, end_o)
        overlap_min = to_minutes(overlap_end - overlap_start)

        travel_min = get_travel_minutes_for_logic(
            new_ev.get("location", ""),
            other.get("location", ""),
            mode=mode,
        )
        k = overlap_min + travel_min + 30
        return {"type": "overlap", "k": max(0, k)}

    if end_new <= start_o:
        first, second = new_ev, other
    elif end_o <= start_new:
        first, second = other, new_ev
    else:
        return None

    travel_min = get_travel_minutes_for_logic(
        first.get("location", ""),
        second.get("location", ""),
        mode=mode,
    )
    gap_min = to_minutes(second["start"] - first["end"])

    if gap_min - travel_min > 0:
        return None  # 이동 가능

    k = (-gap_min + travel_min) + 30
    return {"type": "travel_impossible", "k": max(0, k)}


def evaluate_new_event_against_all(new_ev_logic: Dict, existing_logic: List[Dict], mode: str = "driving") -> Dict:
    """새 일정 vs 기존 모든 일정(하루 전체)을 종합 평가"""
    same_date_found = False
    best_overlap_k = 0
    best_travel_k = 0

    for ev in existing_logic:
        if ev["start"].date() == new_ev_logic["start"].date():
            same_date_found = True

        res = compare_two_events_logic(new_ev_logic, ev, mode=mode)
        if not res:
            continue

        if res["type"] == "overlap":
            best_overlap_k = max(best_overlap_k, res["k"])
        elif res["type"] == "travel_impossible":
            best_travel_k = max(best_travel_k, res["k"])

    if not same_date_found:
        return {
            "status": "ok",
            "message": "같은 날짜에 다른 일정이 없네요! 입력한 일정은 단독 일정이에요.",
        }

    if best_overlap_k > 0:
        return {
            "status": "warn",
            "k": best_overlap_k,
            "message": f"약속 시간이 겹치는 일정이 있어요. 최소 {best_overlap_k}분 정도는 일정을 미루는 게 안전해요.",
        }

    if best_travel_k > 0:
        return {
            "status": "warn",
            "k": best_travel_k,
            "message": f"시간은 안 겹치지만 이동 시간을 고려하면 빠듯해요. 최소 {best_travel_k}분 정도는 여유 있게 미루는 걸 추천해요.",
        }

    return {
        "status": "ok",
        "message": "하루 전체 일정을 봐도 이동 시간과 여유가 충분해요!",
    }


def shift_last_event(minutes: int):
    """내부 로직용: 마지막 일정 시간을 분 단위로 미루기 (UI에서는 현재 사용 X)"""
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

st.markdown('<div class="app-title">📅 일정? 바로잡GO!</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-subtitle">대한민국에 한하여 작동하는 프로그램입니다.</div>',
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

        # 입력이 바뀌면 자동완성 페이지 1로 초기화
        current_input = loc_input.strip()
        if st.session_state.last_loc_input != current_input:
            st.session_state.autocomplete_page = 1
            st.session_state.last_loc_input = current_input

        if current_input:
            autocomplete_results = places_autocomplete(current_input)
            if autocomplete_results:
                chosen_idx = st.radio(
                    "주소 자동완성 결과",
                    options=list(range(len(autocomplete_results))),
                    format_func=lambda i: autocomplete_results[i]["description"],
                    key="autocomplete_choice",
                )
                chosen_desc = autocomplete_results[chosen_idx]["description"]
                chosen_place_id = autocomplete_results[chosen_idx]["place_id"]
                st.caption(
                    f"선택된 주소: {chosen_desc}  "
                    f"(페이지 {st.session_state.autocomplete_page}/{st.session_state.autocomplete_total_pages})"
                )
            else:
                st.caption("자동완성 결과가 없습니다. 주소를 조금 더 구체적으로 입력해 보세요.")

        memo = st.text_area("메모 (선택)", placeholder="간단한 메모를 적을 수 있어요.")

        # 🔁 체크하면 Google Calendar에도 같이 저장
        save_to_google = st.checkbox("이 일정을 내 Google Calendar에도 저장하기", value=False)

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

                # 1) 프로그램 내 목록에 추가
                st.session_state.custom_events.append(new_event)
                st.session_state.last_added_event = new_event
                st.success("새 일정을 화면 내 목록에 추가했습니다. (Google Calendar에는 자동으로 쓰지 않습니다.)")

                # 2) 체크된 경우에만 Google Calendar에도 실제 저장
                if save_to_google:
                    service, err = get_calendar_service()
                    if err or not service:
                        st.error(err or "Google Calendar service 생성 실패")
                    else:
                        ev_id = create_google_event_from_custom(service, new_event)
                        if ev_id:
                            st.success("✅ Google Calendar에도 일정을 저장했습니다!")

    # 🔢 폼 밖: 주소 자동완성 페이지 네비게이션 (< ◀ 1 2 3 ▶ >)
    if st.session_state.last_loc_input:
        total_pages = st.session_state.autocomplete_total_pages
        current_page = st.session_state.autocomplete_page
        if total_pages > 1:
            st.markdown("##### 주소 자동완성 페이지 이동")
            nav_cols = st.columns(total_pages + 2)

            # ◀ 이전
            with nav_cols[0]:
                if st.button("◀", key="auto_prev", disabled=(current_page == 1)):
                    st.session_state.autocomplete_page = current_page - 1
                    st.experimental_rerun()

            # 1,2,3 번호 버튼
            for i in range(1, total_pages + 1):
                with nav_cols[i]:
                    if st.button(f"{i}", key=f"auto_page_{i}", help=f"{i}페이지 보기"):
                        st.session_state.autocomplete_page = i
                        st.experimental_rerun()

            # ▶ 다음
            with nav_cols[-1]:
                if st.button("▶", key="auto_next", disabled=(current_page == total_pages)):
                    st.session_state.autocomplete_page = current_page + 1
                    st.experimental_rerun()

    if st.session_state.last_added_event and st.session_state.last_added_event.get("location"):
        st.markdown("#### 🗺 방금 추가한 일정 위치 (Google 지도)")
        loc = st.session_state.last_added_event["location"]
        st.write(f"📍 {loc}")
        key = get_maps_api_key()
        if key:
            q = urllib.parse.quote(loc)
            src = f"https://www.google.com/maps/embed/v1/place?key={key}&q={q}"
            iframe_html = f"""
            <iframe
                width="100%"
                height="300"
                style="border:0; border-radius: 14px;"
                loading="lazy"
                referrerpolicy="no-referrer-when-downgrade"
                src="{src}">
            </iframe>
            """
            st.markdown(iframe_html, unsafe_allow_html=True)
    else:
        st.caption("위에서 일정을 추가하면 이곳에 지도가 표시됩니다.")

    st.markdown("</div>", unsafe_allow_html=True)

# ---------- 3. 기존 일정 ↔ 새 일정 거리·시간 비교 ----------
with st.container():
    st.markdown('<div class="section-card">', unsafe_allow_html=True)

    st.markdown("### 3. 기존 일정 ↔ 새 일정 거리·시간 비교")

    calendar_events_with_loc = [
        ev for ev in st.session_state.google_events if ev.get("location")
    ]

    base_event = None

    if not calendar_events_with_loc:
        st.info("위치 정보가 있는 Google Calendar 일정이 없습니다.")
    else:
        ne = st.session_state.last_added_event
        filtered_calendar_events = calendar_events_with_loc

        # 프로그램에 등록한 일정의 날짜 이후 일정만 선택 가능
        if ne:
            new_date = ne["date"]
            tmp = []
            for ev in calendar_events_with_loc:
                try:
                    start_dt = parse_iso_or_date(ev["start_raw"])
                    if start_dt.date() >= new_date:
                        tmp.append(ev)
                except Exception:
                    continue
            filtered_calendar_events = tmp

        if ne and not filtered_calendar_events:
            st.info("프로그램에 등록한 일정 날짜 이후의 캘린더 일정이 없습니다.")
        else:
            left, right = st.columns(2)

            with left:
                base_event = st.selectbox(
                    "기준이 될 캘린더 일정 선택",
                    options=filtered_calendar_events,
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

        if st.session_state.last_added_event and base_event is not None:
            base_loc_text = base_event["location"]
            new_loc_text = st.session_state.last_added_event["location"]

            if not new_loc_text:
                st.warning("새 일정에 장소가 입력되어 있어야 이동경로를 계산할 수 있습니다.")
            else:
                is_same_day: Optional[bool] = None
                gap_min: Optional[float] = None

                try:
                    base_start_dt = parse_iso_or_date(base_event["start_raw"])
                    base_end_dt = parse_iso_or_date(base_event["end_raw"])

                    new_date = st.session_state.last_added_event["date"]
                    new_start_dt = dt.datetime.combine(
                        new_date,
                        st.session_state.last_added_event["start_time"],
                    )
                    new_end_dt = dt.datetime.combine(
                        new_date,
                        st.session_state.last_added_event["end_time"],
                    )

                    if base_start_dt.tzinfo is not None:
                        base_start_dt = base_start_dt.replace(tzinfo=None)
                    if base_end_dt.tzinfo is not None:
                        base_end_dt = base_end_dt.replace(tzinfo=None)

                    is_same_day = (base_start_dt.date() == new_start_dt.date())

                    if is_same_day:
                        if (new_start_dt < base_end_dt) and (base_start_dt < new_end_dt):
                            overlap_start = max(new_start_dt, base_start_dt)
                            overlap_end = min(new_end_dt, base_end_dt)
                            overlap_min = (overlap_end - overlap_start).total_seconds() / 60.0
                            gap_min = -overlap_min
                        else:
                            if base_end_dt <= new_start_dt:
                                first_end = base_end_dt
                                second_start = new_start_dt
                            else:
                                first_end = new_end_dt
                                second_start = base_start_dt

                            gap_min = (second_start - first_end).total_seconds() / 60.0

                except Exception:
                    gap_min = None

                origin_text = base_loc_text
                origin_label = "기존 일정 위치"

                if is_same_day is False:
                    origin_text = DEFAULT_BASE_LOCATION
                    origin_label = f"기본 위치({DEFAULT_BASE_LOCATION})"

                st.markdown("#### 🗺 이동 경로 지도")

                travel_min: Optional[float] = None

                if mode_value in ("driving", "walking", "bicycling"):
                    travel_min, route_path, coords = get_tmap_route(origin_text, new_loc_text, mode_value)
                    if coords:
                        sx, sy, ex, ey = coords
                        render_tmap_route_map(sx, sy, ex, ey, mode_value)
                    else:
                        st.caption("경로 좌표를 가져오지 못해 Tmap 지도를 표시하지 못했습니다.")
                else:
                    travel_min = get_google_travel_time_minutes(origin_text, new_loc_text, "transit")

                    st.markdown("##### 🚇 대중교통 경로 지도 (Google)")

                    key = get_maps_api_key()
                    if key:
                        o = urllib.parse.quote(origin_text)
                        d = urllib.parse.quote(new_loc_text)
                        src = (
                            f"https://www.google.com/maps/embed/v1/directions"
                            f"?key={key}&origin={o}&destination={d}&mode=transit"
                        )
                        iframe_html = f"""
                        <iframe
                            width="100%"
                            height="420"
                            style="border:0; border-radius: 14px;"
                            loading="lazy"
                            referrerpolicy="no-referrer-when-downgrade"
                            src="{src}">
                        </iframe>
                        """
                        st.markdown(iframe_html, unsafe_allow_html=True)
                    else:
                        st.caption("⚠ Google Maps API 키가 없어 대중교통 경로 지도를 표시할 수 없습니다.")

                st.markdown("#### ⏱ 기준 일정 vs 새 일정 간 간격")

                st.write(f"- 이번 비교에서 출발지는 **{origin_label}** 기준입니다.")

                if travel_min is not None:
                    st.write(f"- 예상 이동 시간: **약 {travel_min:.0f}분**")
                else:
                    st.write("- 이동 시간을 계산할 수 없습니다.")

                if gap_min is not None:
                    if gap_min < 0:
                        st.write(
                            f"- 기준 일정과 새 일정의 시간이 **약 {abs(gap_min):.0f}분 정도 실제로 겹쳐 있습니다.**"
                        )
                    else:
                        st.write(
                            f"- 선행 일정 종료 → 후행 일정 시작 사이 간격: **약 {gap_min:.0f}분**"
                        )
                elif is_same_day is False:
                    st.write("- 서로 다른 날짜의 일정이라 시간상으로는 겹치지 않습니다.")
                else:
                    st.write("- 일정 간 간격을 계산할 수 없습니다.")

                # ==== 하루 전체 일정 기준 안내 ====
                st.markdown("#### 📋 하루 전체 일정 기준 안내")

                ne = st.session_state.last_added_event
                new_start_all = dt.datetime.combine(ne["date"], ne["start_time"])
                new_end_all = dt.datetime.combine(ne["date"], ne["end_time"])

                new_ev_logic = {
                    "start": new_start_all,
                    "end": new_end_all,
                    "location": ne.get("location", ""),
                    "source": "program",
                }

                existing_logic: List[Dict] = []

                # 구글 일정들
                for gev in st.session_state.google_events:
                    try:
                        s = parse_iso_or_date(gev["start_raw"])
                        e = parse_iso_or_date(gev["end_raw"])
                        if s.tzinfo is not None:
                            s = s.replace(tzinfo=None)
                        if e.tzinfo is not None:
                            e = e.replace(tzinfo=None)
                        existing_logic.append(
                            {
                                "start": s,
                                "end": e,
                                "location": gev.get("location", ""),
                                "source": "google",
                            }
                        )
                    except Exception:
                        continue

                # 이미 추가된 커스텀 일정들
                for cev in st.session_state.custom_events:
                    s = dt.datetime.combine(cev["date"], cev["start_time"])
                    e = dt.datetime.combine(cev["date"], cev["end_time"])
                    existing_logic.append(
                        {
                            "start": s,
                            "end": e,
                            "location": cev.get("location", ""),
                            "source": "program",
                        }
                    )

                eval_all = evaluate_new_event_against_all(
                    new_ev_logic,
                    existing_logic,
                    mode=mode_value if mode_value != "transit" else "driving",
                )

                if eval_all["status"] == "warn":
                    st.warning(eval_all["message"])
                else:
                    st.success(eval_all["message"])

    st.markdown("</div>", unsafe_allow_html=True)
