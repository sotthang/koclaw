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
from koclaw.tools.computer_use import ComputerUseTool
from koclaw.tools.email import EmailTool
from koclaw.tools.rss import RssFeedTool
from koclaw.tools.search import SearchTool
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

    computer_use_manager: ComputerUseManager | WindowsComputerUseManager | None = None
    windows_agent_url = env.get("WINDOWS_AGENT_URL", "").strip()
    if windows_agent_url:
        windows_agent_api_key = env.get("WINDOWS_AGENT_API_KEY", "").strip()
        windows_agent_view_url = env.get("WINDOWS_AGENT_VIEW_URL", "").strip()
        computer_use_manager = WindowsComputerUseManager(
            url=windows_agent_url,
            api_key=windows_agent_api_key,
            view_url=windows_agent_view_url,
        )
        tools.register(ComputerUseTool(manager=computer_use_manager))
        logger.info("🖥️  Windows Agent 감지됨 — computer_use 활성화 (%s)", windows_agent_url)
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

    if not runners:
        raise ValueError(
            "설정된 채널이 없습니다. "
            ".env 파일에 SLACK_BOT_TOKEN 또는 DISCORD_BOT_TOKEN을 설정하세요."
        )

    async def route_notify(session_id: str, message: str) -> None:
        fn = match_registry(notify_registry, session_id)
        if fn:
            await fn(session_id, message)
        else:
            logger.warning("알림 라우팅 실패: %s", session_id)

    async def route_agent(session_id: str, user_message: str, files: list) -> str:
        fn = match_registry(agent_registry, session_id)
        if fn:
            return await fn(session_id, user_message, files)
        return ""

    scheduler = SchedulerLoop(db=db, notify_fn=route_notify, agent_fn=route_agent)
    logger.info("🤖 koclaw 시작!")
    try:
        await asyncio.gather(scheduler.start(), *runners)
    finally:
        if computer_use_manager is not None:
            logger.info("🖥️  computer_use 컨테이너 정리 중...")
            await computer_use_manager.stop_all()


if __name__ == "__main__":
    asyncio.run(main())
