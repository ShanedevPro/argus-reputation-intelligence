import unittest
from unittest.mock import AsyncMock, Mock, patch


class MediaCrawlerBridgeTest(unittest.TestCase):
    def test_normalizes_weibo_search_item(self):
        from downstream.mediacrawler.normalizer import normalize_mediacrawler_item

        record = normalize_mediacrawler_item(
            "wb",
            {
                "note_id": "5288433524411119",
                "content": "钛动科技 Navos AI Agent",
                "nickname": "科技名学长",
                "note_url": "https://m.weibo.cn/detail/5288433524411119",
                "create_date_time": "2026-04-16 20:57:49+08:00",
                "liked_count": "322",
                "comments_count": "140",
                "shared_count": "64",
                "source_keyword": "Navos 钛动",
            },
            source_file="raw/weibo/search_contents.json",
        )

        self.assertEqual(record["platform"], "weibo")
        self.assertEqual(record["content_id"], "5288433524411119")
        self.assertEqual(record["content_type"], "note")
        self.assertEqual(record["author"], "科技名学长")
        self.assertEqual(record["engagement"]["comment_count"], "140")
        self.assertTrue(record["is_relevant"])

    def test_prepare_posts_for_bettafish_tables(self):
        from downstream.mediacrawler.import_posts_to_bettafish import (
            prepare_bilibili_video,
            prepare_kuaishou_video,
            prepare_weibo_note,
            prepare_zhihu_content,
        )

        weibo = prepare_weibo_note(
            {
                "platform": "weibo",
                "content_id": "5288433524411119",
                "content": "钛动科技 Navos",
                "author": "科技名学长",
                "engagement": {"comment_count": "140"},
                "raw": {"user_id": "2788698850"},
            }
        )
        bili = prepare_bilibili_video(
            {
                "platform": "bilibili",
                "content_id": "114677539411980",
                "title": "钛动科技买量讨论",
                "content": "视频描述",
                "author": "猫猫yuki_",
                "engagement": {"comment_count": "2348"},
            }
        )
        zhihu = prepare_zhihu_content(
            {
                "platform": "zhihu",
                "content_id": "2015037446610497963",
                "content_type": "article",
                "title": "钛动科技工作体验",
                "content": "讨论钛动科技面试和待遇",
                "author": "左手舞剑",
                "engagement": {"voteup_count": 10, "comment_count": 4},
            }
        )
        kuaishou = prepare_kuaishou_video(
            {
                "platform": "kuaishou",
                "content_id": "3xabc",
                "title": "钛动科技短视频",
                "content": "出海营销",
                "author": "快手用户",
                "engagement": {"view_count": "100"},
            }
        )

        self.assertEqual(weibo["note_id"], 5288433524411119)
        self.assertEqual(bili["video_id"], 114677539411980)
        self.assertEqual(zhihu["content_id"], "2015037446610497963")
        self.assertEqual(kuaishou["video_id"], "3xabc")

    def test_prepare_comments_for_bettafish_tables(self):
        from downstream.mediacrawler.import_comments_to_bettafish import (
            prepare_bilibili_comment,
            prepare_weibo_comment,
        )

        weibo = prepare_weibo_comment(
            {
                "comment_id": "5285425016997138",
                "note_id": "5285190018537848",
                "content": "摸摸",
                "comment_like_count": "0",
            }
        )
        bili = prepare_bilibili_comment(
            {
                "comment_id": "123",
                "video_id": "116408092530160",
                "content": "Navos 有意思",
                "like_count": 5,
            }
        )

        self.assertEqual(weibo["comment_id"], 5285425016997138)
        self.assertEqual(weibo["note_id"], 5285190018537848)
        self.assertEqual(bili["video_id"], 116408092530160)
        self.assertEqual(bili["like_count"], "5")

    def test_weibo_bundle_importer_writes_posts_and_comments(self):
        import asyncio
        import json
        import tempfile
        from pathlib import Path

        from downstream.weibo_data import bundle_importer

        class Connection:
            def __init__(self):
                self.posts = []
                self.comments = []

            async def fetchval(self, query, *params):
                if "FROM weibo_note_comment" in query:
                    return len(self.comments)
                if "FROM weibo_note" in query:
                    return len(self.posts)
                return None

            async def execute(self, query, *params):
                if "INSERT INTO weibo_note_comment" in query:
                    self.comments.append(params)
                elif "INSERT INTO weibo_note" in query:
                    self.posts.append(params)

            async def close(self):
                return None

        connection = Connection()
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle = Path(tmp_dir) / "weibo_bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "provider": "mediacrawler",
                        "posts": [{"content_id": "1", "content": "小米SU7交付争议"}],
                        "comments": [{"comment_id": "10", "note_id": "1", "content": "评论"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.object(bundle_importer, "connect_postgres", AsyncMock(return_value=connection)):
                result = asyncio.run(
                    bundle_importer.import_weibo_bundle([bundle], "postgresql://example")
                )

        self.assertEqual(result["counts"]["weibo_note"], 1)
        self.assertEqual(result["counts"]["weibo_note_comment"], 1)

    def test_postgres_adapter_uses_psycopg_when_asyncpg_is_missing(self):
        import asyncio

        from downstream.mediacrawler.db_adapter import connect_postgres

        class Cursor:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def execute(self, query, params):
                self.query = query
                self.params = params

            async def fetchone(self):
                return {"id": 7}

        class Connection:
            def cursor(self):
                return Cursor()

            async def close(self):
                self.closed = True

        psycopg_module = Mock()
        psycopg_module.AsyncConnection.connect = AsyncMock(return_value=Connection())
        psycopg_rows_module = Mock()
        psycopg_rows_module.dict_row = Mock()

        with patch.dict(
            "sys.modules",
            {
                "asyncpg": None,
                "psycopg": psycopg_module,
                "psycopg.rows": psycopg_rows_module,
            },
        ):
            conn = asyncio.run(connect_postgres("postgresql://example"))
            value = asyncio.run(
                conn.fetchval("SELECT id FROM weibo_note WHERE note_id=$1", 123)
            )
            asyncio.run(conn.close())

        self.assertEqual(value, 7)

    def test_postgres_adapter_normalizes_sqlalchemy_asyncpg_dsn(self):
        import asyncio

        from downstream.mediacrawler.db_adapter import connect_postgres

        class Connection:
            pass

        asyncpg_module = Mock()
        asyncpg_module.connect = AsyncMock(return_value=Connection())

        with patch.dict("sys.modules", {"asyncpg": asyncpg_module}):
            conn = asyncio.run(
                connect_postgres("postgresql+asyncpg://user:pass@127.0.0.1:5433/bettafish")
            )

        self.assertIsInstance(conn, Connection)
        asyncpg_module.connect.assert_awaited_once_with(
            "postgresql://user:pass@127.0.0.1:5433/bettafish"
        )


if __name__ == "__main__":
    unittest.main()
