import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
from collections import Counter

st.set_page_config(
    page_title="LMS 발송 성과 대시보드",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── 커스텀 CSS ──────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 4px solid #4C72B0;
        margin-bottom: 10px;
    }
    .metric-label { font-size: 13px; color: #666; margin-bottom: 4px; }
    .metric-value { font-size: 24px; font-weight: 700; color: #1a1a2e; }
    .metric-sub { font-size: 12px; color: #888; margin-top: 2px; }
    .section-title {
        font-size: 17px; font-weight: 700; color: #1a1a2e;
        margin: 24px 0 12px 0; padding-bottom: 6px;
        border-bottom: 2px solid #e9ecef;
        scroll-margin-top: 60px;
    }
    /* 사이드바 하위 메뉴 링크 */
    a.subnav-link { color: #2E68B0; text-decoration: none; }
    a.subnav-link:hover { text-decoration: underline; }
</style>
""", unsafe_allow_html=True)


# ── 데이터 로드 ──────────────────────────────────────────────
@st.cache_data
def load_data(file):
    df = pd.read_excel(file, sheet_name="Sheet1", header=1)
    # 컬럼명 정리
    df = df.rename(columns={
        '구분': '발송일자',
        '발송시간대': '시간대',
        '고객군명': '타겟',
        '주문금액': '거래액',
    })
    df = df.dropna(subset=['캠페인명'])
    df = df[df['캠페인명'].astype(str).str.startswith('MKT_')]

    # 타입 변환
    df['발송일자'] = pd.to_datetime(df['발송일자'], errors='coerce')

    # ROAS: Excel % 포맷셀 → pandas가 /100으로 읽으므로 ×100 복원
    df['ROAS'] = pd.to_numeric(df['ROAS'], errors='coerce') * 100

    # CTR, CR: Excel % 포맷셀 → 소수로 읽힘 (0.135 = 13.5%)
    for col in ['CTR', 'CR']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    for col in ['모수', 'UV', '고객수', '주문수', '거래액']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '', regex=False), errors='coerce')
    if '비용' in df.columns:
        df['비용'] = pd.to_numeric(df['비용'].astype(str).str.replace(',', '', regex=False), errors='coerce')

    df['채널'] = df['채널'].fillna('LMS').str.upper()
    df['월'] = df['발송일자'].dt.to_period('M').astype(str)
    df['연도'] = df['발송일자'].dt.year
    요일맵 = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    df['요일'] = df['발송일자'].dt.dayofweek.map(요일맵)
    df['시간'] = df['시간대'].astype(str).str.extract(r'(\d+)').astype(float)
    df['문구'] = df['문구'].astype(str).str.strip()

    return df


# 형태소 분석기 없이 한글 토큰을 뽑으면 조사·어미가 붙은 노이즈가 많다.
# (1) 불용어를 넓게 잡고 (2) 끝의 조사/어미를 다듬고 (3) 유사어를 실제 대표어로 통합한다.
_KW_STOP = {
    # 발송 boilerplate / 채널 고정문구
    '광고', 'LF몰', 'LFmall', '엘에프몰', '무료수신거부', '수신거부', '고객센터', 'NaN', 'nan',
    '안내', '안내드립니다', '확인', '확인하세요', '클릭', '바로가기', '링크', '여기',
    # 템플릿 변수 (모든 문자에 들어감)
    '고객명', '주문번호', '상품명', '브랜드명', '금액', '날짜', '시간', '이름',
    # 조사/어미/대명사 등 의미 없는 조각
    '님', '님이', '님께', '님은', '님을', '님의', '받을', '받기', '받으', '받아',
    '드려', '드림', '드릴', '드립니다', '합니다', '하세요', '하시', '하실', '하는', '했던',
    '에서', '으로', '에게', '한테', '까지', '부터', '보다', '처럼', '만큼', '에서만',
    '을', '를', '은', '는', '이', '가', '의', '에', '도', '만', '과', '와', '로', '께', '요',
    '지금', '오직', '다시', '바로', '모든', '각종', '다양', '특별', '새로운', '이번', '오늘',
    '경우', '관련', '대한', '통해', '위한', '위해', '정도', '준비', '시작', '진행', '대상',
    # 동사·형용사 조각 (의미 없는 토큰)
    '확인해보세', '확인해', '있는', '있어', '있습', '없는', '없어', '되는', '하는', '드리는',
    '만나', '만나보', '담아', '담긴', '놓치', '놓치지', '챙기', '누리', '드세', '받기', '보기', '오는',
    '지마', '마세', '하지', '잊지', '늦지', '서둘러', '지금만', '바로지금',
    '초특',  # '초특가'는 normalize에서 처리, 잘린 조각은 제외
    # 너무 범용적인 단어
    '상품', '구매', '주문', '배송', '서비스', '사이트', '페이지', '쇼핑', '혜택가',
}
# 유사어 → 실제 대표 키워드로 통합 (카테고리명으로 치환하지 말 것!)
_KW_NORMALIZE = {
    '고객님만': '고객님', '고객님께': '고객님', '고객님을': '고객님', '고객님이': '고객님',
    '보셨던': '관심상품', '담으셨던': '관심상품', '찜하셨던': '관심상품',
    '담으신': '관심상품', '찜하신': '관심상품', '관심상품': '관심상품',
    '할인가': '할인', '특가': '할인', '세일': '할인', '할인율': '할인', '초특가': '할인',
    '오늘까지': '마감임박', '오늘만': '마감임박', '종료임박': '마감임박', '마감임박': '마감임박',
    '쿠폰을': '쿠폰', '쿠폰이': '쿠폰', '적립금': '적립',
}
_KW_PARTICLE_TAILS = ('으로', '에서', '까지', '부터', '에게', '이라', '이나', '만큼', '처럼', '한테', '이신', '으신')
_KW_JOSA = set('을를은는이가의에도만과와로께요')
# 동사·어미로 끝나는 토큰은 키워드가 아니므로 제외
_KW_BAD_TAILS = ('보세', '하세', '으세', '세요', '해요', '어요', '아요', '에요', '니다', '습니', '드려',
                 '드리', '하기', '되기', '하실', '하면', '있는', '없는', '하는', '되는', '있어', '없어',
                 '마세', '지마', '잊지', '늦지', '볼까', '을까', '려고', '면서', '거나')

def _trim_particle(w):
    """끝에 붙은 조사/어미를 보수적으로 제거해 같은 단어를 하나로 모은다."""
    for p in _KW_PARTICLE_TAILS:
        if len(w) > len(p) + 1 and w.endswith(p):
            return w[:-len(p)]
    if len(w) >= 3 and w[-1] in _KW_JOSA:
        return w[:-1]
    return w

def _is_noise_token(w):
    """동사·어미로 끝나는 비(非)키워드 토큰인지."""
    return any(w.endswith(t) for t in _KW_BAD_TAILS)


@st.cache_data
def extract_keywords(texts, top_n=30):
    stop = _KW_STOP
    normalize = _KW_NORMALIZE
    pattern = re.compile(r'[a-zA-Z0-9\[\]\(\)\!\★▷▶◇\-\*·/\.,:↓%~#\[\]]+')
    keyword_counts = Counter()
    for text in texts:
        if pd.isna(text) or str(text) in ('nan', 'NaN', ''):
            continue
        text = re.sub(pattern, ' ', str(text))
        words = re.findall(r'[가-힣]{2,6}', text)
        for w in words:
            w = _trim_particle(w)
            if w in stop or len(w) < 2 or _is_noise_token(w):
                continue
            w = normalize.get(w, w)
            if w in stop or _is_noise_token(w):
                continue
            keyword_counts[w] += 1
    return keyword_counts.most_common(top_n)


# ── 가중/풀링 집계 헬퍼 ──────────────────────────────────────────────
# 비율 지표(CTR·CR·ROAS)를 캠페인별로 단순평균하면 발송규모가 큰 캠페인과
# 작은 캠페인을 같은 무게로 취급해 왜곡된다. 분모 가중평균·풀링으로 보정한다.
def w_avg(values, weights):
    """가중평균 — 비율을 분모(발송규모/클릭수)로 가중."""
    v = pd.to_numeric(values, errors='coerce')
    w = pd.to_numeric(weights, errors='coerce')
    m = v.notna() & w.notna() & (w > 0)
    tot = w[m].sum()
    return float((v[m] * w[m]).sum() / tot) if tot > 0 else np.nan

def pooled_roas(frame):
    """전체 ROAS = Σ거래액 / Σ비용 × 100. 비용은 거래액/ROAS로 역산(단순평균 금지)."""
    rev = pd.to_numeric(frame['거래액'], errors='coerce')
    ratio = pd.to_numeric(frame['ROAS'], errors='coerce') / 100.0
    cost = rev / ratio.where(ratio > 0)
    m = rev.notna() & cost.notna() & (cost > 0)
    return float(rev[m].sum() / cost[m].sum() * 100) if cost[m].sum() > 0 else np.nan

def w_cr(g):
    """CR 가중평균 — 클릭(UV) 가중, 없으면 모수 가중 폴백."""
    val = w_avg(g['CR'], g['UV'])
    return val if pd.notna(val) else w_avg(g['CR'], g['모수'])

def perf_by(frame, by):
    """그룹별 성과 집계. CTR=모수가중, CR=UV가중, ROAS=Σ거래액/Σ비용.
    거래액은 총액뿐 아니라 캠페인당·1인당으로도 제공(효율 비교용)."""
    by_cols = list(by) if isinstance(by, (list, tuple)) else [by]
    cols = by_cols + ['발송건수', '캠페인건수', '평균모수', '총모수', '총고객수',
                      '평균CTR', '평균CR', '평균ROAS',
                      '총거래액', '캠페인당거래액', '1인당거래액', '객단가']
    rows = []
    for key, g in frame.groupby(by):
        keys = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by_cols, keys))
        n = len(g)
        sends = pd.to_numeric(g['모수'], errors='coerce').sum()
        rev = pd.to_numeric(g['거래액'], errors='coerce').sum()
        buyers = pd.to_numeric(g['고객수'], errors='coerce').sum() if '고객수' in g else np.nan
        row.update({
            '발송건수': n, '캠페인건수': n,
            '평균모수': pd.to_numeric(g['모수'], errors='coerce').mean(),
            '총모수': sends,
            '총고객수': buyers,
            '평균CTR': w_avg(g['CTR'], g['모수']),
            '평균CR': w_cr(g),
            '평균ROAS': pooled_roas(g),
            '총거래액': rev,
            '캠페인당거래액': rev / n if n else np.nan,
            '1인당거래액': rev / sends if sends and sends > 0 else np.nan,   # 발송모수(타겟) 1명당
            '객단가': rev / buyers if buyers and buyers > 0 else np.nan,      # 구매고객 1명당
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


# ── 금액 포맷 (만원/백만원/억 — 'M' 같은 SI 표기 금지) ──────────────────────────────
def fmt_won(v):
    """한글 금액 단위. 억/백만원/만원/원으로 자동 축약."""
    if pd.isna(v):
        return '-'
    a = abs(v)
    if a >= 1e8:
        return f"{v/1e8:,.1f}억원"
    if a >= 1e6:
        return f"{v/1e6:,.1f}백만원"
    if a >= 1e4:
        return f"{v/1e4:,.0f}만원"
    return f"{v:,.0f}원"

def to_백만(v):
    """차트 축용 — 백만원 단위 숫자로 변환."""
    return pd.to_numeric(v, errors='coerce') / 1e6


def sec_title(label, anchor):
    """앵커(id) 달린 섹션 제목 — 사이드바 세부 점프용."""
    st.markdown(f'<div class="section-title" id="{anchor}">{label}</div>', unsafe_allow_html=True)


# 페이지별 세부 섹션 (anchor, 표시라벨) — 사이드바 목차에 사용
SECTIONS = {
    "📡 채널별 분석": [("p1-compare", "채널 효율 비교"), ("p1-summary", "채널별 종합 성과"), ("p1-daily", "일자별 추이")],
    "📅 월별 트렌드": [("p2-monthly", "월별 추이"), ("p2-dow", "요일별"), ("p2-hour", "시간대별"), ("p2-heat", "요일×시간 히트맵")],
    "🔤 문구 키워드 분석": [("p3-cat", "카테고리별 성과"), ("p3-freq", "키워드 빈도"), ("p3-lift", "성과 키워드"), ("p3-diag", "문구 진단")],
    "🗂 캠페인 상세": [("p4-table", "캠페인 상세표"), ("p4-recurring", "반복 캠페인")],
    "🏷 AF코드별 효율": [("p5-eff", "AF코드별 효율"), ("p5-scatter", "타겟 vs 거래액")],
    "⚖️ A vs B 비교": [("p6-compare", "A vs B 비교")],
}


# ── 사이드바 ──────────────────────────────────────────────
with st.sidebar:
    st.title("📱 LMS 대시보드")
    st.markdown("---")

    st.markdown("**📂 엑셀 파일 업로드**")
    file_upload = st.file_uploader("26년 문자발송건 통합본", type=["xlsx"], key="file_upload")

    if not file_upload:
        st.info("파일을 업로드하면 대시보드가 로드됩니다.")
        st.stop()

    df_raw = load_data(file_upload)

    # ── 분석 메뉴 (아코디언: 선택한 메뉴 바로 아래 하위 섹션 펼침) ──
    st.markdown("---")
    st.markdown("**📂 분석 메뉴**")
    PAGES = ["📡 채널별 분석", "📅 월별 트렌드", "🔤 문구 키워드 분석",
             "🗂 캠페인 상세", "🏷 AF코드별 효율", "⚖️ A vs B 비교"]
    sel = st.session_state.get('nav', PAGES[0])
    if sel not in PAGES:
        sel = PAGES[0]
    for p in PAGES:
        if st.button(p, key=f'navbtn_{p}', use_container_width=True,
                     type=('primary' if p == sel else 'secondary')):
            if p != sel:
                st.session_state['nav'] = p
                st.rerun()
        if p == sel:
            _secs = SECTIONS.get(p, [])
            if _secs:
                links = "".join(
                    f'<div style="font-size:0.85em;margin:3px 0">'
                    f'<a href="#{a}" class="subnav-link">• {lbl}</a></div>'
                    for a, lbl in _secs
                )
                st.markdown(
                    f"<div style='background:#F2F5FA;border-left:3px solid #2E68B0;"
                    f"padding:6px 10px;margin:2px 0 10px 14px;border-radius:4px'>"
                    f"<span style='font-size:0.78em;color:#666'>📍 '{p.split(' ', 1)[-1]}' 안에서 이동</span>"
                    f"<div style='margin-top:4px'>{links}</div></div>",
                    unsafe_allow_html=True,
                )
    nav = sel
    st.session_state['nav'] = sel

    # ── 데이터 필터 ──
    st.markdown("---")
    st.caption("🔎 데이터 필터")
    선택_채널 = st.multiselect("📡 채널", ['SMS', 'LMS', 'MMS'], default=['SMS', 'LMS'])
    연도_옵션 = sorted(df_raw['연도'].dropna().unique().tolist(), reverse=True)
    선택_연도 = st.multiselect("📅 연도", 연도_옵션, default=연도_옵션)
    st.caption("데이터 기준: 발송일")


# ── 필터 적용 ──────────────────────────────────────────────
df = df_raw.copy()
if 선택_채널:
    df = df[df['채널'].isin(선택_채널)]
if 선택_연도:
    df = df[df['연도'].isin(선택_연도)]

df_with_perf = df.dropna(subset=['CTR', 'CR', 'ROAS'])
df_with_perf = df_with_perf[df_with_perf['ROAS'] > 0]


# ── KPI 요약 ──────────────────────────────────────────────
st.title("📱 문자 발송 성과 분석 대시보드")
st.markdown(f"**필터**: 채널: {', '.join(선택_채널) if 선택_채널 else '전체'} | 연도: {', '.join(map(str, 선택_연도)) if 선택_연도 else '전체'}")
st.markdown("---")

st.markdown('<div class="section-title">📊 전체 현황 요약</div>', unsafe_allow_html=True)
col1, col2, col3, col4, col5 = st.columns(5)
total_send = len(df)
total_reach = df['모수'].sum()
avg_ctr = w_avg(df_with_perf['CTR'], df_with_perf['모수'])
avg_cr = w_cr(df_with_perf)
avg_roas = pooled_roas(df_with_perf)

with col1:
    st.metric("총 발송 건수", f"{total_send:,}건")
with col2:
    st.metric("총 발송 모수", f"{total_reach/10000:.1f}만명" if total_reach > 10000 else f"{int(total_reach):,}명")
with col3:
    st.metric("전체 CTR", f"{avg_ctr:.1%}" if pd.notna(avg_ctr) else "-")
with col4:
    st.metric("전체 CR", f"{avg_cr:.1%}" if pd.notna(avg_cr) else "-")
with col5:
    st.metric("전체 ROAS", f"{avg_roas:.1f}%" if pd.notna(avg_roas) else "-")

st.caption("※ CTR·CR은 발송규모 가중평균, ROAS는 Σ거래액÷Σ비용(전체 풀링) 기준 — 캠페인 단순평균이 아닙니다.")
st.markdown("")


# ── 공통 상수 ──────────────────────────────────────────────
COLORS = {'SMS': '#4C72B0', 'LMS': '#DD8452', 'MMS': '#55A868'}

KW_CATEGORIES = {
    '개인화': ['고객명', '회원님', '고객님', '선생님', '귀하', 'VIP', '등급'],
    '행동기반': ['관심상품', '보셨던', '담으신', '담으셨던', '관심', '찜하신', '찜하셨던',
                '검색하신', '구매하신', '방문하신', '확인하신', '재입고'],
    '혜택/할인': ['할인', '쿠폰', '적립', '무료배송', '무료', '특가', '혜택', '증정',
                '사은품', '캐시백', '포인트', '이벤트', '프로모션', '추가할인'],
    '긴급/한정': ['마감임박', '마감', '한정', '마지막', '종료', '오늘까지', '종료임박', '품절', '선착순', '단', '오늘만'],
    '시즌': ['겨울', '여름', '봄', '가을', '블랙프라이데이', '블랙', '크리스마스', '설날', '추석', '신년', '연말', '시즌오프'],
}
CAT_COLORS = {
    '개인화': '#4C72B0', '행동기반': '#DD8452', '혜택/할인': '#55A868',
    '긴급/한정': '#C44E52', '시즌': '#8172B2', '상품/기타': '#aaaaaa'
}

# AF코드 → 캠페인 라벨 매핑. 매월 코드가 바뀌므로 '의미' 기준으로 묶어서 본다.
# 같은 라벨을 가진 코드(EV20·EV21=승급유도, EV22·EV23=반품미구매)는 자동으로 합쳐진다.
AF_MAP = {
    'EV00': 'VIP자동화_최근미방문',
    'EV01': '리텐션_미구매',
    'EV02': '리텐션_다건',
    'EV03': '리텐션_단건',
    'EV20': '승급유도',
    'EV21': '승급유도',
    'EV22': '반품미구매',
    'EV23': '반품미구매',
    'EV25': 'VIP자동화_멤버십쿠폰미사용',
    'EV28': '라이브_본방',
    'EV40': 'VIP라운지_핫딜',
    'EV42': '라이브_재방',
}
AF_FIXED = {'EV00', 'EV20', 'EV21', 'EV25'}  # 매월 동일(고정) 코드

# 표본이 너무 적은 구간(시간대·히트맵 셀)은 1건짜리 outlier가 효율을 왜곡하므로 제외
MIN_SLOT_N = 2
# 키워드 '효과'를 말하려면 최소 이 정도 표본은 있어야 함 (그 이하는 오퍼·타겟 교란이 더 큼)
MIN_KW_CASES = 5

def classify_keyword(kw):
    for cat, words in KW_CATEGORIES.items():
        if any(w in kw for w in words):
            return cat
    return '상품/기타'

def get_text_categories(text):
    cats = []
    for cat, words in KW_CATEGORIES.items():
        if any(w in str(text) for w in words):
            cats.append(cat)
    return cats if cats else ['상품/기타']

def extract_campaign_group(name):
    s = str(name)
    s = re.sub(r'^(MKT_|nBPU_|BPU_|NBPU_)', '', s, flags=re.IGNORECASE)
    s = re.sub(r'_\d{6}', '', s)
    s = re.sub(r'_(SMS|LMS|MMS)$', '', s, flags=re.IGNORECASE)
    s = s.strip('_')
    parts = [p for p in s.split('_') if p]
    return parts[0] if parts else s

MONEY_METRICS = {'총거래액', '캠페인당거래액', '1인당거래액', '객단가', '거래액', '평균거래액', '총비용'}

def fmt_val(v, metric):
    if pd.isna(v):
        return '-'
    if metric in ['평균CTR', '평균CR', 'CTR', 'CR']:
        return f"{v:.1%}"
    if metric in ['평균ROAS', 'ROAS', 'ROAS_리프트']:
        return f"{v:.1f}%"
    if metric in MONEY_METRICS:
        return fmt_won(v)
    return f"{v:,.0f}"


# ── 인사이트 생성 (현상 설명이 아니라 비교·시사점·액션) ──────────────────────────────
def insight_channel_compare(base, plot_df, x_col, metric, num_years):
    ch = perf_by(base, '채널').dropna(subset=[metric])
    if not len(ch):
        return "효율을 비교할 데이터가 부족합니다."
    ch = ch.sort_values(metric, ascending=False)
    top = ch.iloc[0]
    parts = []
    if len(ch) >= 2:
        bot = ch.iloc[-1]
        lead = f"**{top['채널']}**가 {metric} {fmt_val(top[metric], metric)}로 가장 효율적"
        if metric not in ['평균CTR', '평균CR'] and bot[metric]:
            lead += f" — {bot['채널']}({fmt_val(bot[metric], metric)})의 {top[metric]/bot[metric]:.1f}배"
        parts.append(lead + ".")
        vol = ch.sort_values('발송건수', ascending=False).iloc[0]
        if vol['채널'] != top['채널']:
            parts.append(
                f"그런데 발송량은 **{vol['채널']}**({vol['발송건수']:,}건)가 최다 → "
                f"예산·물량을 {top['채널']}로 일부 이전하면 같은 비용으로 거래액을 더 끌어올릴 여지."
            )
        else:
            parts.append(f"발송량·효율 모두 {top['채널']} 우위 → 핵심 채널로 집중 유지가 합리적.")
    else:
        parts.append(f"**{top['채널']}** {metric} {fmt_val(top[metric], metric)}.")
    sub = plot_df[plot_df['채널'] == top['채널']].dropna(subset=[metric])
    if len(sub) >= 2:
        d = sub.iloc[-1][metric] - sub.iloc[-2][metric]
        parts.append(
            f"{top['채널']}는 최근 {sub.iloc[-1][x_col]} 기준 직전 대비 "
            f"{'개선' if d > 0 else '둔화'}({fmt_val(abs(d), metric)}) — 추세 모니터링 필요."
        )
    return "  \n".join(parts)


def reallocation_gain(ch, share=0.2):
    """저효율 채널 모수의 일부를 고효율 채널로 옮길 때 기대 거래액 증가(동일 효율 가정)."""
    d = ch.dropna(subset=['1인당거래액', '총모수'])
    d = d[d['총모수'] > 0]
    if len(d) < 2:
        return None
    hi = d.loc[d['1인당거래액'].idxmax()]
    lo = d.loc[d['1인당거래액'].idxmin()]
    if hi['채널'] == lo['채널'] or hi['1인당거래액'] <= lo['1인당거래액']:
        return None
    move = share * lo['총모수']
    gain = move * (hi['1인당거래액'] - lo['1인당거래액'])
    total_rev = d['총거래액'].sum()
    pct = gain / total_rev * 100 if total_rev else 0
    return dict(lo=lo['채널'], hi=hi['채널'], move=move, gain=gain, pct=pct, share=share)


def insight_channel_table(ch):
    ch = ch.dropna(subset=['평균ROAS'])
    if not len(ch):
        return "데이터가 부족합니다."
    parts = []
    roas_lead = ch.loc[ch['평균ROAS'].idxmax()]
    parts.append(f"ROAS 1위 **{roas_lead['채널']}** ({roas_lead['평균ROAS']:.1f}%) — 투입 대비 회수 최고.")
    if ch['1인당거래액'].notna().any():
        per1 = ch.loc[ch['1인당거래액'].idxmax()]
        parts.append(f"1인당 거래액 1위 **{per1['채널']}** ({fmt_won(per1['1인당거래액'])}/타겟) — 모수 대비 매출 기여 최고.")
    r = reallocation_gain(ch)
    if r:
        parts.append(
            f"💡 **{r['lo']}** 발송모수의 {int(r['share']*100)}%({r['move']:,.0f}명)를 **{r['hi']}**로 이전하면 "
            f"같은 물량으로 거래액 약 **+{fmt_won(r['gain'])} (+{r['pct']:.1f}%)** 기대 (현재 효율 유지 가정)."
        )
    if len(ch) >= 2 and ch['평균CTR'].notna().any():
        ctr_lead = ch.loc[ch['평균CTR'].idxmax()]
        if ctr_lead['채널'] != roas_lead['채널']:
            parts.append(
                f"**{ctr_lead['채널']}**는 CTR(클릭 {ctr_lead['평균CTR']:.1%})은 최고지만 ROAS 1위는 아님 "
                f"→ 클릭이 구매로 덜 이어짐. 랜딩·오퍼·객단가 점검 포인트."
            )
    return "  \n".join(parts)


def insight_daily(daily, metric):
    d = daily.dropna(subset=[metric])
    if len(d) < 2:
        return "일자별 비교에 데이터가 부족합니다."
    hi, lo = d.loc[d[metric].idxmax()], d.loc[d[metric].idxmin()]
    ds = lambda x: pd.to_datetime(x).strftime('%m/%d')
    parts = [f"{metric} 최고일 **{ds(hi['발송일자'])}** ({fmt_val(hi[metric], metric)}), "
             f"최저일 **{ds(lo['발송일자'])}** ({fmt_val(lo[metric], metric)})."]
    if metric in ['평균ROAS', '1인당거래액', '평균CTR', '평균CR'] and d['발송건수'].nunique() > 1:
        corr = d[metric].corr(d['발송건수'])
        if pd.notna(corr):
            if corr < -0.3:
                parts.append("발송량이 많은 날일수록 효율이 낮아지는 경향 → 대량 발송 시 타겟 정밀도가 떨어지는지 점검.")
            elif corr > 0.3:
                parts.append("발송량이 많은 날 효율도 높음 → 물량 확대 여력 있음.")
            else:
                parts.append("효율과 발송량 간 뚜렷한 상관 없음 → 특정일 성과 차이는 캠페인 내용·타이밍 영향으로 해석.")
    return "  \n".join(parts)


def single_perf(g):
    """한 부분집합의 성과 지표 묶음 (비교용)."""
    sends = pd.to_numeric(g['모수'], errors='coerce').sum()
    rev = pd.to_numeric(g['거래액'], errors='coerce').sum()
    buyers = pd.to_numeric(g['고객수'], errors='coerce').sum() if '고객수' in g else np.nan
    return {
        '발송건수': len(g),
        '총모수': sends,
        '평균CTR': w_avg(g['CTR'], g['모수']),
        '평균CR': w_cr(g),
        '평균ROAS': pooled_roas(g),
        '1인당거래액': rev / sends if sends and sends > 0 else np.nan,
        '객단가': rev / buyers if buyers and buyers > 0 else np.nan,
        '총거래액': rev,
    }


def cmp_fmt(key, v):
    if pd.isna(v):
        return '-'
    if key in ('평균CTR', '평균CR'):
        return f"{v:.1%}"
    if key == '평균ROAS':
        return f"{v:,.0f}%"
    if key in MONEY_METRICS:
        return fmt_won(v)
    return f"{v:,.0f}"


def cmp_delta(key, va, vb):
    """A 기준 B 대비 차이 (st.metric delta용 문자열)."""
    if pd.isna(va) or pd.isna(vb):
        return None
    d = va - vb
    if key in ('평균CTR', '평균CR'):
        return f"{d:+.1%}p"
    if key == '평균ROAS':
        return f"{d:+,.0f}%p"
    if key in MONEY_METRICS:
        return ('+' if d >= 0 else '-') + fmt_won(abs(d))
    return f"{d:+,.0f}"


METRIC_META = {
    '평균ROAS': ('투입 대비 회수', 'eff'),
    '1인당거래액': ('타겟 1명당 매출', 'eff'),
    '객단가': ('구매고객 1명당 매출', 'eff'),
    '평균CTR': ('클릭률', 'eff'),
    '평균CR': ('구매 전환율', 'eff'),
    '총거래액': ('총 매출', 'scale'),
    '총모수': ('도달 규모', 'scale'),
    '발송건수': ('발송 횟수', 'scale'),
}

def metric_comment(k, va, vb, a, b):
    """지표 한 줄 코멘트 — 어느 쪽이 얼마나, 무슨 의미인지."""
    meaning, kind = METRIC_META.get(k, (k, 'eff'))
    if pd.isna(va) or pd.isna(vb):
        return "비교 불가(데이터 없음)"
    if va == vb:
        return f"동일 · {meaning}"
    win = a if va > vb else b
    hi, lo = max(va, vb), min(va, vb)
    if k in ('평균CTR', '평균CR'):
        mag = f"+{abs(va - vb):.1%}p"
    elif lo > 0:
        mag = f"{hi / lo:.1f}배"
    else:
        mag = f"{hi - lo:,.0f} 차"
    tail = " (규모 — 효율 아님)" if kind == 'scale' else ""
    return f"**{win}** {mag} · {meaning}{tail}"


def cmp_item_comment(mine, other):
    """비교 항목 하나의 성격을 한 줄로 — 상대 대비 강·약점과 규모."""
    eff = ['평균ROAS', '1인당거래액', '평균CTR', '평균CR']
    wins = [k for k in eff if pd.notna(mine[k]) and pd.notna(other[k]) and mine[k] > other[k]]
    losses = [k for k in eff if pd.notna(mine[k]) and pd.notna(other[k]) and mine[k] < other[k]]
    if len(wins) >= 3:
        head = "🟢 효율 우위형"
    elif len(losses) >= 3:
        head = "🔴 효율 열위형"
    else:
        head = "🟡 혼조형"
    reach = "도달 큼" if mine['총모수'] >= other['총모수'] else "도달 작음"
    # ROAS 배수 한마디
    extra = ""
    if pd.notna(mine['평균ROAS']) and pd.notna(other['평균ROAS']) and other['평균ROAS'] > 0:
        ratio = mine['평균ROAS'] / other['평균ROAS']
        if ratio >= 1.2:
            extra = f" · ROAS 상대 대비 {ratio:.1f}배"
        elif ratio <= 0.83:
            extra = f" · ROAS 상대의 {ratio:.0%} 수준"
    strong = "·".join(k.replace('평균', '') for k in wins[:3])
    weak = "·".join(k.replace('평균', '') for k in losses[:2])
    bits = [f"강점 {strong}" if wins else "", f"약점 {weak}" if losses else ""]
    bits = [x for x in bits if x]
    return f"{head} · {reach}{extra}" + (" — " + ", ".join(bits) if bits else "")


def build_keyword_perf(df_perf, keywords, min_cases=2):
    """키워드별 포함 vs 미포함 ROAS 리프트 테이블 (풀링 ROAS 기준)."""
    rows = []
    for kw, freq in keywords:
        mask = df_perf['문구'].str.contains(re.escape(kw), na=False)
        has, no = df_perf[mask], df_perf[~mask]
        if len(has) < min_cases or len(no) == 0:
            continue
        hr, nr = pooled_roas(has), pooled_roas(no)
        if pd.isna(hr) or pd.isna(nr):
            continue
        rows.append({'키워드': kw, '카테고리': classify_keyword(kw), '빈도': freq,
                     '포함건수': len(has), '포함_ROAS': hr, '미포함_ROAS': nr, 'ROAS리프트': hr - nr})
    return pd.DataFrame(rows)


def render_campaign_detail(sub, sort_col='ROAS'):
    """특정 구간(요일/시간/일자)에 보낸 개별 캠페인 상세 테이블."""
    cols = [c for c in ['발송일자', '채널', 'AF코드', '캠페인명', '모수', 'CTR', 'CR', 'ROAS', '거래액'] if c in sub.columns]
    s = sub[cols].copy()
    if sort_col in s.columns:
        s = s.sort_values(sort_col, ascending=False, na_position='last')
    if '발송일자' in s.columns:
        s['발송일자'] = pd.to_datetime(s['발송일자'], errors='coerce').dt.strftime('%m/%d')
    st.dataframe(
        s.style.format({
            'CTR': '{:.1%}', 'CR': '{:.1%}', 'ROAS': '{:.1f}%',
            '모수': '{:,.0f}', '거래액': fmt_won,
        }),
        use_container_width=True, hide_index=True
    )
    st.caption(f"{len(s)}건")


def mixed_chart(agg, x_col, perf_metric, vol_col='총모수', vol_label='총 발송모수'):
    """막대=물량(우축) + 선=효율지표(좌축) 혼합차트. 물량 때문인지 효율 때문인지 한눈에."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=agg[x_col], y=agg[vol_col], name=vol_label, marker_color='#d5d5d5', opacity=0.55),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=agg[x_col], y=agg[perf_metric], name=perf_metric, mode='lines+markers+text',
            text=agg[perf_metric].apply(lambda v: fmt_val(v, perf_metric)),
            textposition='top center', line=dict(color='#4C72B0', width=2.5),
        ),
        secondary_y=False,
    )
    fig.update_layout(height=400, xaxis_tickangle=-30, legend=dict(orientation='h', y=1.12))
    fig.update_yaxes(title_text=perf_metric, secondary_y=False)
    fig.update_yaxes(title_text=vol_label, secondary_y=True)
    if perf_metric in ['평균CTR', '평균CR']:
        fig.update_yaxes(tickformat='.1%', secondary_y=False)
    elif perf_metric in MONEY_METRICS:
        fig.update_yaxes(tickformat=',.0f', secondary_y=False)
    return fig


def insight_volume_perf(agg, x_col, metric, label_fmt):
    """효율 최고 구간이 '물량' 때문인지 '효율' 때문인지 구분해주는 인사이트."""
    d = agg.dropna(subset=[metric])
    if len(d) < 2:
        return "데이터가 부족합니다."
    hi, lo = d.loc[d[metric].idxmax()], d.loc[d[metric].idxmin()]
    parts = [f"{metric} 최고 **{label_fmt(hi[x_col])}** ({fmt_val(hi[metric], metric)}), "
             f"최저 **{label_fmt(lo[x_col])}** ({fmt_val(lo[metric], metric)})."]
    if metric not in ['평균CTR', '평균CR', '평균ROAS', '1인당거래액']:
        return "  \n".join(parts)
    vol_rank = int((d['총모수'] > hi['총모수']).sum()) + 1
    if hi['총모수'] == d['총모수'].max():
        parts.append(f"단, **{label_fmt(hi[x_col])}**은 발송모수도 최대 → 효율이 아니라 '물량'이 끌어올렸을 수 있음. "
                     f"순수 효율은 1인당거래액·ROAS로 교차확인 권장.")
    elif vol_rank > len(d) / 2:
        parts.append(f"**{label_fmt(hi[x_col])}**은 발송모수는 적은 편인데 {metric}는 최고 → 순수 효율 우위. "
                     f"이 타이밍 발송 비중 확대 검토.")
    else:
        parts.append("물량·효율이 함께 높은 구간 → 우선 발송 시점으로 활용.")
    # 정량 액션 — 최저 효율 구간 물량을 최고 효율 수준으로 옮기면?
    dd = d.dropna(subset=['1인당거래액', '총모수'])
    dd = dd[dd['총모수'] > 0]
    if len(dd) >= 2:
        b = dd.loc[dd['1인당거래액'].idxmax()]
        w = dd.loc[dd['1인당거래액'].idxmin()]
        gain = w['총모수'] * (b['1인당거래액'] - w['1인당거래액'])
        if b[x_col] != w[x_col] and gain > 0:
            parts.append(
                f"💡 최저 효율 **{label_fmt(w[x_col])}** 발송({w['총모수']:,.0f}명)을 최고 효율 "
                f"**{label_fmt(b[x_col])}**({fmt_won(b['1인당거래액'])}/타겟) 수준으로 옮기면 거래액 약 "
                f"**+{fmt_won(gain)}** 여지 (동일 효율 가정)."
            )
    return "  \n".join(parts)


# ── 페이지 라우팅 (사이드바 메뉴로 전환) ──────────────────────────────────────────────
# ══ 채널별 분석 ══════════════════════════════════
if nav == "📡 채널별 분석":

    # ── 채널별 효율 비교 (연도 2개↑: 전년비 / 1개: 월별) ──────────────────────────────────────────────
    num_years = df_with_perf['연도'].nunique()
    st.caption("총거래액은 발송량 많은 채널이 무조건 높아 효율 비교엔 부적합 → 1인당·캠페인당 거래액/ROAS로 비교  \n"
               "· **1인당거래액 = 거래액 ÷ 발송모수(타겟 수)** · **객단가 = 거래액 ÷ 구매고객수** · **캠페인당거래액 = 거래액 ÷ 발송건수**")
    cmp_metric = st.radio(
        "효율 지표",
        ['평균ROAS', '1인당거래액', '캠페인당거래액', '평균CTR', '평균CR'],
        horizontal=True, key='yoy_m'
    )

    if num_years >= 2:
        sec_title('채널 × 연도별 효율 비교 (전년비)', 'p1-compare')
        plot_df = perf_by(df_with_perf, ['연도', '채널'])
        plot_df['연도'] = plot_df['연도'].astype(str)
        x_col = '연도'
    else:
        sec_title('채널 × 월별 효율 비교', 'p1-compare')
        plot_df = perf_by(df_with_perf, ['월', '채널']).sort_values('월')
        x_col = '월'

    fig_cmp = px.line(
        plot_df, x=x_col, y=cmp_metric, color='채널',
        markers=True, color_discrete_map=COLORS,
        text=plot_df[cmp_metric].apply(lambda v: fmt_val(v, cmp_metric)),
        labels={x_col: '', cmp_metric: cmp_metric}
    )
    fig_cmp.update_traces(textposition='top center', mode='lines+markers+text')
    fig_cmp.update_layout(height=400, xaxis_tickangle=-30)
    if cmp_metric in ['평균CTR', '평균CR']:
        fig_cmp.update_yaxes(tickformat='.1%')
    elif cmp_metric in MONEY_METRICS:
        fig_cmp.update_yaxes(tickformat=',.0f')
    st.plotly_chart(fig_cmp, use_container_width=True)

    st.info(insight_channel_compare(df_with_perf, plot_df, x_col, cmp_metric, num_years))

    # ── 채널별 종합 성과 테이블 ──────────────────────────────────────────────
    sec_title('채널별 종합 성과', 'p1-summary')

    ch_perf = perf_by(df_with_perf, '채널')
    ch_show = ch_perf[['채널', '발송건수', '총모수', '평균CTR', '평균CR',
                       '평균ROAS', '캠페인당거래액', '1인당거래액', '총거래액']]
    st.dataframe(
        ch_show.style.format({
            '평균CTR': '{:.1%}', '평균CR': '{:.1%}', '평균ROAS': '{:.1f}%',
            '총모수': '{:,.0f}', '발송건수': '{:,}',
            '캠페인당거래액': fmt_won, '1인당거래액': fmt_won, '총거래액': fmt_won,
        }),
        use_container_width=True, hide_index=True
    )
    st.info(insight_channel_table(ch_perf))

    # ── 일자별 추이 (채널 분리) + 튀는 날 캠페인 드릴다운 ──────────────────────────────
    sec_title('일자별 효율 추이 (채널별)', 'p1-daily')
    day_metric = st.selectbox(
        "지표 선택",
        ['평균ROAS', '1인당거래액', '객단가', '평균CTR', '평균CR', '발송건수', '총모수'],
        key='daily_m'
    )
    daily_ch = perf_by(df_with_perf, ['발송일자', '채널']).sort_values('발송일자')
    daily_ch = daily_ch[pd.to_datetime(daily_ch['발송일자'], errors='coerce').notna()]
    fig_day = px.line(
        daily_ch, x='발송일자', y=day_metric, color='채널',
        color_discrete_map=COLORS, markers=True,
        labels={day_metric: day_metric, '발송일자': ''}
    )
    fig_day.update_layout(height=380)
    if day_metric in ['평균CTR', '평균CR']:
        fig_day.update_yaxes(tickformat='.1%')
    elif day_metric in MONEY_METRICS:
        fig_day.update_yaxes(tickformat=',.0f')
    st.plotly_chart(fig_day, use_container_width=True)

    daily_tot = perf_by(df_with_perf, '발송일자').sort_values('발송일자')
    daily_tot = daily_tot[pd.to_datetime(daily_tot['발송일자'], errors='coerce').notna()]
    st.info(insight_daily(daily_tot, day_metric))

    # 효율이 튀는 날 → 그날 어떤 캠페인/채널이었나
    with st.expander("📌 효율이 튀는 날 — 그날 보낸 캠페인 보기"):
        dd = daily_tot.dropna(subset=[day_metric])
        if len(dd) >= 2:
            hi_days = dd.nlargest(3, day_metric)['발송일자'].tolist()
            lo_days = dd.nsmallest(3, day_metric)['발송일자'].tolist()
            pick = st.radio("기준", ['최고일 Top3', '최저일 Bottom3'], horizontal=True, key='spike_pick')
            target_days = hi_days if pick.startswith('최고') else lo_days
            detail = df_with_perf[df_with_perf['발송일자'].isin(target_days)].copy()
            detail = detail.sort_values(['발송일자', 'ROAS'], ascending=[True, False])
            detail['일자'] = pd.to_datetime(detail['발송일자']).dt.strftime('%m/%d')
            show = detail[['일자', '채널', '캠페인명', '모수', 'CTR', 'CR', 'ROAS', '거래액']]
            st.dataframe(
                show.style.format({
                    'CTR': '{:.1%}', 'CR': '{:.1%}', 'ROAS': '{:.1f}%',
                    '모수': '{:,.0f}', '거래액': fmt_won,
                }),
                use_container_width=True, hide_index=True
            )
        else:
            st.caption("일자별 데이터가 부족합니다.")


# ══ 월별 트렌드 ══════════════════════════════════
elif nav == "📅 월별 트렌드":
    sec_title('월별 발송량 vs 효율 추이', 'p2-monthly')
    st.caption("회색 막대 = 총 발송모수(우축) / 파란 선 = 효율 지표(좌축)")

    monthly_total = perf_by(df_with_perf, '월').sort_values('월')

    mix_metric = st.selectbox(
        "성과 지표 선택",
        ['평균ROAS', '1인당거래액', '평균CTR', '평균CR'],
        key='mix_m'
    )
    st.plotly_chart(mixed_chart(monthly_total, '월', mix_metric), use_container_width=True)
    st.info(insight_volume_perf(monthly_total, '월', mix_metric, lambda x: f"{x}"))

    # ── 요일별 성과 (혼합: 막대=발송모수 / 선=효율) ──────────────────────────────
    sec_title('요일별 성과 (발송량 vs 효율)', 'p2-dow')
    st.caption("회색 막대 = 총 발송모수(물량) / 파란 선 = 효율 지표 — 주말이 높은 게 물량 때문인지 효율 때문인지 구분")

    요일순서 = ['월', '화', '수', '목', '금', '토', '일']
    df_dow = df_with_perf.dropna(subset=['요일'])
    if len(df_dow):
        dow_agg = perf_by(df_dow, '요일').set_index('요일').reindex(요일순서).reset_index()
        dow_metric = st.radio("요일별 효율 지표", ['평균ROAS', '1인당거래액', '평균CTR', '평균CR'], horizontal=True, key='dow_m')
        st.plotly_chart(mixed_chart(dow_agg, '요일', dow_metric), use_container_width=True)
        st.info(insight_volume_perf(dow_agg, '요일', dow_metric, lambda x: f"{x}요일"))
        with st.expander("📌 요일별 — 그 요일에 보낸 캠페인 보기"):
            dow_opts = [d for d in 요일순서 if d in df_dow['요일'].unique()]
            sel_dow = st.selectbox("요일 선택", dow_opts, key='dow_drill')
            render_campaign_detail(df_dow[df_dow['요일'] == sel_dow])

    # ── 시간대별 성과 (혼합) ──────────────────────────────────────────────
    df_hour = df_with_perf.dropna(subset=['시간'])
    if len(df_hour) and df_hour['시간'].nunique() > 1:
        sec_title('시간대별 성과 (발송량 vs 효율)', 'p2-hour')
        st.caption(f"발송 {MIN_SLOT_N}건 미만 시간대는 1건짜리 outlier 왜곡을 막기 위해 제외  \n"
                   "⚠️ 시간대 효율은 '그 시간 자체'가 아니라 '그 시간에 주로 보낸 캠페인 성격'과 섞여 있음 "
                   "(예: 10시=선착순 쿠폰). 아래 드릴다운으로 무엇을 보냈는지 확인 권장")
        hour_agg = perf_by(df_hour, '시간').sort_values('시간')
        hour_agg = hour_agg[hour_agg['발송건수'] >= MIN_SLOT_N]   # 표본 적은 시간대 제외
        hour_agg['시간'] = hour_agg['시간'].apply(lambda h: f"{int(h)}시")
        hour_metric = st.radio("시간대별 효율 지표", ['평균ROAS', '1인당거래액', '평균CTR', '평균CR'], horizontal=True, key='hour_m')
        st.plotly_chart(mixed_chart(hour_agg, '시간', hour_metric), use_container_width=True)
        st.info(insight_volume_perf(hour_agg, '시간', hour_metric, lambda x: f"{x}"))
        with st.expander("📌 시간대별 — 그 시간에 보낸 캠페인 보기 (효율 교란 확인용)"):
            hr_opts = sorted(int(h) for h in df_hour['시간'].dropna().unique())
            sel_hr = st.selectbox("시간 선택", hr_opts, format_func=lambda h: f"{h}시", key='hour_drill')
            render_campaign_detail(df_hour[df_hour['시간'] == sel_hr])
    else:
        st.caption("발송일자에 시간 정보가 없어 시간대별 분석을 표시할 수 없어요.")

    # ── 요일 × 시간대 효율 히트맵 ──────────────────────────────────────────────
    df_dh = df_with_perf.dropna(subset=['요일', '시간'])
    if len(df_dh) and df_dh['시간'].nunique() > 1 and df_dh['요일'].nunique() > 1:
        sec_title('시간대 × 요일 효율 히트맵', 'p2-heat')
        st.caption(f"행 = 발송시간 · 열 = 요일 · 색이 진할수록 효율 높음 (발송 {MIN_SLOT_N}건 미만 셀은 표본 부족으로 제외)")
        heat_metric = st.radio("히트맵 지표", ['평균ROAS', '1인당거래액', '평균CTR', '평균CR'], horizontal=True, key='heat_m')
        dh = perf_by(df_dh, ['요일', '시간'])
        dh['시간'] = dh['시간'].astype(int)
        dh.loc[dh['발송건수'] < MIN_SLOT_N, heat_metric] = np.nan   # 표본 적은 셀 제외
        pivot = dh.pivot(index='시간', columns='요일', values=heat_metric)
        pivot = pivot.reindex(sorted(pivot.index))                       # 행: 시간 오름차순
        pivot = pivot.reindex([d for d in 요일순서 if d in pivot.columns], axis=1)  # 열: 월~일
        txt = pivot.copy()
        for c in txt.columns:
            txt[c] = txt[c].map(lambda v: fmt_val(v, heat_metric) if pd.notna(v) else '')
        fig_heat = px.imshow(
            pivot, color_continuous_scale='Blues', aspect='auto',
            labels=dict(x='', y='발송 시간(시)', color=heat_metric),
        )
        fig_heat.update_traces(text=txt.values, texttemplate='%{text}', textfont_size=10)
        fig_heat.update_xaxes(side='top')
        fig_heat.update_yaxes(dtick=1)
        fig_heat.update_layout(height=max(360, pivot.shape[0] * 34), coloraxis_showscale=True)
        st.plotly_chart(fig_heat, use_container_width=True)
        bc_df = dh.dropna(subset=[heat_metric])
        if len(bc_df):
            bc = bc_df.loc[bc_df[heat_metric].idxmax()]
            st.info(
                f"가장 효율 높은 슬롯: **{bc['요일']}요일 {int(bc['시간'])}시** "
                f"({fmt_val(bc[heat_metric], heat_metric)}, 발송 {int(bc['발송건수'])}건) "
                f"→ 핵심 캠페인을 이 슬롯에 우선 배치 검토."
            )


# ══ 문구 키워드 분석 ══════════════════════════════════
elif nav == "🔤 문구 키워드 분석":
    col_a, col_b = st.columns(2)
    with col_a:
        분석채널 = st.selectbox("채널", ['전체'] + sorted(df['채널'].dropna().unique().tolist()), key='kw_ch')
    with col_b:
        top_n = st.slider("키워드 수", 10, 50, 25)

    df_kw = df.copy()
    if 분석채널 != '전체':
        df_kw = df_kw[df_kw['채널'] == 분석채널]
    # EV40(VIP라운지 핫딜)은 고정 포맷에 브랜드·상품만 갈아끼우는 템플릿이라 문구 키워드 분석에서 제외
    excluded_ev40 = 0
    if 'AF코드' in df_kw.columns:
        ev40_mask = df_kw['AF코드'].astype(str).str.strip().str.upper() == 'EV40'
        excluded_ev40 = int(ev40_mask.sum())
        df_kw = df_kw[~ev40_mask]
    if excluded_ev40:
        st.caption(f"※ EV40(VIP핫딜) {excluded_ev40}건은 템플릿 포맷이라 키워드 분석에서 제외됨")
    df_kw_perf = df_kw.dropna(subset=['CTR', 'CR', 'ROAS', '문구'])
    df_kw_perf = df_kw_perf[df_kw_perf['ROAS'] > 0]

    # 키워드 추출 + 키워드별 성과(리프트)를 한 번만 계산해 여러 섹션에서 재사용
    kw_all = extract_keywords(df_kw['문구'].tolist(), top_n=top_n)
    kw_perf_all = build_keyword_perf(df_kw_perf, kw_all, min_cases=2) if kw_all else pd.DataFrame()

    # ── 1. 카테고리별 평균 성과 (가장 먼저, 크게) ──────────────────────────────────────────────
    sec_title('카테고리별 평균 성과', 'p3-cat')
    st.caption("문구에 해당 카테고리 키워드가 포함된 캠페인의 평균 실적 — 어떤 문구 유형이 성과를 올리는지 파악")

    cat_rows = []
    for _, row in df_kw_perf.iterrows():
        for cat in get_text_categories(row['문구']):
            cat_rows.append({
                '카테고리': cat, 'CTR': row['CTR'], 'CR': row['CR'], 'ROAS': row['ROAS'],
                '모수': row['모수'], 'UV': row['UV'], '거래액': row['거래액'],
            })

    if cat_rows:
        cat_perf_df = pd.DataFrame(cat_rows)
        cat_agg = perf_by(cat_perf_df, '카테고리').rename(columns={'캠페인건수': '캠페인수'})[
            ['카테고리', '캠페인수', '평균CTR', '평균CR', '평균ROAS']
        ]

        cat_metric = st.radio("비교 지표", ['평균ROAS', '평균CTR', '평균CR'], horizontal=True, key='cat_m')
        cat_sorted = cat_agg.sort_values(cat_metric, ascending=False)

        fig_cat = px.bar(
            cat_sorted, x='카테고리', y=cat_metric, color='카테고리',
            color_discrete_map=CAT_COLORS,
            text=cat_sorted[cat_metric].apply(lambda v: fmt_val(v, cat_metric)),
            hover_data={'캠페인수': True},
        )
        fig_cat.update_traces(textposition='outside')
        fig_cat.update_layout(height=420, showlegend=False)
        if cat_metric in ['평균CTR', '평균CR']:
            fig_cat.update_yaxes(tickformat='.1%')
        st.plotly_chart(fig_cat, use_container_width=True)

        best_cat = cat_agg.loc[cat_agg[cat_metric].idxmax()]
        worst_cat = cat_agg.loc[cat_agg[cat_metric].idxmin()]
        st.info(
            f"**{cat_metric} 1위: {best_cat['카테고리']}** ({fmt_val(best_cat[cat_metric], cat_metric)}, {best_cat['캠페인수']:.0f}건)  \n"
            f"→ 문구에 **{best_cat['카테고리']}** 요소를 넣으면 성과가 높은 경향이 있어요.  \n"
            f"가장 낮은 카테고리: **{worst_cat['카테고리']}** ({fmt_val(worst_cat[cat_metric], cat_metric)}, {worst_cat['캠페인수']:.0f}건)"
        )

        with st.expander("카테고리별 상세 수치"):
            st.dataframe(cat_agg.style.format({
                '평균CTR': '{:.1%}', '평균CR': '{:.1%}', '평균ROAS': '{:.1f}%', '캠페인수': '{:.0f}'
            }), use_container_width=True, hide_index=True)

        with st.expander("🔎 카테고리 안에서 어떤 키워드/캠페인이 성과를 만들었는지 보기"):
            cat_pick = st.selectbox("카테고리 선택", cat_agg['카테고리'].tolist(), key='cat_kw_pick')
            # 카테고리 평균성과와 동일 기준 — 그 카테고리로 분류된 캠페인을 직접 사용
            cat_mask = df_kw_perf['문구'].apply(lambda t: cat_pick in get_text_categories(t))
            cat_campaigns = df_kw_perf[cat_mask]
            st.caption(f"'{cat_pick}' 분류 캠페인 {len(cat_campaigns)}건 (위 카테고리 평균성과와 동일 집합)")

            # 카테고리 정의 단어별 성과 (실제 문구에 등장한 것만)
            words = KW_CATEGORIES.get(cat_pick, [])
            wrows = []
            for w in words:
                m = df_kw_perf['문구'].str.contains(re.escape(w), na=False)
                has, no = df_kw_perf[m], df_kw_perf[~m]
                if len(has) == 0:
                    continue
                hr, nr = pooled_roas(has), pooled_roas(no)
                wrows.append({'키워드': w, '포함건수': len(has),
                              '표본': '충분' if len(has) >= MIN_KW_CASES else '부족(참고만)',
                              '포함_ROAS': hr,
                              'ROAS리프트': (hr - nr) if (pd.notna(hr) and pd.notna(nr)) else np.nan})
            if wrows:
                wdf = pd.DataFrame(wrows).sort_values('포함건수', ascending=False)
                st.markdown("**카테고리 정의 단어별 등장·ROAS** (포함건수 순)")
                st.caption(f"⚠️ 포함 {MIN_KW_CASES}건 미만('부족')은 그 캠페인의 오퍼·타겟 영향이 더 커서 "
                           "키워드 효과로 단정 불가 — 예: 99% 할인 1건에 우연히 들어간 단어도 ROAS가 높게 찍힘")
                st.dataframe(
                    wdf.style.format({'포함_ROAS': '{:,.0f}%', 'ROAS리프트': '{:+,.0f}%p', '포함건수': '{:,}'}),
                    use_container_width=True, hide_index=True
                )
            elif cat_pick != '상품/기타':
                st.caption("이 카테고리 정의 단어가 실제 문구에 등장하지 않았어요. (분류는 다른 단어로 됐을 수 있음)")

            # 실제 캠페인 직접 확인 — 유효성 판단용
            if len(cat_campaigns):
                st.markdown(f"**'{cat_pick}' 분류 캠페인 (ROAS순)**")
                render_campaign_detail(cat_campaigns)

    # ── 2. 키워드 빈도 ──────────────────────────────────────────────
    sec_title('키워드 빈도 (카테고리별 색상)', 'p3-freq')
    st.caption("개인화([고객명]·고객님)는 거의 모든 문구에 공통 포함돼 변별력이 없어 빈도에서 제외 — 위 카테고리 성과로 확인")

    if kw_all:
        kw_df = pd.DataFrame(kw_all, columns=['키워드', '빈도'])
        kw_df['카테고리'] = kw_df['키워드'].apply(classify_keyword)

        cat_options = ['전체'] + sorted(kw_df['카테고리'].unique().tolist())
        선택_카테고리 = st.selectbox("카테고리 필터", cat_options, key='kw_cat')
        kw_df_view = kw_df if 선택_카테고리 == '전체' else kw_df[kw_df['카테고리'] == 선택_카테고리]

        fig_kw = px.bar(
            kw_df_view.sort_values('빈도'), x='빈도', y='키워드', orientation='h',
            color='카테고리', color_discrete_map=CAT_COLORS, text='빈도'
        )
        fig_kw.update_layout(height=max(400, len(kw_df_view) * 22), yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig_kw, use_container_width=True)

        with st.expander("카테고리 기준 보기"):
            for cat, words in KW_CATEGORIES.items():
                st.markdown(f"**{cat}**: {', '.join(words)}")
            st.markdown("**상품/기타**: 위 분류에 해당하지 않는 상품명·소재명 등")

    # ── 3. 키워드별 성과 리프트 ──────────────────────────────────────────────
    sec_title('ROAS와 함께 등장하는 키워드 (상관, 인과 아님)', 'p3-lift')
    st.caption(f"키워드 포함 vs 미포함 캠페인의 ROAS 차이(%p) · 포함 {MIN_KW_CASES}건 이상만.  \n"
               "⚠️ 이건 '효과'가 아니라 '상관'입니다 — 키워드가 ROAS를 올린 게 아니라, 그 키워드를 주로 쓰는 "
               "캠페인의 오퍼·타겟이 ROAS를 좌우했을 가능성이 큼. 단정 말고 가설로만 활용하세요.")

    if kw_all and len(kw_perf_all):
        kw_perf_df = kw_perf_all[kw_perf_all['포함건수'] >= MIN_KW_CASES].sort_values('ROAS리프트', ascending=False)
        if len(kw_perf_df):
            N = 8
            top = kw_perf_df.head(N)
            bot = kw_perf_df.tail(N)
            show = pd.concat([top, bot]).drop_duplicates('키워드').sort_values('ROAS리프트')
            show['색'] = np.where(show['ROAS리프트'] >= 0, '성과↑', '성과↓')

            fig_lift = px.bar(
                show, x='ROAS리프트', y='키워드', orientation='h',
                color='색', color_discrete_map={'성과↑': '#3C8C5A', '성과↓': '#C0504D'},
                text=show['ROAS리프트'].apply(lambda v: f"{v:+,.0f}%p"),
                hover_data={'포함건수': True, '포함_ROAS': ':,.0f', '미포함_ROAS': ':,.0f', '색': False},
            )
            fig_lift.add_vline(x=0, line_color='#888')
            fig_lift.update_traces(textposition='outside', cliponaxis=False)
            fig_lift.update_layout(
                height=max(420, len(show) * 30), yaxis={'categoryorder': 'total ascending'},
                legend_title_text='', xaxis_title='ROAS 리프트 (%p)', yaxis_title='',
                margin=dict(l=10, r=60),
            )
            st.plotly_chart(fig_lift, use_container_width=True)

            t = kw_perf_df.iloc[0]
            b = kw_perf_df.iloc[-1]
            st.info(
                f"**'{t['키워드']}'**({t['카테고리']}, {t['포함건수']}건)가 들어간 캠페인은 ROAS가 평균 대비 "
                f"**{t['ROAS리프트']:+,.0f}%p** 높게 '관찰'됨 → 다만 인과는 아님. 예시 문구로 어떤 오퍼와 함께 쓰였는지 확인 후 가설로.  \n"
                f"**'{b['키워드']}'**({b['포함건수']}건)는 ROAS가 **{b['ROAS리프트']:+,.0f}%p**로 낮게 관찰 → "
                f"키워드 탓이 아니라 저관여 캠페인에 주로 쓰였을 가능성. 예시 문구 확인 권장."
            )

            with st.expander("키워드별 상세 수치"):
                st.dataframe(
                    kw_perf_df[['키워드', '카테고리', '포함건수', '포함_ROAS', '미포함_ROAS', 'ROAS리프트']].style.format({
                        '포함_ROAS': '{:,.0f}%', '미포함_ROAS': '{:,.0f}%', 'ROAS리프트': '{:+,.0f}%p',
                    }),
                    use_container_width=True, hide_index=True
                )

            with st.expander("📝 키워드 예시 문구 보기 (왜 성과를 올리/깎는지 납득)"):
                kw_pick = st.selectbox("키워드 선택", kw_perf_df['키워드'].tolist(), key='kw_example')
                row = kw_perf_df[kw_perf_df['키워드'] == kw_pick].iloc[0]
                st.caption(
                    f"'{kw_pick}' 포함 {int(row['포함건수'])}건 — 포함 ROAS {row['포함_ROAS']:,.0f}% vs "
                    f"미포함 {row['미포함_ROAS']:,.0f}% (리프트 {row['ROAS리프트']:+,.0f}%p)"
                )
                ex = df_kw_perf[df_kw_perf['문구'].str.contains(re.escape(kw_pick), na=False)].copy()
                ex_show = ex[['채널', '캠페인명', 'ROAS', '거래액', '문구']].sort_values('ROAS', ascending=False)
                ex_show['문구'] = ex_show['문구'].astype(str).str.slice(0, 90)
                st.dataframe(
                    ex_show.style.format({'ROAS': '{:.0f}%', '거래액': fmt_won}),
                    use_container_width=True, hide_index=True
                )
                st.caption("ROAS 높은 순. 실제 문구를 보면 이 키워드가 어떤 맥락에서 쓰였는지(예: 저관여 캠페인에 주로 등장) 확인됩니다.")
        else:
            st.caption(f"포함 {MIN_KW_CASES}건 이상인 키워드가 부족해 리프트를 표시할 수 없어요.")

    # ── 4. 문구 진단기 (입력 → 예상 효율 + 키워드 코멘트) ──────────────────────────────
    sec_title('✍️ 문구 진단 — 입력하면 예상 효율 + 키워드 코멘트', 'p3-diag')
    st.caption("과거 발송 데이터 기반 '예상'(상관)이지 보장은 아닙니다. 표본 적은 키워드는 참고만.")
    diag_txt = st.text_area("진단할 문구 입력", key='diag_txt', height=90,
                            placeholder="예: (광고)[LF몰] 겨울 시즌오프 단 3일 최대 50% 할인 쿠폰 ▷ 지금 확인")
    if diag_txt.strip():
        base_ctr = w_avg(df_kw_perf['CTR'], df_kw_perf['모수'])
        base_cr = w_cr(df_kw_perf)
        base_roas = pooled_roas(df_kw_perf)

        def _band(v, base):
            if pd.isna(v) or pd.isna(base) or base == 0:
                return '데이터 없음'
            r = v / base
            return '높은 편 ▲' if r >= 1.15 else ('낮은 편 ▼' if r <= 0.87 else '보통 —')

        # 개인화([고객명])는 거의 모든 문구에 들어가 변별력이 없음 → 유사도 기준에서 제외
        cats_all = get_text_categories(diag_txt)
        cats = [c for c in cats_all if c not in ('상품/기타', '개인화')]
        if cats:
            sim = df_kw_perf[df_kw_perf['문구'].apply(lambda t: any(c in get_text_categories(t) for c in cats))]
            basis = f"'{', '.join(cats)}' 포함 과거 문구 {len(sim):,}건 기준"
        else:
            sim = df_kw_perf
            basis = f"변별 카테고리 없음(개인화·상품명 위주) → 전체 {len(sim):,}건 평균 기준"
        exp_ctr, exp_cr, exp_roas = w_avg(sim['CTR'], sim['모수']), w_cr(sim), pooled_roas(sim)

        shown_cats = [c for c in cats_all if c != '상품/기타']
        st.markdown("**감지 카테고리:** " + (
            " ".join(f"`{c}`" + ("(변별X)" if c == '개인화' else "") for c in shown_cats)
            if shown_cats else "특이 카테고리 없음(일반 문구)"))
        d1, d2, d3 = st.columns(3)
        d1.metric("예상 CTR", f"{exp_ctr:.1%}" if pd.notna(exp_ctr) else '-', _band(exp_ctr, base_ctr), delta_color="off")
        d2.metric("예상 CR", f"{exp_cr:.1%}" if pd.notna(exp_cr) else '-', _band(exp_cr, base_cr), delta_color="off")
        d3.metric("예상 ROAS", f"{exp_roas:,.0f}%" if pd.notna(exp_roas) else '-', _band(exp_roas, base_roas), delta_color="off")
        st.caption(f"{basis} · 전체 평균 CTR {base_ctr:.1%} / ROAS {base_roas:,.0f}%")

        cand = set()
        for ws in KW_CATEGORIES.values():
            cand.update(ws)
        if len(kw_perf_all):
            cand.update(kw_perf_all['키워드'].tolist())
        present = sorted({w for w in cand if w and w in diag_txt}, key=lambda x: -len(x))
        krows = []
        for w in present:
            has = df_kw_perf[df_kw_perf['문구'].str.contains(re.escape(w), na=False)]
            if len(has) == 0:
                continue
            krows.append({
                '키워드': w, '카테고리': classify_keyword(w), '과거이력': len(has),
                'CTR 영향': _band(w_avg(has['CTR'], has['모수']), base_ctr),
                'ROAS 영향': _band(pooled_roas(has), base_roas),
                '표본': '충분' if len(has) >= MIN_KW_CASES else '부족(참고)',
            })
        if krows:
            st.markdown("**입력 문구 속 키워드별 예상 영향** (과거 이 키워드가 든 캠페인 기준)")
            st.dataframe(pd.DataFrame(krows), use_container_width=True, hide_index=True)
            st.caption("⚠️ '영향'은 인과가 아니라 과거 상관. 표본 '부족'은 그 캠페인 오퍼·타겟 탓일 수 있으니 참고만.")
        else:
            st.caption("과거 데이터에 매칭되는 키워드가 없어요. (신규 표현이거나 상품명 위주 문구)")


# ══ 캠페인 상세 ══════════════════════════════════
elif nav == "🗂 캠페인 상세":
    sec_title('캠페인별 상세 데이터', 'p4-table')

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search = st.text_input("🔍 캠페인명 / 요청부서 검색", "")
    with col2:
        sort_by = st.selectbox("정렬 기준", ['ROAS', 'CTR', 'CR', '발송일자', '모수'])
    with col3:
        sort_asc = st.checkbox("오름차순", value=False)

    all_display_cols = ['발송일자', '출처', '채널', '요청부서', '캠페인명', '모수', 'CTR', 'CR', 'ROAS', '거래액', '문구']
    display_cols = [c for c in all_display_cols if c in df.columns]
    df_detail = df[display_cols].copy()

    if search:
        mask = df_detail['캠페인명'].str.contains(search, na=False, case=False)
        if '요청부서' in df_detail.columns:
            mask |= df_detail['요청부서'].str.contains(search, na=False, case=False)
        df_detail = df_detail[mask]

    df_detail = df_detail.sort_values(sort_by, ascending=sort_asc, na_position='last')
    df_detail['문구_미리보기'] = df_detail['문구'].str[:60] + '...'

    st.dataframe(
        df_detail.drop(columns=['문구']).rename(columns={'문구_미리보기': '문구(미리보기)'}).style.format({
            'CTR': lambda x: f"{x:.1%}" if pd.notna(x) else '-',
            'CR': lambda x: f"{x:.1%}" if pd.notna(x) else '-',
            'ROAS': lambda x: f"{x:.1f}%" if pd.notna(x) else '-',
            '모수': lambda x: f"{int(x):,}" if pd.notna(x) else '-',
            '거래액': lambda x: f"{int(x):,}" if pd.notna(x) else '-',
        }),
        use_container_width=True, height=450, hide_index=True
    )

    if st.checkbox("선택한 행 문구 전체 보기"):
        idx = st.number_input("행 번호 (0부터)", min_value=0, max_value=max(len(df_detail)-1, 0), value=0)
        row = df_detail.iloc[idx]
        st.markdown(f"**캠페인명**: {row['캠페인명']}")
        st.text_area("문구 전문", value=row['문구'], height=200)

    st.caption(f"총 {len(df_detail):,}건 | CTR·CR·ROAS는 성과 데이터가 있는 건만 표시")

    # ── 반복 캠페인 성과 추이 (연도 2개↑: 전년비 / 1개: 월별) ──────────────────
    df['캠페인그룹'] = df['캠페인명'].apply(extract_campaign_group)
    df_rec_base = df_with_perf.copy()
    df_rec_base['캠페인그룹'] = df_rec_base['캠페인명'].apply(extract_campaign_group)

    num_years_rec = df_rec_base['연도'].nunique()

    if num_years_rec >= 2:
        sec_title('🔁 반복 캠페인 연도별 전년비', 'p4-recurring')
        st.caption("핵심 키워드 기준 그룹핑 | 2개 이상 연도에 걸쳐 발송된 캠페인만 표시")
        group_yr_counts = df_rec_base.groupby('캠페인그룹')['연도'].nunique()
        recurring_groups = sorted(group_yr_counts[group_yr_counts >= 2].index.tolist())
        x_col_rec = '연도'
    else:
        sec_title('🔁 반복 캠페인 월별 성과 추이', 'p4-recurring')
        st.caption("핵심 키워드 기준 그룹핑 | 2개월 이상 발송된 캠페인만 표시")
        group_mo_counts = df_rec_base.groupby('캠페인그룹')['월'].nunique()
        recurring_groups = sorted(group_mo_counts[group_mo_counts >= 2].index.tolist())
        x_col_rec = '월'

    if recurring_groups:
        selected_group = st.selectbox("캠페인 그룹 선택", recurring_groups, key='rec_group')
        df_rec = df_rec_base[df_rec_base['캠페인그룹'] == selected_group]

        rec_agg = perf_by(df_rec, x_col_rec)
        if x_col_rec == '연도':
            rec_agg['연도'] = rec_agg['연도'].astype(str)
        else:
            rec_agg = rec_agg.sort_values('월')

        metric_rec = st.radio("지표", ['평균ROAS', '평균CTR', '평균CR', '총거래액', '발송건수'], horizontal=True, key='rec_metric')
        fig_rec = px.line(
            rec_agg, x=x_col_rec, y=metric_rec, markers=True,
            text=rec_agg[metric_rec].apply(lambda v: fmt_val(v, metric_rec)),
            labels={x_col_rec: '', metric_rec: metric_rec}
        )
        fig_rec.update_traces(mode='lines+markers+text', textposition='top center', line=dict(color='#4C72B0', width=2))
        fig_rec.update_layout(height=380, xaxis_tickangle=-30)
        if metric_rec in ['평균CTR', '평균CR']:
            fig_rec.update_yaxes(tickformat='.1%')
        elif metric_rec in MONEY_METRICS:
            fig_rec.update_yaxes(tickformat=',.0f')
        st.plotly_chart(fig_rec, use_container_width=True)

        # 인사이트
        periods = sorted(rec_agg[x_col_rec].unique())
        if len(periods) >= 2:
            prev_v = rec_agg[rec_agg[x_col_rec] == periods[-2]][metric_rec].values[0]
            curr_v = rec_agg[rec_agg[x_col_rec] == periods[-1]][metric_rec].values[0]
            diff = curr_v - prev_v
            st.info(
                f"**'{selected_group}'** {periods[-2]}→{periods[-1]} {'↑' if diff>0 else '↓'}  \n"
                f"{metric_rec}: {fmt_val(prev_v, metric_rec)} → {fmt_val(curr_v, metric_rec)} "
                f"({'+' if diff>0 else ''}{fmt_val(diff, metric_rec)} 변동)"
            )

        label = '연도별' if x_col_rec == '연도' else '월별'
        unit = '연도' if x_col_rec == '연도' else '월'
        with st.expander(f"'{selected_group}' {label} 상세 + 캠페인 드릴다운", expanded=False):
            rec_show = rec_agg[[x_col_rec, '발송건수', '평균모수', '평균CTR', '평균CR',
                                '평균ROAS', '1인당거래액', '총거래액']]
            st.dataframe(rec_show.style.format({
                '평균CTR': '{:.1%}', '평균CR': '{:.1%}', '평균ROAS': '{:.1f}%',
                '총거래액': fmt_won, '1인당거래액': fmt_won, '평균모수': '{:,.0f}', '발송건수': '{:,}',
            }), use_container_width=True, hide_index=True)

            # 하위 뎁스 — 선택한 기간에 실제로 보낸 개별 캠페인
            st.markdown(f"**↳ {unit} 선택 시 그 {unit}에 보낸 '{selected_group}' 캠페인 상세**")
            period_opts = rec_show[x_col_rec].astype(str).tolist()
            sel_period = st.selectbox(f"{unit} 선택", period_opts, key='rec_period')
            sub = df_rec.copy()
            if x_col_rec == '연도':
                sub = sub[sub['연도'].astype(str) == str(sel_period)]
            else:
                sub = sub[sub['월'].astype(str) == str(sel_period)]
            sub = sub.sort_values('발송일자')
            detail_cols = [c for c in ['발송일자', '채널', '캠페인명', '모수', 'CTR', 'CR', 'ROAS', '거래액', '문구'] if c in sub.columns]
            sub_show = sub[detail_cols].copy()
            if '발송일자' in sub_show.columns:
                sub_show['발송일자'] = pd.to_datetime(sub_show['발송일자'], errors='coerce').dt.strftime('%Y-%m-%d')
            st.dataframe(
                sub_show.style.format({
                    'CTR': '{:.1%}', 'CR': '{:.1%}', 'ROAS': '{:.1f}%',
                    '모수': '{:,.0f}', '거래액': fmt_won,
                }),
                use_container_width=True, hide_index=True
            )
            st.caption(f"{sel_period} '{selected_group}' 발송 {len(sub_show)}건")
    else:
        msg = "2개 이상 연도에" if num_years_rec >= 2 else "2개월 이상"
        st.info(f"{msg} 걸쳐 발송된 반복 캠페인 그룹이 없습니다.")


# ══ AF코드별 효율 ══════════════════════════════════
elif nav == "🏷 AF코드별 효율":
    sec_title('AF코드별 효율 비교', 'p5-eff')

    # 제공된 고정 AF코드(AF_MAP)만 집계. 같은 캠페인명 코드(EV20·EV21=승급유도)는 묶는다.
    has_af = 'AF코드' in df.columns and df['AF코드'].notna().any()
    if has_af:
        raw = df['AF코드'].astype(str).str.strip().str.upper()
        raw = raw.where(raw.isin(list(AF_MAP)))   # 고정 코드만, 나머지는 결측 처리(제외)
        df['_AF원본'] = raw
        df['_분석코드'] = raw.map(lambda c: AF_MAP.get(c) if pd.notna(c) else np.nan)
    else:
        df['_AF원본'] = np.nan
        df['_분석코드'] = np.nan
    st.caption("※ 제공된 고정 AF코드만 집계 (EV00~EV42). 같은 캠페인 코드(EV20·EV21=승급유도 등)는 묶어서 표시  \n"
               "· 표기: **AF코드(캠페인명)** · 1인당거래액 = 거래액÷발송모수 · ROAS = Σ거래액÷Σ비용")

    base = df_with_perf.copy()
    base['_분석코드'] = df.loc[base.index, '_분석코드']
    base['_AF원본'] = df.loc[base.index, '_AF원본']
    base = base.dropna(subset=['_분석코드'])

    if not has_af:
        st.info("AF코드 열이 없어 집계할 수 없어요. 파일에 'AF코드' 열을 추가해주세요.")
    elif not len(base):
        st.info("고정 AF코드(EV00~EV42)에 해당하는 성과 데이터가 없습니다.")
    else:
        # 코드 정렬 키 (EV00, EV01 … 순)
        code_rows = []
        for label, g in base.groupby('_분석코드'):
            sends = pd.to_numeric(g['모수'], errors='coerce').sum()
            rev = pd.to_numeric(g['거래액'], errors='coerce').sum()
            codes = sorted(set(g['_AF원본'].dropna().astype(str)))
            disp = f"{'·'.join(codes)}({label})"
            code_rows.append({
                '캠페인': disp,
                '코드': ', '.join(codes),
                '발송횟수': len(g),
                '총모수': sends,
                '총거래액': rev,
                '1인당거래액': rev / sends if sends and sends > 0 else np.nan,
                '객단가': rev / pd.to_numeric(g['고객수'], errors='coerce').sum()
                          if pd.to_numeric(g['고객수'], errors='coerce').sum() > 0 else np.nan,
                '평균CTR': w_avg(g['CTR'], g['모수']),
                '평균CR': w_cr(g),
                '평균ROAS': pooled_roas(g),
            })
        code_df = pd.DataFrame(code_rows)

        eff_metric = st.radio(
            "효율 지표",
            ['평균ROAS', '1인당거래액', '객단가', '총거래액', '평균CTR', '평균CR'],
            horizontal=True, key='af_metric'
        )
        top_n_af = st.slider("표시할 캠페인 수 (상위)", 5, 40, max(5, min(15, len(code_df))), key='af_topn')
        code_sorted = code_df.sort_values(eff_metric, ascending=False).head(top_n_af).sort_values(eff_metric)

        fig_af = px.bar(
            code_sorted, x=eff_metric, y='캠페인', orientation='h',
            text=code_sorted[eff_metric].apply(lambda v: fmt_val(v, eff_metric)),
            color=eff_metric, color_continuous_scale='Blues',
            hover_data={'코드': True, '발송횟수': True, '총모수': ':,.0f'},
        )
        fig_af.update_traces(textposition='outside', cliponaxis=False)
        fig_af.update_layout(height=max(380, len(code_sorted) * 30), yaxis={'categoryorder': 'total ascending'},
                             coloraxis_showscale=False, margin=dict(l=10, r=70), yaxis_title='')
        if eff_metric in ['평균CTR', '평균CR']:
            fig_af.update_xaxes(tickformat='.1%')
        elif eff_metric in MONEY_METRICS:
            fig_af.update_xaxes(tickformat=',.0f')
        st.plotly_chart(fig_af, use_container_width=True)

        # 효율 산점도: 타겟(모수) vs 거래액
        sec_title('타겟 규모 vs 거래액 (버블=ROAS)', 'p5-scatter')
        st.caption("점선(평균 효율)보다 위에 있으면 모수 1명당 거래액이 평균보다 높다는 뜻")
        scatter_df = code_df.dropna(subset=['총모수', '총거래액'])
        scatter_df = scatter_df[scatter_df['총모수'] > 0]
        if len(scatter_df):
            avg_eff = scatter_df['총거래액'].sum() / scatter_df['총모수'].sum()
            fig_sc = px.scatter(
                scatter_df, x='총모수', y='총거래액',
                size=scatter_df['평균ROAS'].clip(lower=0).fillna(0),
                color='1인당거래액', color_continuous_scale='RdYlGn',
                hover_name='캠페인',
                hover_data={'코드': True, '발송횟수': True, '평균ROAS': ':.1f', '1인당거래액': ':,.0f'},
                labels={'총모수': '타겟(총 모수, 명)', '총거래액': '총 거래액(원)'},
            )
            x_max = scatter_df['총모수'].max()
            fig_sc.add_shape(type='line', x0=0, y0=0, x1=x_max, y1=x_max * avg_eff,
                             line=dict(color='gray', dash='dash'))
            fig_sc.update_layout(height=460)
            fig_sc.update_xaxes(tickformat=',.0f')
            fig_sc.update_yaxes(tickformat=',.0f')
            st.plotly_chart(fig_sc, use_container_width=True)
            st.caption(f"평균 효율(점선): 1인당 {fmt_won(avg_eff)}")

        # 인사이트 — 효율 vs 규모 시사점
        valid = code_df.dropna(subset=['1인당거래액'])
        if len(valid) >= 2:
            best = valid.loc[valid['1인당거래액'].idxmax()]
            worst = valid.loc[valid['1인당거래액'].idxmin()]
            big = valid.loc[valid['총모수'].idxmax()]
            parts = [
                f"효율 1위 **{best['캠페인']}** — 타겟 {best['총모수']:,.0f}명 → "
                f"{fmt_won(best['총거래액'])} (1인당 {fmt_won(best['1인당거래액'])}, ROAS {best['평균ROAS']:.1f}%).",
                f"효율 최하위 **{worst['캠페인']}** — 1인당 {fmt_won(worst['1인당거래액'])}.",
            ]
            if big['캠페인'] != best['캠페인']:
                parts.append(
                    f"타겟이 가장 큰 **{big['캠페인']}**({big['총모수']:,.0f}명)는 1인당 {fmt_won(big['1인당거래액'])}로 "
                    f"효율 1위만 못함 → 규모는 크지만 모수 대비 효율은 개선 여지. 타겟 정밀화·오퍼 강화 검토."
                )
            st.info("  \n".join(parts))

        with st.expander("AF코드별 상세 수치"):
            st.dataframe(
                code_df.sort_values(eff_metric, ascending=False).style.format({
                    '총모수': '{:,.0f}', '총거래액': fmt_won, '1인당거래액': fmt_won, '객단가': fmt_won,
                    '평균CTR': '{:.1%}', '평균CR': '{:.1%}', '평균ROAS': '{:.1f}%', '발송횟수': '{:,}',
                }),
                use_container_width=True, hide_index=True
            )


# ══ A vs B 비교 ══════════════════════════════════
elif nav == "⚖️ A vs B 비교":
    sec_title('캠페인 비교 (A vs B)', 'p6-compare')
    st.caption("기준을 정하고 두 항목을 골라 효율을 나란히 비교 — 요금제 비교처럼 어느 쪽이 더 나은지 한눈에")

    basis = st.radio("비교 기준", ['채널', 'AF코드(캠페인)', '캠페인 그룹'], horizontal=True, key='cmp_basis')
    cmpdf = df_with_perf.copy()
    if basis == '채널':
        cmpdf['_키'] = cmpdf['채널'].astype(str)
    elif basis == 'AF코드(캠페인)':
        if 'AF코드' in cmpdf.columns:
            up = cmpdf['AF코드'].astype(str).str.strip().str.upper()
            cmpdf['_키'] = up.map(lambda c: AF_MAP.get(c))   # 고정 코드만
        else:
            cmpdf['_키'] = np.nan
    else:
        cmpdf['_키'] = cmpdf['캠페인명'].apply(extract_campaign_group)
    cmpdf = cmpdf.dropna(subset=['_키'])
    cmpdf = cmpdf[cmpdf['_키'].astype(str).str.strip() != '']
    opts = sorted(cmpdf['_키'].astype(str).unique().tolist())

    if len(opts) < 2:
        st.info("이 기준에선 비교할 항목이 2개 미만이에요. 다른 기준을 선택해보세요.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            a = st.selectbox("A 선택", opts, index=0, key='cmp_a')
        with c2:
            b = st.selectbox("B 선택", opts, index=min(1, len(opts) - 1), key='cmp_b')

        if a == b:
            st.warning("서로 다른 항목을 선택하세요.")
        else:
            ma = single_perf(cmpdf[cmpdf['_키'] == a])
            mb = single_perf(cmpdf[cmpdf['_키'] == b])
            METRICS = ['평균ROAS', '1인당거래액', '객단가', '평균CTR', '평균CR', '총거래액', '총모수', '발송건수']
            EFF = ['평균ROAS', '1인당거래액', '객단가', '평균CTR', '평균CR']  # 효율(높을수록 우세)

            # 지표별 한 행에 A·B 나란히 + 행마다 코멘트 (좌우로 안 멀고, 세로로 안 길게)
            def winner(k):
                if pd.isna(ma[k]) or pd.isna(mb[k]) or ma[k] == mb[k]:
                    return '='
                return 'A' if ma[k] > mb[k] else 'B'
            tbl = pd.DataFrame({
                '지표': METRICS,
                f'A: {a}': [cmp_fmt(k, ma[k]) for k in METRICS],
                f'B: {b}': [cmp_fmt(k, mb[k]) for k in METRICS],
                '우세': [winner(k) for k in METRICS],
                '코멘트': [metric_comment(k, ma[k], mb[k], a, b).replace('**', '') for k in METRICS],
            })

            def hl(row):
                w = row['우세']
                out = [''] * len(row)
                if w in ('A', 'B'):
                    col = f'A: {a}' if w == 'A' else f'B: {b}'
                    out[list(row.index).index(col)] = 'background-color:#E7F3EC;font-weight:600'
                return out
            st.dataframe(tbl.style.apply(hl, axis=1), use_container_width=True, hide_index=True)

            # 종합 판정 (효율 지표만 집계)
            awin = [k for k in EFF if pd.notna(ma[k]) and pd.notna(mb[k]) and ma[k] > mb[k]]
            bwin = [k for k in EFF if pd.notna(ma[k]) and pd.notna(mb[k]) and mb[k] > ma[k]]
            if len(awin) > len(bwin):
                verdict = f"**{a}** 효율 우세 ({len(awin)}:{len(bwin)})"
            elif len(bwin) > len(awin):
                verdict = f"**{b}** 효율 우세 ({len(bwin)}:{len(awin)})"
            else:
                verdict = f"효율 {len(awin)}:{len(bwin)} 무승부 — 목적 따라 선택"
            reach = a if ma['총모수'] > mb['총모수'] else b
            st.info(f"⚖️ {verdict} · 도달(모수)은 **{reach}**가 큼 — 효율과 규모는 다른 축이니 목적에 맞게 판단.")


# ── 스크롤스파이: 현재 보는 섹션의 사이드바 하위 메뉴에 밑줄 (베스트-에포트 JS) ──────────────
st.components.v1.html(
    """
    <script>
    const doc = window.parent.document;
    function getScroller(){
      const cands = [doc.scrollingElement,
                     doc.querySelector('section.main'),
                     doc.querySelector('[data-testid="stMain"]'),
                     doc.querySelector('[data-testid="stAppViewContainer"]'),
                     doc.documentElement, doc.body];
      for(const c of cands){ if(c && c.scrollHeight > c.clientHeight + 5) return c; }
      return doc.scrollingElement || doc.documentElement;
    }
    function spy(){
      const titles = Array.from(doc.querySelectorAll('.section-title')).filter(t => t.id);
      if(!titles.length) return;
      let active = titles[0].id;
      for(const t of titles){
        if(t.getBoundingClientRect().top <= 140) active = t.id;
      }
      // 페이지 끝까지 스크롤되면(마지막 섹션은 맨 위까지 못 올라감) 마지막 섹션 활성
      const se = getScroller();
      if(se && se.scrollTop + se.clientHeight >= se.scrollHeight - 8){
        active = titles[titles.length - 1].id;
      }
      doc.querySelectorAll('a.subnav-link').forEach(a=>{
        const on = a.getAttribute('href') === '#'+active;
        a.style.textDecoration = on ? 'underline' : 'none';
        a.style.fontWeight = on ? '700' : '400';
        a.style.color = on ? '#163E78' : '#2E68B0';
      });
    }
    window.parent.addEventListener('scroll', spy, true);
    setInterval(spy, 400);
    setTimeout(spy, 300);
    </script>
    """,
    height=0,
)
