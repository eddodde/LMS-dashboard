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
    }
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

    df['채널'] = df['채널'].fillna('LMS').str.upper()
    df['월'] = df['발송일자'].dt.to_period('M').astype(str)
    df['연도'] = df['발송일자'].dt.year
    요일맵 = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    df['요일'] = df['발송일자'].dt.dayofweek.map(요일맵)
    df['시간'] = df['시간대'].astype(str).str.extract(r'(\d+)').astype(float)
    df['문구'] = df['문구'].astype(str).str.strip()

    return df


@st.cache_data
def extract_keywords(texts, top_n=30):
    stop = {
        '광고', 'LF몰', 'LFmall', '무료수신거부', '고객센터', 'NaN', 'nan',
        '님', '을', '를', '이', '가', '은', '는', '의', '에', '에서', '으로', '로',
        '과', '와', '도', '만', '에서만', '까지', '수신거부', '안내', '확인',
        # 템플릿 변수 — 모든 문자에 들어가는 boilerplate
        '고객명', '주문번호', '상품명', '금액', '날짜', '시간', '브랜드명',
        # 너무 범용적인 단어
        '상품', '구매', '주문', '배송', '서비스', '앱', '사이트', '페이지',
    }
    # 유사어 → 대표어로 통합 (정규화 맵)
    normalize = {
        '고객님만': '고객님', '고객님께': '고객님', '고객님을': '고객님',
        '보셨던': '행동기반', '담으셨던': '행동기반', '찜하셨던': '행동기반',
        '할인가': '할인', '특가': '할인', '세일': '할인',
        '오늘까지': '마감임박', '오늘만': '마감임박', '종료임박': '마감임박',
    }
    pattern = re.compile(r'[a-zA-Z0-9\[\]\(\)\!\★▷▶◇\-\*·/\.,:↓%~#\[\]]+')
    keyword_counts = Counter()
    for text in texts:
        if pd.isna(text) or str(text) in ('nan', 'NaN', ''):
            continue
        text = re.sub(pattern, ' ', str(text))
        words = re.findall(r'[가-힣]{2,6}', text)
        for w in words:
            if w in stop or len(w) < 2:
                continue
            w = normalize.get(w, w)
            keyword_counts[w] += 1
    return keyword_counts.most_common(top_n)


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

    선택_채널 = st.multiselect("📡 채널", ['SMS', 'LMS', 'MMS'], default=['SMS', 'LMS'])
    연도_옵션 = sorted(df_raw['연도'].dropna().unique().tolist(), reverse=True)
    선택_연도 = st.multiselect("📅 연도", 연도_옵션, default=연도_옵션)

    st.markdown("---")
    st.caption("데이터 기준: 발송일 기준")


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
avg_ctr = df_with_perf['CTR'].mean()
avg_cr = df_with_perf['CR'].mean()
avg_roas = df_with_perf['ROAS'].mean()

with col1:
    st.metric("총 발송 건수", f"{total_send:,}건")
with col2:
    st.metric("총 발송 모수", f"{total_reach/10000:.1f}만명" if total_reach > 10000 else f"{int(total_reach):,}명")
with col3:
    st.metric("평균 CTR", f"{avg_ctr:.1%}" if pd.notna(avg_ctr) else "-")
with col4:
    st.metric("평균 CR", f"{avg_cr:.1%}" if pd.notna(avg_cr) else "-")
with col5:
    st.metric("평균 ROAS", f"{avg_roas:.1f}%" if pd.notna(avg_roas) else "-")

st.markdown("")


# ── 공통 상수 ──────────────────────────────────────────────
COLORS = {'SMS': '#4C72B0', 'LMS': '#DD8452', 'MMS': '#55A868'}

KW_CATEGORIES = {
    '개인화': ['고객명', '이름', '회원님', '고객님', '선생님', '귀하'],
    '행동기반': ['보셨던', '담으신', '관심', '찜하신', '검색하신', '구매하신', '방문하신', '클릭', '확인하신'],
    '혜택/할인': ['할인', '쿠폰', '적립', '무료', '특가', '혜택', '증정', '사은품', '캐시백', '포인트', '이벤트', '프로모션'],
    '긴급/한정': ['마감', '오늘', '지금', '한정', '마지막', '종료', '오늘까지', '곧', '종료임박', '품절'],
    '시즌': ['겨울', '여름', '봄', '가을', '블랙', '크리스마스', '설날', '추석', '신년', '연말'],
}
CAT_COLORS = {
    '개인화': '#4C72B0', '행동기반': '#DD8452', '혜택/할인': '#55A868',
    '긴급/한정': '#C44E52', '시즌': '#8172B2', '상품/기타': '#aaaaaa'
}

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

def fmt_val(v, metric):
    if pd.isna(v):
        return '-'
    if metric in ['평균CTR', '평균CR', 'CTR', 'CR']:
        return f"{v:.1%}"
    if metric in ['평균ROAS', 'ROAS', 'ROAS_리프트']:
        return f"{v:.1f}%"
    return f"{v:,.1f}"


# ── 탭 구성 ──────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📡 채널별 분석", "📅 월별 트렌드", "🔤 문구 키워드 분석", "🗂 캠페인 상세"])


# ══ TAB 1: 채널별 분석 ══════════════════════════════════
with tab1:

    # ── 채널 × 연도별 전년비 비교 ──────────────────────────────────────────────
    st.markdown('<div class="section-title">채널 × 연도별 성과 비교 (전년비)</div>', unsafe_allow_html=True)

    ch_yr = df_with_perf.groupby(['연도', '채널']).agg(
        발송건수=('캠페인명', 'count'),
        평균CTR=('CTR', 'mean'),
        평균CR=('CR', 'mean'),
        평균ROAS=('ROAS', 'mean'),
        총거래액=('거래액', 'sum'),
        평균모수=('모수', 'mean'),
    ).reset_index()
    ch_yr['연도'] = ch_yr['연도'].astype(str)

    yoy_metric = st.radio("비교 지표", ['평균CTR', '평균CR', '평균ROAS', '총거래액', '발송건수'], horizontal=True, key='yoy_m')

    fig_yoy = px.line(
        ch_yr, x='연도', y=yoy_metric, color='채널',
        markers=True, color_discrete_map=COLORS,
        text=ch_yr[yoy_metric].apply(lambda v: fmt_val(v, yoy_metric)),
        labels={'연도': '', yoy_metric: yoy_metric}
    )
    fig_yoy.update_traces(textposition='top center', mode='lines+markers+text')
    fig_yoy.update_layout(height=380)
    if yoy_metric in ['평균CTR', '평균CR']:
        fig_yoy.update_yaxes(tickformat='.1%')
    st.plotly_chart(fig_yoy, use_container_width=True)

    # 전년비 인사이트
    years = sorted(ch_yr['연도'].unique())
    if len(years) >= 2:
        prev_y, curr_y = years[-2], years[-1]
        insights = []
        for ch in sorted(ch_yr['채널'].unique()):
            prev_row = ch_yr[(ch_yr['연도'] == prev_y) & (ch_yr['채널'] == ch)]
            curr_row = ch_yr[(ch_yr['연도'] == curr_y) & (ch_yr['채널'] == ch)]
            if len(prev_row) and len(curr_row):
                diff = curr_row[yoy_metric].values[0] - prev_row[yoy_metric].values[0]
                arrow = "↑" if diff > 0 else "↓"
                insights.append(f"**{ch}**: {prev_y}→{curr_y} {arrow} {fmt_val(abs(diff), yoy_metric)} 변동")
        if insights:
            st.info("  \n".join(insights))

    # ── 채널별 종합 성과 테이블 ──────────────────────────────────────────────
    st.markdown('<div class="section-title">채널별 종합 성과</div>', unsafe_allow_html=True)

    ch_perf = df_with_perf.groupby('채널').agg(
        발송건수=('캠페인명', 'count'),
        평균모수=('모수', 'mean'),
        평균CTR=('CTR', 'mean'),
        평균CR=('CR', 'mean'),
        평균ROAS=('ROAS', 'mean'),
        총거래액=('거래액', 'sum'),
    ).reset_index()

    st.dataframe(
        ch_perf.style.format({
            '평균CTR': '{:.1%}', '평균CR': '{:.1%}',
            '평균ROAS': '{:.1f}%', '총거래액': '{:,.0f}',
            '평균모수': '{:,.0f}', '발송건수': '{:,}'
        }),
        use_container_width=True, hide_index=True
    )

    if len(ch_perf) >= 2:
        best_ctr_ch = ch_perf.loc[ch_perf['평균CTR'].idxmax()]
        best_roas_ch = ch_perf.loc[ch_perf['평균ROAS'].idxmax()]
        st.info(
            f"CTR 최고 채널: **{best_ctr_ch['채널']}** ({best_ctr_ch['평균CTR']:.1%})  \n"
            f"ROAS 최고 채널: **{best_roas_ch['채널']}** ({best_roas_ch['평균ROAS']:.1f}%)"
        )

    # ── 월별 시계열 (채널별) ──────────────────────────────────────────────
    st.markdown('<div class="section-title">월별 시계열 추이 (채널별)</div>', unsafe_allow_html=True)

    monthly_ch = df_with_perf.groupby(['월', '채널']).agg(
        캠페인건수=('캠페인명', 'count'),
        평균모수=('모수', 'mean'),
        평균CTR=('CTR', 'mean'),
        평균CR=('CR', 'mean'),
        평균ROAS=('ROAS', 'mean'),
        총거래액=('거래액', 'sum'),
    ).reset_index().sort_values('월')

    ts_metric = st.selectbox(
        "지표 선택",
        ['평균CTR', '평균CR', '평균ROAS', '평균모수', '총거래액', '캠페인건수'],
        key='ts_ch'
    )
    fig_ts = px.line(
        monthly_ch, x='월', y=ts_metric, color='채널',
        markers=True, color_discrete_map=COLORS,
        labels={ts_metric: ts_metric, '월': ''}
    )
    fig_ts.update_layout(height=380, xaxis_tickangle=-30)
    if ts_metric in ['평균CTR', '평균CR']:
        fig_ts.update_yaxes(tickformat='.1%')
    st.plotly_chart(fig_ts, use_container_width=True)

    # ── 채널별 비용 효율 ──────────────────────────────────────────────
    if '비용' in df.columns and df['비용'].notna().any():
        st.markdown('<div class="section-title">채널별 캠페인당 평균 비용 vs 거래액</div>', unsafe_allow_html=True)
        cost_eff = df_with_perf.groupby('채널').agg(
            평균비용=('비용', 'mean'),
            평균거래액=('거래액', 'mean'),
        ).reset_index().dropna()
        if len(cost_eff):
            cost_melt = cost_eff.melt(id_vars='채널', value_vars=['평균비용', '평균거래액'], var_name='항목', value_name='금액')
            fig_eff = px.line(
                cost_melt, x='채널', y='금액', color='항목',
                markers=True, color_discrete_sequence=['#C44E52', '#55A868'],
                labels={'금액': '금액(원)'}
            )
            fig_eff.update_layout(height=320)
            st.plotly_chart(fig_eff, use_container_width=True)
            best_eff = cost_eff.assign(효율=cost_eff['평균거래액'] / cost_eff['평균비용'].replace(0, np.nan)).dropna()
            if len(best_eff):
                top = best_eff.loc[best_eff['효율'].idxmax()]
                st.info(f"비용 대비 거래액 효율 최고 채널: **{top['채널']}** (비용 {top['평균비용']:,.0f}원 → 거래액 {top['평균거래액']:,.0f}원)")


# ══ TAB 2: 월별 트렌드 ══════════════════════════════════
with tab2:
    st.markdown('<div class="section-title">월별 발송 모수 & 성과 혼합 추이</div>', unsafe_allow_html=True)
    st.caption("막대 = 평균 발송 모수(우축) / 선 = 선택 지표(좌축)")

    monthly_total = df_with_perf.groupby('월').agg(
        평균모수=('모수', 'mean'),
        평균CTR=('CTR', 'mean'),
        평균CR=('CR', 'mean'),
        평균ROAS=('ROAS', 'mean'),
        총거래액=('거래액', 'sum'),
        캠페인건수=('캠페인명', 'count'),
    ).reset_index().sort_values('월')

    mix_metric = st.selectbox(
        "성과 지표 선택",
        ['평균CTR', '평균CR', '평균ROAS', '총거래액', '캠페인건수'],
        key='mix_m'
    )

    fig_mix = make_subplots(specs=[[{"secondary_y": True}]])
    fig_mix.add_trace(
        go.Bar(
            x=monthly_total['월'], y=monthly_total['평균모수'],
            name='평균모수', marker_color='#d0d0d0', opacity=0.6
        ),
        secondary_y=True
    )
    line_text = monthly_total[mix_metric].apply(lambda v: fmt_val(v, mix_metric))
    fig_mix.add_trace(
        go.Scatter(
            x=monthly_total['월'], y=monthly_total[mix_metric],
            name=mix_metric, mode='lines+markers+text',
            line=dict(color='#4C72B0', width=2),
            text=line_text, textposition='top center'
        ),
        secondary_y=False
    )
    fig_mix.update_layout(height=420, xaxis_tickangle=-30, legend=dict(orientation='h', y=1.1))
    fig_mix.update_yaxes(title_text=mix_metric, secondary_y=False)
    fig_mix.update_yaxes(title_text='평균모수', secondary_y=True)
    if mix_metric in ['평균CTR', '평균CR']:
        fig_mix.update_yaxes(tickformat='.1%', secondary_y=False)
    st.plotly_chart(fig_mix, use_container_width=True)

    if len(monthly_total) >= 2:
        peak = monthly_total.loc[monthly_total[mix_metric].idxmax()]
        low = monthly_total.loc[monthly_total[mix_metric].idxmin()]
        st.info(
            f"{mix_metric} 최고: **{peak['월']}** ({fmt_val(peak[mix_metric], mix_metric)})  \n"
            f"{mix_metric} 최저: **{low['월']}** ({fmt_val(low[mix_metric], mix_metric)})"
        )

    # ── 요일별 성과 ──────────────────────────────────────────────
    st.markdown('<div class="section-title">요일별 평균 성과</div>', unsafe_allow_html=True)

    요일순서 = ['월', '화', '수', '목', '금', '토', '일']
    df_dow = df_with_perf.dropna(subset=['요일'])
    if len(df_dow):
        dow_agg = df_dow.groupby('요일').agg(
            캠페인건수=('캠페인명', 'count'),
            평균CTR=('CTR', 'mean'),
            평균CR=('CR', 'mean'),
            평균ROAS=('ROAS', 'mean'),
            평균모수=('모수', 'mean'),
        ).reindex(요일순서).reset_index()

        dow_metric = st.radio("요일별 지표", ['평균CTR', '평균CR', '평균ROAS', '캠페인건수'], horizontal=True, key='dow_m')
        fig_dow = px.line(
            dow_agg, x='요일', y=dow_metric,
            markers=True,
            text=dow_agg[dow_metric].apply(lambda v: fmt_val(v, dow_metric)),
            labels={'요일': '', dow_metric: dow_metric}
        )
        fig_dow.update_traces(textposition='top center', mode='lines+markers+text', line=dict(color='#4C72B0'))
        fig_dow.update_layout(height=340)
        if dow_metric in ['평균CTR', '평균CR']:
            fig_dow.update_yaxes(tickformat='.1%')
        st.plotly_chart(fig_dow, use_container_width=True)

        best_dow = dow_agg.dropna(subset=[dow_metric]).loc[dow_agg.dropna(subset=[dow_metric])[dow_metric].idxmax()]
        worst_dow = dow_agg.dropna(subset=[dow_metric]).loc[dow_agg.dropna(subset=[dow_metric])[dow_metric].idxmin()]
        st.info(
            f"{dow_metric} 최고 요일: **{best_dow['요일']}요일** ({fmt_val(best_dow[dow_metric], dow_metric)})  \n"
            f"{dow_metric} 최저 요일: **{worst_dow['요일']}요일** ({fmt_val(worst_dow[dow_metric], dow_metric)})"
        )

    # ── 시간대별 성과 (시간 데이터 있을 때만) ──────────────────────────────────────────────
    df_hour = df_with_perf.dropna(subset=['시간'])
    if len(df_hour) and df_hour['시간'].nunique() > 1:
        st.markdown('<div class="section-title">시간대별 평균 성과</div>', unsafe_allow_html=True)
        hour_agg = df_hour.groupby('시간').agg(
            캠페인건수=('캠페인명', 'count'),
            평균CTR=('CTR', 'mean'),
            평균CR=('CR', 'mean'),
            평균ROAS=('ROAS', 'mean'),
        ).reset_index().sort_values('시간')

        hour_metric = st.radio("시간대별 지표", ['평균CTR', '평균CR', '평균ROAS', '캠페인건수'], horizontal=True, key='hour_m')
        fig_hr = px.line(
            hour_agg, x='시간', y=hour_metric,
            markers=True,
            text=hour_agg[hour_metric].apply(lambda v: fmt_val(v, hour_metric)),
            labels={'시간': '발송 시간', hour_metric: hour_metric}
        )
        fig_hr.update_traces(textposition='top center', mode='lines+markers+text', line=dict(color='#DD8452'))
        fig_hr.update_layout(height=340)
        if hour_metric in ['평균CTR', '평균CR']:
            fig_hr.update_yaxes(tickformat='.1%')
        st.plotly_chart(fig_hr, use_container_width=True)

        best_hr = hour_agg.loc[hour_agg[hour_metric].idxmax()]
        st.info(f"{hour_metric} 최고 시간대: **{int(best_hr['시간'])}시** ({fmt_val(best_hr[hour_metric], hour_metric)})")
    else:
        st.caption("발송일자에 시간 정보가 없어 시간대별 분석을 표시할 수 없어요.")


# ══ TAB 3: 문구 키워드 분석 ══════════════════════════════════
with tab3:
    col_a, col_b = st.columns(2)
    with col_a:
        분석채널 = st.selectbox("채널", ['전체'] + sorted(df['채널'].dropna().unique().tolist()), key='kw_ch')
    with col_b:
        top_n = st.slider("키워드 수", 10, 50, 25)

    df_kw = df.copy()
    if 분석채널 != '전체':
        df_kw = df_kw[df_kw['채널'] == 분석채널]
    df_kw_perf = df_kw.dropna(subset=['CTR', 'CR', 'ROAS', '문구'])
    df_kw_perf = df_kw_perf[df_kw_perf['ROAS'] > 0]

    # ── 1. 카테고리별 평균 성과 (가장 먼저, 크게) ──────────────────────────────────────────────
    st.markdown('<div class="section-title">카테고리별 평균 성과</div>', unsafe_allow_html=True)
    st.caption("문구에 해당 카테고리 키워드가 포함된 캠페인의 평균 실적 — 어떤 문구 유형이 성과를 올리는지 파악")

    cat_rows = []
    for _, row in df_kw_perf.iterrows():
        for cat in get_text_categories(row['문구']):
            cat_rows.append({'카테고리': cat, 'CTR': row['CTR'], 'CR': row['CR'], 'ROAS': row['ROAS']})

    if cat_rows:
        cat_perf_df = pd.DataFrame(cat_rows)
        cat_agg = cat_perf_df.groupby('카테고리').agg(
            캠페인수=('CTR', 'count'),
            평균CTR=('CTR', 'mean'),
            평균CR=('CR', 'mean'),
            평균ROAS=('ROAS', 'mean'),
        ).reset_index()

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

    # ── 2. 키워드 빈도 ──────────────────────────────────────────────
    st.markdown('<div class="section-title">키워드 빈도 (카테고리별 색상)</div>', unsafe_allow_html=True)
    kw_all = extract_keywords(df_kw['문구'].tolist(), top_n=top_n)

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
    st.markdown('<div class="section-title">키워드 포함 시 성과 리프트</div>', unsafe_allow_html=True)
    st.caption("포함 건수가 적을수록 해당 캠페인 고유 특성일 수 있으므로 해석 주의")

    if kw_all:
        kw_perf_rows = []
        for kw, _ in kw_all[:20]:
            mask = df_kw_perf['문구'].str.contains(kw, na=False)
            has = df_kw_perf[mask]
            no  = df_kw_perf[~mask]
            if len(has) > 0 and len(no) > 0:
                kw_perf_rows.append({
                    '키워드': kw,
                    '카테고리': classify_keyword(kw),
                    '포함건수': len(has),
                    'ROAS_리프트': has['ROAS'].mean() - no['ROAS'].mean(),
                    'CTR_리프트': has['CTR'].mean() - no['CTR'].mean(),
                    '포함_ROAS': has['ROAS'].mean(),
                    '미포함_ROAS': no['ROAS'].mean(),
                })
        if kw_perf_rows:
            kw_perf_df = pd.DataFrame(kw_perf_rows)
            lift_metric = st.radio("리프트 지표", ['ROAS_리프트', 'CTR_리프트'], horizontal=True, key='lift_m')
            kw_sorted = kw_perf_df.sort_values(lift_metric)

            fig_lift = px.bar(
                kw_sorted, x=lift_metric, y='키워드', orientation='h',
                color='카테고리', color_discrete_map=CAT_COLORS,
                text=kw_sorted[lift_metric].apply(
                    lambda v: f"{v:+.1%}" if lift_metric == 'CTR_리프트' else f"{v:+.1f}%"
                ),
                hover_data={'포함건수': True, '포함_ROAS': ':.1f', '미포함_ROAS': ':.1f'},
            )
            fig_lift.add_vline(x=0, line_dash='dash', line_color='gray')
            fig_lift.update_layout(height=max(420, len(kw_sorted) * 24), yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_lift, use_container_width=True)

            top_lift = kw_perf_df.loc[kw_perf_df[lift_metric].idxmax()]
            bot_lift = kw_perf_df.loc[kw_perf_df[lift_metric].idxmin()]
            st.info(
                f"**리프트 1위: '{top_lift['키워드']}'** (포함 {top_lift['포함건수']:.0f}건) — "
                f"포함 ROAS {top_lift['포함_ROAS']:.1f}% vs 미포함 {top_lift['미포함_ROAS']:.1f}% ({top_lift['ROAS_리프트']:+.1f}%p)  \n"
                f"리프트 최하위: **'{bot_lift['키워드']}'** — 이 키워드 단독 포함 시 성과가 낮은 경향"
            )

            with st.expander("상세 수치 보기"):
                st.dataframe(
                    kw_perf_df.sort_values(lift_metric, ascending=False)[
                        ['키워드', '카테고리', '포함건수', '포함_ROAS', '미포함_ROAS', 'ROAS_리프트', 'CTR_리프트']
                    ].style.format({
                        '포함_ROAS': '{:.1f}%', '미포함_ROAS': '{:.1f}%',
                        'ROAS_리프트': '{:+.1f}', 'CTR_리프트': '{:+.1%}',
                    }),
                    use_container_width=True, hide_index=True
                )


# ══ TAB 4: 캠페인 상세 ══════════════════════════════════
with tab4:
    st.markdown('<div class="section-title">캠페인별 상세 데이터</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search = st.text_input("🔍 캠페인명 / 요청부서 검색", "")
    with col2:
        sort_by = st.selectbox("정렬 기준", ['ROAS', 'CTR', 'CR', '발송일자', '모수'])
    with col3:
        sort_asc = st.checkbox("오름차순", value=False)

    display_cols = ['발송일자', '출처', '채널', '요청부서', '캠페인명', '모수', 'CTR', 'CR', 'ROAS', '거래액', '문구']
    df_detail = df[display_cols].copy()

    if search:
        mask = (
            df_detail['캠페인명'].str.contains(search, na=False, case=False) |
            df_detail['요청부서'].str.contains(search, na=False, case=False)
        )
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

    # ── 반복 캠페인 연도별 전년비 ──────────────────────────────────────────────
    st.markdown('<div class="section-title">🔁 반복 캠페인 연도별 전년비</div>', unsafe_allow_html=True)
    st.caption("핵심 키워드 기준 그룹핑 | 2개 이상 연도에 걸쳐 발송된 캠페인만 표시")

    df['캠페인그룹'] = df['캠페인명'].apply(extract_campaign_group)
    df_rec_base = df_with_perf.copy()
    df_rec_base['캠페인그룹'] = df_rec_base['캠페인명'].apply(extract_campaign_group)

    # 2개 이상 연도에 발송된 그룹만
    group_yr_counts = df_rec_base.groupby('캠페인그룹')['연도'].nunique()
    recurring_groups = sorted(group_yr_counts[group_yr_counts >= 2].index.tolist())

    if recurring_groups:
        selected_group = st.selectbox("캠페인 그룹 선택", recurring_groups, key='rec_group')
        df_rec = df_rec_base[df_rec_base['캠페인그룹'] == selected_group]

        rec_yr = df_rec.groupby('연도').agg(
            발송건수=('캠페인명', 'count'),
            평균CTR=('CTR', 'mean'),
            평균CR=('CR', 'mean'),
            평균ROAS=('ROAS', 'mean'),
            총거래액=('거래액', 'sum'),
            평균모수=('모수', 'mean'),
        ).reset_index()
        rec_yr['연도'] = rec_yr['연도'].astype(str)

        metric_rec = st.radio("지표", ['평균ROAS', '평균CTR', '평균CR', '총거래액', '발송건수'], horizontal=True, key='rec_metric')
        fig_rec = px.line(
            rec_yr, x='연도', y=metric_rec, markers=True,
            text=rec_yr[metric_rec].apply(lambda v: fmt_val(v, metric_rec)),
            labels={'연도': '', metric_rec: metric_rec}
        )
        fig_rec.update_traces(mode='lines+markers+text', textposition='top center', line=dict(color='#4C72B0', width=2))
        fig_rec.update_layout(height=360)
        if metric_rec in ['평균CTR', '평균CR']:
            fig_rec.update_yaxes(tickformat='.1%')
        st.plotly_chart(fig_rec, use_container_width=True)

        # 전년비 인사이트
        years = sorted(rec_yr['연도'].unique())
        if len(years) >= 2:
            prev_v = rec_yr[rec_yr['연도'] == years[-2]][metric_rec].values[0]
            curr_v = rec_yr[rec_yr['연도'] == years[-1]][metric_rec].values[0]
            diff = curr_v - prev_v
            arrow = "↑" if diff > 0 else "↓"
            st.info(
                f"**'{selected_group}'** {years[-2]}→{years[-1]} {arrow}  \n"
                f"{metric_rec}: {fmt_val(prev_v, metric_rec)} → {fmt_val(curr_v, metric_rec)} "
                f"({'+' if diff > 0 else ''}{fmt_val(diff, metric_rec)} 변동)"
            )

        with st.expander(f"'{selected_group}' 연도별 상세"):
            st.dataframe(rec_yr.style.format({
                '평균CTR': '{:.1%}', '평균CR': '{:.1%}', '평균ROAS': '{:.1f}%',
                '총거래액': '{:,.0f}', '평균모수': '{:,.0f}',
            }), use_container_width=True, hide_index=True)
    else:
        st.info("2개 이상 연도에 걸쳐 발송된 반복 캠페인 그룹이 없습니다.")
