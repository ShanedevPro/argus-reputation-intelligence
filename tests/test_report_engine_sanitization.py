import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ReportEngine.ir import IRValidator
from ReportEngine.core import ChapterStorage, TemplateSection
from ReportEngine.nodes.chapter_generation_node import ChapterGenerationNode
from ReportEngine.renderers.markdown_renderer import MarkdownRenderer


def _cell(text):
    return {"blocks": [{"type": "paragraph", "inlines": [{"text": text}]}]}


def _cell_texts(table_block):
    texts = []
    for row in table_block["rows"]:
        for cell in row["cells"]:
            for block in cell["blocks"]:
                for inline in block.get("inlines", []):
                    texts.append(inline.get("text", ""))
    return texts


class ChapterSanitizationTestCase(unittest.TestCase):
    """Lightweight regression tests for the chapter sanitization helpers."""

    def setUp(self):
        self.node = ChapterGenerationNode(llm_client=None, validator=IRValidator(), storage=None)

    def test_table_cell_empty_blocks_repaired(self):
        chapter = {
            "blocks": [
                {
                    "type": "table",
                    "rows": [
                        {
                            "cells": [
                                {"blocks": []},
                                {"text": "同比变化", "blocks": None},
                            ]
                        }
                    ],
                }
            ]
        }
        self.node._sanitize_chapter_blocks(chapter)
        table_block = chapter["blocks"][0]
        cells = table_block["rows"][0]["cells"]
        self.assertEqual(len(cells), 2)
        for cell in cells:
            blocks = cell.get("blocks")
            self.assertIsInstance(blocks, list)
            self.assertGreater(len(blocks), 0)
            for block in blocks:
                self.assertEqual(block.get("type"), "paragraph")

    def test_table_rows_scalar_values_expanded(self):
        chapter = {"blocks": [{"type": "table", "rows": ["全国趋势"]}]}
        self.node._sanitize_chapter_blocks(chapter)
        table_block = chapter["blocks"][0]
        self.assertEqual(len(table_block["rows"]), 1)
        row = table_block["rows"][0]
        self.assertIn("cells", row)
        self.assertEqual(len(row["cells"]), 1)
        cell = row["cells"][0]
        self.assertIsInstance(cell.get("blocks"), list)
        self.assertEqual(
            cell["blocks"][0]["inlines"][0]["text"],
            "全国趋势",
        )

    def test_table_overflow_heading_cells_move_outside_table(self):
        chapter = {
            "blocks": [
                {
                    "type": "table",
                    "rows": [
                        {"cells": [_cell("机会"), _cell("依据")]},
                        {
                            "cells": [
                                _cell("IP热度延展"),
                                _cell("核心粉丝仍在讨论价格和渠道"),
                                _cell("6.3 最终行动建议"),
                                _cell("6.3.1 控制发售节奏"),
                                _cell("把补货、抽签和售后口径公开化，降低黄牛叙事空间"),
                            ]
                        },
                    ],
                }
            ]
        }

        self.node._sanitize_chapter_blocks(chapter)

        table_block = chapter["blocks"][0]
        self.assertEqual(table_block["type"], "table")
        self.assertEqual([len(row["cells"]) for row in table_block["rows"]], [2, 2])
        self.assertFalse(any(text.startswith("6.3") for text in _cell_texts(table_block)))
        self.assertEqual(chapter["blocks"][1]["type"], "heading")
        self.assertEqual(chapter["blocks"][1]["text"], "6.3 最终行动建议")
        self.assertEqual(chapter["blocks"][2]["type"], "heading")
        self.assertEqual(chapter["blocks"][2]["text"], "6.3.1 控制发售节奏")
        self.assertEqual(chapter["blocks"][3]["type"], "paragraph")

    def test_table_placeholder_rows_removed_when_real_rows_exist(self):
        chapter = {
            "blocks": [
                {
                    "type": "table",
                    "rows": [
                        {"cells": [_cell("机会领域"), _cell("具体描述"), _cell("价值"), _cell("难度")]},
                        {"cells": [_cell("优化销售"), _cell("透明补货"), _cell("高"), _cell("中")]},
                        {"cells": [_cell("--")]},
                        {"cells": [_cell("--")]},
                    ],
                }
            ]
        }

        self.node._sanitize_chapter_blocks(chapter)

        table_block = chapter["blocks"][0]
        self.assertEqual([len(row["cells"]) for row in table_block["rows"]], [4, 4])

    def test_engine_quote_validation(self):
        validator = IRValidator()
        chapter = {
            "chapterId": "S1",
            "title": "Engine 引用校验",
            "anchor": "section-1",
            "order": 1,
            "blocks": [
                {
                    "type": "engineQuote",
                    "engine": "insight",
                    "title": "舆情洞察员",
                    "blocks": [
                        {
                            "type": "paragraph",
                            "inlines": [{"text": "来自 Insight Engine 的观点"}],
                        }
                    ],
                }
            ],
        }
        valid, errors = validator.validate_chapter(chapter)
        self.assertTrue(valid, errors)
        self.assertFalse(errors)

    def test_engine_quote_rejects_disallowed_marks_and_blocks(self):
        validator = IRValidator()
        chapter = {
            "chapterId": "S1",
            "title": "Engine 引用校验",
            "anchor": "section-1",
            "order": 1,
            "blocks": [
                {
                    "type": "engineQuote",
                    "engine": "media",
                    "title": "传播观察员",
                    "blocks": [
                        {"type": "math", "latex": "x=y"},
                        {
                            "type": "paragraph",
                            "inlines": [
                                {"text": "test", "marks": [{"type": "color"}]}
                            ],
                        },
                    ],
                }
            ],
        }
        valid, errors = validator.validate_chapter(chapter)
        self.assertFalse(valid)
        self.assertTrue(any("仅允许 paragraph" in err for err in errors))
        self.assertTrue(any("仅允许 bold/italic" in err for err in errors))

    def test_engine_quote_sanitization_strips_disallowed(self):
        chapter = {
            "blocks": [
                {
                    "type": "engineQuote",
                    "engine": "query",
                    "blocks": [
                        {"type": "list", "items": [["非法"]]},
                        {
                            "type": "paragraph",
                            "inlines": [
                                {
                                    "text": "abc",
                                    "marks": [{"type": "bold"}, {"type": "highlight"}],
                                }
                            ],
                        },
                    ],
                }
            ]
        }
        node = self.node
        node._sanitize_chapter_blocks(chapter)
        eq_block = chapter["blocks"][0]
        self.assertEqual(eq_block["type"], "engineQuote")
        self.assertEqual(eq_block.get("title"), "事实核验员")
        inner_blocks = eq_block.get("blocks")
        self.assertTrue(all(b.get("type") == "paragraph" for b in inner_blocks))
        marks = inner_blocks[0]["inlines"][0].get("marks")
        self.assertEqual(marks, [])
        marks2 = inner_blocks[1]["inlines"][0].get("marks")
        self.assertEqual(marks2, [{"type": "bold"}])

    def test_engine_quote_title_must_match_engine(self):
        validator = IRValidator()
        chapter = {
            "chapterId": "S1",
            "title": "Engine 引用校验",
            "anchor": "section-1",
            "order": 1,
            "blocks": [
                {
                    "type": "engineQuote",
                    "engine": "query",
                    "title": "传播观察员",
                    "blocks": [
                        {
                            "type": "paragraph",
                            "inlines": [{"text": "错误标题"}],
                        }
                    ],
                }
            ],
        }
        valid, errors = validator.validate_chapter(chapter)
        self.assertFalse(valid)
        self.assertTrue(any("title 必须与engine一致" in err for err in errors))

    def test_markdown_renderer_uses_first_table_row_as_header_without_placeholders(self):
        document_ir = {
            "metadata": {"title": "测试报告"},
            "chapters": [
                {
                    "chapterId": "S1",
                    "title": "关键证据",
                    "order": 10,
                    "blocks": [
                        {
                            "type": "table",
                            "rows": [
                                {"cells": [_cell("类型"), _cell("证据摘录")]},
                                {"cells": [_cell("微博帖子"), _cell("王鹤棣回应不舒服")]},
                            ],
                        }
                    ],
                }
            ],
        }

        markdown = MarkdownRenderer().render(document_ir)

        self.assertIn("| 类型 | 证据摘录 |", markdown)
        self.assertNotIn("列1", markdown)

    def test_chapter_payload_uses_customer_facing_data_notes_not_raw_manifest(self):
        section = TemplateSection(
            title="舆论场观点与情绪光谱",
            slug="opinion-spectrum",
            order=40,
            depth=2,
            raw_title="四、舆论场观点与情绪光谱",
            number="4.0",
            chapter_id="S4",
        )
        context = {
            "query": "王鹤棣 不舒服文学",
            "reports": {},
            "data_bundles": [
                {
                    "type": "weibo_evidence_manifest",
                    "provider": "tikhub",
                    "sample_boundary": {
                        "platform": "weibo",
                        "comment_depth": "first_level_only",
                        "represents": "collected_weibo_sample_only",
                        "warning": "This sample does not represent all public opinion.",
                    },
                    "counts": {"posts": 31, "comments": 46, "authors": 69, "keywords": 6},
                    "keywords": ["王鹤棣 不舒服文学", "我当时确实不舒服"],
                    "research_request": {
                        "affectedSubject": "王鹤棣",
                        "timeWindow": "2026-05-01 至 2026-05-29",
                    },
                }
            ],
        }

        payload = self.node._build_payload(section, context)
        rendered = str(payload)

        self.assertNotIn("dataBundles", payload)
        self.assertNotIn("weibo_evidence_manifest", rendered)
        self.assertNotIn("first_level_only", rendered)
        self.assertNotIn("This sample does not represent", rendered)
        self.assertIn("dataNotes", payload)
        self.assertIn("数据来源与样本说明", rendered)
        self.assertIn("帖子 31 条、一级评论 46 条、作者 69 个、关键词 6 个", rendered)
        self.assertIn("仅代表本次采集到的微博样本，不代表全网或全部公众意见", rendered)
        self.assertNotIn("requiredSections", rendered)

    def test_chapter_payload_uses_chinese_report_source_labels(self):
        section = TemplateSection(
            title="风险评估",
            slug="risk",
            order=60,
            depth=2,
            raw_title="六、风险评估",
            number="6.0",
            chapter_id="S6",
        )
        context = {
            "query": "王鹤棣 不舒服文学",
            "reports": {
                "query_engine": "确认事实",
                "media_engine": "传播分析",
                "insight_engine": "舆情洞察",
            },
        }

        payload = self.node._build_payload(section, context)
        rendered = str(payload)

        self.assertIn("事实核验员", rendered)
        self.assertIn("传播观察员", rendered)
        self.assertIn("舆情洞察员", rendered)
        self.assertNotIn("query_engine", rendered)
        self.assertNotIn("media_engine", rendered)
        self.assertNotIn("insight_engine", rendered)

    def test_sanitizer_replaces_internal_engine_ids_in_user_facing_text(self):
        chapter = {
            "blocks": [
                {
                    "type": "paragraph",
                    "inlines": [
                        {"text": "根据insight_engine分析，query_engine和media_engine结论一致。"}
                    ],
                },
                {
                    "type": "table",
                    "rows": [
                        {
                            "cells": [
                                _cell("来源"),
                                _cell("结论"),
                            ]
                        },
                        {
                            "cells": [
                                _cell("insight_engine"),
                                _cell("media_engine认为传播正在扩散"),
                            ]
                        },
                    ],
                },
                {
                    "type": "engineQuote",
                    "engine": "insight",
                    "title": "舆情洞察员",
                    "blocks": [
                        {
                            "type": "paragraph",
                            "inlines": [{"text": "insight_engine提示需要降低结论语气。"}],
                        }
                    ],
                },
            ]
        }

        self.node._sanitize_chapter_blocks(chapter)
        rendered = str(chapter)

        self.assertIn("舆情洞察员", rendered)
        self.assertIn("事实核验员", rendered)
        self.assertIn("传播观察员", rendered)
        self.assertNotIn("insight_engine", rendered)
        self.assertNotIn("query_engine", rendered)
        self.assertNotIn("media_engine", rendered)

    def test_markdown_renderer_skips_obvious_leaked_json_fragments(self):
        document_ir = {
            "metadata": {"title": "测试报告"},
            "chapters": [
                {
                    "chapterId": "S1",
                    "title": "情绪分析",
                    "order": 10,
                    "blocks": [
                        {
                            "type": "paragraph",
                            "inlines": [
                                {
                                    "text": '"text": "这是一段从IR泄漏出来的内部字段"',
                                }
                            ],
                        },
                        {
                            "type": "paragraph",
                            "inlines": [
                                {
                                    "text": "正常引用：网友说“我当时确实不舒服”。",
                                }
                            ],
                        },
                    ],
                }
            ],
        }

        markdown = MarkdownRenderer().render(document_ir)

        self.assertNotIn('"text":', markdown)
        self.assertIn("正常引用：网友说“我当时确实不舒服”。", markdown)

    def test_sanitizer_removes_provider_refusal_text_from_user_facing_content(self):
        chapter = {
            "blocks": [
                {
                    "type": "table",
                    "rows": [
                        {"cells": [_cell("核心主张"), _cell("代表性论据")]},
                        {
                            "cells": [
                                _cell("The request was rejected because it was considered high risk"),
                                _cell(""),
                            ]
                        },
                        {"cells": [_cell("支持情绪表达"), _cell("玩笑应有边界")]},
                    ],
                },
                {
                    "type": "paragraph",
                    "inlines": [
                        {
                            "text": "The request was rejected because it was considered high risk"
                        }
                    ],
                },
            ]
        }

        self.node._sanitize_chapter_blocks(chapter)
        rendered = str(chapter)

        self.assertNotIn("The request was rejected", rendered)
        self.assertNotIn("considered high risk", rendered)
        self.assertIn("支持情绪表达", rendered)

    def test_stream_llm_retries_transient_chunked_read_without_keeping_partial_raw(self):
        class FlakyStreamingClient:
            def __init__(self):
                self.attempts = 0

            def stream_invoke(self, *_args, **_kwargs):
                self.attempts += 1
                if self.attempts == 1:
                    def broken_stream():
                        yield '{"partial":'
                        raise RuntimeError(
                            "peer closed connection without sending complete message body "
                            "(incomplete chunked read)"
                        )

                    return broken_stream()
                return iter(['{"chapterId":"S1","title":"报告摘要","blocks":[]}'])

        with TemporaryDirectory() as temp_dir:
            storage = ChapterStorage(str(Path(temp_dir) / "chapters"))
            node = ChapterGenerationNode(
                llm_client=FlakyStreamingClient(),
                validator=IRValidator(),
                storage=storage,
            )
            chapter_dir = Path(temp_dir) / "chapter"
            with patch.dict(
                "os.environ",
                {
                    "REPORT_ENGINE_CHAPTER_STREAM_MAX_RETRIES": "1",
                    "REPORT_ENGINE_CHAPTER_STREAM_RETRY_INITIAL_DELAY": "0",
                },
            ):
                result = node._stream_llm("user prompt", chapter_dir)

            self.assertEqual(result, '{"chapterId":"S1","title":"报告摘要","blocks":[]}')
            self.assertEqual(node.llm_client.attempts, 2)
            self.assertEqual(
                (chapter_dir / "stream.raw").read_text(encoding="utf-8"),
                '{"chapterId":"S1","title":"报告摘要","blocks":[]}',
            )

    def test_stream_llm_does_not_emit_failed_attempt_chunks_to_callback(self):
        class FlakyStreamingClient:
            def __init__(self):
                self.attempts = 0

            def stream_invoke(self, *_args, **_kwargs):
                self.attempts += 1
                if self.attempts == 1:
                    def broken_stream():
                        yield '{"partial":'
                        raise RuntimeError("Error 504: origin_gateway_timeout retry_after: 0")

                    return broken_stream()
                return iter(['{"chapterId":"S1","title":"报告摘要","blocks":[]}'])

        with TemporaryDirectory() as temp_dir:
            storage = ChapterStorage(str(Path(temp_dir) / "chapters"))
            node = ChapterGenerationNode(
                llm_client=FlakyStreamingClient(),
                validator=IRValidator(),
                storage=storage,
            )
            emitted = []

            def capture_callback(delta, meta):
                emitted.append((delta, meta))

            with patch.dict(
                "os.environ",
                {
                    "REPORT_ENGINE_CHAPTER_STREAM_MAX_RETRIES": "1",
                    "REPORT_ENGINE_CHAPTER_STREAM_RETRY_INITIAL_DELAY": "0",
                    "REPORT_ENGINE_CHAPTER_STREAM_RETRY_MAX_DELAY": "0",
                },
            ):
                node._stream_llm(
                    "user prompt",
                    Path(temp_dir) / "chapter",
                    stream_callback=capture_callback,
                    section_meta={"chapterId": "S1"},
                )

        self.assertEqual(
            emitted,
            [
                (
                    '{"chapterId":"S1","title":"报告摘要","blocks":[]}',
                    {"chapterId": "S1"},
                )
            ],
        )

    def test_stream_llm_raises_after_transient_retry_budget_is_exhausted(self):
        class AlwaysBrokenStreamingClient:
            def __init__(self):
                self.attempts = 0

            def stream_invoke(self, *_args, **_kwargs):
                self.attempts += 1

                def broken_stream():
                    yield '{"partial":'
                    raise RuntimeError("Error 504: origin_gateway_timeout retry_after: 0")

                return broken_stream()

        with TemporaryDirectory() as temp_dir:
            storage = ChapterStorage(str(Path(temp_dir) / "chapters"))
            node = ChapterGenerationNode(
                llm_client=AlwaysBrokenStreamingClient(),
                validator=IRValidator(),
                storage=storage,
            )
            with patch.dict(
                "os.environ",
                {
                    "REPORT_ENGINE_CHAPTER_STREAM_MAX_RETRIES": "1",
                    "REPORT_ENGINE_CHAPTER_STREAM_RETRY_INITIAL_DELAY": "0",
                    "REPORT_ENGINE_CHAPTER_STREAM_RETRY_MAX_DELAY": "0",
                },
            ):
                with self.assertRaisesRegex(RuntimeError, "origin_gateway_timeout"):
                    node._stream_llm("user prompt", Path(temp_dir) / "chapter")

            self.assertEqual(node.llm_client.attempts, 2)

    def test_stream_llm_does_not_retry_non_transient_errors(self):
        class InvalidStreamingClient:
            def __init__(self):
                self.attempts = 0

            def stream_invoke(self, *_args, **_kwargs):
                self.attempts += 1

                def broken_stream():
                    raise ValueError("invalid chapter payload")
                    yield ""

                return broken_stream()

        with TemporaryDirectory() as temp_dir:
            storage = ChapterStorage(str(Path(temp_dir) / "chapters"))
            node = ChapterGenerationNode(
                llm_client=InvalidStreamingClient(),
                validator=IRValidator(),
                storage=storage,
            )
            with patch.dict(
                "os.environ",
                {
                    "REPORT_ENGINE_CHAPTER_STREAM_MAX_RETRIES": "3",
                    "REPORT_ENGINE_CHAPTER_STREAM_RETRY_INITIAL_DELAY": "0",
                },
            ):
                with self.assertRaisesRegex(ValueError, "invalid chapter payload"):
                    node._stream_llm("user prompt", Path(temp_dir) / "chapter")

            self.assertEqual(node.llm_client.attempts, 1)

    def test_stream_llm_uses_chapter_reasoning_effort_override(self):
        class CapturingStreamingClient:
            def __init__(self):
                self.kwargs = None

            def stream_invoke(self, *_args, **kwargs):
                self.kwargs = kwargs
                return iter(['{"chapterId":"S1","title":"报告摘要","blocks":[]}'])

        with TemporaryDirectory() as temp_dir:
            storage = ChapterStorage(str(Path(temp_dir) / "chapters"))
            client = CapturingStreamingClient()
            node = ChapterGenerationNode(
                llm_client=client,
                validator=IRValidator(),
                storage=storage,
            )
            with patch.dict(
                "os.environ",
                {"REPORT_ENGINE_CHAPTER_REASONING_EFFORT": "high"},
            ):
                node._stream_llm("user prompt", Path(temp_dir) / "chapter")

        self.assertEqual(client.kwargs["reasoning_effort"], "high")

    def test_stream_llm_can_disable_default_reasoning_effort_for_chapters(self):
        class CapturingStreamingClient:
            def __init__(self):
                self.kwargs = None

            def stream_invoke(self, *_args, **kwargs):
                self.kwargs = kwargs
                return iter(['{"chapterId":"S1","title":"报告摘要","blocks":[]}'])

        with TemporaryDirectory() as temp_dir:
            storage = ChapterStorage(str(Path(temp_dir) / "chapters"))
            client = CapturingStreamingClient()
            node = ChapterGenerationNode(
                llm_client=client,
                validator=IRValidator(),
                storage=storage,
            )
            with patch.dict(
                "os.environ",
                {"REPORT_ENGINE_CHAPTER_REASONING_EFFORT": "none"},
            ):
                node._stream_llm("user prompt", Path(temp_dir) / "chapter")

        self.assertEqual(client.kwargs["reasoning_effort"], "none")


if __name__ == "__main__":
    unittest.main()
