"""발음 변환 — 숫자·영어를 소리 나는 대로 한글로 바꾼 '읽기용' 텍스트 생성.

TTS 가 영어를 글자 단위로 읽는(CREATE→씨알이에이티이) 문제를 피한다. **규칙 기반**(용어 사전)
이라 LLM 을 쓰지 않는다 → 할당량(quota) 걱정 없이 즉시·무료·안정. 사전에 없는 용어는
config/reading_map.yaml 에 추가하거나 발음사전(/dict)으로 보완한다.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

_CONFIG = Path(__file__).resolve().parents[1] / "config" / "reading_map.yaml"

# 기본 읽기 사전 (SQLD 빈출 영어·약어 → 한글 소리). 다단어는 길이순으로 먼저 치환된다.
_DEFAULT_READINGS: dict[str, str] = {
    "GROUP BY": "그룹 바이", "ORDER BY": "오더 바이", "UNION ALL": "유니온 올",
    "NOT NULL": "낫 널", "IS NULL": "이즈 널", "IS NOT NULL": "이즈 낫 널",
    "ON DELETE SET NULL": "온 딜리트 셋 널", "ON DELETE CASCADE": "온 딜리트 캐스케이드",
    "PRIMARY KEY": "프라이머리 키", "FOREIGN KEY": "포린 키", "INNER JOIN": "이너 조인",
    "OUTER JOIN": "아우터 조인", "LEFT OUTER": "레프트 아우터", "RIGHT OUTER": "라이트 아우터",
    "FULL OUTER": "풀 아우터", "CROSS JOIN": "크로스 조인", "START WITH": "스타트 위드",
    "CONNECT BY": "커넥트 바이", "ROW_NUMBER": "로우 넘버", "DENSE_RANK": "덴스 랭크",
    "SELECT": "셀렉트", "INSERT": "인서트", "UPDATE": "업데이트", "DELETE": "딜리트",
    "CREATE": "크리에이트", "ALTER": "얼터", "DROP": "드롭", "TRUNCATE": "트렁케이트",
    "GRANT": "그랜트", "REVOKE": "리보크", "COMMIT": "커밋", "ROLLBACK": "롤백",
    "SAVEPOINT": "세이브포인트", "WHERE": "웨어", "HAVING": "해빙", "FROM": "프롬",
    "DISTINCT": "디스팅트", "UNIQUE": "유니크", "UNION": "유니온", "INTERSECT": "인터섹트",
    "MINUS": "마이너스", "EXISTS": "이그지스츠", "BETWEEN": "비트윈", "JOIN": "조인",
    "ROLLUP": "롤업", "CUBE": "큐브", "RANK": "랭크", "NTILE": "엔타일", "LISTAGG": "리스트애그",
    "NVL": "엔브이엘", "NULLIF": "널이프", "COALESCE": "코얼레스", "DECODE": "디코드",
    "PIVOT": "피벗", "UNPIVOT": "언피벗", "CASCADE": "캐스케이드", "RESTRICT": "리스트릭트",
    "DDL": "디디엘", "DML": "디엠엘", "DCL": "디씨엘", "TCL": "티씨엘", "SQL": "에스큐엘",
    "SQLD": "에스큐엘디", "ERD": "이알디", "ACID": "에이시아이디", "NULL": "널",
    "PK": "피케이", "FK": "에프케이", "1NF": "제일정규형", "2NF": "제이정규형",
    "3NF": "제삼정규형", "BCNF": "비씨엔에프", "IN": "인", "ANY": "애니", "ALL": "올",
    "TOP": "탑", "GROUP": "그룹", "ONLY": "온리", "EQUALS": "이퀄즈", "PRIOR": "프라이어",
    "ATOMICITY": "어토미시티", "CONSISTENCY": "컨시스턴시", "DURABILITY": "듀러빌리티",
    "OPTIONALITY": "옵셔낼리티", "CARDINALITY": "카디낼리티", "ENTITY": "엔터티",
    "ATTRIBUTE": "애트리뷰트", "IDENTIFIER": "아이덴티파이어",
}

_KOR_NUM = {"1": "일", "2": "이", "3": "삼", "4": "사", "5": "오",
            "6": "육", "7": "칠", "8": "팔", "9": "구", "10": "십"}


@lru_cache(maxsize=1)
def _readings() -> dict[str, str]:
    m = dict(_DEFAULT_READINGS)
    try:
        if _CONFIG.is_file():
            import yaml
            extra = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
            for k, v in extra.items():
                m[str(k)] = str(v)
    except Exception:
        pass
    return m


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[re.Pattern, str]]:
    m = _readings()
    out = []
    for term in sorted(m, key=len, reverse=True):     # 다단어 우선
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.IGNORECASE)
        out.append((pat, m[term]))
    return out


def _num_before_bun(text: str) -> str:
    """'1번' 같은 표기의 숫자를 한글로 (일번, 이번…). 1~10만."""
    def rep(mo):
        n = mo.group(1)
        return _KOR_NUM.get(n, n) + "번"
    return re.sub(r"(?<!\d)(10|[1-9])번", rep, text)


def to_reading(text: str, model: Optional[str] = None) -> str:
    """낭독 텍스트 → 소리 나는 대로 한글 읽기(규칙 기반). model 인자는 호환용(미사용)."""
    t = (text or "").strip()
    if not t:
        return ""
    for pat, rep in _compiled():
        t = pat.sub(rep, t)
    t = _num_before_bun(t)
    return t
