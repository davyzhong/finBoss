"""业务员映射 API 路由"""
import io
from fastapi import APIRouter, HTTPException, UploadFile, File

from api.dependencies import SalespersonMappingServiceDep
from api.schemas.salesperson_mapping import (
    CSVUploadResponse,
    CustomerMappingResponse,
    SalespersonMappingCreate,
    SalespersonMappingResponse,
    SalespersonMappingUpdate,
)

router = APIRouter()


@router.get("/mappings")
async def list_mappings(service: SalespersonMappingServiceDep):
    items = service.list_mappings()
    return {"items": items, "total": len(items)}


@router.post("/mappings", response_model=dict)
async def create_mapping(data: SalespersonMappingCreate, service: SalespersonMappingServiceDep):
    try:
        result = service.create_mapping(data.model_dump())
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/mappings/{record_id}", response_model=dict)
async def update_mapping(
    record_id: str,
    data: SalespersonMappingUpdate,
    service: SalespersonMappingServiceDep,
):
    result = service.update_mapping(record_id, data.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=404, detail="记录不存在")
    return result


@router.delete("/mappings/{record_id}")
async def delete_mapping(record_id: str, service: SalespersonMappingServiceDep):
    success = service.delete_mapping(record_id)
    if not success:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"status": "deleted", "id": record_id}


@router.post("/mappings/upload", response_model=CSVUploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    service: SalespersonMappingServiceDep = None,
):
    if not service:
        from api.dependencies import get_salesperson_mapping_service
        service = get_salesperson_mapping_service()
    content = await file.read()
    result = service.upload_csv(io.BytesIO(content), file.filename or "upload.csv")
    return result


@router.get("/{salesperson_id}/customers", response_model=list[dict])
async def get_customers(
    salesperson_id: str,
    service: SalespersonMappingServiceDep,
):
    return service.list_customers_by_salesperson(salesperson_id)
