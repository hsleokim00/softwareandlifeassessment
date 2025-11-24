import streamlit as st
import datetime as dt
import calendar

# ==================== 기본 설정 ====================
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ==================== 세션 상태 초기화 ====================
today = dt.date.today()

if "cal_year" not in st.session_state:
    st.session_state.cal_year = today.year

if "cal_month" not in st.session_state:
    st.session_state.cal_month = today.month

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today


# ==================== 헬퍼 함수들 ====================
def move_month(delta: int):
    """
    delta = +1 이면 다음 달, -1 이면 이전 달로 이동.
    연도 넘어가는 부분까지 처리.
    """
    year = st.session_state.cal_year
    month = st.session_state.cal_month

    # month를 1~12 범위로 안전하게 이동
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
    """
    주어진 year, month 에 대한 달력을 화면에 렌더링.
    - 월의 일수는 calendar 모듈에서 자동으로 계산 (윤년 포함)
    - 오늘 날짜는 배경 색으로 강조
    - 날짜를 클릭하면 selected_date를 업데이트
    """
    st.markdown("### 📅 달력")

    # 요일 헤더 (월~일 또는 일~토 원하는 걸로 조정 가능)
    # 여기서는 '월'을 첫 번째 요일로 설정 (한국 스타일)
    cal = calendar.Calendar(firstweekday=0)  # 0: 월요일, 6: 일요일 (파이썬 기본은 월요일)
    # → 만약 일요일부터 시작하고 싶으면 firstweekday=6 으로 바꿔도 됨

    # monthdayscalendar: 해당 월을 주 단위 리스트로 반환 (0은 빈 칸)
    month_weeks = cal.monthdayscalendar(year, month)

    # 헤더: 년/월 표시 + 이동 버튼
    col_prev, col_title, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀", key="prev_month"):
            move_month(-1)
            st.experimental_rerun()

    with col_title:
        st.markdown(
            f"<h4 style='text-align:center;'>{year}년 {month}월</h4>",
            unsafe_allow_html=True,
        )

    with col_next:
        if st.button("▶", key="next_month"):
            move_month(1)
            st.experimental_rerun()

    # 요일 이름 표시
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    cols = st.columns(7)
    for i, name in enumerate(weekday_names):
        with cols[i]:
            st.markdown(
                f"<div style='text-align:center; font-weight:600;'>{name}</div>",
                unsafe_allow_html=True,
            )

    # 오늘 날짜 (강조용)
    today_local = today

    # 날짜 그리드
    for week_idx, week in enumerate(month_weeks):
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    # 이 달에 속하지 않는 칸 (빈 칸)
                    st.write(" ")
                else:
                    current_date = dt.date(year, month, day)

                    # 오늘이면 배경색 강조
                    is_today = (current_date == today_local)
                    is_selected = (current_date == st.session_state.selected_date)

                    base_style = (
                        "display:block; width:100%; padding:0.4rem 0; "
                        "border-radius:0.5rem; text-align:center; "
                        "border:1px solid #dddddd; cursor:pointer;"
                    )

                    # 스타일 분기
                    if is_selected:
                        # 선택된 날짜
                        style = (
                            base_style
                            + "background-color:#4b8df8; color:white; font-weight:700;"
                        )
                    elif is_today:
                        # 오늘 날짜
                        style = (
                            base_style
                            + "background-color:#ffe9b5; color:#333333; font-weight:700;"
                        )
                    else:
                        style = base_style + "background-color:white; color:#333333;"

                    # 버튼으로 날짜 선택
                    if st.button(
                        f"{day}",
                        key=f"day_{year}_{month}_{day}",
                    ):
                        st.session_state.selected_date = current_date

                    # 버튼 텍스트를 꾸미려고 한 번 더 마크다운으로 덮어 씌우는 대신,
                    # 버튼 대신 click-like 효과를 원하면 아래처럼 사용 가능:
                    # st.markdown(f"<div style='{style}'>{day}</div>", unsafe_allow_html=True)


# ==================== 메인 영역 ====================
st.title("일정? 바로잡 GO! (달력 UI 버전)")

st.caption(
    "현재 버전은 **달력 UI만 먼저 안정화**한 상태입니다. "
    "나중에 여기에 구글 캘린더 / 구글 맵 연동을 올릴 수 있도록 구조를 단순하게 유지했습니다."
)

year = st.session_state.cal_year
month = st.session_state.cal_month

# 달력 렌더링
render_calendar(year, month)

# 현재 선택된 날짜 표시
st.markdown("---")
st.markdown("### 선택된 날짜")

if st.session_state.selected_date:
    sel = st.session_state.selected_date
    st.write(f"**{sel.year}년 {sel.month}월 {sel.day}일** 이 선택되어 있습니다.")
else:
    st.write("아직 날짜를 선택하지 않았습니다.")
