# main.py
# ------------------------------------------------------------
# 현재 상영작 천만 관객 달성 현황
#
# 주요 기능
# 1. 최근 7일간 KOBIS 일일 박스오피스 자료 수집
# 2. 현재 상영작의 천만 관객 달성률 순위 표시
# 3. 최근 7일 평균 관객 수로 천만 달성 예상 기간 계산
# 4. 이미 천만 관객을 달성한 현재 상영작 표시
# 5. 천만 미달 영화 중 누적 관객이 가장 많은
#    '천만 마지노선 영화' 표시
#
# 주의
# - KOBIS 일일 API의 상위 목록에 등장한 영화를 대상으로 합니다.
# - 예상 기간은 단순 통계적 참고값이며 실제 흥행을 보장하지 않습니다.
# ------------------------------------------------------------

import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ------------------------------------------------------------
# 1. 페이지 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="천만 관객 도전 현황",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 현재 상영작 천만 관객 도전 현황")

st.caption(
    "최근 7일간 KOBIS 일일 박스오피스에 등장한 영화를 대상으로 "
    "천만 관객 달성률과 예상 기간을 계산합니다."
)


# ------------------------------------------------------------
# 2. 기본 설정값
# ------------------------------------------------------------
TEN_MILLION = 10_000_000

# 최근 며칠간 자료를 분석할지 정합니다.
# 7이면 어제부터 과거 7일간의 데이터를 가져옵니다.
ANALYSIS_DAYS = 7

KOBIS_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)


# ------------------------------------------------------------
# 3. 간단한 화면 디자인
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container {
        max-width: 1500px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    div[data-testid="stMetric"] {
        background-color: #fafafa;
        border: 1px solid #e9e9e9;
        border-radius: 14px;
        padding: 0.85rem 1rem;
    }

    .movie-card {
        background: #fafafa;
        border: 1px solid #e8e8e8;
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }

    .movie-title {
        font-size: 1.25rem;
        font-weight: 750;
        margin-bottom: 0.35rem;
    }

    .movie-description {
        color: #555555;
        line-height: 1.7;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# 4. Streamlit Secrets에서 인증키 가져오기
# ------------------------------------------------------------
# Streamlit Cloud의 Secrets에 다음 형식으로 저장합니다.
#
# KOBIS_KEY = "발급받은 인증키"
#
# 인증키는 코드에 직접 적지 않습니다.
try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]

except KeyError:
    st.error(
        "Streamlit Secrets에서 KOBIS_KEY를 찾지 못했습니다. "
        "앱 설정의 Secrets에 인증키를 등록해 주세요."
    )
    st.stop()


# ------------------------------------------------------------
# 5. 한국 시간 기준 날짜 계산
# ------------------------------------------------------------
korea_now = datetime.now(
    ZoneInfo("Asia/Seoul")
)

# KOBIS 일일 박스오피스는 전일 자료를 사용합니다.
latest_date = korea_now.date() - timedelta(days=1)

analysis_dates = [
    latest_date - timedelta(days=offset)
    for offset in range(ANALYSIS_DAYS)
]

st.caption(
    f"분석 기간: {min(analysis_dates):%Y-%m-%d} ~ "
    f"{max(analysis_dates):%Y-%m-%d}"
)


# ------------------------------------------------------------
# 6. KOBIS 일일 박스오피스 호출
# ------------------------------------------------------------
@st.cache_data(
    ttl=60 * 30,
    show_spinner=False,
)
def request_daily_boxoffice(
    api_key: str,
    target_date: date,
) -> list:
    """
    특정 날짜의 KOBIS 일일 박스오피스 자료를 가져옵니다.

    반환값은 영화 목록입니다.
    """
    target_dt = target_date.strftime("%Y%m%d")

    response = requests.get(
        KOBIS_URL,
        params={
            "key": api_key,
            "targetDt": target_dt,
        },
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    # KOBIS는 키가 잘못된 경우에도 HTTP 200을 보내고
    # faultInfo 안에 오류 내용을 넣는 경우가 있습니다.
    if "faultInfo" in data:
        fault_info = data.get(
            "faultInfo",
            {},
        )

        message = fault_info.get(
            "message",
            "인증키 또는 요청 정보를 확인해 주세요.",
        )

        raise ValueError(
            f"KOBIS API 오류: {message}"
        )

    return (
        data
        .get("boxOfficeResult", {})
        .get("dailyBoxOfficeList", [])
    )


# ------------------------------------------------------------
# 7. 최근 여러 날짜의 박스오피스 자료 수집
# ------------------------------------------------------------
@st.cache_data(
    ttl=60 * 30,
    show_spinner=False,
)
def load_recent_boxoffice(
    api_key: str,
    date_texts: tuple,
) -> pd.DataFrame:
    """
    여러 날짜의 일일 박스오피스 자료를 하나의 표로 합칩니다.

    date_texts를 튜플로 받는 이유는 Streamlit 캐시에서
    안전하게 사용할 수 있도록 하기 위해서입니다.
    """
    rows = []

    for date_text in date_texts:
        target_date = datetime.strptime(
            date_text,
            "%Y-%m-%d",
        ).date()

        daily_movies = request_daily_boxoffice(
            api_key,
            target_date,
        )

        for movie in daily_movies:
            movie_row = movie.copy()
            movie_row["기준일"] = target_date
            rows.append(movie_row)

    return pd.DataFrame(rows)


date_texts = tuple(
    target_date.strftime("%Y-%m-%d")
    for target_date in analysis_dates
)


try:
    with st.spinner(
        "최근 박스오피스와 관객 추세를 불러오는 중입니다..."
    ):
        raw_df = load_recent_boxoffice(
            KOBIS_KEY,
            date_texts,
        )

except requests.exceptions.Timeout:
    st.error(
        "KOBIS 서버 응답 시간이 초과되었습니다. "
        "잠시 후 다시 시도해 주세요."
    )
    st.stop()

except requests.exceptions.RequestException as error:
    st.error(
        "KOBIS 데이터를 불러오지 못했습니다."
    )
    st.exception(error)
    st.stop()

except ValueError as error:
    st.error(str(error))
    st.stop()

except Exception as error:
    st.error(
        "박스오피스 자료를 처리하는 중 문제가 발생했습니다."
    )
    st.exception(error)
    st.stop()


if raw_df.empty:
    st.warning(
        "분석 기간에 박스오피스 자료가 없습니다."
    )
    st.stop()


# ------------------------------------------------------------
# 8. 숫자 열 정리
# ------------------------------------------------------------
numeric_columns = [
    "rank",
    "rankInten",
    "salesAmt",
    "salesAcc",
    "audiCnt",
    "audiInten",
    "audiChange",
    "audiAcc",
    "scrnCnt",
    "showCnt",
]

for column in numeric_columns:
    if column in raw_df.columns:
        raw_df[column] = pd.to_numeric(
            raw_df[column],
            errors="coerce",
        ).fillna(0)


required_columns = {
    "movieCd",
    "movieNm",
    "openDt",
    "rank",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
    "showCnt",
    "기준일",
}

missing_columns = (
    required_columns
    - set(raw_df.columns)
)

if missing_columns:
    missing_text = ", ".join(
        sorted(missing_columns)
    )

    st.error(
        f"KOBIS 응답에 필요한 항목이 없습니다: {missing_text}"
    )
    st.stop()


# ------------------------------------------------------------
# 9. 개봉일 변환
# ------------------------------------------------------------
raw_df["개봉일"] = pd.to_datetime(
    raw_df["openDt"],
    errors="coerce",
).dt.date


# ------------------------------------------------------------
# 10. 현재 상영작 선정
# ------------------------------------------------------------
# 최근 7일 자료 중 가장 최신 날짜에 등장한 작품을
# 현재 상영 중인 주요 작품으로 봅니다.
latest_daily_df = raw_df.loc[
    raw_df["기준일"].eq(latest_date)
].copy()

if latest_daily_df.empty:
    # 어제 데이터가 없을 때는 실제 자료가 있는 가장 최근 날짜를 씁니다.
    available_dates = raw_df["기준일"].dropna()

    if available_dates.empty:
        st.warning(
            "사용할 수 있는 박스오피스 기준일이 없습니다."
        )
        st.stop()

    latest_date = available_dates.max()

    latest_daily_df = raw_df.loc[
        raw_df["기준일"].eq(latest_date)
    ].copy()


current_movie_codes = (
    latest_daily_df["movieCd"]
    .astype(str)
    .unique()
    .tolist()
)

current_history = raw_df.loc[
    raw_df["movieCd"]
    .astype(str)
    .isin(current_movie_codes)
].copy()


# ------------------------------------------------------------
# 11. 영화별 최근 관객 추세 집계
# ------------------------------------------------------------
def safe_first_date(series):
    """
    유효한 날짜 중 가장 빠른 날짜를 반환합니다.
    """
    valid_values = series.dropna()

    if valid_values.empty:
        return pd.NaT

    return min(valid_values)


def safe_latest_value(
    movie_rows: pd.DataFrame,
    column: str,
):
    """
    영화의 가장 최신 날짜 행에서 값을 가져옵니다.
    """
    sorted_rows = movie_rows.sort_values(
        "기준일",
        ascending=False,
    )

    if sorted_rows.empty:
        return 0

    return sorted_rows.iloc[0][column]


movie_rows = []

for movie_code, group in current_history.groupby(
    "movieCd"
):
    group = group.sort_values("기준일")

    latest_row = (
        group
        .sort_values("기준일", ascending=False)
        .iloc[0]
    )

    movie_name = latest_row["movieNm"]
    opening_date = safe_first_date(
        group["개봉일"]
    )

    accumulated_audience = int(
        latest_row["audiAcc"]
    )

    latest_daily_audience = int(
        latest_row["audiCnt"]
    )

    latest_rank = int(
        latest_row["rank"]
    )

    latest_screen_count = int(
        latest_row["scrnCnt"]
    )

    latest_show_count = int(
        latest_row["showCnt"]
    )

    # 최근 분석 기간 중 영화가 박스오피스에 등장한 날의
    # 일일 관객 수 평균입니다.
    observed_daily_audience = (
        group["audiCnt"]
        .clip(lower=0)
    )

    average_daily_audience = (
        observed_daily_audience.mean()
        if not observed_daily_audience.empty
        else 0
    )

    # 최근 3개 관측일의 평균도 계산합니다.
    recent_three_average = (
        observed_daily_audience
        .tail(3)
        .mean()
        if not observed_daily_audience.empty
        else 0
    )

    # 최근 흐름을 조금 더 반영하기 위해
    # 최근 3일 평균 70%, 전체 기간 평균 30%를 적용합니다.
    forecast_daily_audience = (
        recent_three_average * 0.7
        + average_daily_audience * 0.3
    )

    achievement_rate = (
        accumulated_audience
        / TEN_MILLION
        * 100
    )

    remaining_audience = max(
        TEN_MILLION - accumulated_audience,
        0,
    )

    # 개봉 후 경과일
    if pd.notna(opening_date):
        days_since_release = (
            latest_date - opening_date
        ).days + 1
    else:
        days_since_release = pd.NA

    # 이미 천만 관객을 달성했다면 예상 소요일은 0일입니다.
    if accumulated_audience >= TEN_MILLION:
        expected_days = 0
        expected_date = latest_date

    # 최근 예상 일일 관객 수가 0 이하면 계산할 수 없습니다.
    elif forecast_daily_audience <= 0:
        expected_days = pd.NA
        expected_date = pd.NaT

    else:
        expected_days = math.ceil(
            remaining_audience
            / forecast_daily_audience
        )

        expected_date = (
            latest_date
            + timedelta(days=expected_days)
        )

    movie_rows.append(
        {
            "영화코드": str(movie_code),
            "영화명": movie_name,
            "개봉일": opening_date,
            "최근 순위": latest_rank,
            "누적 관객 수": accumulated_audience,
            "최근 일일 관객 수": latest_daily_audience,
            "최근 평균 관객 수": int(
                round(average_daily_audience)
            ),
            "예측 기준 일일 관객 수": int(
                round(forecast_daily_audience)
            ),
            "스크린 수": latest_screen_count,
            "상영 횟수": latest_show_count,
            "천만 달성률": achievement_rate,
            "천만까지 남은 관객": remaining_audience,
            "예상 소요일": expected_days,
            "예상 달성일": expected_date,
            "개봉 후 경과일": days_since_release,
            "천만 달성 여부": (
                "달성"
                if accumulated_audience >= TEN_MILLION
                else "도전 중"
            ),
        }
    )


movies = pd.DataFrame(movie_rows)

if movies.empty:
    st.warning(
        "현재 상영작 정보를 계산할 수 없습니다."
    )
    st.stop()


# ------------------------------------------------------------
# 12. 표시용 문자열 만들기
# ------------------------------------------------------------
def format_expected_period(days):
    """
    예상 소요일을 보기 쉬운 문자열로 바꿉니다.
    """
    if pd.isna(days):
        return "예측 불가"

    days = int(days)

    if days == 0:
        return "이미 달성"

    if days < 7:
        return f"약 {days}일"

    if days < 30:
        weeks = days / 7
        return f"약 {weeks:.1f}주"

    months = days / 30
    return f"약 {months:.1f}개월"


def format_expected_date(expected_date):
    """
    예상 달성일을 문자열로 바꿉니다.
    """
    if pd.isna(expected_date):
        return "예측 불가"

    return expected_date.strftime(
        "%Y-%m-%d"
    )


movies["예상 기간"] = movies[
    "예상 소요일"
].apply(
    format_expected_period
)

movies["예상 달성일 표시"] = movies[
    "예상 달성일"
].apply(
    format_expected_date
)

movies["달성률 표시"] = movies[
    "천만 달성률"
].apply(
    lambda value: f"{value:.1f}%"
)


# ------------------------------------------------------------
# 13. 천만 달성률 순위
# ------------------------------------------------------------
ranking = (
    movies
    .sort_values(
        by=[
            "천만 달성률",
            "최근 일일 관객 수",
        ],
        ascending=[
            False,
            False,
        ],
    )
    .reset_index(drop=True)
)

ranking.insert(
    0,
    "달성률 순위",
    range(1, len(ranking) + 1),
)


# ------------------------------------------------------------
# 14. 이미 천만을 달성한 현재 상영작
# ------------------------------------------------------------
achieved_movies = (
    movies.loc[
        movies["누적 관객 수"] >= TEN_MILLION
    ]
    .sort_values(
        "누적 관객 수",
        ascending=False,
    )
    .reset_index(drop=True)
)


# ------------------------------------------------------------
# 15. 천만 미달 작품과 마지노선 영화
# ------------------------------------------------------------
under_ten_million = (
    movies.loc[
        movies["누적 관객 수"] < TEN_MILLION
    ]
    .sort_values(
        "누적 관객 수",
        ascending=False,
    )
    .reset_index(drop=True)
)

borderline_movie = None

if not under_ten_million.empty:
    borderline_movie = (
        under_ten_million
        .iloc[0]
    )


# ------------------------------------------------------------
# 16. 상단 핵심 지표
# ------------------------------------------------------------
metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "현재 주요 상영작",
    f"{len(movies):,}편",
)

metric2.metric(
    "천만 달성 작품",
    f"{len(achieved_movies):,}편",
)

metric3.metric(
    "천만 도전 작품",
    f"{len(under_ten_million):,}편",
)

if borderline_movie is not None:
    metric4.metric(
        "천만 마지노선",
        borderline_movie["영화명"],
        f"{borderline_movie['누적 관객 수']:,}명",
    )
else:
    metric4.metric(
        "천만 마지노선",
        "해당 없음",
    )


# ------------------------------------------------------------
# 17. 천만 마지노선 영화 강조
# ------------------------------------------------------------
st.divider()
st.subheader("🔥 천만 관객 마지노선 영화")

if borderline_movie is None:
    st.success(
        "현재 주요 상영작 가운데 천만 관객 미달 영화가 없습니다."
    )

else:
    border_col1, border_col2, border_col3, border_col4 = (
        st.columns(4)
    )

    border_col1.metric(
        "영화",
        borderline_movie["영화명"],
    )

    border_col2.metric(
        "누적 관객 수",
        f"{int(borderline_movie['누적 관객 수']):,}명",
    )

    border_col3.metric(
        "천만 달성률",
        f"{borderline_movie['천만 달성률']:.1f}%",
    )

    border_col4.metric(
        "예상 기간",
        borderline_movie["예상 기간"],
    )

    st.markdown(
        f"""
        <div class="movie-card">
            <div class="movie-title">
                {borderline_movie["영화명"]}
            </div>
            <div class="movie-description">
                현재 천만 관객 미달 작품 중 누적 관객 수가 가장 많습니다.<br>
                천만 관객까지
                <b>{int(borderline_movie["천만까지 남은 관객"]):,}명</b>이
                남았습니다.<br>
                최근 관객 추세가 유지되면 예상 달성일은
                <b>{borderline_movie["예상 달성일 표시"]}</b>입니다.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# 18. 현재 상영작 천만 달성률 순위
# ------------------------------------------------------------
st.divider()
st.subheader("🏆 현재 상영작 천만 관객 달성률 순위")

st.caption(
    "누적 관객 수를 천만 명으로 나눈 비율이 높은 순서입니다. "
    "이미 천만을 넘은 작품은 달성률이 100%보다 크게 표시됩니다."
)

ranking_table = ranking[
    [
        "달성률 순위",
        "영화명",
        "천만 달성 여부",
        "최근 순위",
        "누적 관객 수",
        "천만 달성률",
        "천만까지 남은 관객",
        "최근 일일 관객 수",
        "예측 기준 일일 관객 수",
        "예상 기간",
        "예상 달성일 표시",
    ]
].copy()

ranking_table.columns = [
    "순위",
    "영화명",
    "상태",
    "최근 박스오피스 순위",
    "누적 관객 수",
    "천만 달성률",
    "남은 관객 수",
    "최근 일일 관객 수",
    "예측 기준 관객 수",
    "예상 기간",
    "예상 달성일",
]

st.dataframe(
    ranking_table,
    hide_index=True,
    use_container_width=True,
    column_config={
        "순위": st.column_config.NumberColumn(
            "달성률 순위",
            format="%d위",
        ),
        "최근 박스오피스 순위": (
            st.column_config.NumberColumn(
                "최근 순위",
                format="%d위",
            )
        ),
        "누적 관객 수": st.column_config.NumberColumn(
            "누적 관객 수",
            format="%d명",
        ),
        "천만 달성률": st.column_config.NumberColumn(
            "천만 달성률",
            format="%.1f%%",
        ),
        "남은 관객 수": st.column_config.NumberColumn(
            "남은 관객 수",
            format="%d명",
        ),
        "최근 일일 관객 수": (
            st.column_config.NumberColumn(
                "최근 일일 관객 수",
                format="%d명",
            )
        ),
        "예측 기준 관객 수": (
            st.column_config.NumberColumn(
                "예측 기준 일일 관객 수",
                format="%d명",
            )
        ),
        "예상 기간": st.column_config.TextColumn(
            "예상 기간",
        ),
        "예상 달성일": st.column_config.TextColumn(
            "예상 달성일",
        ),
    },
)


# ------------------------------------------------------------
# 19. 달성률 막대 차트
# ------------------------------------------------------------
st.subheader("📊 영화별 천만 달성률")

chart_data = (
    ranking
    .set_index("영화명")["천만 달성률"]
)

st.bar_chart(
    chart_data,
)


# ------------------------------------------------------------
# 20. 천만 달성 영화 정보
# ------------------------------------------------------------
st.divider()
st.subheader("🎉 현재 상영 중인 천만 관객 달성 영화")

if achieved_movies.empty:
    st.info(
        "현재 주요 상영작 중 천만 관객을 달성한 영화가 없습니다."
    )

else:
    achieved_display = achieved_movies.copy()

    achieved_display.insert(
        0,
        "천만 영화 순위",
        range(
            1,
            len(achieved_display) + 1,
        ),
    )

    achieved_table = achieved_display[
        [
            "천만 영화 순위",
            "영화명",
            "개봉일",
            "누적 관객 수",
            "천만 달성률",
            "개봉 후 경과일",
            "최근 일일 관객 수",
            "스크린 수",
            "상영 횟수",
        ]
    ].copy()

    achieved_table.columns = [
        "순위",
        "영화명",
        "개봉일",
        "누적 관객 수",
        "천만 대비 관객률",
        "개봉 후 기간",
        "최근 일일 관객 수",
        "스크린 수",
        "상영 횟수",
    ]

    st.dataframe(
        achieved_table,
        hide_index=True,
        use_container_width=True,
        column_config={
            "순위": st.column_config.NumberColumn(
                "순위",
                format="%d위",
            ),
            "개봉일": st.column_config.DateColumn(
                "개봉일",
                format="YYYY-MM-DD",
            ),
            "누적 관객 수": (
                st.column_config.NumberColumn(
                    "누적 관객 수",
                    format="%d명",
                )
            ),
            "천만 대비 관객률": (
                st.column_config.NumberColumn(
                    "천만 대비 관객률",
                    format="%.1f%%",
                )
            ),
            "개봉 후 기간": (
                st.column_config.NumberColumn(
                    "개봉 후 경과일",
                    format="%d일",
                )
            ),
            "최근 일일 관객 수": (
                st.column_config.NumberColumn(
                    "최근 일일 관객 수",
                    format="%d명",
                )
            ),
            "스크린 수": (
                st.column_config.NumberColumn(
                    "스크린 수",
                    format="%d개",
                )
            ),
            "상영 횟수": (
                st.column_config.NumberColumn(
                    "상영 횟수",
                    format="%d회",
                )
            ),
        },
    )

    st.warning(
        "표의 '개봉 후 경과일'은 개봉일부터 현재 조회 기준일까지의 "
        "기간입니다. KOBIS 일일 박스오피스 API만으로는 영화가 정확히 "
        "천만 명을 돌파한 날짜를 알 수 없으므로, "
        "'천만 달성까지 걸린 기간'과는 다릅니다."
    )


# ------------------------------------------------------------
# 21. 천만 도전 중인 작품만 별도 표시
# ------------------------------------------------------------
st.divider()
st.subheader("🚀 천만 관객 도전 중인 영화")

if under_ten_million.empty:
    st.success(
        "현재 주요 상영작이 모두 천만 관객을 달성했습니다."
    )

else:
    challenge_movies = (
        under_ten_million
        .sort_values(
            by=[
                "천만 달성률",
                "최근 일일 관객 수",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .reset_index(drop=True)
    )

    challenge_movies.insert(
        0,
        "도전 순위",
        range(
            1,
            len(challenge_movies) + 1,
        ),
    )

    challenge_table = challenge_movies[
        [
            "도전 순위",
            "영화명",
            "누적 관객 수",
            "천만 달성률",
            "천만까지 남은 관객",
            "예측 기준 일일 관객 수",
            "예상 기간",
            "예상 달성일 표시",
        ]
    ].copy()

    challenge_table.columns = [
        "순위",
        "영화명",
        "누적 관객 수",
        "천만 달성률",
        "남은 관객 수",
        "예측 기준 일일 관객 수",
        "예상 기간",
        "예상 달성일",
    ]

    st.dataframe(
        challenge_table,
        hide_index=True,
        use_container_width=True,
        column_config={
            "순위": st.column_config.NumberColumn(
                "도전 순위",
                format="%d위",
            ),
            "누적 관객 수": (
                st.column_config.NumberColumn(
                    "누적 관객 수",
                    format="%d명",
                )
            ),
            "천만 달성률": (
                st.column_config.ProgressColumn(
                    "천만 달성률",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                )
            ),
            "남은 관객 수": (
                st.column_config.NumberColumn(
                    "남은 관객 수",
                    format="%d명",
                )
            ),
            "예측 기준 일일 관객 수": (
                st.column_config.NumberColumn(
                    "예측 기준 일일 관객 수",
                    format="%d명",
                )
            ),
            "예상 기간": (
                st.column_config.TextColumn(
                    "예상 기간",
                )
            ),
            "예상 달성일": (
                st.column_config.TextColumn(
                    "예상 달성일",
                )
            ),
        },
    )


# ------------------------------------------------------------
# 22. 계산 방법 안내
# ------------------------------------------------------------
with st.expander("예상 기간과 현재 상영작 선정 방법"):
    st.markdown(
        f"""
        ### 현재 상영작 기준

        KOBIS 일일 박스오피스 API는 전국에서 상영 중인 모든 작품의
        목록을 직접 제공하는 방식이 아닙니다.

        이 앱에서는 **가장 최근 조회일인 {latest_date:%Y-%m-%d}의
        일일 박스오피스에 포함된 영화**를 현재 주요 상영작으로 봅니다.

        ### 천만 달성률

        `누적 관객 수 ÷ 10,000,000 × 100`

        ### 예측 기준 일일 관객 수

        최근 흐름을 더 많이 반영하기 위해 다음과 같이 계산합니다.

        `최근 3개 관측일 평균 × 70% + 최근 7일 평균 × 30%`

        영화가 최근 7일 중 일부 날짜에만 박스오피스에 등장했다면
        실제로 자료가 있는 날짜만 평균에 사용합니다.

        ### 예상 소요일

        `천만까지 남은 관객 수 ÷ 예측 기준 일일 관객 수`

        계산 결과의 소수점은 올림합니다.

        ### 주의 사항

        실제 관객 수는 평일과 주말, 신작 개봉, 스크린 수 변화,
        입소문, 연휴 등에 따라 크게 달라질 수 있습니다.

        따라서 예상 기간과 예상 달성일은 참고용이며,
        흥행 결과를 보장하는 예측이 아닙니다.
        """
    )


st.caption(
    f"마지막 박스오피스 기준일: {latest_date:%Y-%m-%d} · "
    f"추세 분석 기간: 최근 {ANALYSIS_DAYS}일 · "
    "자료 출처: 영화진흥위원회 KOBIS"
)
