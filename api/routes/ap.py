"""AP 管理 API 路由（占位，后续 Task 4 完整实现）"""
import io
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.dependencies import APServiceDep
from api.schemas.ap import APUploadResponse
from services.ap_bank_parser import APBankStatementParser

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=APUploadResponse)
async def upload_bank_statement(
    file: UploadFile = File(...),
    service: APServiceDep = None,
):
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过 10MB 限制")

    allowed = {
        "text/csv": "csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    }
    content_type = file.content_type or ""
    if content_type not in allowed and not file.filename.endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="仅支持 .csv 和 .xlsx 文件")

    parser = APBankStatementParser()
    result = parser.process_upload(io.BytesIO(content), file.filename or "upload.csv")
    return result


@router.get("/kpi")
async def get_ap_kpi(service: APServiceDep):
    return service.get_kpi()


@router.get("/suppliers")
async def get_ap_suppliers(service: APServiceDep, limit: int = 20):
    return service.get_suppliers(limit=limit)


@router.get("/records")
async def get_ap_records(
    service: APServiceDep,
    supplier_name: str | None = None,
    is_settled: int | None = None,
    limit: int = 100,
):
    return service.get_records(supplier_name=supplier_name, is_settled=is_settled, limit=limit)


@router.post("/dashboard/generate")
async def generate_ap_dashboard(service: APServiceDep):
    path = service.generate_dashboard()
    return {"status": "generated", "file": path}


@router.get("/dashboard")
async def get_ap_dashboard(service: APServiceDep):
    """返回 AP 看板 HTML 页面"""
    kpi = service.get_kpi()
    suppliers = service.get_suppliers(limit=10)
    return {
        "kpi": kpi,
        "suppliers": suppliers,
        "generated_at": datetime.now().isoformat(),
    }
