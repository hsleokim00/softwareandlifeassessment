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
SCOPES = ["https://www.googleapis.com/auth/calendar"]   # 읽기+쓰기 허용

DEFAULT_BASE_LOCATION = "하나고등학교"
MAX_PLACE_SUGGESTIONS = 15

st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ==================== CSS ====================
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

.section-card {
    padding: 1.2rem 1.2rem;
    border-radius: 14px;
    background: #ffffff;
    border: 1px solid #e7f4f3;
    box-shadow: 0 4px 12px rgba(0,0,0,0.04);
    margin-bottom: 1.3rem;
}

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

.stTextInput > div > div > input,
.stTextArea > div > textarea,
.stDateInput > div > input,
.stTimeInput > div > input {
    border-radius: 10px !important;
}

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


# ==================== Places 자동완성 ====================

PLACES_PER_PAGE = 5
MAX_AUTO_PAGES = 3
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
    Google Places Text Search 기반 자동완성
    - 최대 15개
    - 거리순 정렬
    - 페이지네이션 적용
    """
    key = get_maps_api_key()
    if not key or not text.strip():
        if not key:
            st.warning("⚠ Google Maps API 키가 없습니다.")
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
        if data.get("status") != "OK":
            st.caption(f"장소 검색 상태: {data.get('status')}")
            return []

        raw = data.get("results", [])[: PLACES_PER_PAGE * MAX_AUTO_PAGES]
        base = _get_base_coord()

        enriched = []
        for r in raw:
            name = r.get("name", "")
            addr = r.get("formatted_address", "")
            place_id = r.get("place_id", "")
            geom = r.get("geometry", {}).get("location")

            if not (name or addr):
                continue

            dist = 1e9
            if base and geom:
                try:
                    lon = float(geom["lng"])
                    lat = float(geom["lat"])
                    dist = _haversine(base[0], base[1], lon, lat)
                except:
                    pass

            enriched.append(
                {
                    "name": name,
                    "addr": addr,
                    "place_id": place_id,
                    "distance": dist,
                }
            )

        enriched.sort(key=lambda x: x["distance"])

        total = len(enriched)
        total_pages = max(1, min(MAX_AUTO_PAGES, math.ceil(total / PLACES_PER_PAGE)))
        st.session_state.autocomplete_total_pages = total_pages

        page = st.session_state.autocomplete_page
        page = max(1, min(page, total_pages))  # 클램프
        st.session_state.autocomplete_page = page

        start = (page - 1) * PLACES_PER_PAGE
        end = start + PLACES_PER_PAGE
        rows = enriched[start:end]

        results = []
        for r in rows:
            desc = f"{r['name']} ({r['addr']})" if r["name"] and r["addr"] else (r["name"] or r["addr"])
            results.append(
                {
                    "description": desc,
                    "place_id": r["place_id"],
                }
            )
        return results

    except Exception as e:
        st.caption(f"장소 검색 오류: {e}")
        return []


# ---- Google Distance Matrix 시간 ----
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
        if data.get("status") != "OK":
            st.caption(f"Distance Matrix 상태: {data.get('status')}")
            return None

        el = data.get("rows", [{}])[0].get("elements", [{}])[0]
        if el.get("status") != "OK":
            return None

        return el["duration"]["value"] / 60.0
    except:
        return None


# ---- Tmap 경로에서 시간 + 경로선 추출 ----
def _extract_tmap_time_and_path(features: List[Dict]) -> Tuple[Optional[float], List[List[float]]]:
    total_sec = None
    path = []

    for f in features:
        props = f.get("properties", {})
        if total_sec is None and "totalTime" in props:
            try:
                total_sec = float(props["totalTime"])
            except:
                pass

        geom = f.get("geometry", {})
        if geom.get("type") == "LineString":
            for c in geom.get("coordinates", []):
                if isinstance(c, (list, tuple)) and len(c) >= 2:
                    lon, lat = float(c[0]), float(c[1])
                    path.append([lon, lat])

    return total_sec, path


# ---- Tmap 경로 + 시간 ----
def get_tmap_route(origin: str, dest: str, mode: str):
    """
    return: (minutes, path, (start_x, start_y, end_x, end_y))
    """
    app_key = get_tmap_app_key()
    if not app_key:
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
            data = resp.json()
            total_sec, path = _extract_tmap_time_and_path(data.get("features", []))
            if total_sec is None:
                return None, path, (start_x, start_y, end_x, end_y)
            minutes = total_sec / 60.0
            if mode == "walking":
                return minutes, path, (start_x, start_y, end_x, end_y)
            else:
                return minutes * 0.35, path, (start_x, start_y, end_x, end_y)

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
            data = resp.json()
            total_sec, path = _extract_tmap_time_and_path(data.get("features", []))
            if total_sec is None:
                return None, path, (start_x, start_y, end_x, end_y)
            return total_sec / 60.0, path, (start_x, start_y, end_x, end_y)

        else:
            return None, None, (start_x, start_y, end_x, end_y)

    except Exception as e:
        st.caption(f"Tmap 경로 오류: {e}")
        return None, None, (start_x, start_y, end_x, end_y)


# ---- Tmap JS 지도 렌더러 (경로선 표시) ----
def render_tmap_route_map(start_x: float, start_y: float, end_x: float, end_y: float, mode: str, height: int = 420):
    app_key = get_tmap_app_key()
    if not app_key:
        st.caption("⚠ Tmap appKey가 없어 지도를 표시할 수 없습니다.")
        return

    if mode in ("walking", "bicycling"):
        route_api = "pedestrian"
        stroke_color = "#0078ff"
    else:
        route_api = "routes"
        stroke_color = "#dd0000"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <script src="https://code.jquery.com/jquery-3.2.1.min.js"></script>
        <script src="https://apis.openapi.sk.com/tmap/jsv2?version=1&appKey={app_key}"></script>
        <style>
            html, body {{ margin:0; padding:0; width:100%; height:100%; }}
            #map_div {{ width:100%; height:100%; }}
        </style>
    </head>
    <body>
        <div id="map_div"></div>
        <script>
            var map;

            function init() {{
                map = new Tmapv2.Map("map_div", {{
                    center: new Tmapv2.LatLng({start_y}, {start_x}),
                    width: "100%",
                    height: "100%",
                    zoom: 14
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
                        var drawArr = [];

                        for (var i=0; i < resultData.length; i++) {{
                            var geom = resultData[i].geometry;
                            if (geom.type === "LineString") {{
                                for (var j=0; j < geom.coordinates.length; j++) {{
                                    var pt = new Tmapv2.Point(geom.coordinates[j][0], geom.coordinates[j][1]);
                                    var geo = Tmapv2.Projection.convertEPSG3857ToWGS84GEO(pt);
                                    drawArr.push(new Tmapv2.LatLng(geo._lat, geo._lng));
                                }}
                            }}
                        }}

                        if (drawArr.length > 0) {{
                            new Tmapv2.Polyline({{
                                path: drawArr,
                                strokeColor: "{stroke_color}",
                                strokeWeight: 6,
                                map: map
                            }});
                            map.setCenter(drawArr[0]);
                        }}
                    }},
                    error: function(r, s, e) {{
                        console.log("Tmap 경로 에러:", r.status);
                    }}
                }});
            }}

            window.onload = init;
        </script>
    </body>
    </html>
    """

    components.html(html, height=height, scrolling=False)
# ---- Google Directions JS: 경유지 포함 경로선 표시 ----
def google_travel_mode_js(mode: str) -> str:
    mapping = {
        "transit": "TRANSIT",
        "driving": "DRIVING",
        "walking": "WALKING",
        "bicycling": "BICYCLING",
    }
    return mapping.get(mode, "DRIVING")


def _escape_js_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render_google_route_map_with_waypoints(
    api_key: str,
    origin: str,
    destination: str,
    waypoint: Optional[str],
    mode: str,
    height: int = 420,
):
    origin_js = _escape_js_string(origin)
    dest_js = _escape_js_string(destination)
    waypoint_js = _escape_js_string(waypoint) if waypoint else ""
    mode_js = google_travel_mode_js(mode)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <style>
            html, body {{ margin:0; padding:0; width:100%; height:100%; }}
            #map {{ width:100%; height:100%; }}
        </style>
        <script>
            function initMap() {{
                var map = new google.maps.Map(document.getElementById('map'), {{
                    zoom: 13,
                    center: {{lat: 37.5665, lng: 126.9780}}
                }});

                var ds = new google.maps.DirectionsService();
                var dr = new google.maps.DirectionsRenderer({{ map: map }});

                var req = {{
                    origin: "{origin_js}",
                    destination: "{dest_js}",
                    travelMode: google.maps.TravelMode.{mode_js}
                }};

                var w = "{waypoint_js}";
                if (w !== "") {{
                    req.waypoints = [{{ location: w, stopover: true }}];
                    req.optimizeWaypoints = true;
                }}

                ds.route(req, function(result, status) {{
                    if (status === "OK") {{
                        dr.setDirections(result);
                    }} else {{
                        console.error("Directions failed:", status);
                    }}
                }});
            }}
        </script>
    </head>
    <body>
        <div id="map"></div>
        <script async defer src="https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap"></script>
    </body>
    </html>
    """

    components.html(html, height=height, scrolling=False)


# ==================== 이동시간/충돌 로직 ====================

def to_minutes(delta: dt.timedelta) -> int:
    return int(delta.total_seconds() // 60)


def get_travel_minutes_for_logic(origin: str, dest: str, mode: str = "driving") -> int:
    if not origin or not dest:
        return 0

    minutes = None

    if mode in ("driving", "walking", "bicycling"):
        minutes, _, _ = get_tmap_route(origin, dest, mode)
    else:  # transit
        minutes = get_google_travel_time_minutes(origin, dest, "transit")

    if minutes is None:
        return 0

    return int(math.ceil(minutes))


BUFFER_MIN = 30  # 이동 후 여유시간


def evaluate_time_gap(move_min: float, gap_min: float, label: str = "선행 일정") -> Dict[str, object]:
    if gap_min < 0:
        overlap = abs(gap_min)
        msg = (
            f"{label} 종료 시각과 새 일정 시작이 이미 {overlap:.0f}분 겹쳐 있어요. "
            f"최소 {overlap:.0f}분 이상 조정해야 해요."
        )
        return {"level": 2, "shortage": overlap, "msg": msg}

    if move_min > gap_min:
        shortage = move_min - gap_min
        msg = (
            f"{label} 종료 → 새 일정 시작 간격 {gap_min:.0f}분, "
            f"이동 {move_min:.0f}분 → 시간이 겹쳐요. "
            f"최소 {shortage:.0f}분 이상 미뤄야 해요."
        )
        return {"level": 2, "shortage": shortage, "msg": msg}

    if move_min + BUFFER_MIN > gap_min:
        shortage = move_min + BUFFER_MIN - gap_min
        msg = (
            f"{label} 종료 → 새 일정 시작 간격 {gap_min:.0f}분, 이동 {move_min:.0f}분. "
            f"여유 {BUFFER_MIN}분까지 포함하면 {shortage:.0f}분 정도 미루면 좋아요."
        )
        return {"level": 1, "shortage": shortage, "msg": msg}

    msg = (
        f"{label} 종료 → 새 일정 시작 간격 {gap_min:.0f}분, 이동 {move_min:.0f}분 → 충분해요!"
    )
    return {"level": 0, "shortage": 0, "msg": msg}


# ---- 하루 전체 일정 비교 (BUT k 계산은 쓰지 않음) ----
def compare_two_events_logic(new_ev: Dict, other: Dict, mode: str = "driving") -> Optional[Dict]:
    start_new = new_ev["start"]
    end_new = new_ev["end"]
    start_o = other["start"]
    end_o = other["end"]

    if start_new.date() != start_o.date():
        return None

    # 시간 겹침
    if (start_new < end_o) and (start_o < end_new):
        overlap = to_minutes(min(end_new, end_o) - max(start_new, start_o))
        travel = get_travel_minutes_for_logic(new_ev.get("location", ""), other.get("location", ""), mode)
        k = overlap + travel + BUFFER_MIN
        return {"type": "overlap", "k": k}

    # 시간은 안 겹치는데 이동이 불가
    if end_new <= start_o:
        first, second = new_ev, other
    elif end_o <= start_new:
        first, second = other, new_ev
    else:
        return None

    travel = get_travel_minutes_for_logic(first.get("location", ""), second.get("location", ""), mode)
    gap = to_minutes(second["start"] - first["end"])

    if gap - travel > 0:
        return None

    k = (-gap + travel) + BUFFER_MIN
    return {"type": "travel_impossible", "k": k}


def evaluate_new_event_against_all(new_ev_logic: Dict, existing_logic: List[Dict], mode: str):
    """하루 전체 메시지용 — 추천 k는 사용하지 않음"""
    same_date = any(ev["start"].date() == new_ev_logic["start"].date() for ev in existing_logic)
    if not same_date:
        return {"status": "ok", "message": "같은 날짜에 다른 일정이 없습니다!"}

    overlap_k = 0
    travel_k = 0

    for ev in existing_logic:
        res = compare_two_events_logic(new_ev_logic, ev, mode)
        if not res:
            continue
        if res["type"] == "overlap":
            overlap_k = max(overlap_k, res["k"])
        else:
            travel_k = max(travel_k, res["k"])

    if overlap_k > 0:
        return {"status": "warn", "message": "시간이 겹치는 일정이 있어요."}

    if travel_k > 0:
        return {"status": "warn", "message": "이동 시간이 빠듯한 일정이 있어요."}

    return {"status": "ok", "message": "하루 전체로 봐도 여유 충분해요!"}


# ==================== 연쇄 이동 기능 (Google + Custom 모두) ====================

def shift_google_event(service, event_obj, minutes: int):
    """Google Calendar 일정 1개를 minutes만큼 미루기"""
    if minutes == 0:
        return True

    event_id = event_obj["id"]
    start_raw = event_obj["start_raw"]
    end_raw = event_obj["end_raw"]

    s = parse_iso_or_date(start_raw)
    e = parse_iso_or_date(end_raw)

    ns = s + dt.timedelta(minutes=minutes)
    ne = e + dt.timedelta(minutes=minutes)

    body = {
        "start": {"dateTime": ns.isoformat(), "timeZone": "Asia/Seoul"},
        "end":   {"dateTime": ne.isoformat(), "timeZone": "Asia/Seoul"},
    }

    try:
        service.events().patch(calendarId=CALENDAR_ID, eventId=event_id, body=body).execute()
        return True
    except Exception as e:
        st.error(f"Google Calendar 이동 오류: {e}")
        return False


def shift_following_all_events(base_event, minutes: int):
    """새 일정 이후의 모든 일정(custom + google)을 minutes만큼 이동"""
    if minutes == 0:
        return

    base_end = dt.datetime.combine(base_event["date"], base_event["end_time"])

    # 1) custom_events 이동
    for ev in st.session_state.custom_events:
        if ev is base_event:
            continue
        ev_start = dt.datetime.combine(ev["date"], ev["start_time"])
        if ev_start >= base_end:
            ns = ev_start + dt.timedelta(minutes=minutes)
            ne = dt.datetime.combine(ev["date"], ev["end_time"]) + dt.timedelta(minutes=minutes)
            ev["date"] = ns.date()
            ev["start_time"] = ns.time()
            ev["end_time"] = ne.time()

    # 2) Google Calendar 이동
    service, err = get_calendar_service()
    if err or not service:
        return

    for gev in st.session_state.google_events:
        try:
            s = parse_iso_or_date(gev["start_raw"])
            if s >= base_end:
                shift_google_event(service, gev, minutes)
        except:
            continue
# ==================== UI ====================

st.markdown('<div class="app-title">📅 일정? 바로잡GO!</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-subtitle">대한민국 일정 시스템 기반으로 최적화된 프로그램입니다.</div>',
    unsafe_allow_html=True,
)

today = dt.date.today()

# -------------------------------------------------------------
# 1. Google Calendar 불러오기
# -------------------------------------------------------------
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
                st.error(f"캘린더 불러오는 중 오류 발생: {e}")

    # 날짜별 일정 보기
    selected_date = st.date_input("날짜별 일정 보기", value=today, key="calendar_date")

    # Google 일정
    day_events = []
    for ev in st.session_state.google_events:
        try:
            s = parse_iso_or_date(ev["start_raw"])
            if s.date() == selected_date:
                day_events.append(ev)
        except:
            pass

    # custom 일정
    custom_day_events = [
        ev for ev in st.session_state.custom_events if ev["date"] == selected_date
    ]

    # 출력
    if day_events or custom_day_events:
        st.markdown("**📅 선택한 날짜의 전체 일정**")

        if day_events:
            st.markdown("#### 🔹 Google Calendar 일정")
            for ev in day_events:
                disp = (
                    f"- **{ev['summary']}**  \n"
                    f"  ⏰ {format_event_time_str(ev['start_raw'], ev['end_raw'])}"
                )
                if ev.get("location"):
                    disp += f"  \n  📍 {ev['location']}"
                st.markdown(disp)

        if custom_day_events:
            st.markdown("#### 🔸 화면에서 추가한 일정")
            for ev in custom_day_events:
                disp = (
                    f"- **{ev['summary']}**  \n"
                    f"  ⏰ {ev['date']} {ev['start_time'].strftime('%H:%M')} ~ "
                    f"{ev['end_time'].strftime('%H:%M')}"
                )
                if ev.get("location"):
                    disp += f"  \n  📍 {ev['location']}"
                st.markdown(disp)

    else:
        st.caption("선택한 날짜에 일정이 없습니다.")

    # 전체 일정 Expander
    if st.session_state.google_events:
        with st.expander("📄 오늘 이후 전체 일정 보기"):
            for ev in st.session_state.google_events:
                disp = (
                    f"**{ev['summary']}**  \n"
                    f"⏰ {format_event_time_str(ev['start_raw'], ev['end_raw'])}"
                )
                if ev.get("location"):
                    disp += f"  \n📍 {ev['location']}"
                st.markdown(disp)
    else:
        st.info("아직 불러온 Google 일정이 없습니다.")

    st.markdown("</div>", unsafe_allow_html=True)
# -------------------------------------------------------------
# 2. 새 일정 입력 (주소 자동완성 포함)
# -------------------------------------------------------------
with st.container():
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### 2. 새 일정 입력 (주소 자동완성 포함)")

    with st.form("add_event_form"):
        title = st.text_input("일정 제목", placeholder="예) 동아리, 학원, 모임 등")
        date = st.date_input("날짜", value=today, key="new_event_date")
        start_time = st.time_input("시작 시간", value=dt.time(15, 0))
        end_time = st.time_input("끝나는 시간", value=dt.time(16, 0))

        # -------- 장소 자동완성 --------
        loc_input = st.text_input(
            "일정 장소 (자동완성)",
            placeholder="예) 서울시청, 강남역 2번출구 등",
            key="new_event_location",
        )

        # 자동완성 초기화
        if st.session_state.last_loc_input != loc_input.strip():
            st.session_state.autocomplete_page = 1
            st.session_state.last_loc_input = loc_input.strip()

        autocomplete_results = []
        chosen_desc = None
        chosen_place_id = None

        if loc_input.strip():
            autocomplete_results = places_autocomplete(loc_input.strip())
            if autocomplete_results:
                idx = st.radio(
                    "자동완성 결과",
                    options=list(range(len(autocomplete_results))),
                    format_func=lambda i: autocomplete_results[i]["description"],
                )
                chosen_desc = autocomplete_results[idx]["description"]
                chosen_place_id = autocomplete_results[idx]["place_id"]

                st.caption(
                    f"🛈 선택: {chosen_desc} "
                    f"({st.session_state.autocomplete_page}/{st.session_state.autocomplete_total_pages})"
                )
            else:
                st.caption("자동완성 결과 없음")

        memo = st.text_area("메모 (선택)", placeholder="간단한 설명을 적을 수 있어요.")

        save_to_google = st.checkbox("이 일정을 Google Calendar에 저장", value=False)

        submitted = st.form_submit_button("➕ 일정 추가")

        if submitted:
            if not title.strip():
                st.warning("제목은 반드시 입력해야 합니다.")
            else:
                final_loc = chosen_desc if chosen_desc else loc_input.strip()
                new_event = {
                    "summary": title.strip(),
                    "date": date,
                    "start_time": start_time,
                    "end_time": end_time,
                    "location": final_loc,
                    "place_id": chosen_place_id,
                    "memo": memo.strip(),
                }

                st.session_state.custom_events.append(new_event)
                st.session_state.last_added_event = new_event
                st.success("📌 새 일정을 화면에 추가했습니다!")

                if save_to_google:
                    service, err = get_calendar_service()
                    if not err and service:
                        ev_id = create_google_event_from_custom(service, new_event)
                        if ev_id:
                            st.success("📥 Google Calendar에도 저장 완료!")

    # 자동완성 페이지 이동 버튼
    if st.session_state.last_loc_input and st.session_state.autocomplete_total_pages > 1:
        tp = st.session_state.autocomplete_total_pages
        cp = st.session_state.autocomplete_page
        cols = st.columns(tp + 2)
        with cols[0]:
            if st.button("◀", disabled=cp == 1):
                st.session_state.autocomplete_page -= 1
                st.experimental_rerun()
        for i in range(1, tp + 1):
            with cols[i]:
                if st.button(str(i)):
                    st.session_state.autocomplete_page = i
                    st.experimental_rerun()
        with cols[-1]:
            if st.button("▶", disabled=cp == tp):
                st.session_state.autocomplete_page += 1
                st.experimental_rerun()

    # 새 일정 위치 지도 미리보기
    last = st.session_state.last_added_event
    if last and last.get("location"):
        st.markdown("#### 🗺 방금 추가한 일정 위치")
        key = get_maps_api_key()
        if key:
            q = urllib.parse.quote(last["location"])
            iframe = f"""
            <iframe
                width="100%" height="300"
                style="border:0;border-radius:12px"
                src="https://www.google.com/maps/embed/v1/place?key={key}&q={q}">
            </iframe>
            """
            st.markdown(iframe, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)



# -------------------------------------------------------------
# 3. 기존 일정 ↔ 새 일정 거리·시간 비교 + 경유지 지도 + 추천 이동 + 연쇄 이동
# -------------------------------------------------------------
with st.container():
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### 3. 기존 일정 ↔ 새 일정 거리·시간 비교")

    # 이동수단 선택
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

    ne = st.session_state.last_added_event
    if not ne:
        st.info("새 일정을 먼저 추가하세요.")
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    # 새 일정 요약
    st.markdown("#### 🆕 새 일정 정보")
    st.write(
        f"- 제목: **{ne['summary']}**  \n"
        f"- 시간: {ne['start_time'].strftime('%H:%M')} ~ {ne['end_time'].strftime('%H:%M')}  \n"
        f"- 장소: {ne['location'] or '(입력 없음)'}"
    )

    # 동일 날짜 일정 파싱
    new_date = ne["date"]
    new_start = dt.datetime.combine(new_date, ne["start_time"])
    new_end = dt.datetime.combine(new_date, ne["end_time"])
    new_loc = ne.get("location", "")

    same_day = []

    # google 일정 포함
    for gev in st.session_state.google_events:
        try:
            s = parse_iso_or_date(gev["start_raw"])
            e = parse_iso_or_date(gev["end_raw"])
            if s.date() == new_date:
                if s.tzinfo: s = s.replace(tzinfo=None)
                if e.tzinfo: e = e.replace(tzinfo=None)
                same_day.append({
                    "summary": gev["summary"],
                    "start": s,
                    "end": e,
                    "location": gev.get("location", ""),
                    "source": "google",
                    "raw_obj": gev,
                })
        except:
            pass

    # custom 일정 포함
    for cev in st.session_state.custom_events:
        if cev is ne: 
            continue
        if cev["date"] == new_date:
            s = dt.datetime.combine(cev["date"], cev["start_time"])
            e = dt.datetime.combine(cev["date"], cev["end_time"])
            same_day.append({
                "summary": cev["summary"],
                "start": s,
                "end": e,
                "location": cev.get("location", ""),
                "source": "program",
                "raw_obj": cev,
            })

    if not same_day:
        st.info("동일 날짜의 비교 대상 일정이 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    # 타임라인 정렬
    same_day.sort(key=lambda x: x["start"])

    # 앞/뒤 일정 찾기
    prev_event = None
    next_event = None
    for ev in same_day:
        if ev["end"] <= new_start:
            if not prev_event or ev["end"] > prev_event["end"]:
                prev_event = ev
        if ev["start"] >= new_end:
            if not next_event or ev["start"] < next_event["start"]:
                next_event = ev

    # 타임라인 표시
    st.markdown("#### 📆 오늘의 일정 타임라인")
    for ev in same_day:
        st.write(
            f"- [{ev['source']}] **{ev['summary']}** — "
            f"{ev['start'].strftime('%H:%M')} ~ {ev['end'].strftime('%H:%M')} / "
            f"📍 {ev['location'] or '(장소 없음)'}"
        )

    # ---------------------------------------------------------
    # 이동 가능 여부 계산
    # ---------------------------------------------------------
    st.markdown("#### ⏱ 이전·다음 일정과 이동 가능 여부")

    def link_eval(name_from, name_to, ev1, ev2):
        o = ev1.get("location") or ""
        d = ev2.get("location") or ""
        if not o or not d:
            st.write(f"- **{name_from} → {name_to}**: 장소 정보 부족")
            return None

        travel = get_travel_minutes_for_logic(
            o, d,
            mode=mode_value if mode_value != "transit" else "driving"
        )
        gap = to_minutes(ev2["start"] - ev1["end"])
        res = evaluate_time_gap(travel, gap, name_from)

        st.write(
            f"- **{name_from} → {name_to}**  \n"
            f"  · 이동시간: **{travel}분**  \n"
            f"  · 간격: **{gap}분**  \n"
            f"  · 판단: {res['msg']}"
        )
        return res

    prev_eval = next_eval = None
    if prev_event:
        prev_eval = link_eval("이전 일정", "새 일정", prev_event, {
            "start": new_start, "end": new_end, "location": new_loc
        })
    else:
        st.write("- 이전 일정 없음")

    if next_event:
        next_eval = link_eval("새 일정", "다음 일정", {
            "start": new_start, "end": new_end, "location": new_loc
        }, next_event)
    else:
        st.write("- 다음 일정 없음")

       # ---------------------------------------------------------
    # 경유지 포함 Google 지도 표시 (Embed API 사용: 경로선 확실히 보이게)
    # ---------------------------------------------------------
    st.markdown("#### 🗺 경유지 포함 이동 경로 지도")

    key = get_maps_api_key()
    if key:
        origin = dest = waypoint = None

        # 이전 + 새 + 다음 모두 있는 경우: 이전 → (새) → 다음
        if prev_event and next_event and new_loc:
            origin = prev_event["location"]
            dest = next_event["location"]
            waypoint = new_loc
        # 이전만 있는 경우: 이전 → 새
        elif prev_event and new_loc:
            origin = prev_event["location"]
            dest = new_loc
        # 다음만 있는 경우: 새 → 다음
        elif next_event and new_loc:
            origin = new_loc
            dest = next_event["location"]

        if origin and dest:
            o = urllib.parse.quote(origin)
            d = urllib.parse.quote(dest)

            # embed용 mode
            embed_mode = "driving"
            if mode_value in ("walking", "bicycling", "transit"):
                embed_mode = mode_value

            if waypoint:
                w = urllib.parse.quote(waypoint)
                src = (
                    "https://www.google.com/maps/embed/v1/directions"
                    f"?key={key}&origin={o}&destination={d}"
                    f"&mode={embed_mode}&waypoints={w}"
                )
            else:
                src = (
                    "https://www.google.com/maps/embed/v1/directions"
                    f"?key={key}&origin={o}&destination={d}"
                    f"&mode={embed_mode}"
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
            st.caption("경로를 표시할 수 없습니다. (장소 정보 부족)")
    else:
        st.caption("⚠ Google Maps API Key 없음.")

    # ---------------------------------------------------------
    # 추천 이동 k 계산 (2개 평가값의 shortage만 합산)
    # ---------------------------------------------------------
    st.markdown("#### ⭐ 추천 이동 시간 계산")

    shortages = []
    if prev_eval: shortages.append(prev_eval["shortage"])
    if next_eval: shortages.append(next_eval["shortage"])

    raw_k = max(shortages) if shortages else 0

    # 10분 단위 올림
    def ceil_to_10(x):
        return int(math.ceil(x / 10.0) * 10)

    k = ceil_to_10(raw_k)

    if k > 0:
        st.warning(f"🕒 추천: 새 일정을 **{k}분** 뒤로 미루면 더 안전해요!")
    else:
        st.success("충분한 여유가 있습니다! 이동 조정 필요 없음.")

    # ---------------------------------------------------------
    # 추천 이동 + 연쇄 이동 버튼
    # ---------------------------------------------------------
    st.markdown("#### 📥 Google Calendar 저장")

    col1, col2 = st.columns(2)

    # 그대로 저장
    with col1:
        if st.button("현재 시간 저장"):
            service, err = get_calendar_service()
            if not err and service:
                ev_id = create_google_event_from_custom(service, ne)
                if ev_id:
                    st.success("저장 완료!")

    # 추천 시간 저장 + 연쇄 조정
    if k > 0:
        new_start_shifted = new_start + dt.timedelta(minutes=k)
        new_end_shifted = new_end + dt.timedelta(minutes=k)

        with col2:
            if st.button(f"추천 시간(+{k}분) 저장 + 연쇄 이동"):
                shifted = ne.copy()
                shifted["date"] = new_start_shifted.date()
                shifted["start_time"] = new_start_shifted.time()
                shifted["end_time"] = new_end_shifted.time()

                service, err = get_calendar_service()
                if not err and service:
                    create_google_event_from_custom(service, shifted)

                # 연쇄 이동 적용
                shift_following_all_events(ne, k)

                st.success("새 일정 + 뒤 일정들까지 모두 안전하게 이동했습니다!")

    st.markdown("</div>", unsafe_allow_html=True)
