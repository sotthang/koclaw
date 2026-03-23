import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from koclaw.app import create_provider
from koclaw.channels import match_registry
from koclaw.core.computer_use_manager import ComputerUseManager
from koclaw.core.scheduler_loop import SchedulerLoop
from koclaw.core.tool import ToolRegistry
from koclaw.core.windows_computer_use_manager import WindowsComputerUseManager
from koclaw.storage.db import Database
from koclaw.tools.browse import BrowseTool
from koclaw.tools.calendar import CalendarTool
from koclaw.tools.computer_use import ComputerUseTool
from koclaw.tools.docker_logs import DockerLogsTool
from koclaw.tools.email import EmailTool
from koclaw.tools.rss import RssFeedTool
from koclaw.tools.search import SearchTool
from koclaw.tools.weather import WeatherTool
from koclaw.tools.youtube import YouTubeTool

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STORAGE_DIR = Path("storage")
DB_PATH = STORAGE_DIR / "koclaw.db"
WORKSPACE_DIR = STORAGE_DIR / "workspace"


async def main():
    STORAGE_DIR.mkdir(exist_ok=True)
    WORKSPACE_DIR.mkdir(exist_ok=True)

    db = Database(DB_PATH)
    await db.initialize()

    env = dict(os.environ)
    provider = create_provider(env)

    tools = ToolRegistry()
    tools.register(SearchTool())
    tools.register(BrowseTool())
    tools.register(YouTubeTool())
    tools.register(RssFeedTool())
    tools.register(EmailTool())
    tools.register(WeatherTool())
    tools.register(CalendarTool())
    tools.register(DockerLogsTool())

    computer_use_manager: ComputerUseManager | WindowsComputerUseManager | None = None
    windows_agent_url = env.get("WINDOWS_AGENT_URL", "").strip()
    if windows_agent_url:
        windows_agent_api_key = env.get("WINDOWS_AGENT_API_KEY", "").strip()
        windows_agent_view_url = env.get("WINDOWS_AGENT_VIEW_URL", "").strip()
        from koclaw.tools.browser import BrowserTool
        from koclaw.tools.windows_file import WindowsFileTool
        from koclaw.tools.windows_shell import WindowsShellTool

        computer_use_manager = WindowsComputerUseManager(
            url=windows_agent_url,
            api_key=windows_agent_api_key,
            view_url=windows_agent_view_url,
        )
        tools.register(ComputerUseTool(manager=computer_use_manager))
        tools.register(BrowserTool(manager=computer_use_manager))
        tools.register(WindowsShellTool(manager=computer_use_manager))
        tools.register(WindowsFileTool(manager=computer_use_manager))
        logger.info(
            "🖥️  Windows Agent 감지됨 — computer_use + browser + windows_shell + windows_file 활성화 (%s)",
            windows_agent_url,
        )
    elif shutil.which("docker"):
        host_workspace = Path(os.environ.get("HOST_WORKSPACE_DIR", str(WORKSPACE_DIR)))
        computer_use_manager = ComputerUseManager(
            workspace=WORKSPACE_DIR,
            host_workspace=host_workspace,
            db=db,
        )
        await computer_use_manager.restore_containers()
        tools.register(ComputerUseTool(manager=computer_use_manager))
        logger.info("🖥️  Docker 감지됨 — computer_use 활성화")
    else:
        logger.warning("⚠️  Docker 없음, WINDOWS_AGENT_URL 미설정 — computer_use 비활성화")

    tools.load_installed()

    # MCP 서버 연결 (mcp_servers.json 존재 시)
    from koclaw.core.mcp_loader import load_mcp_servers

    mcp_config_path = Path(env.get("MCP_SERVERS_CONFIG", "mcp_servers.json"))
    mcp_manager = await load_mcp_servers(mcp_config_path, tools)

    # DelegateTool은 provider와 완성된 registry가 필요하므로 마지막에 등록
    from koclaw.tools.delegate import DelegateTool

    tools.register(DelegateTool(provider=provider, registry=tools))

    notify_registry: dict[str, Any] = {}
    agent_registry: dict[str, Any] = {}
    runners = []

    if env.get("SLACK_BOT_TOKEN") and env.get("SLACK_APP_TOKEN"):
        from koclaw.channels import slack

        runners.append(
            slack.start(
                env,
                provider,
                tools,
                db,
                workspace=WORKSPACE_DIR,
                notify_registry=notify_registry,
                agent_registry=agent_registry,
                computer_use_manager=computer_use_manager,
            )
        )
        logger.info("Slack 채널 활성화")

    if env.get("DISCORD_BOT_TOKEN"):
        try:
            import discord  # noqa: F401

            from koclaw.channels import discord as discord_ch

            runners.append(
                discord_ch.start(
                    env,
                    provider,
                    tools,
                    db,
                    workspace=WORKSPACE_DIR,
                    notify_registry=notify_registry,
                    agent_registry=agent_registry,
                    computer_use_manager=computer_use_manager,
                )
            )
            logger.info("Discord 채널 활성화")
        except ImportError:
            logger.warning(
                "⚠️  Discord 채널 비활성화: discord.py 미설치 (pip install 'koclaw[discord]')"
            )

    if env.get("TELEGRAM_BOT_TOKEN"):
        try:
            from telegram.ext import Application  # noqa: F401

            from koclaw.channels import telegram as telegram_ch

            runners.append(
                telegram_ch.start(
                    env,
                    provider,
                    tools,
                    db,
                    workspace=WORKSPACE_DIR,
                    notify_registry=notify_registry,
                    agent_registry=agent_registry,
                    computer_use_manager=computer_use_manager,
                )
            )
            logger.info("Telegram 채널 활성화")
        except ImportError:
            logger.warning(
                "⚠️  Telegram 채널 비활성화: python-telegram-bot 미설치 "
                "(pip install 'koclaw[telegram]')"
            )

    if not runners:
        raise ValueError(
            "설정된 채널이 없습니다. "
            ".env 파일에 SLACK_BOT_TOKEN, DISCORD_BOT_TOKEN 또는 "
            "TELEGRAM_BOT_TOKEN을 설정하세요."
        )

    async def route_notify(session_id: str, message: str) -> None:
        fn = match_registry(notify_registry, session_id)
        if fn:
            await fn(session_id, message)
        else:
            logger.warning("알림 라우팅 실패: %s", session_id)

    async def route_agent(
        session_id: str,
        user_message: str,
        files: list,
        *,
        progress_callback=None,
    ) -> str:
        fn = match_registry(agent_registry, session_id)
        if fn:
            return await fn(session_id, user_message, files, progress_callback=progress_callback)
        return ""

    # 웹훅 tool 등록
    from koclaw.tools.webhook import WebhookTool

    tools.register(WebhookTool(db=db))

    # 웹훅 서버 (WEBHOOK_HOST 설정 시 활성화)
    from koclaw.core.webhook_server import WebhookServer

    webhook_server: WebhookServer | None = None
    if env.get("WEBHOOK_HOST"):
        webhook_port = int(env.get("WEBHOOK_PORT", "8080"))
        webhook_server = WebhookServer(db=db, notify_fn=route_notify, port=webhook_port)
        runners.append(webhook_server.start())
        logger.info("🌐 웹훅 서버 활성화: 포트 %d", webhook_port)
    else:
        logger.info("ℹ️  웹훅 서버 비활성화 (WEBHOOK_HOST 미설정)")

    scheduler = SchedulerLoop(db=db, notify_fn=route_notify, agent_fn=route_agent)
    logger.info("🤖 koclaw 시작!")
    try:
        await asyncio.gather(scheduler.start(), *runners)
    finally:
        if computer_use_manager is not None:
            logger.info("🖥️  computer_use 컨테이너 정리 중...")
            await computer_use_manager.stop_all()
        if mcp_manager is not None:
            await mcp_manager.close()
        if webhook_server is not None:
            await webhook_server.stop()


if __name__ == "__main__":
    asyncio.run(main())
