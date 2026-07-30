import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ------------------------------------------------------------
# 1. 페이지 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="박스오피스 대시보드",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 어제의 박스오피스")


# ------------------------------------------------------------
# 2. 비밀 금고에서 KOBIS 인증키 가져오기
# ------------------------------------------------------------
# Streamlit Cloud의 Secrets에 다음처럼 저장해야 합니다.
#
# KOBIS_KEY = "발급받은 인증키"
#
# 인증키는 코드에 직접 적지 않습니다.
try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]

except KeyError:
    st.error(
        "Secrets에서 KOBIS_KEY를 찾지 못했습니다. "
        "Streamlit Cloud의 Secrets 설정을 확인해 주세요."
    )
    st.stop()


# ------------------------------------------------------------
# 3. 한국 시간 기준 어제 날짜 계산
# ------------------------------------------------------------
# 배포 서버는 한국이 아닌 다른 시간대를 사용할 수 있으므로
# Asia/Seoul 시간대를 직접 지정합니다.
yesterday = (
    datetime.now(ZoneInfo("Asia/Seoul"))
    - timedelta(days=1)
)

target_dt = yesterday.strftime("%Y%m%d")

st.caption(
    f"조회 기준일: {yesterday.strftime('%Y-%m-%d')}"
)


# ------------------------------------------------------------
# 4. KOBIS 일일 박스오피스 API 요청
# ------------------------------------------------------------
url = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

try:
    res = requests.get(
        url,
        params={
            "key": KOBIS_KEY,
            "targetDt": target_dt,
        },
        timeout=10,
    )

    res.raise_for_status()

except requests.exceptions.Timeout:
    st.error(
        "KOBIS 서버의 응답이 늦어 요청 시간이 초과되었습니다."
    )
    st.stop()

except requests.exceptions.RequestException as error:
    st.error(
        "KOBIS 데이터를 불러오는 중 오류가 발생했습니다."
    )
    st.exception(error)
    st.stop()


# ------------------------------------------------------------
# 5. 응답 데이터 확인
# ------------------------------------------------------------
try:
    data = res.json()

except ValueError:
    st.error(
        "KOBIS 서버에서 올바른 JSON 응답을 받지 못했습니다."
    )
    st.stop()


# KOBIS는 인증키 오류가 있어도 HTTP 상태코드 200을 반환하고
# faultInfo를 담아 보내는 경우가 있습니다.
if "faultInfo" in data:
    fault_message = data.get(
        "faultInfo",
        {},
    ).get(
        "message",
        "인증키 또는 요청 정보를 확인해 주세요.",
    )

    st.error(
        f"KOBIS API 오류: {fault_message}"
    )
    st.stop()


box_list = (
    data
    .get("boxOfficeResult", {})
    .get("dailyBoxOfficeList", [])
)

if not box_list:
    st.warning(
        "해당 날짜의 박스오피스 자료가 없습니다."
    )
    st.stop()


# ------------------------------------------------------------
# 6. 데이터프레임 만들기
# ------------------------------------------------------------
df = pd.DataFrame(box_list)


# KOBIS API에서 숫자가 문자열로 전달되므로
# 계산과 정렬을 위해 숫자형으로 변환합니다.
numeric_columns = [
    "rank",
    "rankInten",
    "salesAmt",
    "salesAcc",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
    "showCnt",
]

for column in numeric_columns:
    if column in df.columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)


# ------------------------------------------------------------
# 7. 1위 영화 지표 카드
# ------------------------------------------------------------
top = (
    df
    .sort_values("rank")
    .iloc[0]
)

c1, c2, c3 = st.columns(3)

c1.metric(
    "어제 1위",
    top["movieNm"],
)

c2.metric(
    "어제 관객 수",
    f"{int(top['audiCnt']):,}명",
)

c3.metric(
    "누적 관객 수",
    f"{int(top['audiAcc']):,}명",
)


# ------------------------------------------------------------
# 8. 전체 박스오피스 표
# ------------------------------------------------------------
table = df[
    [
        "rank",
        "movieNm",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]
].copy()

table.columns = [
    "순위",
    "영화명",
    "개봉일",
    "일일 관객 수",
    "누적 관객 수",
    "스크린 수",
]

table = (
    table
    .sort_values("순위")
    .reset_index(drop=True)
)

st.subheader("📋 어제의 박스오피스 TOP 10")

st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
    column_config={
        "순위": st.column_config.NumberColumn(
            "순위",
            format="%d위",
        ),
        "일일 관객 수": st.column_config.NumberColumn(
            "일일 관객 수",
            format="%d명",
        ),
        "누적 관객 수": st.column_config.NumberColumn(
            "누적 관객 수",
            format="%d명",
        ),
        "스크린 수": st.column_config.NumberColumn(
            "스크린 수",
            format="%d개",
        ),
    },
)


# ------------------------------------------------------------
# 9. 일일 관객 수 상위 5편 차트
# ------------------------------------------------------------
st.subheader("📈 일일 관객 수 상위 5편")

top5 = (
    table
    .sort_values(
        "일일 관객 수",
        ascending=False,
    )
    .head(5)
)

st.bar_chart(
    top5.set_index("영화명")["일일 관객 수"]
)


# ------------------------------------------------------------
# 10. 천만 관객 미달 영화 순위
# ------------------------------------------------------------
st.divider()
st.subheader("🎟️ 누적 천만 관객 미달 영화 순위")

st.caption(
    "어제의 일일 박스오피스 TOP 10 가운데 "
    "누적 관객 수가 1,000만 명 미만인 영화입니다."
)

TEN_MILLION = 10_000_000

under_ten_million = table.loc[
    table["누적 관객 수"] < TEN_MILLION
].copy()


if under_ten_million.empty:
    st.success(
        "어제의 박스오피스 TOP 10 영화가 모두 "
        "누적 1,000만 관객을 달성했습니다."
    )

else:
    # 원래 일일 박스오피스 순위를 유지합니다.
    under_ten_million = (
        under_ten_million
        .sort_values("순위")
        .reset_index(drop=True)
    )

    # 천만 관객까지 몇 명이 남았는지 계산합니다.
    under_ten_million["천만까지 남은 관객"] = (
        TEN_MILLION
        - under_ten_million["누적 관객 수"]
    )

    # 천만 관객 달성률을 계산합니다.
    under_ten_million["천만 달성률"] = (
        under_ten_million["누적 관객 수"]
        / TEN_MILLION
        * 100
    ).round(1)

    under_ten_million_table = under_ten_million[
        [
            "순위",
            "영화명",
            "일일 관객 수",
            "누적 관객 수",
            "천만까지 남은 관객",
            "천만 달성률",
        ]
    ]

    st.dataframe(
        under_ten_million_table,
        hide_index=True,
        use_container_width=True,
        column_config={
            "순위": st.column_config.NumberColumn(
                "어제 순위",
                format="%d위",
            ),
            "일일 관객 수": st.column_config.NumberColumn(
                "어제 관객 수",
                format="%d명",
            ),
            "누적 관객 수": st.column_config.NumberColumn(
                "누적 관객 수",
                format="%d명",
            ),
            "천만까지 남은 관객": st.column_config.NumberColumn(
                "천만까지 남은 관객",
                format="%d명",
            ),
            "천만 달성률": st.column_config.ProgressColumn(
                "천만 달성률",
                format="%.1f%%",
                min_value=0,
                max_value=100,
            ),
        },
    )


# ------------------------------------------------------------
# 11. 천만 관객에 가까운 영화 순위
# ------------------------------------------------------------
st.subheader("🏃 천만 관객에 가까운 영화")

st.caption(
    "누적 관객 수가 많은 순서로 다시 정렬한 순위입니다."
)

closest_to_ten_million = (
    under_ten_million
    .sort_values(
        "누적 관객 수",
        ascending=False,
    )
    .reset_index(drop=True)
)

if not closest_to_ten_million.empty:
    closest_to_ten_million.insert(
        0,
        "천만 도전 순위",
        range(
            1,
            len(closest_to_ten_million) + 1,
        ),
    )

    closest_table = closest_to_ten_million[
        [
            "천만 도전 순위",
            "영화명",
            "누적 관객 수",
            "천만까지 남은 관객",
            "천만 달성률",
        ]
    ]

    st.dataframe(
        closest_table,
        hide_index=True,
        use_container_width=True,
        column_config={
            "천만 도전 순위": st.column_config.NumberColumn(
                "순위",
                format="%d위",
            ),
            "누적 관객 수": st.column_config.NumberColumn(
                "누적 관객 수",
                format="%d명",
            ),
            "천만까지 남은 관객": st.column_config.NumberColumn(
                "천만까지 남은 관객",
                format="%d명",
            ),
            "천만 달성률": st.column_config.ProgressColumn(
                "천만 달성률",
                format="%.1f%%",
                min_value=0,
                max_value=100,
            ),
        },
    )
