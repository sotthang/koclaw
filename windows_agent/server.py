"""Windows 네이티브 데스크탑 제어 에이전트 서버.

Windows에서 직접 실행하는 FastAPI 서버입니다.
koclaw 봇(WSL/OCI)에서 HTTP로 호출해 실제 Windows 화면을 제어합니다.

실행 방법 (Windows PowerShell):
    pip install fastapi uvicorn pyautogui pyperclip pillow
    python server.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import subprocess

import pyautogui
import pyperclip
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# 화면 모서리 이동 시 예외 방지
pyautogui.FAILSAFE = False

app = FastAPI(title="koclaw Windows Agent", version="1.0.0")


# ── 요청 모델 ─────────────────────────────────────────────


class ClickRequest(BaseModel):
    x: int
    y: int
    button: int = 1  # 1=왼쪽, 2=가운데, 3=오른쪽


class TypeRequest(BaseModel):
    text: str


class KeyRequest(BaseModel):
    key_name: str  # 예: "Return", "ctrl+c", "ctrl+l"


class ScrollRequest(BaseModel):
    x: int
    y: int
    direction: str = "down"
    amount: int = 3


class CommandRequest(BaseModel):
    command: str
    timeout: float = 60.0


class ReadFileRequest(BaseModel):
    path: str


# ── 헬퍼 ────────────────────────────────────────────────


def _take_screenshot_png() -> bytes:
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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


@app.get("/screenshot")
async def screenshot():
    """현재 화면을 캡처해 base64 PNG로 반환."""
    png = await asyncio.to_thread(_take_screenshot_png)
    return {"data": base64.b64encode(png).decode()}


@app.post("/click")
async def click(req: ClickRequest):
    """지정 좌표 마우스 클릭."""
    btn = _map_button(req.button)
    await asyncio.to_thread(pyautogui.click, req.x, req.y, button=btn)
    return {"ok": True}


@app.post("/type")
async def type_text(req: TypeRequest):
    """텍스트 입력 — 클립보드 경유로 한글 포함 모든 문자 지원."""

    def _do():
        pyperclip.copy(req.text)
        pyautogui.hotkey("ctrl", "v")

    await asyncio.to_thread(_do)
    return {"ok": True}


@app.post("/key")
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


@app.post("/scroll")
async def scroll(req: ScrollRequest):
    """스크롤 — direction: 'up' | 'down'."""
    clicks = -req.amount if req.direction == "down" else req.amount
    await asyncio.to_thread(pyautogui.scroll, clicks, req.x, req.y)
    return {"ok": True}


@app.post("/command")
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


@app.post("/read_file")
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


@app.get("/stream")
async def stream():
    """MJPEG 스트림 — 브라우저에서 실시간 화면 시청."""

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
    """브라우저에서 실시간 화면을 볼 수 있는 간단한 뷰어."""
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
    uvicorn.run(app, host="0.0.0.0", port=7777)
