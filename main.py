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

# ==================== CSS (달력 셀 스타일) ====================
st.markdown("""
<style>
.calendar-cell {
    width: 48px;
    height: 48px;
    border-radius: 10px;
    display: flex;
    justify-content: center;
    align-items: center;
    font-size: 1rem;
    margin-bottom: 4px;
    border: 1px solid rgba(255,255,255,0.15);
    background-color: transparent;
    color: white;
}

.calendar-empty {
    width: 48px;
    height: 48px;
    border-radius: 10px;
    background-color: rgba(255,255,255,0.03);
    margin-bottom: 4px;
}
</style>
""", unsafe_allow_html=True)

# ==================== KST(한국 시간) 기준 현재 시각/오늘 날짜 ====================
KST = dt.timezone(dt.timedelta(hours=9))
now = dt.datetime.now(KST)
today = now.date()

# ==================== 세션 상태 초기화 ====================
if "cal_year" not in st.session_state:
    st.session_state.cal_year = today.year

if "cal_month" not in st.session_state:
    st.session_state.cal_month = today.month

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

if "local_events" not in st.session_state:
    # 각 이벤트: {id, title, start_dt, end_dt, location, source}
    st.session_state.local_events: List[Dict] = []


# ==================== 구글 캘린더 & 맵 연동용 함수들 ====================

def fetch_google_events(creds, date: dt.date) -> List[Dict]:
    """
    주어진 날짜(date)에 해당하는 구글 캘린더 일정 목록 반환.
    - creds가 None 이거나 google-api-python-client 미설치면 [] 반환.
    - 나중에 OAuth 끝나고 st.session_state["google_creds"]에 크리덴셜 넣으면 바로 작동.
    """
    if creds is None or build is None:
        return []

    service = build("calendar", "v3", credentials=creds)

    start_of_day = dt.datetime.combine(date, dt.time(0, 0, tzinfo=KST))
    end_of_day = start_of_day + dt.timedelta(days=1)

    time_min = start_of_day.isoformat()
    time_max = end_of_day.isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    items = events_result.get("items", [])
    events = []

    for ev in items:
        start_str = ev["start"].get("dateTime") or ev["start"].get("date")
        end_str = ev["end"].get("dateTime") or ev["end"].get("date")

        # date-only(all-day)인 경우 00:00~24:00으로 처리
        if "T" not in start_str:
            start_dt = dt.datetime.fromisoformat(start_str + "T00:00:00+09:00")
        else:
            start_dt = dt.datetime.fromisoformat(start_str)

        if "T" not in end_str:
            end_dt = dt.datetime.fromisoformat(end_str + "T23:59:59+09:00")
        else:
            end_dt = dt.datetime.fromisoformat(end_str)

        events.append({
            "id": ev.get("id"),
            "title": ev.get("summary", "(제목 없음)"),
            "start_dt": start_dt,
            "end_dt": end_dt,
            "location": ev.get("location", ""),
            "source": "google",
        })

    return events


def estimate_travel_minutes(origin: str, destination: str, api_key: Optional[str]) -> Optional[float]:
    """
    구글 Distance Matrix API를 사용해 origin → destination 이동 시간(분)을 추정.
    - api_key가 없으면 None 반환.
    - 나중에 st.secrets["GOOGLE_MAPS_API_KEY"]에 키 넣으면 바로 작동.
    """
    if not api_key:
        return None
    if not origin or not destination:
        return None

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "mode": "driving",  # 필요하면 walking, transit 등으로 변경 가능
        "language": "ko",
        "key": api_key,
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        element = data["rows"][0]["elements"][0]
        if element.get("status") != "OK":
            return None
        seconds = element["duration"]["value"]
        return seconds / 60.0
    except Exception:
        return None


def times_overlap(s1: dt.datetime, e1: dt.datetime, s2: dt.datetime, e2: dt.datetime) -> bool:
    """두 시간 구간이 겹치는지 여부."""
    return max(s1, s2) < min(e1, e2)


def find_nearest_event_by_time(events: List[Dict], target_start: dt.datetime) -> Optional[Dict]:
    """
    target_start와 가장 시간 차이가 작은 이벤트(과거/미래 포함)를 하나 반환.
    이동 시간 계산할 때 사용.
    """
    if not events:
        return None

    best = None
    best_diff = None

    for ev in events:
        # 기준은 이벤트 시작 시각
        start_dt = ev["start_dt"]
        diff = abs((start_dt - target_start).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best = ev

    return best


# ==================== 달력 함수 ====================

def move_month(delta: int):
    y = st.session_state.cal_year
    m = st.session_state.cal_month
    m += delta
    if m <= 0:
        m += 12
        y -= 1
    elif m >= 13:
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
        st.markdown(
            f"<h4 style='text-align:center;'>{year}년 {month}월</h4>",
            unsafe_allow_html=True,
        )
    with c3:
        if st.button("▶", key=f"next_{year}_{month}"):
            move_month(1)
            st.rerun()

    # 요일 헤더
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    cols = st.columns(7)
    for i, w in enumerate(weekdays):
        with cols[i]:
            st.markdown(
                f"<div style='text-align:center; font-weight:600;'>{w}</div>",
                unsafe_allow_html=True,
            )

    # 달력 데이터 (월요일 시작)
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    for week in weeks:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    # 빈 칸
                    st.markdown("<div class='calendar-empty'></div>", unsafe_allow_html=True)
                else:
                    current = dt.date(year, month, day)
                    is_today = (current == today)
                    is_selected = (current == st.session_state.selected_date)

                    border_color = "rgba(255,255,255,0.15)"
                    bg_color = "transparent"
                    text_color = "white"

                    if is_today:
                        border_color = "#FFD54F"
                    if is_selected:
                        bg_color = "#4B8DF8"
                        text_color = "white"
                        # 오늘이면서 선택이면 노란 테두리 + 파란 배경
                        if is_today:
                            border_color = "#FFD54F"

                    st.markdown(
                        f"""
<div class="calendar-cell"
     style="border: 2px solid {border_color};
            background-color: {bg_color};
            color: {text_color};">
    {day}
</div>
""",
                        unsafe_allow_html=True,
                    )

                    # 클릭 감지용 투명 버튼 (UI는 위 div가 담당)
                    if st.button(" ", key=f"click_{year}_{month}_{day}"):
                        st.session_state.selected_date = current
                        st.rerun()


# ==================== 메인 UI ====================

st.title("일정? 바로잡 GO!")
st.caption(f"현재 시각 (KST 기준): {now.strftime('%Y-%m-%d %H:%M:%S')}")

# ---- 드롭다운으로 날짜 직접 선택 ----
st.markdown("### 날짜 선택")

cY, cM, cD = st.columns(3)

year_list = list(range(today.year - 5, today.year + 6))
cur_year = st.session_state.cal_year
cur_month = st.session_state.cal_month
cur_sel = st.session_state.selected_date

year_sel = cY.selectbox("연도", year_list, index=year_list.index(cur_year))
month_sel = cM.selectbox("월", list(range(1, 13)), index=cur_month - 1)

days_in_month = calendar.monthrange(year_sel, month_sel)[1]
default_day = cur_sel.day if (cur_sel.year == year_sel and cur_sel.month == month_sel) else 1
day_sel = cD.selectbox("일", list(range(1, days_in_month + 1)), index=default_day - 1)

st.session_state.cal_year = year_sel
st.session_state.cal_month = month_sel
st.session_state.selected_date = dt.date(year_sel, month_sel, day_sel)

# ---- 달력 렌더링 ----
render_calendar(st.session_state.cal_year, st.session_state.cal_month)

# ---- 오늘 버튼 ----
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
    # 기본 유효성 검증
    start_dt = dt.datetime.combine(sel_date, start_time, tzinfo=KST)
    end_dt = dt.datetime.combine(sel_date, end_time, tzinfo=KST)

    if end_dt <= start_dt:
        st.error("종료 시간은 시작 시간보다 늦어야 합니다.")
    else:
        # 1) 로컬 일정 겹침 체크
        overlaps_local = []
        for ev in st.session_state.local_events:
            if times_overlap(start_dt, end_dt, ev["start_dt"], ev["end_dt"]):
                overlaps_local.append(ev)

        if overlaps_local:
            st.warning(f"⚠ 선택한 날짜에 이미 {len(overlaps_local)}개의 로컬 일정이 겹칩니다.")

        # 2) 구글 캘린더 일정 겹침 체크
        google_creds = st.session_state.get("google_creds")  # 나중에 OAuth 완료 후 넣어주면 됨
        google_events = fetch_google_events(google_creds, sel_date)

        overlaps_google = []
        for ev in google_events:
            if times_overlap(start_dt, end_dt, ev["start_dt"], ev["end_dt"]):
                overlaps_google.append(ev)

        if google_events and not overlaps_google:
            st.info("✅ 구글 캘린더 일정과 시간대가 직접적으로 겹치지는 않습니다.")
        if overlaps_google:
            st.warning(f"⚠ 구글 캘린더 일정 {len(overlaps_google)}개와 시간이 겹칩니다.")

        # 3) 구글 맵 이동 시간 체크 (가장 가까운 일정 기준)
        all_for_travel: List[Dict] = []

        # 로컬 일정들 + 구글 일정들을 한 리스트에 모으기
        all_for_travel.extend(st.session_state.local_events)
        all_for_travel.extend(google_events)

        maps_key = st.secrets.get("GOOGLE_MAPS_API_KEY", None)

        if location and maps_key and all_for_travel:
            nearest = find_nearest_event_by_time(all_for_travel, start_dt)
            if nearest and nearest.get("location"):
                travel_min = estimate_travel_minutes(
                    nearest["location"], location, maps_key
                )
                if travel_min is not None:
                    gap_min = abs((start_dt - nearest["end_dt"]).total_seconds()) / 60.0
                    # 단순 기준: 이동 시간이 일정 간격보다 길면 경고
                    if travel_min > gap_min:
                        st.warning(
                            f"⚠ 이전/다음 일정('{nearest['title']}')에서 "
                            f"이동 시간({travel_min:.1f}분)이 "
                            f"일정 간격({gap_min:.1f}분)보다 길 수 있습니다."
                        )
                    else:
                        st.info(
                            f"✅ 가까운 다른 일정과의 이동 시간({travel_min:.1f}분)이 "
                            f"일정 간격({gap_min:.1f}분) 내에 있습니다."
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


# ==================== 선택된 날짜의 일정 목록 표시 ====================

st.markdown("## 이 날짜의 로컬 일정")

events_today = [
    ev for ev in st.session_state.local_events
    if ev["start_dt"].date() == sel_date
]

if not events_today:
    st.write("아직 추가된 로컬 일정이 없습니다.")
else:
    for ev in sorted(events_today, key=lambda e: e["start_dt"]):
        st.markdown(
            f"- **{ev['title']}** "
            f"({ev['start_dt'].strftime('%H:%M')} ~ {ev['end_dt'].strftime('%H:%M')})"
            + (f" @ {ev['location']}" if ev["location"] else "")
        )
