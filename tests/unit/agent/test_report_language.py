import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from Agent.causal_agent import nodes


class ReportLanguageTests(unittest.IsolatedAsyncioTestCase):
    def test_report_language_follows_user_request_with_chinese_fallback(self):
        instruction = nodes._report_language_instruction()

        self.assertIn("用户明确指定报告语言", instruction)
        self.assertIn("用户当前请求的主要语言", instruction)
        self.assertIn("默认使用中文", instruction)
        self.assertNotIn("请用英文回复", instruction)

    async def test_report_node_passes_language_policy_to_the_model(self):
        captured = {}

        async def capture_prompt(prompt_value, **_kwargs):
            captured["messages"] = prompt_value.to_messages()
            return AIMessage(content="报告正文")

        state = {
            "messages": [HumanMessage(content="请用中文生成报告")],
            "analysis_parameters": {},
            "visualizations": {},
            "preprocess_summary": "",
            "causal_analysis_result": {},
            "knowledge_base_result": {},
            "web_search_result": {},
            "postprocess_result": {},
        }
        with (
            patch.object(nodes, "metadata_summary", return_value="meta"),
            patch.object(nodes, "metadata_mapping", return_value={}),
            patch.object(nodes, "format_rag_summary_for_prompt", return_value="rag"),
            patch.object(nodes, "format_web_search_summary_for_prompt", return_value="web"),
            patch.object(nodes, "causal_report_prompt", return_value="role"),
            patch.object(nodes, "_causal_method_context_for_report", return_value="method"),
        ):
            result = await nodes.report_node(state, RunnableLambda(capture_prompt))

        system_prompt = captured["messages"][0].content
        self.assertIn("默认使用中文", system_prompt)
        self.assertIn("用户明确指定报告语言", system_prompt)
        self.assertNotIn("请用英文回复", system_prompt)
        self.assertEqual(captured["messages"][-1].content, "请用中文生成报告")
        self.assertEqual(result["final_report"], "报告正文")
