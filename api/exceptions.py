class FinBossError(Exception):
    """业务异常基类"""

    code: str = "INTERNAL_ERROR"
    detail: str = ""

    def __init__(self, detail: str = ""):
        super().__init__(detail)
        self.detail = detail


class QualityError(FinBossError):
    code: str = "QUALITY_ERROR"


class DataServiceError(FinBossError):
    code: str = "DATA_SERVICE_ERROR"


class AIServiceError(FinBossError):
    code: str = "AI_SERVICE_ERROR"
