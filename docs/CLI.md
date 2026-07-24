# mp4maker CLI 옵션

```
python -m mp4maker <bundle> [옵션]
python -m mp4maker --probe              # ffmpeg/폰트/패키지 점검
python -m mp4maker <bundle> --dry-run   # 검증 + 계획만 (ffmpeg 호출 없음)
```
종료코드: 0=성공, 2=입력/검증 오류.

## 자주 쓰는 옵션
| 옵션 | 기본 | 설명 |
|---|---|---|
| `--only 1,3` | — | 특정 씬만 렌더 |
| `--keep-work` | off | 임시폴더(_work) 보존 |
| `--resolution` | 1920x1080 | 출력 해상도 |
| `--fps` | 30 | 프레임레이트 |
| `--crossfade` | 0.6 | 씬 전환 길이(초) |

## 화질/용량 (YouTube 친화 — mediaforge 기본값)
| 옵션 | 기본 | 설명 |
|---|---|---|
| `--crf` | **20** | 작을수록 고화질·큰 용량 (18=고화질, 23=작은 용량) |
| `--maxrate` | **12M** | 비트레이트 상한(≈YouTube 1080p 권장). `""`=무제한 |
| `--bufsize` | 24M | 비트레이트 버퍼 |
| `--audio-bitrate` | 128k | 오디오 비트레이트 |
| `--preset` | medium | x264 속도/효율 |

> 용량을 더 줄이려면 `--crf 23` 또는 `--maxrate 8M`. 화질을 더 높이려면 `--crf 18 --maxrate ""`.

## 자막 (한 줄에 더 많이 → 둘째 줄 방지)
| 옵션 | 기본 | 설명 |
|---|---|---|
| `--wrap-chars` | **50** | 한 줄 최대 글자수(넘으면 줄바꿈). 키우면 한 줄에 더 들어감 |
| `--font-size` | **14** | 자막 폰트 크기(약간 작게 → 한 줄에 더 들어감) |
| `--max-cue-seconds` | 7.0 | 이 길이 넘는 자막은 분할(표시 시간 상한) |
| `--no-split-subs` | off | 긴 자막을 분할하지 않음 |
| `--margin-v` | 40 | 자막 하단 여백 |

## stdout 진행률 태그 (mediaforge가 파싱)
```
[bundle] chNN '<title>'  scenes=N
[scene]  scNN done  (T.Ts)  progress=K/N
[done]   <output path>
[total]  T.Ts
```
