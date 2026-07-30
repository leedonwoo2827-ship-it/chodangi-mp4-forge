렌더 작업 폴더 (copy-and-run)
================================

이 폴더에 #2(exambook-forge)가 만든 번들을 복사해 넣고, 상위의 render.bat 를
더블클릭하면 여기 있는 번들을 전부 렌더한다. 기본 책 경로(D:\00work\ocr-output-260723)
대신 이 work\05\ 가 있으면 render.bat 가 자동으로 이쪽을 쓴다.

넣는 방법 (둘 중 아무거나)
--------------------------
1) 회차 단위로 통째:
     work\05\m01-1\   (source\deck.html, script\m01-1_script.json, images\, review.json ...)
     work\05\m01-2\
     ...
   즉 <책>\05\<번들> 의 <번들> 폴더들을 work\05\ 아래로 복사.

2) 한두 개만:
   render.bat 위로 번들 폴더(또는 그 안 script\*.json)를 드래그해도 된다.

렌더 실행
---------
- work\05\ 에 번들을 넣은 뒤 render.bat 더블클릭  → 전부 렌더
- 특정 회차만:  cmd 에서  render.bat m01-1
- 슬라이드만(음성/합성 생략):  render.bat m01-1 --no-audio

결과물
------
각 번들의  draft\<번들>.static.mp4  (일반영상) + review.json 갱신.
(audio/subtitles/draft/clips 는 .gitignore 로 커밋 제외 — 여기 work\ 도 전체 제외됨)
