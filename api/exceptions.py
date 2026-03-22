class FinBossError(Exception):
    """业务异常基类"""
    code: str = "INTERNAL_ERROR"


class QualityError(FinBossError):
    code = "QUALITY_ERROR"


class DataServiceError(FinBossError):
    code = "DATA_SERVICE_ERROR"


class AIServiceError(FinBossError):
    code = "AI_SERVICE_ERROR"
