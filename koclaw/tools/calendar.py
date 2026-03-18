import os
import uuid
from datetime import date, datetime, timedelta, timezone

from koclaw.core.tool import Tool

_KST = timezone(timedelta(hours=9))


class CalendarTool(Tool):
    name = "calendar"
    description = (
        "캘린더 일정을 조회, 추가, 수정, 삭제합니다. "
        "iCloud CalDAV를 지원합니다. "
        ".env에 CALDAV_URL, CALDAV_USERNAME, CALDAV_PASSWORD 설정이 필요합니다."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["calendars", "list", "create", "delete", "update"],
                "description": "calendars: 연동된 캘린더 목록 조회, list: 일정 조회, create: 일정 추가, delete: 일정 삭제, update: 일정 수정",
            },
            "title": {
                "type": "string",
                "description": "일정 제목 (create/delete/update 시 필수)",
            },
            "start": {
                "type": "string",
                "description": "시작 일시 (create/update 시, 예: '2026-03-18 14:00' 또는 '2026-03-18')",
            },
            "end": {
                "type": "string",
                "description": "종료 일시 (create/update 시, 예: '2026-03-18 15:00' 또는 '2026-03-18')",
            },
            "days": {
                "type": "integer",
                "description": "조회할 날짜 범위 (list 시, 기본값 7)",
            },
            "description": {
                "type": "string",
                "description": "일정 설명 (create/update 시 선택)",
            },
            "location": {
                "type": "string",
                "description": "장소 (create/update 시 선택)",
            },
            "calendar_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "사용할 캘린더 이름 목록 (예: ['업무', '가족']). 미지정 시 전체 캘린더 사용. 사용자가 메모리에 저장한 캘린더 목록이 있으면 그것을 사용하세요.",
            },
        },
        "required": ["action"],
    }
    is_sandboxed = False

    async def execute(
        self,
        action: str,
        title: str = "",
        start: str = "",
        end: str = "",
        days: int = 7,
        description: str = "",
        location: str = "",
        calendar_names: list[str] | None = None,
    ) -> str:
        try:
            import caldav  # noqa: F401
        except ImportError:
            return (
                "오류: caldav가 설치되지 않았습니다. "
                "`uv sync --all-extras` 또는 `pip install 'koclaw[calendar]'`을 실행하세요."
            )

        caldav_url = os.getenv("CALDAV_URL")
        caldav_username = os.getenv("CALDAV_USERNAME")
        caldav_password = os.getenv("CALDAV_PASSWORD")

        if not caldav_url or not caldav_username or not caldav_password:
            return (
                "오류: CalDAV 설정이 없습니다. "
                ".env 파일에 다음 항목을 설정하세요:\n"
                "  CALDAV_URL=https://caldav.icloud.com\n"
                "  CALDAV_USERNAME=your@icloud.com\n"
                "  CALDAV_PASSWORD=앱 전용 비밀번호 (iCloud → 보안 → 앱 전용 비밀번호)"
            )

        import asyncio

        return await asyncio.to_thread(
            self._execute_sync,
            action,
            title,
            start,
            end,
            days,
            description,
            location,
            calendar_names or [],
            caldav_url,
            caldav_username,
            caldav_password,
        )

    def _execute_sync(
        self,
        action: str,
        title: str,
        start: str,
        end: str,
        days: int,
        description: str,
        location: str,
        calendar_names: list[str],
        url: str,
        username: str,
        password: str,
    ) -> str:
        import caldav

        try:
            client = caldav.DAVClient(url=url, username=username, password=password)
            principal = client.principal()
            all_calendars = principal.calendars()
        except Exception as e:
            return f"오류: CalDAV 서버 연결에 실패했습니다 — {e}"

        if not all_calendars:
            return "오류: 사용 가능한 캘린더가 없습니다."

        filtered = _filter_calendars(all_calendars, calendar_names)

        if action == "calendars":
            return self._calendars(all_calendars)
        if action == "list":
            return self._list(filtered, days)
        if action == "create":
            return self._create(filtered[0], title, start, end, description, location)
        if action == "delete":
            return self._delete(filtered[0], title)
        if action == "update":
            return self._update(filtered[0], title, start, end, description, location)
        return f"알 수 없는 action: {action}"

    def _calendars(self, cals: list) -> str:
        lines = ["🗓️ 연동된 캘린더 목록:"]
        for cal in cals:
            name = str(getattr(cal, "name", "") or "(이름 없음)")
            lines.append(f"• {name}")
        return "\n".join(lines)

    def _list(self, cals: list, days: int) -> str:
        now = datetime.now(_KST)
        end_dt = now + timedelta(days=days)

        all_events = []
        for cal in cals:
            try:
                all_events.extend(cal.search(start=now, end=end_dt, event=True, expand=True))
            except Exception:
                pass  # 개별 캘린더 오류는 건너뜀

        if not all_events:
            return f"앞으로 {days}일 내 일정이 없습니다."

        lines = [f"📅 앞으로 {days}일 일정:"]
        for ev in sorted(all_events, key=_event_sort_key):
            summary, dt_start, dt_end, desc, loc = _parse_event(ev)
            time_str = _format_dt(dt_start)
            end_str = f" ~ {_format_dt(dt_end)}" if dt_end else ""
            line = f"• {time_str}{end_str}  {summary}"
            if loc:
                line += f"  📍{loc}"
            if desc:
                line += f"\n  {desc[:80]}"
            lines.append(line)
        return "\n".join(lines)

    def _create(
        self,
        cal: object,
        title: str,
        start: str,
        end: str,
        description: str,
        location: str,
    ) -> str:
        if not title:
            return "오류: 일정 제목(title)을 지정해주세요."
        if not start:
            return "오류: 시작 일시(start)를 지정해주세요."

        start_dt = _parse_dt(start)
        if start_dt is None:
            return f"오류: 날짜 형식을 인식할 수 없습니다: {start!r} (예: '2026-03-18 14:00')"

        if end:
            end_dt = _parse_dt(end)
            if end_dt is None:
                return f"오류: 날짜 형식을 인식할 수 없습니다: {end!r}"
        else:
            if isinstance(start_dt, date) and not isinstance(start_dt, datetime):
                end_dt = start_dt + timedelta(days=1)
            else:
                end_dt = start_dt + timedelta(hours=1)

        ical = _build_ical(title, start_dt, end_dt, description, location)
        try:
            cal.save_event(ical)
        except Exception as e:
            return f"오류: 일정 생성에 실패했습니다 — {e}"
        return f"✅ 일정이 추가되었습니다: '{title}' ({_format_dt(start_dt)})"

    def _delete(self, cal: object, title: str) -> str:
        if not title:
            return "오류: 삭제할 일정 제목(title)을 지정해주세요."

        event = _find_event_by_title(cal, title)
        if event is None:
            return f"'{title}' 일정을 찾을 수 없습니다."
        try:
            event.delete()
        except Exception as e:
            return f"오류: 일정 삭제에 실패했습니다 — {e}"
        return f"✅ '{title}' 일정이 삭제되었습니다."

    def _update(
        self,
        cal: object,
        title: str,
        start: str,
        end: str,
        description: str,
        location: str,
    ) -> str:
        if not title:
            return "오류: 수정할 일정 제목(title)을 지정해주세요."
        if not start and not end and not description and not location:
            return "오류: 변경할 내용이 없습니다. start, end, description, location 중 하나를 지정해주세요."

        event = _find_event_by_title(cal, title)
        if event is None:
            return f"'{title}' 일정을 찾을 수 없습니다."

        try:
            ical_obj = event.icalendar_instance
            vevent = ical_obj.walk("vevent")[0]
        except Exception as e:
            return f"오류: 기존 일정 파싱에 실패했습니다 — {e}"

        existing_start = vevent.get("dtstart").dt if vevent.get("dtstart") else None
        existing_end = vevent.get("dtend").dt if vevent.get("dtend") else None
        existing_desc = str(vevent.get("description", ""))
        existing_loc = str(vevent.get("location", ""))

        new_start = _parse_dt(start) if start else existing_start
        new_end = _parse_dt(end) if end else existing_end
        new_desc = description if description else existing_desc
        new_loc = location if location else existing_loc

        ical = _build_ical(title, new_start, new_end, new_desc, new_loc)
        try:
            event.delete()
            cal.save_event(ical)
        except Exception as e:
            return f"오류: 일정 수정에 실패했습니다 — {e}"
        return f"✅ '{title}' 일정이 수정되었습니다."


# ── 헬퍼 함수 ──────────────────────────────────────────────────────────────


def _filter_calendars(calendars: list, names: list[str]) -> list:
    """이름 목록에 해당하는 캘린더만 반환. 빈 목록이면 전체 반환."""
    if not names:
        return calendars
    result = [
        cal
        for cal in calendars
        if any(n.lower() in str(getattr(cal, "name", "") or "").lower() for n in names)
    ]
    return result if result else calendars


def _find_event_by_title(cal: object, title: str) -> object | None:
    """제목으로 이벤트 검색 (지난 30일 ~ 앞으로 365일)"""
    now = datetime.now(_KST)
    search_start = now - timedelta(days=30)
    search_end = now + timedelta(days=365)
    try:
        events = cal.search(start=search_start, end=search_end, event=True, expand=False)
    except Exception:
        return None
    for ev in events:
        summary, *_ = _parse_event(ev)
        if title.lower() in summary.lower():
            return ev
    return None


def _parse_event(ev: object) -> tuple[str, object, object, str, str]:
    """이벤트에서 (제목, 시작, 종료, 설명, 장소) 반환"""
    try:
        ical_obj = ev.icalendar_instance
        vevent = ical_obj.walk("vevent")[0]
        summary = str(vevent.get("summary", "(제목 없음)"))
        dt_start = vevent.get("dtstart").dt if vevent.get("dtstart") else None
        dt_end = vevent.get("dtend").dt if vevent.get("dtend") else None
        description = str(vevent.get("description", ""))
        location = str(vevent.get("location", ""))
        return summary, dt_start, dt_end, description, location
    except Exception:
        return "(파싱 오류)", None, None, "", ""


def _event_sort_key(ev: object) -> datetime:
    """이벤트를 시작 시각 기준으로 정렬하기 위한 키"""
    _, dt_start, *_ = _parse_event(ev)
    if dt_start is None:
        return datetime.max.replace(tzinfo=_KST)
    if isinstance(dt_start, datetime):
        return dt_start.astimezone(_KST) if dt_start.tzinfo else dt_start.replace(tzinfo=_KST)
    return datetime(dt_start.year, dt_start.month, dt_start.day, tzinfo=_KST)


def _format_dt(dt: object) -> str:
    """datetime 또는 date를 사람이 읽기 좋은 문자열로 변환"""
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        return (
            dt.astimezone(_KST).strftime("%m/%d %H:%M") if dt.tzinfo else dt.strftime("%m/%d %H:%M")
        )
    return dt.strftime("%m/%d (종일)")


def _parse_dt(s: str) -> datetime | date | None:
    """날짜 문자열을 datetime(KST) 또는 date로 파싱"""
    s = s.strip()
    date_only_formats = ("%Y-%m-%d", "%Y/%m/%d", "%Y년 %m월 %d일")
    datetime_formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y년 %m월 %d일 %H시 %M분",
    )
    for fmt in datetime_formats:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=_KST)
        except ValueError:
            continue
    for fmt in date_only_formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _build_ical(
    title: str,
    start: datetime | date,
    end: datetime | date,
    description: str,
    location: str,
) -> bytes:
    """iCalendar 바이트 생성"""
    from icalendar import Calendar, Event

    cal = Calendar()
    cal.add("prodid", "-//koclaw//koclaw//KO")
    cal.add("version", "2.0")

    event = Event()
    event.add("summary", title)
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add("uid", str(uuid.uuid4()))
    if description:
        event.add("description", description)
    if location:
        event.add("location", location)

    cal.add_component(event)
    return cal.to_ical()
