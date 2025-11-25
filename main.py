import streamlit as st
import datetime as dt
import calendar
from typing import List, Dict, Optional
import requests

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

/* 버튼 공통 (오늘 버튼 등) */
div[data-testid="stButton"] > button {
    padding-top: 0.2rem;
    padding-bottom: 0.2rem;
    border-radius: 999px;
    font-size: 0.75rem;
}

/* 모바일 최적화 */
@media (max-width: 600px) {
    .calendar-cell, .calendar-empty {
        width: min(12vw, 48px);
        height: min(12vw, 48px);
        font-size: 0.85rem;
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


def estimate_travel_minutes(origin, destination, api_key):
    if not api_key or not origin or not destination:
        return None

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "mode": "driving",
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


def times_overlap(s1, e1, s2, e2):
    return max(s1, s2) < min(e1, e2)


def find_nearest_event_by_time(events: List[Dict], target_start: dt.datetime) -> Optional[Dict]:
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

    # 상단: 화살표 + 타이틀
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

# 달력 렌더링
render_calendar(st.session_state.cal_year, st.session_state.cal_month)

# 오늘 버튼
st.markdown("---")
if st.button("오늘로 이동"):
    st.session_state.cal_year = today.year
    st.session_state.cal_month = today.month
    st.session_state.selected_date = today
    st.rerun()

sel_date = st.session_state.selected_date
st.markdown(f"### 선택된 날짜: **{sel_date.year}년 {sel_date.month}월 {sel_date.day}일**")

# ==================== 일정 추가 폼 ====================

st.markdown("## 일정 추가")

with st.form("add_event_form"):
    title = st.text_input("일정 제목", value="새 일정")
    start_time = st.time_input("시작 시간", value=dt.time(9, 0))
    end_time = st.time_input("종료 시간", value=dt.time(10, 0))
    location = st.text_input("장소(선택)", value="")
    submitted = st.form_submit_button("일정 추가")

if submitted:
    start_dt = dt.datetime.combine(sel_date, start_time, tzinfo=KST)
    end_dt = dt.datetime.combine(sel_date, end_time, tzinfo=KST)

    if end_dt <= start_dt:
        st.error("종료 시간은 시작 시간보다 늦어야 합니다.")
    else:
        overlaps_local = [
            ev for ev in st.session_state.local_events
            if times_overlap(start_dt, end_dt, ev["start_dt"], ev["end_dt"])
        ]

        if overlaps_local:
            st.warning(f"⚠ 선택 날짜에 {len(overlaps_local)}개의 로컬 일정이 겹칩니다.")

        google_creds = st.session_state.get("google_creds")
        google_events = fetch_google_events(google_creds, sel_date)

        overlaps_google = [
            ev for ev in google_events
            if times_overlap(start_dt, end_dt, ev["start_dt"], ev["end_dt"])
        ]

        if overlaps_google:
            st.warning(f"⚠ 구글 일정 {len(overlaps_google)}개와 시간이 겹칩니다.")
        elif google_events:
            st.info("✅ 구글 캘린더 일정과 직접 겹치는 시간대는 없습니다.")

        maps_key = st.secrets.get("GOOGLE_MAPS_API_KEY", None)
        all_events = st.session_state.local_events + google_events

        if location and maps_key and all_events:
            nearest = find_nearest_event_by_time(all_events, start_dt)
            if nearest and nearest.get("location"):
                travel_min = estimate_travel_minutes(nearest["location"], location, maps_key)
                if travel_min is not None:
                    gap = abs((start_dt - nearest["end_dt"]).total_seconds()) / 60
                    if travel_min > gap:
                        st.warning(
                            f"⚠ 가까운 일정('{nearest['title']}')에서 이동 시간({travel_min:.1f}분)이 "
                            f"일정 간격({gap:.1f}분)보다 길 수 있습니다."
                        )
                    else:
                        st.info(
                            f"✅ 가까운 일정과의 이동 시간({travel_min:.1f}분)이 "
                            f"일정 간격({gap:.1f}분) 내에 있습니다."
                        )

        st.session_state.local_events.append({
            "id": len(st.session_state.local_events) + 1,
            "title": title,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "location": location,
            "source": "local",
        })
        st.success("일정이 추가되었습니다!")

# ==================== 선택 날짜 일정 목록 표시 ====================
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
