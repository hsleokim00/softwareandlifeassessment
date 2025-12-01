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
    st.session_state.google_events = []

if "custom_events" not in st.session_state:
    st.session_state.custom_events = []

if "last_added_event" not in st.session_state:
    st.session_state.last_added_event = None


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
    Google Geocoding 사용
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


# ---- Places 자동완성 ----
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
    """
    features 배열에서 totalTime(sec)와 전체 경로 좌표(lon, lat 리스트)를 추출
    """
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
    """
    mode: 'driving', 'walking', 'bicycling'
    반환: (예상시간_분, 경로좌표[ [lon,lat], ... ], (startX, startY, endX, endY))
    """
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
            # 보행자 경로
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
                # 자전거: 도보보다 약 3배 빠른 정도로 (0.35배)
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
    """
    Tmap JS v2를 사용해 Streamlit 안에 경로 지도 렌더링
    mode: 'walking', 'bicycling', 'driving'
    """
    app_key = get_tmap_app_key()
    if not app_key:
        st.caption("⚠ Tmap appKey가 없어 경로 지도를 표시할 수 없습니다.")
        return

    # 보행자/자전거는 pedestrian API, 자동차는 routes API로 구분
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
                var headers = {{}};
                headers["appKey"] = "{app_key}";

                var url;
                var data;

                if ("{route_api}" === "pedestrian") {{
                    url = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1&format=json";
                    data = {{
                        startX: "{start_x}",
                        startY: "{start_y}",
                        endX: "{end_x}",
                        endY: "{end_y}",
                        reqCoordType: "WGS84GEO",
                        resCoordType: "EPSG3857"
                    }};
                }} else {{
                    url = "https://apis.openapi.sk.com/tmap/routes?version=1&format=json";
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
                    headers: headers,
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


# ==================== (추가) 일정 충돌/이동시간 로직용 유틸 ====================

def to_minutes(delta: dt.timedelta) -> int:
    """timedelta -> 분 단위 정수"""
    return int(delta.total_seconds() // 60)


def get_travel_minutes_for_logic(origin: str, dest: str, mode: str = "driving") -> int:
    """
    로직 계산용 이동시간(분).
    - 기본: 자동차(Tmap driving)
    - origin/dest 없거나 API 실패 시 0분으로 처리
    """
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


# ---- (추가) 이동시간 vs 간격 평가 공통 함수 ----
BUFFER_MIN = 30  # 이동 후 여유 시간(분)


def evaluate_time_gap(move_min: float, gap_min: float, label: str = "선행 일정") -> Dict[str, object]:
    """
    이동시간 vs 일정 간 간격 평가
    - move_min: 이동 시간(분)
    - gap_min : 선행 일정 종료 -> 후행 일정 시작 사이 간격(분)
    - label   : 선행 일정을 설명하는 라벨 문자열

    반환:
    {
        "level": 0|1|2,   # 0: 충분, 1: 빠듯(추천), 2: 실제 겹침/도착 불가(강한 경고)
        "shortage": int,  # 부족한 분 (0 이상) – '이 정도는 미루는 걸 추천'
        "msg": str,
    }
    """

    # gap_min < 0 이면 이미 시간이 겹쳐 있는 상태
    if gap_min < 0:
        overlap = abs(gap_min)
        msg = (
            f"{label} 종료 시각과 새 일정 시작 시각이 이미 {overlap:.0f}분만큼 겹쳐 있어요. "
            f"실제로 시간이 겹치는 상태라, 최소 {overlap:.0f}분 이상은 일정을 조정해야 해요."
        )
        return {
            "level": 2,
            "shortage": overlap,
            "msg": msg,
        }

    # 1) 이동 시간 자체가 간격보다 길면 → 실제로 도착 불가 (강한 경고)
    if move_min > gap_min:
        shortage = move_min - gap_min
        msg = (
            f"{label} 종료 → 새 일정 시작 사이 간격은 {gap_min:.0f}분인데, "
            f"이동 시간이 {move_min:.0f}분이라 실제로 시간이 겹쳐요. "
            f"최소 {shortage:.0f}분 이상 일정을 미루어야 해요."
        )
        return {
            "level": 2,
            "shortage": shortage,
            "msg": msg,
        }

    # 2) 이동은 가능하지만, 이동 + 여유 30분이 모자람 → 빠듯(추천)
    if move_min + BUFFER_MIN > gap_min:
        shortage = (move_min + BUFFER_MIN) - gap_min
        msg = (
            f"{label} 종료 → 새 일정 시작 사이 간격은 {gap_min:.0f}분, "
            f"이동 시간은 {move_min:.0f}분이에요. 이동은 가능하지만, "
            f"이동 후 여유 {BUFFER_MIN}분까지 생각하면 "
            f"{shortage:.0f}분 정도 일정을 미루면 더 여유롭겠어요."
        )
        return {
            "level": 1,
            "shortage": shortage,
            "msg": msg,
        }

    # 3) 이동 + 여유까지 모두 충분 → 문제 없음
    msg = (
        f"{label} 종료 → 새 일정 시작 사이 간격은 {gap_min:.0f}분, "
        f"이동 시간은 {move_min:.0f}분이라 여유 {BUFFER_MIN}분까지 포함해도 충분해요."
    )
    return {
        "level": 0,
        "shortage": 0,
        "msg": msg,
    }


def compare_two_events_logic(new_ev: Dict, other: Dict, mode: str = "driving") -> Optional[Dict]:
    """
    새로 입력한 일정(new_ev)과 기존 일정(other)을 비교해서
    - i-a) 약속 시간이 겹치는 경우:
        k = (겹치는 시간) + (이동시간) + 30
    - i-b) 겹치지 않지만 이동시간을 고려하면 도착 불가능한 경우:
        k = (선행 종료 - 후행 시작 + 이동시간) + 30  (= -gap + travel + 30)
    를 계산해서 반환.

    반환 예:
      {'type': 'overlap', 'k': 50}
      {'type': 'travel_impossible', 'k': 40}
      문제가 없으면 None
    """
    start_new: dt.datetime = new_ev["start"]
    end_new: dt.datetime = new_ev["end"]
    start_o: dt.datetime = other["start"]
    end_o: dt.datetime = other["end"]

    # 날짜가 다르면 이 둘 사이에서는 충돌 계산 안 함
    if start_new.date() != start_o.date():
        return None

    # 1) 시간이 겹치는지 확인 (i-a)
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

    # 2) 시간이 안 겹칠 때: 선행/후행 구분 (i-b)
    if end_new <= start_o:
        # new_ev가 선행
        first, second = new_ev, other
    elif end_o <= start_new:
        # other가 선행
        first, second = other, new_ev
    else:
        # 이 경우는 논리상 이미 겹치는 케이스라 여기까지 오지 않는 게 정상
        return None

    travel_min = get_travel_minutes_for_logic(
        first.get("location", ""),
        second.get("location", ""),
        mode=mode,
    )
    gap_min = to_minutes(second["start"] - first["end"])  # (후행 시작 - 선행 종료)

    # 의미상:
    #   (후행 시작 - 선행 종료 - 이동시간) > 0  → 이동 가능
    # 코드: gap_min - travel_min > 0 이면 OK
    if gap_min - travel_min > 0:
        return None  # 이동 가능 → k 필요 없음

    # 이동 불가능 → k 계산
    #   k = (선행 종료 - 후행 시작 + 이동시간) + 30 = (-gap_min + travel_min) + 30
    k = (-gap_min + travel_min) + 30
    return {"type": "travel_impossible", "k": max(0, k)}


def evaluate_new_event_against_all(new_ev_logic: Dict, existing_logic: List[Dict], mode: str = "driving") -> Dict:
    """
    새 일정 vs 기존 모든 일정(구글 + 커스텀)을 비교해서
    i) 경고 & 미루기 추천 / ii) 그대로 등록 추천 을 판정.

    반환 예:
      {"status": "warn", "k": 60, "message": "..."}
      {"status": "ok", "message": "..."}
    """
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

    # ii-a) 같은 날짜 일정 자체가 없을 때
    if not same_date_found:
        return {
            "status": "ok",
            "message": "겹치는 일정이 없네요! 입력하신 일정을 등록하겠습니다!",
        }

    # i-a) 날짜는 같고, 시간이 실제로 겹치는 일정이 있을 때
    if best_overlap_k > 0:
        return {
            "status": "warn",
            "k": best_overlap_k,
            "message": f"약속 시간이 겹치네요!! {best_overlap_k}분 만큼 약속을 미루는 것을 추천해요!",
        }

    # i-b) 날짜는 같고, 시간은 안 겹치지만 이동시간 때문에 도착 불가능한 경우
    if best_travel_k > 0:
        return {
            "status": "warn",
            "k": best_travel_k,
            "message": f"이동 시간을 고려했을 때, 제시간에 도착하지 못할 수도 있어요! {best_travel_k}분 만큼 약속을 미루는 것을 추천해요!",
        }

    # ii-b) 날짜는 같고, 모든 일정 쌍에 대해 이동 충분
    return {
        "status": "ok",
        "message": "일정 간 이동이 충분히 가능해요! 입력하신 일정을 등록하겠습니다!!",
    }


# ---- 새 일정 시간 미루기 ----
def shift_last_event(minutes: int):
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

                # ====== 새 일정 vs 기존 모든 일정 로직 적용 ======
                new_start_dt = dt.datetime.combine(date, start_time)
                new_end_dt = dt.datetime.combine(date, end_time)
                new_ev_logic = {
                    "start": new_start_dt,
                    "end": new_end_dt,
                    "location": final_location,
                    "source": "program",
                }

                existing_logic: List[Dict] = []

                # 1) 구글 일정들
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

                # 2) 이미 추가된 커스텀 일정들
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

                eval_result = evaluate_new_event_against_all(
                    new_ev_logic,
                    existing_logic,
                    mode="driving",
                )

                if eval_result["status"] == "warn":
                    st.warning(eval_result["message"])
                else:
                    st.info(eval_result["message"])
                # ====== 로직 끝, 기존 기능 그대로 유지 ======

                st.session_state.custom_events.append(new_event)
                st.session_state.last_added_event = new_event
                st.success("새 일정을 화면 내 목록에 추가했습니다. (Google Calendar에는 쓰지 않습니다.)")

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

                travel_min: Optional[float] = None

                if mode_value in ("driving", "walking", "bicycling"):
                    travel_min, route_path, coords = get_tmap_route(base_loc_text, new_loc_text, mode_value)
                    if coords:
                        sx, sy, ex, ey = coords
                        render_tmap_route_map(sx, sy, ex, ey, mode_value)
                    else:
                        st.caption("경로 좌표를 가져오지 못해 Tmap 지도를 표시하지 못했습니다.")
                else:
                    # 대중교통 → Google 지도 embed + 예상 시간 계산
                    travel_min = get_google_travel_time_minutes(base_loc_text, new_loc_text, "transit")

                    st.markdown("##### 🚇 대중교통 경로 지도 (Google)")

                    key = get_maps_api_key()
                    if key:
                        o = urllib.parse.quote(base_loc_text)
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

                # ---- 일정 간 간격 + 겹침/추천 로직 (선행/후행 판단 포함) ----
                is_same_day: Optional[bool] = None
                gap_min: Optional[float] = None
                delay_min_recommend: Optional[int] = None

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

                    # 타임존 제거
                    if base_start_dt.tzinfo is not None:
                        base_start_dt = base_start_dt.replace(tzinfo=None)
                    if base_end_dt.tzinfo is not None:
                        base_end_dt = base_end_dt.replace(tzinfo=None)

                    is_same_day = (base_start_dt.date() == new_start_dt.date())

                    if is_same_day:
                        # 1) 시간이 실제로 겹치는지 먼저 확인
                        if (new_start_dt < base_end_dt) and (base_start_dt < new_end_dt):
                            overlap_start = max(new_start_dt, base_start_dt)
                            overlap_end = min(new_end_dt, base_end_dt)
                            overlap_min = (overlap_end - overlap_start).total_seconds() / 60.0
                            # 겹친 경우 gap_min을 음수로 전달 → evaluate_time_gap에서 level 2 처리
                            gap_min = -overlap_min
                        else:
                            # 2) 겹치지 않으면 선행/후행 구분해서 "선행 종료 → 후행 시작" 간격 계산
                            if base_end_dt <= new_start_dt:
                                # 기존 일정이 선행, 새 일정이 후행
                                first_end = base_end_dt
                                second_start = new_start_dt
                            else:
                                # 새 일정이 선행, 기존 일정이 후행
                                first_end = new_end_dt
                                second_start = base_start_dt

                            gap_min = (second_start - first_end).total_seconds() / 60.0

                except Exception:
                    gap_min = None

                st.markdown("#### ⏱ 이동 시간 vs 일정 간 간격")

                # 예상 이동 시간 출력
                if travel_min is not None:
                    st.write(f"- 예상 이동 시간: **약 {travel_min:.0f}분**")
                else:
                    st.write("- 이동 시간을 계산할 수 없습니다.")

                # 간격 출력
                if gap_min is not None:
                    if gap_min < 0:
                        st.write(
                            f"- 기존 일정과 새 일정의 시간이 **약 {abs(gap_min):.0f}분 정도 실제로 겹쳐 있습니다.**"
                        )
                    else:
                        st.write(
                            f"- 선행 일정 종료 → 후행 일정 시작 사이 간격: **약 {gap_min:.0f}분**"
                        )
                elif is_same_day is False:
                    st.write("- 서로 다른 날짜의 일정이라 시간상 겹치지 않아요.")
                else:
                    st.write("- 일정 간 간격을 계산할 수 없습니다.")

                # ====== 추천 로직 (evaluate_time_gap 사용) ======
                if (travel_min is not None) and (is_same_day is True) and (gap_min is not None):
                    result_gap = evaluate_time_gap(
                        move_min=float(travel_min),
                        gap_min=float(gap_min),
                        label="선행 일정",
                    )

                    level = result_gap["level"]
                    shortage = result_gap["shortage"]
                    msg = result_gap["msg"]

                    delay_min_recommend = int(math.ceil(shortage)) if shortage > 0 else 0

                    if level == 2:
                        st.error("🚨 2단계 경고 (실제 겹침/도착 불가)\n\n" + msg)
                    elif level == 1:
                        st.warning("⚠️ 1단계 알림 (이동 가능하지만 빠듯함)\n\n" + msg)
                    else:
                        st.success("✅ 문제 없음 (이동 + 여유 30분까지 충분)\n\n" + msg)

                elif (travel_min is not None) and (is_same_day is False):
                    # 날짜가 서로 다르면, 겹칠 수 없으므로 이 한 줄로 끝
                    st.info("📅 서로 다른 날짜라서 일정이 겹치지 않아요. 그대로 진행해도 됩니다.")
                else:
                    # 데이터 부족한 경우
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
