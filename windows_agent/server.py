"""Windows 네이티브 데스크탑 제어 에이전트 서버.

Windows에서 직접 실행하는 FastAPI 서버입니다.
koclaw 봇(WSL/OCI)에서 HTTP로 호출해 실제 Windows 화면을 제어합니다.

실행 방법 (Windows PowerShell):
    pip install fastapi uvicorn pyautogui pyperclip pillow
    python server.py

환경변수:
    WINDOWS_AGENT_API_KEY  API 키 (설정 시 모든 요청에 X-API-Key 헤더 필요)
    WINDOWS_AGENT_PORT     포트 (기본값: 7777)
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import subprocess

import pyautogui
import pyperclip
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# 화면 모서리 이동 시 예외 방지
pyautogui.FAILSAFE = False

_API_KEY = os.environ.get("WINDOWS_AGENT_API_KEY", "").strip()
_PORT = int(os.environ.get("WINDOWS_AGENT_PORT", "7777"))

app = FastAPI(title="koclaw Windows Agent", version="1.1.0")


# ── 인증 ─────────────────────────────────────────────────


async def verify_api_key(x_api_key: str = Header(default="")) -> None:
    """API 키 검증 — WINDOWS_AGENT_API_KEY 미설정 시 인증 생략."""
    if _API_KEY and x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


Auth = Depends(verify_api_key)


# ── 요청 모델 ─────────────────────────────────────────────


class ClickRequest(BaseModel):
    x: int
    y: int
    button: int = 1  # 1=왼쪽, 2=가운데, 3=오른쪽
    double: bool = False


class TypeRequest(BaseModel):
    text: str


class KeyRequest(BaseModel):
    key_name: str  # 예: "Return", "ctrl+c", "ctrl+l"


class ScrollRequest(BaseModel):
    x: int
    y: int
    direction: str = "down"
    amount: int = 3


class DragRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    duration: float = 0.3


class CommandRequest(BaseModel):
    command: str
    timeout: float = 60.0


class ReadFileRequest(BaseModel):
    path: str


# ── 헬퍼 ────────────────────────────────────────────────


_SCREENSHOT_MAX_WIDTH = 1280  # LLM 전송용 최대 가로 픽셀


def _take_screenshot_for_llm() -> tuple[bytes, int, int, int, int]:
    """LLM 전송용 스크린샷 — JPEG로 압축 + 필요 시 리사이즈.

    Returns:
        (jpeg_bytes, orig_w, orig_h, img_w, img_h)
        img_w/img_h: LLM이 실제로 받는 이미지 해상도 (좌표 계산 기준)
    """
    img = pyautogui.screenshot()
    orig_w, orig_h = img.size
    if orig_w > _SCREENSHOT_MAX_WIDTH:
        ratio = _SCREENSHOT_MAX_WIDTH / orig_w
        img = img.resize((int(orig_w * ratio), int(orig_h * ratio)))
    img_w, img_h = img.size
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return buf.getvalue(), orig_w, orig_h, img_w, img_h


def _scale_to_screen(x: int, y: int) -> tuple[int, int]:
    """이미지 좌표(_SCREENSHOT_MAX_WIDTH 기준)를 실제 화면 좌표로 변환."""
    screen_w, screen_h = pyautogui.size()
    if screen_w <= _SCREENSHOT_MAX_WIDTH:
        return x, y
    scale = screen_w / _SCREENSHOT_MAX_WIDTH
    return int(x * scale), int(y * scale)


def _take_screenshot_jpeg(quality: int = 50) -> bytes:
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _map_button(button: int) -> str:
    return {1: "left", 2: "middle", 3: "right"}.get(button, "left")


def _parse_key(key_name: str) -> list[str]:
    """xdotool 스타일 키 이름을 pyautogui 형식으로 변환."""
    key_map = {
        "return": "enter",
        "super": "win",
        "ctrl": "ctrl",
        "alt": "alt",
        "shift": "shift",
        "escape": "esc",
        "tab": "tab",
        "space": "space",
        "backspace": "backspace",
        "delete": "delete",
        "home": "home",
        "end": "end",
        "prior": "pageup",
        "next": "pagedown",
    }
    parts = [p.strip().lower() for p in key_name.split("+")]
    return [key_map.get(p, p) for p in parts]


# ── 엔드포인트 ────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/screen_size", dependencies=[Auth])
async def screen_size():
    """LLM 좌표 계산 기준 해상도 반환 (스크린샷 이미지와 동일한 크기)."""
    orig_w, orig_h = await asyncio.to_thread(pyautogui.size)
    if orig_w > _SCREENSHOT_MAX_WIDTH:
        ratio = _SCREENSHOT_MAX_WIDTH / orig_w
        return {"width": _SCREENSHOT_MAX_WIDTH, "height": int(orig_h * ratio)}
    return {"width": orig_w, "height": orig_h}


@app.get("/screenshot", dependencies=[Auth])
async def screenshot():
    """현재 화면을 캡처해 base64 JPEG(리사이즈) + 이미지 해상도로 반환.

    width/height는 LLM이 실제로 받는 이미지 크기입니다.
    LLM은 이 해상도 기준으로 좌표를 계산해야 합니다.
    서버에서 클릭 시 실제 화면 좌표로 자동 변환합니다.
    """
    jpeg, orig_w, orig_h, img_w, img_h = await asyncio.to_thread(_take_screenshot_for_llm)
    return {
        "data": base64.b64encode(jpeg).decode(),
        "width": img_w,
        "height": img_h,
        "format": "jpeg",
    }


@app.post("/click", dependencies=[Auth])
async def click(req: ClickRequest):
    """지정 좌표 마우스 클릭 (더블클릭 지원).

    이미지 좌표(_SCREENSHOT_MAX_WIDTH 기준)를 실제 화면 좌표로 자동 변환합니다.
    """
    btn = _map_button(req.button)
    x, y = _scale_to_screen(req.x, req.y)

    def _do():
        if req.double:
            pyautogui.doubleClick(x, y, button=btn)
        else:
            pyautogui.click(x, y, button=btn)

    await asyncio.to_thread(_do)
    action = "더블클릭" if req.double else "클릭"
    return {"ok": True, "action": action}


@app.post("/type", dependencies=[Auth])
async def type_text(req: TypeRequest):
    """텍스트 입력 — 클립보드 경유로 한글 포함 모든 문자 지원."""

    def _do():
        pyperclip.copy(req.text)
        pyautogui.hotkey("ctrl", "v")

    await asyncio.to_thread(_do)
    return {"ok": True}


@app.post("/key", dependencies=[Auth])
async def key(req: KeyRequest):
    """키 입력 (예: Return, ctrl+c, ctrl+l)."""
    parts = _parse_key(req.key_name)

    def _do():
        if len(parts) > 1:
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(parts[0])

    await asyncio.to_thread(_do)
    return {"ok": True}


@app.post("/scroll", dependencies=[Auth])
async def scroll(req: ScrollRequest):
    """스크롤 — direction: 'up' | 'down'."""
    clicks = -req.amount if req.direction == "down" else req.amount
    x, y = _scale_to_screen(req.x, req.y)
    await asyncio.to_thread(pyautogui.scroll, clicks, x, y)
    return {"ok": True}


@app.post("/drag", dependencies=[Auth])
async def drag(req: DragRequest):
    """마우스 드래그."""
    x1, y1 = _scale_to_screen(req.x1, req.y1)
    x2, y2 = _scale_to_screen(req.x2, req.y2)
    await asyncio.to_thread(
        pyautogui.drag,
        x2 - x1,
        y2 - y1,
        duration=req.duration,
        startX=x1,
        startY=y1,
    )
    return {"ok": True}


@app.post("/command", dependencies=[Auth])
async def command(req: CommandRequest):
    """PowerShell 명령 실행 후 stdout+stderr 반환."""

    def _run():
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", req.command],
            capture_output=True,
            text=True,
            timeout=req.timeout,
            encoding="utf-8",
            errors="replace",
        )
        parts = []
        if result.stdout.strip():
            parts.append(result.stdout.strip())
        if result.stderr.strip():
            parts.append(f"[stderr]\n{result.stderr.strip()}")
        return "\n".join(parts) if parts else "(출력 없음)"

    try:
        output = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="명령 타임아웃")
    return {"output": output}


@app.post("/read_file", dependencies=[Auth])
async def read_file(req: ReadFileRequest):
    """Windows 파일을 읽어 base64로 반환 (copy_from 용도)."""
    from pathlib import Path

    p = Path(req.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"파일 없음: {req.path}")
    data = await asyncio.to_thread(p.read_bytes)
    return {
        "data": base64.b64encode(data).decode(),
        "name": p.name,
        "size": len(data),
    }


@app.get("/windows", dependencies=[Auth])
async def list_windows():
    """현재 열려 있는 창 목록을 반환한다 (MainWindowTitle이 있는 프로세스만)."""

    def _run():
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process | Where-Object { $_.MainWindowTitle -ne '' } "
                "| Select-Object Name, MainWindowTitle "
                "| ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip()

    import json as _json

    raw = await asyncio.to_thread(_run)
    try:
        data = _json.loads(raw) if raw else []
        # 단일 항목이면 리스트로 감싸기
        if isinstance(data, dict):
            data = [data]
    except _json.JSONDecodeError:
        data = []
    return {"windows": data}


# ── Playwright 브라우저 엔드포인트 ───────────────────────────────────────────


class BrowserNavigateRequest(BaseModel):
    url: str
    wait_until: str = "domcontentloaded"


class BrowserClickRequest(BaseModel):
    selector: str


class BrowserTypeRequest(BaseModel):
    selector: str
    text: str
    clear_first: bool = True


class BrowserScrollRequest(BaseModel):
    direction: str = "down"
    amount: int = 3


class BrowserEvaluateRequest(BaseModel):
    script: str


class BrowserWaitForRequest(BaseModel):
    selector: str
    timeout: float = 10.0


class BrowserSelectRequest(BaseModel):
    selector: str
    value: str


def _get_browser():
    """Playwright 브라우저 인스턴스를 반환 (없으면 예외)."""
    if _pw_page is None:
        raise HTTPException(
            status_code=503,
            detail="브라우저가 시작되지 않았습니다. /browser/navigate로 먼저 URL을 열어주세요.",
        )
    return _pw_page


# Playwright 전역 상태
_pw_playwright = None
_pw_browser = None
_pw_page = None


async def _ensure_browser():
    """Playwright 브라우저가 없으면 시작한다. Chromium 미설치 시 자동 설치."""
    global _pw_playwright, _pw_browser, _pw_page
    if _pw_page is not None:
        return _pw_page
    from playwright.async_api import async_playwright

    _pw_playwright = await async_playwright().start()
    try:
        _pw_browser = await _pw_playwright.chromium.launch(headless=False)
    except Exception:
        # Chromium 바이너리 없으면 자동 설치 후 재시도
        await asyncio.to_thread(
            subprocess.run,
            ["playwright", "install", "chromium"],
            check=True,
        )
        _pw_browser = await _pw_playwright.chromium.launch(headless=False)
    _pw_page = await _pw_browser.new_page()
    return _pw_page


@app.post("/browser/navigate", dependencies=[Auth])
async def browser_navigate(req: BrowserNavigateRequest):
    """URL로 이동."""
    page = await _ensure_browser()
    await page.goto(req.url, wait_until=req.wait_until)
    return {"ok": True, "url": page.url, "title": await page.title()}


@app.get("/browser/screenshot", dependencies=[Auth])
async def browser_screenshot():
    """브라우저 현재 화면 캡처 — base64 JPEG."""
    page = _get_browser()
    jpeg = await page.screenshot(type="jpeg", quality=75)
    vp = page.viewport_size or {"width": 1280, "height": 720}
    return {
        "data": base64.b64encode(jpeg).decode(),
        "width": vp["width"],
        "height": vp["height"],
        "format": "jpeg",
    }


@app.post("/browser/click", dependencies=[Auth])
async def browser_click(req: BrowserClickRequest):
    """selector로 요소 클릭."""
    page = _get_browser()
    await page.click(req.selector)
    return {"ok": True}


@app.post("/browser/type", dependencies=[Auth])
async def browser_type(req: BrowserTypeRequest):
    """selector 요소에 텍스트 입력."""
    page = _get_browser()
    if req.clear_first:
        await page.fill(req.selector, req.text)
    else:
        await page.type(req.selector, req.text)
    return {"ok": True}


@app.post("/browser/scroll", dependencies=[Auth])
async def browser_scroll(req: BrowserScrollRequest):
    """페이지 스크롤."""
    page = _get_browser()
    delta = req.amount * 300
    if req.direction == "up":
        delta = -delta
    await page.evaluate(f"window.scrollBy(0, {delta})")
    return {"ok": True}


@app.post("/browser/evaluate", dependencies=[Auth])
async def browser_evaluate(req: BrowserEvaluateRequest):
    """JavaScript 실행."""
    page = _get_browser()
    result = await page.evaluate(req.script)
    return {"result": str(result) if result is not None else "(결과 없음)"}


@app.get("/browser/content", dependencies=[Auth])
async def browser_content():
    """현재 페이지 텍스트 내용."""
    page = _get_browser()
    title = await page.title()
    url = page.url
    content = await page.evaluate("document.body.innerText")
    return {"title": title, "url": url, "content": content[:5000]}


@app.post("/browser/wait_for", dependencies=[Auth])
async def browser_wait_for(req: BrowserWaitForRequest):
    """selector가 나타날 때까지 대기."""
    page = _get_browser()
    await page.wait_for_selector(req.selector, timeout=req.timeout * 1000)
    return {"ok": True}


@app.post("/browser/select", dependencies=[Auth])
async def browser_select(req: BrowserSelectRequest):
    """<select> 요소 선택."""
    page = _get_browser()
    await page.select_option(req.selector, req.value)
    return {"ok": True}


@app.post("/browser/close", dependencies=[Auth])
async def browser_close():
    """브라우저 닫기."""
    global _pw_playwright, _pw_browser, _pw_page
    if _pw_page is not None:
        await _pw_page.close()
        _pw_page = None
    if _pw_browser is not None:
        await _pw_browser.close()
        _pw_browser = None
    if _pw_playwright is not None:
        await _pw_playwright.stop()
        _pw_playwright = None
    return {"ok": True}


@app.get("/stream")
async def stream():
    """MJPEG 스트림 — 브라우저에서 실시간 화면 시청 (인증 불필요)."""

    async def generate():
        while True:
            jpeg = await asyncio.to_thread(_take_screenshot_jpeg)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
            await asyncio.sleep(0.5)  # 2 FPS

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/view", response_class=HTMLResponse)
async def view():
    """브라우저에서 실시간 화면을 볼 수 있는 간단한 뷰어 (인증 불필요)."""
    return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>koclaw — Windows 화면 실시간 보기</title>
  <style>
    body { margin: 0; background: #111; display: flex; justify-content: center; align-items: center; height: 100vh; }
    img { max-width: 100%; max-height: 100vh; object-fit: contain; }
  </style>
</head>
<body>
  <img src="/stream" alt="Windows 화면">
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=_PORT)
