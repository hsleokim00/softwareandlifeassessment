import streamlit as st
import datetime as dt
import calendar

# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
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
    """달력 렌더링 (월요일 시작, 격자 맞춤)"""
    st.markdown("### 📅 달력")

    # 달력 상단: 연도/월 제목 + 좌우 이동
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

    # 날짜 격자
    for week in month_weeks:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    # 이 달에 속하지 않는 칸도 같은 크기의 박스로 채워서 '선' 맞추기
                    st.markdown(
                        "<div style='padding:0.6rem 0; border-radius:0.7rem;"
                        "border:1px solid rgba(255,255,255,0.06);'></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    current_date = dt.date(year, month, day)
                    is_today = (current_date == today)
                    is_selected = (current_date == st.session_state.selected_date)

                    # 버튼 라벨
                    label = f"{day}"

                    # 버튼 그리기 (테마에 맞게 기본 스타일 사용)
                    if st.button(label, key=f"day_{year}_{month}_{day}"):
                        st.session_state.selected_date = current_date

                    # 선택/오늘 표시용 보조 텍스트 (원하면 지워도 됨)
                    if is_selected:
                        st.markdown(
                            "<div style='text-align:center; font-size:0.7rem;'>선택</div>",
                            unsafe_allow_html=True,
                        )
                    elif is_today:
                        st.markdown(
                            "<div style='text-align:center; font-size:0.7rem;'>오늘</div>",
                            unsafe_allow_html=True,
                        )


# ==================== 메인 ====================
st.title("일정? 바로잡 GO!")

# 현재 시간 표시 (디버깅/확인용)
st.caption(f"현재 시각 (KST 기준): {now.strftime('%Y-%m-%d %H:%M:%S')}")

# -------- 연/월/일 드롭다운으로 날짜 바로 이동 --------
st.markdown("### 날짜 선택")

col_y, col_m, col_d = st.columns(3)

# 연도 범위는 오늘 기준 ±5년 정도로 설정 (원하면 바꿀 수 있음)
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

# 선택된 연/월에 맞는 일 수 계산
days_in_month = calendar.monthrange(year_sel, month_sel)[1]

# 현재 선택된 날짜의 일(day)을 기본값으로 쓰되,
# 해당 월에 없는 날짜(예: 31일 → 30일/28일)는 1일로 보정
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
