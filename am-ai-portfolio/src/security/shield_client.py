from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv

load_dotenv()

from .llm_shield_sdk_v2 import (
    ClientV2,
    ModerateV2Request,
    ModerateV2Response,
    ModerateV2StreamSession,
    MessageV2,
    DecisionTypeV2,
    ContentTypeV2,
    RiskInfoV2,
    PermitInfoV2,
)


class ShieldConfig(BaseModel):
    """安全层配置"""
    url: str = Field(..., description="安全审核服务URL")
    api_key: str = Field(..., description="API密钥")
    timeout: float = Field(5.0, description="请求超时时间(秒)")
    default_scene: str = Field("default", description="默认审核场景")
    enable_fallback: bool = Field(True, description="服务不可用时是否降级放行")
    max_retries: int = Field(1, description="最大重试次数")


class ShieldResult(BaseModel):
    """统一的安全审核结果返回结构"""
    success: bool = Field(True, description="审核是否成功")
    passed: bool = Field(True, description="内容是否通过审核")
    message: str = Field("", description="结果消息")
    risk_info: RiskInfoV2 = Field(default_factory=RiskInfoV2, description="风险信息")
    permit_info: PermitInfoV2 = Field(default_factory=PermitInfoV2, description="放行信息")
    decision_type: int = Field(0, description="决策类型")
    replaced_content: Optional[str] = Field(None, description="替换后的内容")
    error_code: Optional[str] = Field(None, description="错误码")
    error_message: Optional[str] = Field(None, description="错误信息")


class ShieldClient:
    """安全层客户端封装"""
    
    _instance: Optional['ShieldClient'] = None
    
    def __init__(self, config: Optional[ShieldConfig] = None):
        if config is None:
            config = ShieldConfig(
                url=os.getenv("SHIELD_URL", ""),
                api_key=os.getenv("SHIELD_API_KEY", ""),
                timeout=float(os.getenv("SHIELD_TIMEOUT", "5.0")),
                default_scene=os.getenv("LLM_SHIELD_APP_ID", "default"),
                enable_fallback=os.getenv("SHIELD_ENABLE_FALLBACK", "true").lower() == "true",
                max_retries=int(os.getenv("SHIELD_MAX_RETRIES", "1"))
            )
        self._config = config
        self._client = ClientV2(
            url=config.url,
            api_key=config.api_key,
            timeout=config.timeout
        )
    
    @classmethod
    def get_instance(cls, config: Optional[ShieldConfig] = None) -> 'ShieldClient':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance
    
    def _create_request(self, content: str, scene: Optional[str] = None, 
                        history: Optional[List[dict]] = None) -> ModerateV2Request:
        """创建审核请求"""
        message = MessageV2(
            role="user",
            content=content,
            content_type=ContentTypeV2.TEXT
        )
        
        # 转换历史消息格式
        history_messages = []
        if history:
            for item in history:
                history_messages.append(MessageV2(
                    role=item.get("role", ""),
                    content=item.get("content", ""),
                    content_type=item.get("content_type", ContentTypeV2.TEXT)
                ))
        
        return ModerateV2Request(
            message=message,
            msg_id="",  # 由服务端生成
            use_stream=0,
            scene=scene or self._config.default_scene,
            history=history_messages
        )
    
    def moderate(self, content: str, scene: Optional[str] = None, 
                  history: Optional[List[dict]] = None) -> ShieldResult:
        """
        非流式文本审核
        :param content: 待审核文本内容
        :param scene: 审核场景（可选）
        :param history: 历史消息列表，格式: [{"role": "...", "content": "...", "content_type": 1}]
        :return: 审核结果
        """
        import logging
        logger = logging.getLogger(__name__)
        
        for attempt in range(self._config.max_retries):
            try:
                request = self._create_request(content, scene, history)
                response: ModerateV2Response = self._client.Moderate(request)
                
                return self._parse_response(response)
            
            except Exception as e:
                error_msg = str(e)
                # 判断是否是网络超时类错误
                if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                    logger.warning(f"Shield service timeout/connection error (attempt {attempt + 1}): {error_msg}")
                    if attempt < self._config.max_retries - 1:
                        continue  # 重试
                else:
                    logger.error(f"Shield service error: {error_msg}")
                
                # 降级处理
                if self._config.enable_fallback:
                    logger.warning("Shield service unavailable, falling back to allow")
                    return ShieldResult(
                        success=True,
                        passed=True,
                        message="安全审核服务暂不可用，已降级放行",
                        error_code="SHIELD_FALLBACK",
                        error_message=error_msg
                    )
                
                return ShieldResult(
                    success=False,
                    passed=False,
                    message="审核失败",
                    error_code="SHIELD_ERROR",
                    error_message=error_msg
                )
        
        # 所有重试都失败
        if self._config.enable_fallback:
            logger.warning("All retries failed, falling back to allow")
            return ShieldResult(
                success=True,
                passed=True,
                message="安全审核服务暂不可用，已降级放行",
                error_code="SHIELD_FALLBACK",
                error_message="Max retries exceeded"
            )
        
        return ShieldResult(
            success=False,
            passed=False,
            message="审核失败",
            error_code="SHIELD_ERROR",
            error_message="Max retries exceeded"
        )
    
    def moderate_stream(self, content: str, session: ModerateV2StreamSession, 
                        scene: Optional[str] = None) -> ShieldResult:
        """
        流式文本审核
        :param content: 当前流式文本片段
        :param session: 流式会话对象
        :param scene: 审核场景（可选）
        :return: 审核结果
        """
        try:
            request = self._create_request(content, scene)
            request.use_stream = 1  # 标记为流式请求
            
            response: Optional[ModerateV2Response] = self._client.ModerateStream(request, session)
            
            if response is None:
                # 未达到发送阈值，返回默认响应
                return ShieldResult(
                    success=True,
                    passed=True,
                    message="未触发审核"
                )
            
            return self._parse_response(response)
        
        except ValueError as e:
            return ShieldResult(
                success=False,
                passed=False,
                message="参数错误",
                error_code="INVALID_PARAM",
                error_message=str(e)
            )
        except Exception as e:
            return ShieldResult(
                success=False,
                passed=False,
                message="流式审核失败",
                error_code="SHIELD_STREAM_ERROR",
                error_message=str(e)
            )
    
    def _parse_response(self, response: ModerateV2Response) -> ShieldResult:
        """解析审核响应"""
        result = response.result
        decision = result.decision
        
        success = True
        passed = False
        message = ""
        replaced_content = None
        
        # 判断决策类型
        if decision.decision_type == DecisionTypeV2.PASS:
            passed = True
            message = "内容通过审核"
        elif decision.decision_type == DecisionTypeV2.BLOCK:
            passed = False
            message = "内容被拦截"
        elif decision.decision_type == DecisionTypeV2.MARK:
            passed = True
            message = "内容已标记"
        elif decision.decision_type == DecisionTypeV2.REPLACE:
            passed = True
            message = "内容已替换"
            if (decision.decision_detail.replace_detail and 
                decision.decision_detail.replace_detail.replacement):
                replaced_content = decision.decision_detail.replace_detail.replacement.content
        elif decision.decision_type == DecisionTypeV2.OPTIMIZE:
            passed = True
            message = "内容已优化"
            if (decision.decision_detail.replace_detail and 
                decision.decision_detail.replace_detail.replacement):
                replaced_content = decision.decision_detail.replace_detail.replacement.content
        else:
            passed = True
            message = f"未知决策类型: {decision.decision_type}"
        
        return ShieldResult(
            success=success,
            passed=passed,
            message=message,
            risk_info=result.risk_info,
            permit_info=result.permit_info,
            decision_type=decision.decision_type,
            replaced_content=replaced_content
        )
    
    def create_stream_session(self) -> ModerateV2StreamSession:
        """创建流式会话对象"""
        return ModerateV2StreamSession()
