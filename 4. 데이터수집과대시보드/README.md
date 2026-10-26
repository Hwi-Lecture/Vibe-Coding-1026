# 유가 실습 체크포인트

명령은 각 단계 폴더 안의 터미널에서 실행합니다.

| 단계 폴더 | 시작 방법 |
| --- | --- |
| `checkpoint/1. 데이터수집` | `python collect_opinet.py` |
| `checkpoint/2. 수집결과정리` | `python make_opinet_excel.py` |
| `checkpoint/3. 메일전송기능추가` | `python send_opinet_email.py --to recipient@example.com --dry-run` |
| `checkpoint/4. 정적대시보드` | `python build_dashboard.py` 후 html_dashboard.html 열기 |
| `checkpoint/5. 동적대시보드` | 해당 폴더 README에 따라 서버 실행 |

CSV·엑셀 예시는 2026-10-23 기준입니다. 새로 수집하면 실행일 기준 자료가 생성됩니다.

## 설정

실습 루트의 `.env.sample`을 `.env`로 복사합니다. 수집·메일 코드는 이 공통 설정과 현재 단계의 `.env`를 읽습니다. 같은 항목은 단계 폴더 값이 우선하고 환경변수가 가장 우선합니다.

- 수집: `opinet_api_key`
- 메일: `email_address`, `gmail_app_password`
- 동적 화면의 AI 기능: 그 단계의 `.env.example`과 README 참고

API 문서는 노션에 따라 오피넷에서 내려받습니다. 키가 없어도 제공된 CSV로 엑셀과 정적 화면을 확인할 수 있습니다.

## 복사해 이어가기

원하는 단계 폴더의 파일과 하위 data 폴더 전체를 새 빈 작업 폴더로 복사하고 그 폴더를 엽니다. 필요한 `.env`를 준비한 뒤 명령을 실행합니다.

동적 단계만 별도로 복사할 때는 앞 단계의 data 폴더도 동적 폴더 안으로 복사하면 저장 자료를 사용할 수 있습니다. 제공된 구조에서 직접 실행할 때는 앞 단계의 CSV를 자동으로 찾습니다.

## 정적 화면 다시 만들기

생성 코드는 현재 단계의 data/opinet/날짜 아래에서 가장 최근 엑셀을 선택합니다. 다른 파일은 지정할 수 있습니다.

```powershell
python build_dashboard.py --source "유가_기간비교.xlsx"
```

`template.html`은 생성용 화면 틀이므로 코드와 함께 보관합니다. 완성된 `html_dashboard.html`은 데이터를 포함하므로 단독으로 열 수 있습니다.

## 메일 확인

`--dry-run`은 구성을 확인하고 실제로 전송하지 않습니다. 본인 수신 주소·첨부파일을 확인한 뒤 실제 발송을 원할 때만 옵션을 뺍니다. 앱 비밀번호를 사용할 수 없는 계정은 코드와 첨부 구성만 확인합니다.
