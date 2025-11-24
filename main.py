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
now = dt.datetime.now(KST)               # 현재 시각 (한국 기준)
today = now.date()                       # 오늘 날짜

# 디버깅/확인용 출력 (원하면 숨겨도 됨)
st.caption(f"현재 시각 (KST 기준): {now.strftime('%Y-%m-%d %H:%M:%S')}")

# ==================== 세션 상태 초기화 ====================
# 처음 들어왔을 때는 '오늘이 속한 연/월'이 기본이 되도록 설정
if "cal_year" not in st.session_state:
    st.session_state.cal_year = today.year

if "cal_month" not in st.session_state:
    st.session_state.cal_month = today.month

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today  # 기본 선택 날짜도 오늘


# ==================== 헬퍼 함수들 ====================
def move_month(delta: int):
    """
    delta = +1 이면 다음 달, -1 이면 이전 달로 이동.
    연도 넘어가는 부분까지 처리.
    """
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
    """
    주어진 year, month 에 대한 달력을 화면에 렌더링.
    - 월의 일수는 calendar 모듈에서 자동으로 계산 (윤년 포함)
    - 오늘 날짜는 배경 색으로 강조
    - 날짜를 클릭하면 selected_date를 업데이트
    """
    st.markdown("### 📅 달력")

    # 달력 객체: 월요일 시작
    cal = calendar.Calendar(firstweekday=0)  # 0: 월요일

    # monthdayscalendar: 해당 월을 주 단위 리스트로 반환 (0은 빈 칸)
    month_weeks = cal.monthdayscalendar(year, month)

    # ===== 상단: 년/월 + 좌우 이동 버튼 =====
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

    # ===== 요일 헤더 =====
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    cols = st.columns(7)
    for i, name in enumerate(weekday_names):
        with cols[i]:
            st.markdown(
                f"<div style='text-align:center; font-weight:600;'>{name}</div>",
                unsafe_allow_html=True,
            )

    # ===== 날짜 그리드 =====
    for week_idx, week in enumerate(month_weeks):
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    # 이 달에 속하지 않는 칸 (빈 칸)
                    st.write(" ")
                else:
                    current_date = dt.date(year, month, day)

                    is_today = (current_date == today)
                    is_selected = (current_date == st.session_state.selected_date)

                    base_style = (
                        "display:block; width:100%; padding:0.4rem 0; "
                        "border-radius:0.5rem; text-align:center; "
                        "border:1px solid #dddddd; cursor:pointer;"
                    )

                    if is_selected:
                        style = (
                            base_style
                            + "background-color:#4b8df8; color:white; font-weight:700;"
                        )
                    elif is_today:
                        style = (
                            base_style
                            + "background-color:#ffe9b5; color:#333333; font-weight:700;"
                        )
                    else:
                        style = base_style + "background-color:white; color:#333333;"

                    # 날짜 버튼
                    if st.button(
                        f"{day}",
                        key=f"day_{year}_{month}_{day}",
                    ):
                        st.session_state.selected_date = current_date

                    # 버튼 모양을 더 예쁘게 커스터마이징하려면,
                    # st.markdown(f"<div style='{style}'>{day}</div>", unsafe_allow_html=True)
                    # 형태로 바꾸고, 클릭은 다른 방식으로 처리해도 됨.


# ==================== 메인 영역 ====================
st.title("일정? 바로잡 GO! (달력 + 현재 시간 반영)")

st.caption(
    "이 달력은 **한국 시간(UTC+9)** 기준으로 오늘 날짜와 현재 시각을 반영합니다. "
    "오늘 날짜는 노란색으로, 선택한 날짜는 파란색으로 표시돼요."
)

# 현재 연/월 가져오기
year = st.session_state.cal_year
month = st.session_state.cal_month

# 달력 렌더링
render_calendar(year, month)

# ==================== 선택된 날짜 / 현재 시각 표시 ====================
st.markdown("---")
st.markdown("### 선택된 날짜 / 현재 시각")

if st.session_state.selected_date:
    sel = st.session_state.selected_date
    st.write(f"**선택된 날짜:** {sel.year}년 {sel.month}월 {sel.day}일")
else:
    st.write("아직 날짜를 선택하지 않았습니다.")

st.write(f"**현재 시각 (KST):** {now.strftime('%Y-%m-%d %H:%M:%S')}")
