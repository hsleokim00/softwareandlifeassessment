import streamlit as st
import datetime as dt
import calendar

# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ==================== CSS (UI 완전 제어) ====================
st.markdown("""
<style>
.calendar-cell {
    width: 48px;
    height: 48px;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.15);
    display: flex;
    justify-content: center;
    align-items: center;
    font-size: 1rem;
    cursor: pointer;
}

/* 오늘 날짜 강조 */
.calendar-today {
    border: 2px solid #FFD54F !important;
}

/* 선택 날짜 강조 */
.calendar-selected {
    background-color: #4B8DF8 !important;
    color: white !important;
}

/* 빈 칸 */
.calendar-empty {
    width: 48px;
    height: 48px;
    border-radius: 10px;
    background-color: rgba(255,255,255,0.03);
}
</style>
""", unsafe_allow_html=True)


# ==================== KST 기준 시간 ====================
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


# ==================== 함수들 ====================
def move_month(delta):
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


def render_calendar(year, month):
    st.markdown("### 📅 달력")

    # 상단 화살표 + 제목
    c1, c2, c3 = st.columns([1, 3, 1])
    with c1:
        if st.button("◀"): move_month(-1); st.rerun()
    with c2:
        st.markdown(f"<h4 style='text-align:center;'>{year}년 {month}월</h4>", unsafe_allow_html=True)
    with c3:
        if st.button("▶"): move_month(1); st.rerun()

    # 요일 헤더
    weekdays = ["월","화","수","목","금","토","일"]
    cols = st.columns(7)
    for i, w in enumerate(weekdays):
        with cols[i]:
            st.markdown(f"<div style='text-align:center; font-weight:600;'>{w}</div>", unsafe_allow_html=True)

    # 달력 데이터
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    # 날짜 출력
    for w in weeks:
        cols = st.columns(7)
        for idx, day in enumerate(w):
            with cols[idx]:
                if day == 0:
                    # 빈 칸
                    st.markdown("<div class='calendar-empty'></div>", unsafe_allow_html=True)
                else:
                    current = dt.date(year, month, day)

                    # 기본 클래스
                    classes = ["calendar-cell"]

                    if current == today:
                        classes.append("calendar-today")
                    if current == st.session_state.selected_date:
                        classes.append("calendar-selected")

                    class_str = " ".join(classes)

                    # UI 박스 표시
                    st.markdown(
                        f"<div class='{class_str}'>{day}</div>",
                        unsafe_allow_html=True
                    )

                    # 클릭 이벤트 처리 (투명 버튼)
                    if st.button(" ", key=f"btn_{year}_{month}_{day}"):
                        st.session_state.selected_date = current
                        st.rerun()


# ==================== 드롭다운 선택 ====================
st.markdown("### 날짜 선택")

cY, cM, cD = st.columns(3)

year_list = list(range(today.year - 5, today.year + 6))
year_sel = cY.selectbox("연도", year_list, index=year_list.index(st.session_state.cal_year))
month_sel = cM.selectbox("월", list(range(1,13)), index=st.session_state.cal_month - 1)

days = calendar.monthrange(year_sel, month_sel)[1]

current_sel = st.session_state.selected_date
default_day = current_sel.day if (current_sel.year == year_sel and current_sel.month == month_sel) else 1

day_sel = cD.selectbox("일", list(range(1, days+1)), index=default_day - 1)

# 적용
st.session_state.cal_year = year_sel
st.session_state.cal_month = month_sel
st.session_state.selected_date = dt.date(year_sel, month_sel, day_sel)

# ==================== 달력 렌더링 ====================
render_calendar(st.session_state.cal_year, st.session_state.cal_month)

# 오늘 버튼
st.markdown("---")
if st.button("오늘로 이동"):
    st.session_state.cal_year = today.year
    st.session_state.cal_month = today.month
    st.session_state.selected_date = today
    st.rerun()

# 선택된 날짜 표시
st.write(f"**선택된 날짜:** {st.session_state.selected_date}")
