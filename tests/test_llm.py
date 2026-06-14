"""测试 LLM 调用模块的指数退避重试机制"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, Mock

import pytest
from kb.llm import _request_with_retry, _RETRYABLE_STATUSES


class TestRequestWithRetry:
    """测试 _request_with_retry 重试和退避逻辑"""

    def test_success_on_first_try(self):
        """正常情况：第一次请求即成功，不应重试"""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None

        with patch('kb.llm.requests.request', return_value=mock_resp) as mock_request:
            result = _request_with_retry('GET', 'http://test.local/api')
            assert result is mock_resp
            assert mock_request.call_count == 1

    def test_retry_on_timeout(self):
        """超时异常：应重试最多 3 次后抛出"""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None

        with patch('kb.llm.requests.request', side_effect=[
            TimeoutError('timeout'),  # 第1次：超时
            TimeoutError('timeout'),  # 第2次：超时
            mock_resp,                # 第3次：成功
        ]) as mock_request:
            from requests.exceptions import Timeout
            mock_request.side_effect = [Timeout('timeout'), Timeout('timeout'), mock_resp]
            result = _request_with_retry('GET', 'http://test.local/api', max_retries=3)
            assert result is mock_resp
            assert mock_request.call_count == 3

    def test_retry_on_429(self):
        """HTTP 429：应重试后成功"""
        mock_429 = Mock()
        mock_429.status_code = 429
        mock_429.raise_for_status.side_effect = Exception('rate limit')

        mock_200 = Mock()
        mock_200.status_code = 200
        mock_200.raise_for_status.return_value = None

        with patch('kb.llm.requests.request', side_effect=[mock_429, mock_200]) as mock_request:
            result = _request_with_retry('GET', 'http://test.local/api', max_retries=2)
            assert result is mock_200
            assert mock_request.call_count == 2

    def test_retry_on_503(self):
        """HTTP 503：应重试后成功"""
        mock_503 = Mock()
        mock_503.status_code = 503
        mock_503.raise_for_status.side_effect = Exception('service unavailable')

        mock_200 = Mock()
        mock_200.status_code = 200
        mock_200.raise_for_status.return_value = None

        with patch('kb.llm.requests.request', side_effect=[mock_503, mock_200]) as mock_request:
            result = _request_with_retry('GET', 'http://test.local/api', max_retries=2)
            assert result is mock_200
            assert mock_request.call_count == 2

    def test_give_up_after_max_retries(self):
        """重试耗尽：所有重试均失败，应抛出原始异常"""
        from requests.exceptions import Timeout
        with patch('kb.llm.requests.request', side_effect=Timeout('always timeout')) as mock_request:
            with pytest.raises(Timeout, match='always timeout'):
                _request_with_retry('GET', 'http://test.local/api', max_retries=2)
            assert mock_request.call_count == 2

    def test_give_up_on_non_retryable_status(self):
        """非可重试状态码（如 400）：不重试，直接抛出"""
        mock_400 = Mock()
        mock_400.status_code = 400
        mock_400.raise_for_status.side_effect = Exception('bad request')

        with patch('kb.llm.requests.request', return_value=mock_400) as mock_request:
            with pytest.raises(Exception):
                _request_with_retry('GET', 'http://test.local/api', max_retries=3)
            assert mock_request.call_count == 1  # 只请求一次

    def test_retryable_statuses_exist(self):
        """验证 _RETRYABLE_STATUSES 包含预期的状态码"""
        assert 429 in _RETRYABLE_STATUSES
        assert 500 in _RETRYABLE_STATUSES
        assert 502 in _RETRYABLE_STATUSES
        assert 503 in _RETRYABLE_STATUSES
        assert 504 in _RETRYABLE_STATUSES
        assert len(_RETRYABLE_STATUSES) == 5


class TestLLMFunctions:
    """测试 LLM 调用入口函数的正常路径"""

    def test_is_llm_available_returns_false_without_config(self):
        """未配置 LLM 时返回 False"""
        from kb.llm import is_llm_available

        with patch('kb.llm._get_llm_config', return_value={}):
            assert is_llm_available() is False

    def test_is_llm_available_returns_true_with_config(self):
        """完整配置时返回 True"""
        from kb.llm import is_llm_available

        full_config = {
            'enabled': True,
            'api_key': 'sk-test',
            'base_url': 'https://api.openai.com',
            'model': 'gpt-4',
        }
        with patch('kb.llm._get_llm_config', return_value=full_config):
            assert is_llm_available() is True
