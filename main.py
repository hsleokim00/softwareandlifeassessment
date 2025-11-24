import streamlit as st
import datetime as dt
import calendar

# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ===== 캘린더 버튼 공통 스타일 + 오늘 날짜 노란 테두리 =====
st.markdown(
    """
<style>
/* 모든 버튼 공통(특히 캘린더 버튼) 스타일 통일 */
div[data-testid="stButton"] > button {
    border-radius: 0.7rem;
    padding-top: 0.6rem;
    padding-bottom: 0.6rem;
}

/* 오늘 날짜 버튼: help="TODAY_CELL" 이 붙은 버튼만 노란 테두리 */
button[title="TODAY_CELL"] {
    border: 2px solid #FFD54F !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ==================== KST(한국 시간) 기준 현재 시각/오늘 날짜 ====================
KST = dt.timezone(dt.timedelta(hours=9))  # UTC+9
now = dt.datetime.now(KST)
today = now.date()

# ==================== 세션 상태 초기화 ====================
if "cal_year" not in st.session_state:
    st.session_state.cal_year = today.year

if "cal_month" not in st.session_state:
    st.session_state.cal_month = today.month

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today


# ==================== 헬퍼 함수들 ====================
def move_month(delta: int):
    """delta = +1 → 다음 달, -1 → 이전 달"""
    year = st.session_state.cal_year
    month = st.session_state.cal_month

    month += delta
    if month <= 0:
        month += 12
        year -= 1
    elif month >= 13:
        month -= 12
        year += 1

    st.session_state.cal_year = year
    st.session_state.cal_month = month


def render_calendar(year: int, month: int):
    """달력 렌더링 (월요일 시작, 모든 칸 버튼으로 정렬 깔끔하게)"""
    st.markdown("### 📅 달력")

    # 상단: 좌/우 이동 + 타이틀
    col_prev, col_title, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀", key=f"prev_{year}_{month}"):
            move_month(-1)
            st.rerun()

    with col_title:
        st.markdown(
            f"<h4 style='text-align:center;'>{year}년 {month}월</h4>",
            unsafe_allow_html=True,
        )

    with col_next:
        if st.button("▶", key=f"next_{year}_{month}"):
            move_month(1)
            st.rerun()

    # 요일 헤더
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    cols = st.columns(7)
    for i, name in enumerate(weekday_names):
        with cols[i]:
            st.markdown(
                f"<div style='text-align:center; font-weight:600;'>{name}</div>",
                unsafe_allow_html=True,
            )

    # 달력 데이터 (월요일 시작)
    cal = calendar.Calendar(firstweekday=0)
    month_weeks = cal.monthdayscalendar(year, month)

    # 날짜/빈칸 모두 버튼으로 통일
    for week_idx, week in enumerate(month_weeks):
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    # 이 달에 속하지 않는 빈 칸도 버튼으로 만들어 모양 통일
                    st.button(
                        " ",
                        key=f"empty_{year}_{month}_{week_idx}_{i}",
                    )
                else:
                    current_date = dt.date(year, month, day)
                    is_today = (current_date == today)

                    help_text = "TODAY_CELL" if is_today else None

                    if st.button(
                        f"{day}",
                        key=f"day_{year}_{month}_{day}",
                        help=help_text,  # 오늘인 경우에만 title="TODAY_CELL" 부여
                    ):
                        st.session_state.selected_date = current_date


# ==================== 메인 ====================
st.title("일정? 바로잡 GO!")

st.caption(f"현재 시각 (KST 기준): {now.strftime('%Y-%m-%d %H:%M:%S')}")

# -------- 연/월/일 드롭다운으로 날짜 바로 이동 --------
st.markdown("### 날짜 선택")

col_y, col_m, col_d = st.columns(3)

year_options = list(range(today.year - 5, today.year + 6))
current_year = st.session_state.cal_year
current_month = st.session_state.cal_month
current_sel = st.session_state.selected_date

with col_y:
    year_sel = st.selectbox(
        "연도",
        year_options,
        index=year_options.index(current_year),
    )

with col_m:
    month_sel = st.selectbox(
        "월",
        list(range(1, 13)),
        index=current_month - 1,
    )

days_in_month = calendar.monthrange(year_sel, month_sel)[1]

default_day = 1
if (
    isinstance(current_sel, dt.date)
    and current_sel.year == year_sel
    and current_sel.month == month_sel
    and 1 <= current_sel.day <= days_in_month
):
    default_day = current_sel.day

with col_d:
    day_sel = st.selectbox(
        "일",
        list(range(1, days_in_month + 1)),
        index=default_day - 1,
    )

# 드롭다운 선택 결과를 세션 상태에 반영
st.session_state.cal_year = year_sel
st.session_state.cal_month = month_sel
st.session_state.selected_date = dt.date(year_sel, month_sel, day_sel)

# -------- 달력 렌더링 --------
render_calendar(st.session_state.cal_year, st.session_state.cal_month)

# -------- '오늘' 버튼: 현재 날짜로 이동 --------
st.markdown("---")
col_today, _ = st.columns([1, 3])
with col_today:
    if st.button("오늘로 이동"):
        st.session_state.cal_year = today.year
        st.session_state.cal_month = today.month
        st.session_state.selected_date = today
        st.rerun()

# 선택된 날짜 정보
st.markdown("### 선택된 날짜")
sel = st.session_state.selected_date
st.write(f"**{sel.year}년 {sel.month}월 {sel.day}일** 이(가) 선택되어 있습니다.")
