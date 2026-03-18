"""CalendarTool 단위 테스트 — caldav, 외부 서버 없이 mock으로 격리"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from koclaw.tools.calendar import (
    CalendarTool,
    _build_ical,
    _format_dt,
    _parse_dt,
)

_KST = timezone(timedelta(hours=9))


# ── _parse_dt ──────────────────────────────────────────────────────────────


def test_parse_dt_datetime_hyphen():
    result = _parse_dt("2026-03-18 14:00")
    assert isinstance(result, datetime)
    assert result.year == 2026
    assert result.month == 3
    assert result.day == 18
    assert result.hour == 14


def test_parse_dt_date_only():
    result = _parse_dt("2026-03-18")
    assert isinstance(result, date)
    assert not isinstance(result, datetime)


def test_parse_dt_korean_datetime():
    result = _parse_dt("2026년 03월 18일 14시 30분")
    assert isinstance(result, datetime)
    assert result.hour == 14
    assert result.minute == 30


def test_parse_dt_invalid():
    assert _parse_dt("not-a-date") is None


# ── _format_dt ─────────────────────────────────────────────────────────────


def test_format_dt_datetime():
    dt = datetime(2026, 3, 18, 14, 0, tzinfo=_KST)
    assert _format_dt(dt) == "03/18 14:00"


def test_format_dt_date_only():
    d = date(2026, 3, 18)
    assert _format_dt(d) == "03/18 (종일)"


def test_format_dt_none():
    assert _format_dt(None) == ""


# ── _filter_calendars ──────────────────────────────────────────────────────


def test_filter_calendars_empty_names_returns_all():
    from koclaw.tools.calendar import _filter_calendars

    cal1, cal2 = MagicMock(), MagicMock()
    assert _filter_calendars([cal1, cal2], []) == [cal1, cal2]


def test_filter_calendars_by_single_name():
    from koclaw.tools.calendar import _filter_calendars

    cal1 = MagicMock()
    cal1.name = "업무"
    cal2 = MagicMock()
    cal2.name = "개인"
    result = _filter_calendars([cal1, cal2], ["개인"])
    assert result == [cal2]


def test_filter_calendars_by_multiple_names():
    from koclaw.tools.calendar import _filter_calendars

    cal1 = MagicMock()
    cal1.name = "업무"
    cal2 = MagicMock()
    cal2.name = "개인"
    cal3 = MagicMock()
    cal3.name = "가족"
    result = _filter_calendars([cal1, cal2, cal3], ["업무", "가족"])
    assert cal1 in result
    assert cal3 in result
    assert cal2 not in result


def test_filter_calendars_not_found_returns_all():
    from koclaw.tools.calendar import _filter_calendars

    cal1 = MagicMock()
    cal1.name = "업무"
    result = _filter_calendars([cal1], ["없는캘린더"])
    assert result == [cal1]


# ── _build_ical ────────────────────────────────────────────────────────────


def test_build_ical_contains_title():
    start = datetime(2026, 3, 18, 14, 0, tzinfo=_KST)
    end = datetime(2026, 3, 18, 15, 0, tzinfo=_KST)
    ical = _build_ical("팀 미팅", start, end, "", "")
    assert b"SUMMARY" in ical
    assert "팀 미팅".encode() in ical


def test_build_ical_with_description_and_location():
    start = datetime(2026, 3, 18, 14, 0, tzinfo=_KST)
    end = datetime(2026, 3, 18, 15, 0, tzinfo=_KST)
    ical = _build_ical("회의", start, end, "분기 리뷰", "회의실 A")
    assert b"DESCRIPTION" in ical
    assert b"LOCATION" in ical


# ── CalendarTool.execute (환경변수 없음) ────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_missing_env():
    tool = CalendarTool()
    with patch.dict("os.environ", {}, clear=True):
        # caldav import는 성공하도록 mock
        with patch.dict("sys.modules", {"caldav": MagicMock()}):
            result = await tool.execute(action="list")
    assert "CALDAV_URL" in result or "CalDAV 설정" in result


@pytest.mark.asyncio
async def test_execute_missing_caldav_library():
    tool = CalendarTool()

    with patch.dict("sys.modules", {"caldav": None}):
        # builtins.__import__ 대신 sys.modules에 None 삽입으로 ImportError 시뮬레이션
        # caldav import 실패 시 안내 메시지 반환
        result = await tool.execute(action="list")
    assert "caldav" in result.lower() or "설치" in result


# ── CalendarTool._list ─────────────────────────────────────────────────────


# ── CalendarTool._calendars ────────────────────────────────────────────────


def test_calendars_lists_names():
    tool = CalendarTool()
    cal1 = MagicMock()
    cal1.name = "업무"
    cal2 = MagicMock()
    cal2.name = "가족"
    result = tool._calendars([cal1, cal2])
    assert "업무" in result
    assert "가족" in result
    assert "🗓️" in result


def _make_mock_event(summary: str, start_dt: datetime, end_dt: datetime) -> MagicMock:
    """테스트용 caldav 이벤트 mock 생성"""
    from icalendar import Calendar, Event

    cal = Calendar()
    cal.add("prodid", "-//test//test//KO")
    cal.add("version", "2.0")
    ev = Event()
    ev.add("summary", summary)
    ev.add("dtstart", start_dt)
    ev.add("dtend", end_dt)
    ev.add("uid", "test-uid-1234")
    cal.add_component(ev)

    mock_ev = MagicMock()
    mock_ev.icalendar_instance = cal
    return mock_ev


def test_list_no_events():
    tool = CalendarTool()
    mock_cal = MagicMock()
    mock_cal.search.return_value = []
    result = tool._list([mock_cal], 7)
    assert "없습니다" in result


def test_list_with_events():
    tool = CalendarTool()
    now = datetime.now(_KST)
    mock_ev = _make_mock_event("팀 스탠드업", now + timedelta(hours=1), now + timedelta(hours=2))
    mock_cal = MagicMock()
    mock_cal.search.return_value = [mock_ev]

    result = tool._list([mock_cal], 7)
    assert "팀 스탠드업" in result
    assert "📅" in result


def test_list_multiple_calendars():
    """여러 캘린더의 일정을 합쳐서 반환하는지 확인"""
    tool = CalendarTool()
    now = datetime.now(_KST)
    ev1 = _make_mock_event("업무 미팅", now + timedelta(hours=1), now + timedelta(hours=2))
    ev2 = _make_mock_event("개인 운동", now + timedelta(hours=3), now + timedelta(hours=4))

    mock_cal1 = MagicMock()
    mock_cal1.search.return_value = [ev1]
    mock_cal2 = MagicMock()
    mock_cal2.search.return_value = [ev2]

    result = tool._list([mock_cal1, mock_cal2], 7)
    assert "업무 미팅" in result
    assert "개인 운동" in result


def test_list_one_calendar_error_others_succeed():
    """일부 캘린더 오류가 나도 나머지 결과를 반환하는지 확인"""
    tool = CalendarTool()
    now = datetime.now(_KST)
    ev = _make_mock_event("정상 일정", now + timedelta(hours=1), now + timedelta(hours=2))

    mock_ok = MagicMock()
    mock_ok.search.return_value = [ev]
    mock_err = MagicMock()
    mock_err.search.side_effect = Exception("연결 오류")

    result = tool._list([mock_err, mock_ok], 7)
    assert "정상 일정" in result


# ── CalendarTool._create ───────────────────────────────────────────────────


def test_create_missing_title():
    tool = CalendarTool()
    mock_cal = MagicMock()
    result = tool._create(mock_cal, "", "2026-03-18 14:00", "", "", "")
    assert "title" in result or "제목" in result


def test_create_missing_start():
    tool = CalendarTool()
    mock_cal = MagicMock()
    result = tool._create(mock_cal, "회의", "", "", "", "")
    assert "start" in result or "시작" in result


def test_create_invalid_start():
    tool = CalendarTool()
    mock_cal = MagicMock()
    result = tool._create(mock_cal, "회의", "not-a-date", "", "", "")
    assert "오류" in result


def test_create_success():
    tool = CalendarTool()
    mock_cal = MagicMock()
    mock_cal.save_event.return_value = None
    result = tool._create(mock_cal, "팀 미팅", "2026-03-18 14:00", "2026-03-18 15:00", "", "")
    assert "✅" in result
    assert "팀 미팅" in result
    mock_cal.save_event.assert_called_once()


def test_create_end_defaults_to_one_hour_later():
    tool = CalendarTool()
    mock_cal = MagicMock()
    mock_cal.save_event.return_value = None
    result = tool._create(mock_cal, "회의", "2026-03-18 14:00", "", "", "")
    assert "✅" in result


def test_create_all_day_event():
    tool = CalendarTool()
    mock_cal = MagicMock()
    mock_cal.save_event.return_value = None
    result = tool._create(mock_cal, "휴가", "2026-03-20", "", "", "")
    assert "✅" in result


# ── CalendarTool._delete ───────────────────────────────────────────────────


def test_delete_missing_title():
    tool = CalendarTool()
    mock_cal = MagicMock()
    result = tool._delete(mock_cal, "")
    assert "title" in result or "제목" in result


def test_delete_not_found():
    tool = CalendarTool()
    mock_cal = MagicMock()
    mock_cal.search.return_value = []
    result = tool._delete(mock_cal, "없는 일정")
    assert "찾을 수 없습니다" in result


def test_delete_success():
    tool = CalendarTool()
    now = datetime.now(_KST)
    mock_ev = _make_mock_event("팀 미팅", now + timedelta(hours=1), now + timedelta(hours=2))
    mock_cal = MagicMock()
    mock_cal.search.return_value = [mock_ev]

    result = tool._delete(mock_cal, "팀 미팅")
    assert "✅" in result
    mock_ev.delete.assert_called_once()


# ── CalendarTool._update ───────────────────────────────────────────────────


def test_update_missing_title():
    tool = CalendarTool()
    mock_cal = MagicMock()
    result = tool._update(mock_cal, "", "2026-03-18 15:00", "", "", "")
    assert "title" in result or "제목" in result


def test_update_no_changes():
    tool = CalendarTool()
    mock_cal = MagicMock()
    result = tool._update(mock_cal, "팀 미팅", "", "", "", "")
    assert "변경할 내용" in result


def test_update_not_found():
    tool = CalendarTool()
    mock_cal = MagicMock()
    mock_cal.search.return_value = []
    result = tool._update(mock_cal, "없는 일정", "2026-03-18 15:00", "", "", "")
    assert "찾을 수 없습니다" in result


def test_update_success():
    tool = CalendarTool()
    now = datetime.now(_KST)
    mock_ev = _make_mock_event("팀 미팅", now + timedelta(hours=1), now + timedelta(hours=2))
    mock_cal = MagicMock()
    mock_cal.search.return_value = [mock_ev]
    mock_cal.save_event.return_value = None

    result = tool._update(mock_cal, "팀 미팅", "2026-03-19 10:00", "", "", "강남역 카페")
    assert "✅" in result
    mock_ev.delete.assert_called_once()
    mock_cal.save_event.assert_called_once()
