import streamlit as st
import datetime as dt
import calendar

# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ==================== 버튼 공통 크기/모양 CSS ====================
st.markdown("""
<style>
/* 모든 날짜 버튼 공통 크기/모양 */
div[data-testid="stButton"] > button {
    border-radius: 10px;
    width: 48px;
    height: 48px;
    padding: 0;
}

/* 빈 칸 모양 통일 */
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

# ==================== 세션 상태 ====================
if "cal_year" not in st.session_state:
    st.session_state.cal_year = today.year
if "cal_month" not in st.session_state:
    st.session_state.cal_month = today.month
if "selected_date" not in st.session_state:
    st.session_state.selected_date = today


# ==================== 함수들 ====================
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

    # 상단: 화살표 + 제목
    c1, c2, c3 = st.columns([1, 3, 1])
    with c1:
        if st.button("◀", key=f"prev_{year}_{month}"):
            move_month(-1)
            st.rerun()
    with c2:
        st.markdown(
            f"<h4 style='text-align:center;'>{year}년 {month}월</h4>",
            unsafe_allow_html=True
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
                unsafe_allow_html=True
            )

    # 달력 데이터 (월요일 시작)
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

 # 날짜 렌더링
for w_idx, week in enumerate(weeks):
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

                # div 스타일 결정
                cell_style = """
                    width: 48px;
                    height: 48px;
                    border-radius: 10px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    font-size: 1rem;
                    margin-bottom: 4px;
                """

                # 기본 border
                border_color = "rgba(255,255,255,0.15)"

                # 오늘 강조
                if is_today:
                    border_color = "#FFD54F"

                # 선택 강조
                background_color = "transparent"
                text_color = "white"

                if is_selected:
                    background_color = "#4B8DF8"
                    text_color = "white"

                # 최종 div 출력
                st.markdown(
                    f"""
<div style="
    {cell_style}
    border: 2px solid {border_color};
    background-color: {background_color};
    color: {text_color};
">
    {day}
</div>
""",
                    unsafe_allow_html=True
                )

                # 클릭 처리용 투명 버튼 (UI와 겹치지 않음)
                if st.button(" ", key=f"click_{year}_{month}_{day}"):
                    st.session_state.selected_date = current
                    st.rerun()


# ==================== 메인 ====================
st.title("일정? 바로잡 GO!")
st.caption(f"현재 시각 (KST 기준): {now.strftime('%Y-%m-%d %H:%M:%S')}")

# --- 드롭다운으로 날짜 선택 ---
st.markdown("### 날짜 선택")
cY, cM, cD = st.columns(3)

year_list = list(range(today.year - 5, today.year + 6))
cur_year = st.session_state.cal_year
cur_month = st.session_state.cal_month
cur_sel = st.session_state.selected_date

year_sel = cY.selectbox("연도", year_list, index=year_list.index(cur_year))
month_sel = cM.selectbox("월", list(range(1, 13)), index=cur_month - 1)

days_in_month = calendar.monthrange(year_sel, month_sel)[1]
default_day = 1
if (
    isinstance(cur_sel, dt.date)
    and cur_sel.year == year_sel
    and cur_sel.month == month_sel
    and 1 <= cur_sel.day <= days_in_month
):
    default_day = cur_sel.day

day_sel = cD.selectbox("일", list(range(1, days_in_month + 1)), index=default_day - 1)

# 드롭다운 결과 반영
st.session_state.cal_year = year_sel
st.session_state.cal_month = month_sel
st.session_state.selected_date = dt.date(year_sel, month_sel, day_sel)

# --- 달력 렌더링 ---
render_calendar(st.session_state.cal_year, st.session_state.cal_month)

# --- 오늘 버튼 ---
st.markdown("---")
if st.button("오늘로 이동"):
    st.session_state.cal_year = today.year
    st.session_state.cal_month = today.month
    st.session_state.selected_date = today
    st.rerun()

# --- 선택된 날짜 표시 ---
st.markdown("### 선택된 날짜")
sel = st.session_state.selected_date
st.write(f"**{sel.year}년 {sel.month}월 {sel.day}일** 이(가) 선택되어 있습니다.")
