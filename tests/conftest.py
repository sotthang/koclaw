import pytest

from koclaw.storage.db import Database


@pytest.fixture
async def make_db(tmp_path):
    """Database를 생성하고 테스트 종료 후 자동으로 닫는 factory fixture.

    사용법:
        async def test_something(self, make_db):
            db = await make_db()          # 기본 이름 test.db
            db2 = await make_db("other")  # 다른 이름
    """
    dbs: list[Database] = []

    async def factory(name: str = "test.db") -> Database:
        db = Database(tmp_path / name)
        await db.initialize()
        dbs.append(db)
        return db

    yield factory

    for db in dbs:
        await db.close()
