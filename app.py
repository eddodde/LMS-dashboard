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
def load_data(file_t, file_m):
    # 타부서 발송
    df_t_send = pd.read_excel(file_t, sheet_name="1. 발송", header=3)
    df_t_send = df_t_send[['구분', '요청부서', '수단', '일시', '캠페인명', '타겟', '내용', '비고', '모수', '비용']].copy()
    df_t_send.columns = ['구분', '요청부서', '채널', '발송일자', '캠페인명', '타겟', '문구', '비고', '모수', '비용']
    df_t_send['출처'] = '타부서'

    # 타부서 성과
    df_t_perf = pd.read_excel(file_t, sheet_name="2. 성과", header=4)
    df_t_perf = df_t_perf[['캠페인명', '모수', 'UV', 'CTR', 'CR', '주문금액', 'ROAS']].copy()
    df_t_perf.columns = ['캠페인명', '모수', 'UV', 'CTR', 'CR', '거래액', 'ROAS']

    # 멤버십 발송
    df_m_send = pd.read_excel(file_m, sheet_name="1. 발송", header=3)
    df_m_send = df_m_send[['구분', '일시', '캠페인명', '타겟', '내용', '비고', '모수', '비용']].copy()
    df_m_send.columns = ['구분', '발송일자', '캠페인명', '타겟', '문구', '비고', '모수', '비용']
    df_m_send['요청부서'] = '마케팅'
    # 캠페인명에서 채널 추출 (SMS/LMS)
    df_m_send['채널'] = df_m_send['캠페인명'].str.extract(r'_(SMS|LMS|MMS)')[0]
    df_m_send['채널'] = df_m_send['채널'].fillna('LMS')
    df_m_send['출처'] = '멤버십'

    # 멤버십 성과
    df_m_perf = pd.read_excel(file_m, sheet_name="2. 성과", header=3)
    # 실제 데이터 시작 row 찾기 (구분 컬럼이 숫자인 행)
    df_m_perf.columns = range(len(df_m_perf.columns))
    # header row가 row index 3이므로 실제 데이터 파싱
    df_m_perf2 = pd.read_excel(file_m, sheet_name="2. 성과", header=None, skiprows=3)
    # 컬럼 정렬: 1=구분, 2=발송일자, 3=캠페인명, 4=모수, 7=UV, 8=CTR, 9=고객수, 10=주문수, 11=주문금액, 12=CR, 13=ROAS
    df_m_perf2 = df_m_perf2.iloc[:, [1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13]]
    df_m_perf2.columns = ['구분', '발송일자', '캠페인명', '모수', 'UV', 'CTR', '고객수', '주문수', '주문금액', 'CR', 'ROAS']
    df_m_perf2 = df_m_perf2.dropna(subset=['캠페인명'])
    df_m_perf2 = df_m_perf2[df_m_perf2['캠페인명'].astype(str).str.startswith('MKT_')]
    df_m_perf2 = df_m_perf2.rename(columns={'주문금액': '거래액'})

    # 전체 합치기 - 발송
    send_cols = ['구분', '요청부서', '채널', '발송일자', '캠페인명', '타겟', '문구', '비고', '모수', '비용', '출처']
    df_t_send = df_t_send.dropna(subset=['캠페인명'])
    df_m_send = df_m_send.dropna(subset=['캠페인명'])
    df_send = pd.concat([df_t_send[send_cols], df_m_send[send_cols]], ignore_index=True)

    # 전체 합치기 - 성과
    perf_cols = ['캠페인명', '모수', 'UV', 'CTR', 'CR', '거래액', 'ROAS']
    df_t_perf = df_t_perf.dropna(subset=['캠페인명'])
    df_m_perf2 = df_m_perf2[perf_cols]
    df_perf = pd.concat([df_t_perf[perf_cols], df_m_perf2[perf_cols]], ignore_index=True)

    # JOIN
    df = pd.merge(df_send, df_perf, on='캠페인명', how='left', suffixes=('_send', '_perf'))
    df['모수'] = df['모수_perf'].combine_first(df['모수_send'])
    df = df.drop(columns=['모수_send', '모수_perf'])

    # 타입 정리
    df['발송일자'] = pd.to_datetime(df['발송일자'], errors='coerce')
    for col in ['모수', '비용', 'UV', 'CTR', 'CR', '거래액', 'ROAS']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['문구'] = df['문구'].astype(str).str.strip()
    df['채널'] = df['채널'].fillna('LMS').str.upper()
    df['월'] = df['발송일자'].dt.to_period('M').astype(str)
    df['연도'] = df['발송일자'].dt.year

    return df


@st.cache_data
def extract_keywords(texts, top_n=30):
    """문구에서 핵심 키워드 추출"""
    # 불필요 패턴 제거
    stop = ['광고', 'LF몰', 'LFmall', '무료수신거부', '고객센터', '080', '1544', 'https', 'http',
            'bit', 'ly', '\\n', '\n', 'NaN', 'nan', '님', '을', '를', '이', '가', '은', '는',
            '의', '에', '에서', '으로', '로', '과', '와', '도', '만', '에서만', '까지']
    pattern = re.compile(r'[a-zA-Z0-9\[\]\(\)\!\★▷▶◇\-\*·/\.,:↓%~#]+')

    keyword_counts = Counter()
    for text in texts:
        if pd.isna(text) or text in ('nan', 'NaN', ''):
            continue
        text = re.sub(pattern, ' ', str(text))
        words = re.findall(r'[가-힣]{2,6}', text)
        for w in words:
            if w not in stop and len(w) >= 2:
                keyword_counts[w] += 1

    return keyword_counts.most_common(top_n)


# ── 사이드바 필터 ──────────────────────────────────────────────
with st.sidebar:
    st.title("📱 LMS 대시보드")
    st.markdown("---")

    st.markdown("**📂 엑셀 파일 업로드**")
    file_t = st.file_uploader("타부서 요청 LMS 파일", type=["xlsx"], key="file_t")
    file_m = st.file_uploader("멤버십 LMS 파일", type=["xlsx"], key="file_m")

    if not file_t or not file_m:
        st.info("두 파일을 모두 업로드하면 대시보드가 로드됩니다.")
        st.stop()

    df_raw = load_data(file_t, file_m)

    출처_옵션 = ['전체'] + sorted(df_raw['출처'].dropna().unique().tolist())
    선택_출처 = st.selectbox("📂 구분", 출처_옵션)

    채널_옵션 = ['전체', 'SMS', 'LMS', 'MMS']
    선택_채널 = st.multiselect("📡 채널", ['SMS', 'LMS', 'MMS'], default=['SMS', 'LMS'])

    연도_옵션 = sorted(df_raw['연도'].dropna().unique().tolist(), reverse=True)
    선택_연도 = st.multiselect("📅 연도", 연도_옵션, default=연도_옵션[:2] if len(연도_옵션) >= 2 else 연도_옵션)

    st.markdown("---")
    st.caption("데이터 기준: 발송일 기준")


# ── 필터 적용 ──────────────────────────────────────────────
df = df_raw.copy()
if 선택_출처 != '전체':
    df = df[df['출처'] == 선택_출처]
if 선택_채널:
    df = df[df['채널'].isin(선택_채널)]
if 선택_연도:
    df = df[df['연도'].isin(선택_연도)]

df_with_perf = df.dropna(subset=['CTR', 'CR', 'ROAS'])


# ── 헤더 ──────────────────────────────────────────────
st.title("📱 문자 발송 성과 분석 대시보드")
st.markdown(f"**필터**: {선택_출처} | 채널: {', '.join(선택_채널) if 선택_채널 else '전체'} | 연도: {', '.join(map(str, 선택_연도)) if 선택_연도 else '전체'}")
st.markdown("---")


# ── KPI 요약 ──────────────────────────────────────────────
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
    st.metric("평균 CTR", f"{avg_ctr:.2%}" if pd.notna(avg_ctr) else "-")
with col4:
    st.metric("평균 CR", f"{avg_cr:.2%}" if pd.notna(avg_cr) else "-")
with col5:
    st.metric("평균 ROAS", f"{avg_roas:.1f}" if pd.notna(avg_roas) else "-")

st.markdown("")

# ── 탭 구성 ──────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📡 채널별 분석", "📅 월별 트렌드", "🔤 문구 키워드 분석", "🗂 캠페인 상세"])


# ══ TAB 1: 채널별 분석 ══════════════════════════════════
with tab1:
    st.markdown('<div class="section-title">채널별 (SMS vs LMS) 성과 비교</div>', unsafe_allow_html=True)

    ch_perf = df_with_perf.groupby('채널').agg(
        발송건수=('캠페인명', 'count'),
        평균모수=('모수', 'mean'),
        총모수=('모수', 'sum'),
        평균CTR=('CTR', 'mean'),
        평균CR=('CR', 'mean'),
        평균ROAS=('ROAS', 'mean'),
        총거래액=('거래액', 'sum'),
    ).reset_index()

    # 채널별 KPI 테이블
    col1, col2 = st.columns([1, 2])
    with col1:
        st.dataframe(
            ch_perf.style.format({
                '평균CTR': '{:.2%}', '평균CR': '{:.2%}',
                '평균ROAS': '{:.1f}', '총거래액': '{:,.0f}',
                '평균모수': '{:,.0f}', '총모수': '{:,.0f}',
                '발송건수': '{:,}'
            }),
            use_container_width=True, hide_index=True
        )

    with col2:
        metrics = ['평균CTR', '평균CR', '평균ROAS']
        metric_labels = ['CTR', 'CR', 'ROAS']
        fig = make_subplots(rows=1, cols=3, subplot_titles=metric_labels)
        colors = {'SMS': '#4C72B0', 'LMS': '#DD8452', 'MMS': '#55A868'}

        for i, (m, label) in enumerate(zip(metrics, metric_labels)):
            for _, row in ch_perf.iterrows():
                val = row[m]
                if m in ['평균CTR', '평균CR']:
                    display = f"{val:.2%}"
                else:
                    display = f"{val:.1f}"
                fig.add_trace(
                    go.Bar(
                        x=[row['채널']], y=[val],
                        name=row['채널'],
                        marker_color=colors.get(row['채널'], '#4C72B0'),
                        text=[display], textposition='outside',
                        showlegend=(i == 0)
                    ),
                    row=1, col=i+1
                )
        fig.update_layout(height=320, margin=dict(t=40, b=10), barmode='group')
        st.plotly_chart(fig, use_container_width=True)

    # 채널별 ROAS 분포
    st.markdown('<div class="section-title">채널별 ROAS 분포</div>', unsafe_allow_html=True)
    fig_box = px.box(
        df_with_perf[df_with_perf['ROAS'] < df_with_perf['ROAS'].quantile(0.95)],
        x='채널', y='ROAS', color='채널',
        color_discrete_map=colors,
        points='outliers'
    )
    fig_box.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig_box, use_container_width=True)

    # 출처(멤버십/타부서)별 채널 분포
    st.markdown('<div class="section-title">출처별 채널 구성</div>', unsafe_allow_html=True)
    src_ch = df.groupby(['출처', '채널']).size().reset_index(name='건수')
    fig_bar = px.bar(src_ch, x='출처', y='건수', color='채널',
                     color_discrete_map=colors, barmode='stack', text='건수')
    fig_bar.update_layout(height=320)
    st.plotly_chart(fig_bar, use_container_width=True)


# ══ TAB 2: 월별 트렌드 ══════════════════════════════════
with tab2:
    st.markdown('<div class="section-title">월별 발송 트렌드 & 성과 추이</div>', unsafe_allow_html=True)

    monthly = df_with_perf.groupby(['월', '채널']).agg(
        발송건수=('캠페인명', 'count'),
        평균CTR=('CTR', 'mean'),
        평균CR=('CR', 'mean'),
        평균ROAS=('ROAS', 'mean'),
        총모수=('모수', 'sum'),
    ).reset_index().sort_values('월')

    metric_choice = st.selectbox("지표 선택", ['평균CTR', '평균CR', '평균ROAS', '발송건수', '총모수'])
    colors = {'SMS': '#4C72B0', 'LMS': '#DD8452', 'MMS': '#55A868'}

    fig_trend = px.line(
        monthly, x='월', y=metric_choice, color='채널',
        markers=True, color_discrete_map=colors,
        labels={metric_choice: metric_choice, '월': ''}
    )
    fig_trend.update_layout(height=380, xaxis_tickangle=-30)
    if metric_choice in ['평균CTR', '평균CR']:
        fig_trend.update_yaxes(tickformat='.2%')
    st.plotly_chart(fig_trend, use_container_width=True)

    # 월별 총 모수 bar
    monthly_total = df.groupby('월').agg(총모수=('모수', 'sum'), 발송건수=('캠페인명', 'count')).reset_index()
    fig_bar2 = px.bar(monthly_total, x='월', y='총모수', text='발송건수',
                      labels={'총모수': '총 발송 모수', '월': ''})
    fig_bar2.update_traces(texttemplate='%{text}건', textposition='outside')
    fig_bar2.update_layout(height=300, xaxis_tickangle=-30)
    st.plotly_chart(fig_bar2, use_container_width=True)


# ══ TAB 3: 문구 키워드 분석 ══════════════════════════════════
with tab3:
    st.markdown('<div class="section-title">문구 키워드 빈도 분석</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        분석채널 = st.selectbox("채널", ['전체'] + sorted(df['채널'].dropna().unique().tolist()), key='kw_ch')
    with col_b:
        top_n = st.slider("키워드 수", 10, 50, 25)

    df_kw = df.copy()
    if 분석채널 != '전체':
        df_kw = df_kw[df_kw['채널'] == 분석채널]

    kw_all = extract_keywords(df_kw['문구'].tolist(), top_n=top_n)
    if kw_all:
        kw_df = pd.DataFrame(kw_all, columns=['키워드', '빈도'])
        fig_kw = px.bar(kw_df, x='빈도', y='키워드', orientation='h',
                        color='빈도', color_continuous_scale='Blues')
        fig_kw.update_layout(height=max(400, top_n * 22), yaxis={'categoryorder': 'total ascending'},
                              coloraxis_showscale=False)
        st.plotly_chart(fig_kw, use_container_width=True)
    else:
        st.info("키워드를 추출할 수 있는 문구 데이터가 없습니다.")

    # 키워드 × 성과 상관
    st.markdown('<div class="section-title">주요 키워드 포함 여부에 따른 성과 차이</div>', unsafe_allow_html=True)

    if kw_all:
        top_keywords = [k for k, _ in kw_all[:15]]
        kw_perf_rows = []
        df_kw_perf = df_kw.dropna(subset=['CTR', 'CR', 'ROAS', '문구'])

        for kw in top_keywords:
            mask = df_kw_perf['문구'].str.contains(kw, na=False)
            has = df_kw_perf[mask]
            no  = df_kw_perf[~mask]
            if len(has) > 0 and len(no) > 0:
                kw_perf_rows.append({
                    '키워드': kw,
                    '포함_건수': len(has),
                    '포함_CTR': has['CTR'].mean(),
                    '포함_CR': has['CR'].mean(),
                    '포함_ROAS': has['ROAS'].mean(),
                    '미포함_CTR': no['CTR'].mean(),
                    '미포함_CR': no['CR'].mean(),
                    '미포함_ROAS': no['ROAS'].mean(),
                })

        if kw_perf_rows:
            kw_perf_df = pd.DataFrame(kw_perf_rows)
            kw_perf_df['ROAS_리프트'] = kw_perf_df['포함_ROAS'] - kw_perf_df['미포함_ROAS']
            kw_perf_df['CTR_리프트'] = kw_perf_df['포함_CTR'] - kw_perf_df['미포함_CTR']

            metric_kw = st.radio("비교 지표", ['ROAS_리프트', 'CTR_리프트'], horizontal=True)
            kw_perf_df_sorted = kw_perf_df.sort_values(metric_kw, ascending=False)

            fig_lift = px.bar(
                kw_perf_df_sorted, x='키워드', y=metric_kw,
                color=metric_kw,
                color_continuous_scale=['#d9534f', '#f0f0f0', '#4C72B0'],
                color_continuous_midpoint=0,
                text=kw_perf_df_sorted[metric_kw].round(2)
            )
            fig_lift.add_hline(y=0, line_dash='dash', line_color='gray')
            fig_lift.update_layout(height=370, coloraxis_showscale=False,
                                   title=f"키워드 포함 시 {metric_kw} (양수=포함이 높음)")
            st.plotly_chart(fig_lift, use_container_width=True)


# ══ TAB 4: 캠페인 상세 ══════════════════════════════════
with tab4:
    st.markdown('<div class="section-title">캠페인별 상세 데이터</div>', unsafe_allow_html=True)

    # 정렬 & 검색
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

    # 문구 잘라서 표시
    df_detail['문구_미리보기'] = df_detail['문구'].str[:60] + '...'

    st.dataframe(
        df_detail.drop(columns=['문구']).rename(columns={'문구_미리보기': '문구(미리보기)'}).style.format({
            'CTR': lambda x: f"{x:.2%}" if pd.notna(x) else '-',
            'CR': lambda x: f"{x:.2%}" if pd.notna(x) else '-',
            'ROAS': lambda x: f"{x:.1f}" if pd.notna(x) else '-',
            '모수': lambda x: f"{int(x):,}" if pd.notna(x) else '-',
            '거래액': lambda x: f"{int(x):,}" if pd.notna(x) else '-',
        }),
        use_container_width=True, height=450, hide_index=True
    )

    # 문구 전체 보기
    if st.checkbox("선택한 행 문구 전체 보기"):
        idx = st.number_input("행 번호 (0부터)", min_value=0, max_value=len(df_detail)-1, value=0)
        row = df_detail.iloc[idx]
        st.markdown(f"**캠페인명**: {row['캠페인명']}")
        st.text_area("문구 전문", value=row['문구'], height=200)

    st.caption(f"총 {len(df_detail):,}건 | CTR·CR·ROAS는 성과 데이터가 있는 건만 표시")
