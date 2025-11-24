import streamlit as st
import datetime as dt

# ---------------- 기본 설정 ----------------
st.set_page_config(
    page_title="일정? 바로잡 GO!",
    page_icon="📅",
    layout="centered",
)

# ---------------- 세션 상태 ----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

logged_in = st.session_state.logged_in

# ---------------- 스타일(CSS) ----------------
st.markdown(
    """
    <style>
    .title-text {
        font-size: 2rem;
        font-weight: 800;
        color: #f5f5f5;
        margin: 0.8rem 0 0.5rem 0;
    }
    .calendar-box {
        border-radius: 24px;
        padding: 1.5rem;
        background: #ffffff;
        box-shadow: 0 8px 16px rgba(0,0,0,0.06);
        min-height: 320px;
        margin: 1rem 0 2rem 0;
    }
    .calendar-title {
        font-size: 1.1rem;
        font-weight: 700;
        margin-bottom: 0.4rem;
        color: #222;
    }
    .calendar-caption {
        font-size: 0.85rem;
        color: #666666;
        margin-bottom: 0.8rem;
    }
    .pill-input > div > input {
        border-radius: 999px !important;
    }
    .pill-button > button {
        border-radius: 999px !important;
        font-weight: 600;
        padding: 0.6rem 2.0rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------- 상단 영역: 타이틀 + 로그인 버튼 ----------------
top_left, top_right = st.columns([4, 1])

with top_left:
    # 검은 바탕(스트림릿 다크테마) + 회색 글씨 느낌
    st.markdown('<div class="title-text">일정? 바로잡 GO!</div>', unsafe_allow_html=True)

with top_right:
    if logged_in:
        st.success("구글 로그인 완료 ✅")
    else:
        login_clicked = st.button("구글로 로그인")
        if login_clicked:
            # 나중에 여기에 실제 Google OAuth 연동 넣으면 됨
            st.session_state.logged_in = True

st.write("")  # 약간 여백

# ---------------- 가운데: 캘린더 박스 ----------------
st.markdown('<div class="calendar-box">', unsafe_allow_html=True)

today = dt.date.today()

st.markdown(
    '<div class="calendar-title">캘린더</div>',
    unsafe_allow_html=True,
)

if not logged_in:
    caption_text = "구글 로그인 전에는 날짜만 선택 가능한 일반적인 캘린더입니다."
else:
    caption_text = "구글 캘린더와 연동된 일정이 이 영역에 표시될 예정입니다. (지금은 UI 틀만 구현)"

st.markdown(
    f'<div class="calendar-caption">{caption_text}</div>',
    unsafe_allow_html=True,
)

# ✅ 실제 달력: 과거/미래 다 이동 가능
main_selected_date = st.date_input(
    label="",
    value=today,
    key="main_calendar",
)

st.markdown('</div>', unsafe_allow_html=True)  # calendar-box 닫기

# ---------------- 아래: 새 일정 입력 영역 ----------------
st.markdown("#### 새 일정 입력")

# 위에서 선택한 날짜를 기본값으로 사용
date = st.date_input("날짜", value=main_selected_date, key="input_date")

c1, c2, c3, c4 = st.columns(4)

with c1:
    title = st.text_input("일정명", key="title", placeholder="예: 수학 학원")

with c2:
    st.markdown('<div class="pill-input">', unsafe_allow_html=True)
    place = st.text_input("장소", key="place", placeholder="예: OO학원")
    st.markdown('</div>', unsafe_allow_html=True)

with c3:
    start_time = st.time_input("시작시간", value=dt.time(18, 0))

with c4:
    end_time = st.time_input("종료시간", value=dt.time(19, 0))

st.write("")

btn_col = st.columns([1, 2, 1])[1]
with btn_col:
    clicked = st.button(
        "입력",
        key="submit",
        disabled=not logged_in,
        help="구글 로그인 후 사용 가능합니다.",
    )

if clicked and logged_in:
    st.success(
        f"새 일정이 준비되었습니다: "
        f"{date} {start_time.strftime('%H:%M')}~{end_time.strftime('%H:%M')} / {title} @ {place}"
    )
    # TODO:
    # 1) 여기서 기존 구글 캘린더 일정 + 이동시간 체크
    # 2) 문제 없으면 구글 캘린더에 실제 이벤트 생성
