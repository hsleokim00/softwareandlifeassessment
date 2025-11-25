import streamlit as st
import datetime as dt
import calendar
from typing import List, Dict, Optional
import requests
import urllib.parse
import streamlit.components.v1 as components

# google-api-python-client이 아직 설치 안 되어 있어도 에러 안 나게 처리
try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ==================== CSS (반응형 + 스타일) ====================
st.markdown("""
<style>
/* 메인 컨테이너 */
.main .block-container {
    max-width: 900px;
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
}

/* 제목 폰트 조금 줄이기 */
.main .block-container h1 {
    font-size: 1.7rem;
}

/* ---- 달력 격자 전체 ---- */
.calendar-grid {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    grid-auto-rows: auto;
    gap: 4px;
    justify-items: center;
}

/* 요일 헤더 */
.calendar-weekday {
    text-align: center;
    font-weight: 600;
    margin-bottom: 0.1rem;
}

/* 달력 셀 */
.calendar-cell {
    width: min(11vw, 56px);
    height: min(11vw, 56px);
    border-radius: 10px;
    display: flex;
    justify-content: center;
    align-items: center;
    font-size: 0.95rem;
    margin: 0 auto 3px auto;
    border: 1px solid rgba(255,255,255,0.15);
    background-color: transparent;
    color: white;
}

/* 빈 칸 */
.calendar-empty {
    width: min(11vw, 56px);
    height: min(11vw, 56px);
    border-radius: 10px;
    background-color: rgba(255,255,255,0.03);
    margin: 0 auto 3px auto;
}

/* 오늘 날짜 */
.calendar-cell.today {
    border: 2px solid #FFD54F;
}

/* 선택된 날짜 */
.calendar-cell.selected {
    background-color: #4B8DF8;
    color: white;
}

/* 일정이 있는 날짜 */
.calendar-cell.event-day {
    box-shadow: 0 0 0 2px #ff5252 inset;
}

/* 기본 버튼 (오늘 버튼, 폼 버튼 등) */
div[data-testid="stButton"] > button {
    padding-top: 0.2rem;
    padding-bottom: 0.2rem;
    padding-left: 0.8rem;
    padding-right: 0.8rem;
    border-radius: 999px;
    font-size: 0.75rem;
}

/* 🔵 달력 화살표 전용 스타일 */
.nav-arrow-row [data-testid="stButton"] > button {
    width: 44px;
    height: 44px;
    padding: 0 !important;
    border-radius: 999px;
    font-size: 1.3rem;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* 모바일 최적화 */
@media (max-width: 600px) {
    .calendar-cell, .calendar-empty {
        width: min(12vw, 48px);
        height: min(12vw, 48px);
        font-size: 0.85rem;
    }

    .nav-arrow-row [data-testid="stButton"] > button {
        width: 40px;
        height: 40px;
        font-size: 1.2rem;
    }
}

/* ===================== 🌙 다크 / ☀ 라이트 모드 자동 감지 ===================== */

/* 🌙 다크 모드 (브라우저/OS가 다크일 때) */
@media (prefers-color-scheme: dark) {
    html, body, .main, .main .block-container {
        background-color: #0d1117 !important;
        color: #ffffff !important;
    }

    .calendar-weekday {
        color: #e6edf3 !important;
    }

    .calendar-cell {
        border: 1px solid rgba(240,246,252,0.12) !important;
        background-color: rgba(240,246,252,0.03) !important;
        color: #e6edf3 !important;
    }

    .calendar-empty {
        background-color: rgba(240,246,252,0.02) !important;
    }

    .calendar-cell.today {
        border-color: #FFD54F !important;
    }

    .calendar-cell.selected {
        background-color: #4B8DF8 !important;
        color: #ffffff !important;
    }

    .calendar-cell.event-day {
        box-shadow: 0 0 0 2px #ff5252 inset !important;
    }

    /* 버튼 */
    div[data-testid="stButton"] > button {
        background-color: #30363d !important;
        color: #ffffff !important;
        border: 1px solid #484f58 !important;
    }

    /* 입력창 */
    .stTextInput > div > div > input,
    .stTextArea textarea {
        background-color: #161b22 !important;
        color: #ffffff !important;
        border: 1px solid #30363d !important;
    }

    /* 셀렉트박스 */
    .stSelectbox > div > div {
        background-color: #161b22 !important;
        color: #ffffff !important;
    }

    /* 구분선 색 조금 어둡게 */
    hr {
        border-color: #30363d !important;
    }
}

/* ☀ 라이트 모드 (브라우저/OS가 라이트일 때) */
@media (prefers-color-scheme: light) {
    html, body, .main, .main .block-container {
        background-color: #ffffff !important;
        color: #000000 !important;
    }

    .calendar-weekday {
        color: #111827 !important;
    }

    .calendar-cell {
        border: 1px solid rgba(0,0,0,0.08) !important;
        background-color: #ffffff !important;
        color: #111827 !important;
    }

    .calendar-empty {
        background-color: rgba(0,0,0,0.03) !important;
    }

    .calendar-cell.today {
        border-color: #FFC107 !important;
    }

    .calendar-cell.selected {
        background-color: #1976d2 !important;
        color: #ffffff !important;
    }

    .calendar-cell.event-day {
        box-shadow: 0 0 0 2px #f44336 inset !important;
    }

    /* 버튼 */
    div[data-testid="stButton"] > button {
        background-color: #f3f4f6 !important;
        color: #111827 !important;
        border: 1px solid #d1d5db !important;
    }

    /* 입력창 */
    .stTextInput > div > div > input,
    .stTextArea textarea {
        background-color: #ffffff !important;
        color: #111827 !important;
        border: 1px solid #d1d5db !important;
    }

    /* 셀렉트박스 */
    .stSelectbox > div > div {
        background-color: #ffffff !important;
        color: #111827 !important;
    }

    hr {
        border-color: #e5e7eb !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ==================== KST 기준 현재 시각 ====================
KST = dt.timezone(dt.timedelta(hours=9))
now = dt.datetime.now(KST)
today = now.date()

# ==================== 세션 상태 ====================
if "cal_year" not in st.session_state:
    st.session_state.cal_year = today.year
if "cal_month" not in st.session_state:
    st.session_state.cal_month = today.month
if "selected_date" not in st.session_state:
    st.session_state.selected_date = today
if "local_events" not in st.session_state:
    st.session_state.local_events: List[Dict] = []

# 경로 미리보기용 상태
if "preview_origin" not in st.session_state:
    st.session_state.preview_origin = ""
if "preview_dest" not in st.session_state:
    st.session_state.preview_dest = ""
if "preview_mode" not in st.session_state:
    st.session_state.preview_mode = None
if "preview_minutes" not in st.session_state:
    st.session_state.preview_minutes = None

# ==================== 구글 캘린더 & 맵 연동 함수 ====================

def fetch_google_events(creds, date: dt.date) -> List[Dict]:
    """특정 날짜의 구글 캘린더 일정 가져오기."""
    if creds is None or build is None:
        return []

    service = build("calendar", "v3", credentials=creds)

    start = dt.datetime.combine(date, dt.time(0, 0, tzinfo=KST))
    end = start + dt.timedelta(days=1)

    res = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    items = res.get("items", [])
    events: List[Dict] = []

    for ev in items:
        s = ev["start"].get("dateTime") or ev["start"].get("date")
        e = ev["end"].get("dateTime") or ev["end"].get("date")

        if "T" not in s:
            sdt = dt.datetime.fromisoformat(s + "T00:00:00+09:00")
        else:
            sdt = dt.datetime.fromisoformat(s)

        if "T" not in e:
            edt = dt.datetime.fromisoformat(e + "T23:59:59+09:00")
        else:
            edt = dt.datetime.fromisoformat(e)

        events.append({
            "id": ev.get("id"),
            "title": ev.get("summary", "(제목 없음)"),
            "start_dt": sdt,
            "end_dt": edt,
            "location": ev.get("location", ""),
            "source": "google",
        })

    return events


def estimate_travel_minutes(origin: str, destination: str, api_key: Optional[str], mode: str = "driving") -> Optional[float]:
    """구글 Distance Matrix API로 특정 교통수단의 이동 시간(분) 추정."""
    if not api_key or not origin or not destination:
        return None

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "mode": mode,  # driving, transit, walking, bicycling
        "language": "ko",
        "key": api_key,
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        el = data["rows"][0]["elements"][0]
        if el.get("status") != "OK":
            return None
        return el["duration"]["value"] / 60.0
    except Exception:
        return None


def get_best_travel_option(origin: str, destination: str, api_key: Optional[str]) -> Optional[Dict]:
    """
    여러 교통수단 중 가장 빨리 도착 가능한 옵션 선택.
    반환: {"mode": "driving"/"transit"/..., "minutes": float}
    """
    modes = ["driving", "transit", "walking", "bicycling"]
    best: Optional[Dict] = None

    for m in modes:
        minutes = estimate_travel_minutes(origin, destination, api_key, mode=m)
        if minutes is None:
            continue
        if best is None or minutes < best["minutes"]:
            best = {"mode": m, "minutes": minutes}

    return best


def pretty_mode_name(mode: str) -> str:
    return {
        "driving": "자동차",
        "transit": "대중교통",
        "walking": "도보",
        "bicycling": "자전거",
    }.get(mode, mode)


def times_overlap(s1: dt.datetime, e1: dt.datetime, s2: dt.datetime, e2: dt.datetime) -> bool:
    """두 시간 구간이 겹치는지 여부."""
    return max(s1, s2) < min(e1, e2)


def find_nearest_event_by_time(events: List[Dict], target_start: dt.datetime) -> Optional[Dict]:
    """target_start와 가장 가까운 이벤트 하나."""
    if not events:
        return None
    best = None
    best_diff = None
    for ev in events:
        diff = abs((ev["start_dt"] - target_start).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best = ev
    return best


# ==================== 달력 렌더링 ====================

def move_month(delta: int):
    y = st.session_state.cal_year
    m = st.session_state.cal_month + delta
    if m < 1:
        m += 12
        y -= 1
    elif m > 12:
        m -= 12
        y += 1
    st.session_state.cal_year = y
    st.session_state.cal_month = m


def render_calendar(year: int, month: int):
    st.markdown("### 📅 달력")

    # 상단: 화살표 + 타이틀 (화살표 전용 래퍼로 감싸기)
    st.markdown('<div class="nav-arrow-row">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 3, 1])
    with c1:
        if st.button("◀", key=f"prev_{year}_{month}"):
            move_month(-1)
            st.rerun()
    with c2:
        st.markdown(f"<h4 style='text-align:center;'>{year}년 {month}월</h4>", unsafe_allow_html=True)
    with c3:
        if st.button("▶", key=f"next_{year}_{month}"):
            move_month(1)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # 달력 데이터
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    selected = st.session_state.selected_date
    event_dates = {ev["start_dt"].date() for ev in st.session_state.local_events}

    html = ['<div class="calendar-grid">']

    # 요일 헤더
    for w in ["월", "화", "수", "목", "금", "토", "일"]:
        html.append(f'<div class="calendar-weekday">{w}</div>')

    # 날짜 칸
    for week in weeks:
        for day in week:
            if day == 0:
                html.append('<div class="calendar-empty"></div>')
                continue

            current = dt.date(year, month, day)

            classes = ["calendar-cell"]
            title_attr = ""

            if current == today:
                classes.append("today")
            if current == selected:
                classes.append("selected")
            if current in event_dates:
                classes.append("event-day")
                evs = [ev for ev in st.session_state.local_events if ev["start_dt"].date() == current]
                tooltip = " | ".join(
                    f"{ev['title']} ({ev['start_dt'].strftime('%H:%M')}~{ev['end_dt'].strftime('%H:%M')})"
                    + (f" @ {ev['location']}" if ev["location"] else "")
                    for ev in sorted(evs, key=lambda e: e["start_dt"])
                ).replace('"', "'")
                if tooltip:
                    title_attr = f' title="{tooltip}"'

            class_str = " ".join(classes)
            html.append(f'<div class="{class_str}"{title_attr}>{day}</div>')

    html.append("</div>")

    st.markdown("\n".join(html), unsafe_allow_html=True)


# ==================== 메인 UI ====================

st.title("일정? 바로잡 GO!")
st.caption(f"현재 시각: {now.strftime('%Y-%m-%d %H:%M:%S')} (KST)")

# 전역 MAPS 키
MAPS_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", None)

# 날짜 선택 UI
st.markdown("### 날짜 선택")

cY, cM, cD = st.columns(3)

year_list = list(range(today.year - 5, today.year + 6))
year_sel = cY.selectbox("연도", year_list, index=year_list.index(st.session_state.cal_year))
month_sel = cM.selectbox("월", list(range(1, 13)), index=st.session_state.cal_month - 1)

days = calendar.monthrange(year_sel, month_sel)[1]
current_selected = st.session_state.selected_date
default_day = current_selected.day if (current_selected.year == year_sel and current_selected.month == month_sel) else 1
day_sel = cD.selectbox("일", list(range(1, days + 1)), index=default_day - 1)

st.session_state.cal_year = year_sel
st.session_state.cal_month = month_sel
st.session_state.selected_date = dt.date(year_sel, month_sel, day_sel)

sel_date = st.session_state.selected_date

# 달력 렌더링
render_calendar(st.session_state.cal_year, st.session_state.cal_month)

# 오늘 버튼
st.markdown("---")
if st.button("오늘로 이동"):
    st.session_state.cal_year = today.year
    st.session_state.cal_month = today.month
    st.session_state.selected_date = today
    st.rerun()

st.markdown(f"### 선택된 날짜: **{sel_date.year}년 {sel_date.month}월 {sel_date.day}일**")

# ==================== 이 날짜의 구글 캘린더 일정 ====================

st.markdown("## 이 날짜의 구글 캘린더 일정")

google_creds = st.session_state.get("google_creds", None)

if google_creds is None or build is None:
    st.caption("구글 계정 인증 정보가 없어 구글 캘린더 일정을 불러올 수 없습니다.")
    google_events_today: List[Dict] = []
else:
    try:
        google_events_today = fetch_google_events(google_creds, sel_date)
    except Exception as e:
        st.error(f"구글 캘린더를 불러오는 중 오류가 발생했습니다: {e}")
        google_events_today = []

if google_events_today:
    for ev in sorted(google_events_today, key=lambda e: e["start_dt"]):
        time_str = f"{ev['start_dt'].strftime('%H:%M')} ~ {ev['end_dt'].strftime('%H:%M')}"
        loc_str = f" · @ {ev['location']}" if ev["location"] else ""
        st.markdown(f"- **{ev['title']}** ({time_str}){loc_str}")
else:
    st.write("표시할 구글 일정이 없습니다.")

# ==================== 일정 추가 폼 ====================

st.markdown("## 일정 추가 (로컬 + 구글 일정/이동시간 겹침 확인)")

with st.form("add_event_form"):
    title = st.text_input("일정 제목", value="새 일정")
    start_time = st.time_input("시작 시간", value=dt.time(9, 0))
    end_time = st.time_input("종료 시간", value=dt.time(10, 0))
    location = st.text_input("장소(선택)", value="")
    submitted = st.form_submit_button("일정 추가")

# ==================== (1) 두 지점 직접 입력 경로 미리보기 - 일정 입력 칸 바로 아래 ====================

st.markdown("### 경로 미리보기 (두 지점 직접 입력)")

po = st.text_input(
    "출발지", 
    value=st.session_state.preview_origin, 
    key="preview_origin_input"
)
pdest = st.text_input(
    "도착지", 
    value=st.session_state.preview_dest, 
    key="preview_dest_input"
)

if st.button("이 경로 보기", key="preview_route_btn"):
    st.session_state.preview_origin = po
    st.session_state.preview_dest = pdest
    if MAPS_KEY and po and pdest:
        best = get_best_travel_option(po, pdest, MAPS_KEY)
        if best:
            st.session_state.preview_mode = best["mode"]
            st.session_state.preview_minutes = best["minutes"]
        else:
            st.session_state.preview_mode = None
            st.session_state.preview_minutes = None
    else:
        st.session_state.preview_mode = None
        st.session_state.preview_minutes = None

# 항상 이 자리에서 지도/정보 보여주기 (입력 값이 있으면)
if MAPS_KEY and st.session_state.preview_origin and st.session_state.preview_dest and st.session_state.preview_mode:
    mode = st.session_state.preview_mode
    minutes = st.session_state.preview_minutes
    origin = st.session_state.preview_origin
    dest = st.session_state.preview_dest

    st.info(
        f"**'{origin}' → '{dest}'**\n\n"
        f"- 추천 교통수단: **{pretty_mode_name(mode)}**\n"
        f"- 예상 이동 시간: **{minutes:.1f}분**"
    )

    origin_q = urllib.parse.quote_plus(origin)
    dest_q = urllib.parse.quote_plus(dest)
    embed_url = (
        "https://www.google.com/maps/embed/v1/directions"
        f"?key={MAPS_KEY}&origin={origin_q}&destination={dest_q}&mode={mode}"
    )
    iframe_html = f"""
        <iframe
            width="100%"
            height="360"
            frameborder="0"
            style="border:0; border-radius:12px;"
            src="{embed_url}"
            allowfullscreen>
        </iframe>
    """
    components.html(iframe_html, height=380)
elif st.session_state.preview_origin or st.session_state.preview_dest:
    st.warning("출발지와 도착지, 그리고 유효한 Google Maps API 키가 모두 필요합니다.")

# ==================== (2) 폼 제출 시: 기존 일정 vs 새 일정 위치 비교 + 지도 + 미루기 추천 ====================

if submitted:
    start_dt = dt.datetime.combine(sel_date, start_time, tzinfo=KST)
    end_dt = dt.datetime.combine(sel_date, end_time, tzinfo=KST)

    if end_dt <= start_dt:
        st.error("종료 시간은 시작 시간보다 늦어야 합니다.")
    else:
        # 1) 로컬 일정 겹침 체크
        overlaps_local = [
            ev for ev in st.session_state.local_events
            if times_overlap(start_dt, end_dt, ev["start_dt"], ev["end_dt"])
        ]
        if overlaps_local:
            st.warning(f"⚠ 선택 날짜에 {len(overlaps_local)}개의 로컬 일정이 시간대가 겹칩니다.")

        # 2) 구글 캘린더 일정 겹침 체크
        overlaps_google: List[Dict] = []
        if google_events_today:
            overlaps_google = [
                ev for ev in google_events_today
                if times_overlap(start_dt, end_dt, ev["start_dt"], ev["end_dt"])
            ]

        if overlaps_google:
            st.warning(f"⚠ 구글 캘린더 일정 {len(overlaps_google)}개와 시간이 겹칩니다.")
        elif google_events_today:
            st.info("✅ 이 시간대와 직접적으로 겹치는 구글 일정은 없습니다.")

        # 3) 구글 맵 이동 시간 + 교통수단 + 일정 미루기 추천 + 지도 UI (기존 일정 vs 새 일정)
        all_events_for_travel: List[Dict] = []
        all_events_for_travel.extend(st.session_state.local_events)
        all_events_for_travel.extend(google_events_today or [])

        if location and MAPS_KEY and all_events_for_travel:
            nearest = find_nearest_event_by_time(all_events_for_travel, start_dt)

            if nearest and nearest.get("location"):
                origin = nearest["location"]
                dest = location

                best_option = get_best_travel_option(origin, dest, MAPS_KEY)

                if best_option:
                    travel_min = best_option["minutes"]
                    mode = best_option["mode"]

                    gap_min = abs((start_dt - nearest["end_dt"]).total_seconds()) / 60.0

                    st.info(
                        f"가장 가까운 기존 일정은 **'{nearest['title']}'** "
                        f"({nearest['end_dt'].strftime('%H:%M')} 종료, 장소: {origin}) 입니다.\n\n"
                        f"해당 일정 → 새 일정 장소(**{dest}**) 이동 시\n"
                        f"**{pretty_mode_name(mode)} 기준 예상 이동 시간: {travel_min:.1f}분**"
                    )

                    origin_q = urllib.parse.quote_plus(origin)
                    dest_q = urllib.parse.quote_plus(dest)
                    embed_url = (
                        "https://www.google.com/maps/embed/v1/directions"
                        f"?key={MAPS_KEY}&origin={origin_q}&destination={dest_q}&mode={mode}"
                    )
                    iframe_html = f"""
                        <iframe
                            width="100%"
                            height="360"
                            frameborder="0"
                            style="border:0; border-radius:12px;"
                            src="{embed_url}"
                            allowfullscreen>
                        </iframe>
                    """
                    st.markdown("### 기존 일정 ↔ 새 일정 이동 경로")
                    components.html(iframe_html, height=380)

                    # (이동시간)-(일정 사이 시간 간격)+1시간
                    extra_min = travel_min - gap_min + 60.0
                    if extra_min > 0:
                        new_start_dt = start_dt + dt.timedelta(minutes=extra_min)
                        st.warning(
                            "이동 여유 시간을 고려하면 현재 일정 시작 시간으로는 부족할 수 있습니다.\n\n"
                            f"- 이동시간: **{travel_min:.1f}분**\n"
                            f"- 일정 사이 간격: **{gap_min:.1f}분**\n"
                            f"- 추가 여유 1시간 포함 필요 분: **{extra_min:.1f}분**\n\n"
                            f"➡ **새 일정 시작 시간을 {new_start_dt.strftime('%H:%M')} 이후로 미루는 것을 추천합니다.**"
                        )
                    else:
                        st.info(
                            "이동시간과 1시간 여유를 고려해도 현재 일정 시작 시간으로 충분합니다."
                        )

        # 4) 로컬 일정 저장
        new_event = {
            "id": len(st.session_state.local_events) + 1,
            "title": title,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "location": location,
            "source": "local",
        }
        st.session_state.local_events.append(new_event)
        st.success("일정이 추가되었습니다.")

# ==================== 선택 날짜의 로컬 일정 표시 ====================

st.markdown("## 이 날짜의 로컬 일정")

events_today = [
    ev for ev in st.session_state.local_events
    if ev["start_dt"].date() == sel_date
]

if not events_today:
    st.write("아직 추가된 로컬 일정이 없습니다.")
else:
    for ev in sorted(events_today, key=lambda x: x["start_dt"]):
        st.markdown(
            f"- **{ev['title']}** "
            f"({ev['start_dt'].strftime('%H:%M')} ~ {ev['end_dt'].strftime('%H:%M')})"
            + (f" · @ {ev['location']}" if ev['location'] else "")
        )
