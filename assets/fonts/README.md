# 슬라이드 폰트 (선택)

슬라이드 렌더러(`slides/`)는 이 폴더의 Pretendard TTF 를 우선 사용합니다. 없으면
자동으로 시스템 한글 폰트(맑은 고딕 등, `mp4maker.fonts.find_font()`)로 폴백하므로
**이 폴더가 비어 있어도 동작**합니다.

브랜드 톤(Pretendard)을 맞추려면 아래 파일을 이 폴더에 넣으세요:

- `Pretendard-Bold.ttf`
- `Pretendard-Regular.ttf`

다운로드: https://github.com/orioncactus/pretendard/releases (dist/public/static 의 TTF)

폰트가 어디서 로드됐는지는 다음으로 확인할 수 있습니다:

    python -m slides <bundle>      # 첫 줄에 "font: ..." 출력
