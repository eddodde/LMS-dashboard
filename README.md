# 📱 LMS 발송 성과 대시보드

문자(SMS/LMS) 발송 데이터를 기반으로 채널별 실적, 문구 키워드 영향도, 월별 트렌드를 시각화하는 Streamlit 대시보드입니다.

## 분석 내용

- **채널별 분석**: SMS vs LMS 성과 비교 (CTR, CR, ROAS)
- **월별 트렌드**: 채널별 성과 추이
- **문구 키워드 분석**: NLP 기반 키워드 빈도 및 성과 리프트
- **캠페인 상세**: 전체 캠페인 검색/정렬

## 실행 방법

```bash
# 패키지 설치
pip install -r requirements.txt

# 실행
streamlit run app.py
```

## 데이터 파일

아래 두 파일을 `app.py`와 같은 폴더에 위치시키세요:

- `26년_타_부서_요청_LMS_발송_건.xlsx`
- `26년_멤버십_LMS_발송_건.xlsx`

각 파일은 `1. 발송`, `2. 성과` 시트를 포함해야 합니다.

## 배포 (Streamlit Cloud)

1. 이 레포를 GitHub에 push
2. [streamlit.io/cloud](https://streamlit.io/cloud) 에서 레포 연결
3. Main file: `app.py` 설정 후 Deploy
