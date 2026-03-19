"""金蝶数据模型定义"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class KingdeeARVerify(BaseModel):
    """金蝶应收单模型"""

    fid: int = Field(description="单据ID")
    fbillno: str = Field(description="单据编号")
    fdate: datetime = Field(description="单据日期")
    fcustid: int = Field(description="客户ID")
    fcustname: str = Field(description="客户名称")
    fsuppid: Optional[int] = Field(default=None, description="供应商ID")
    fcurrencyid: Optional[int] = Field(default=None, description="币种ID")
    fbillamount: float = Field(description="单据金额")
    fpaymentamount: float = Field(description="已付款金额")
    fallocateamount: float = Field(description="已核销金额")
    funallocateamount: float = Field(description="未核销金额")
    fstatus: str = Field(description="状态")
    fcompanyid: int = Field(description="公司ID")
    fdeptid: Optional[int] = Field(default=None, description="部门ID")
    femployeeid: Optional[int] = Field(default=None, description="业务员ID")
    fcreatorid: Optional[int] = Field(default=None, description="创建人ID")
    fcreatedate: Optional[datetime] = Field(default=None, description="创建日期")
    fmodifierid: Optional[int] = Field(default=None, description="修改人ID")
    fmodifydate: Optional[datetime] = Field(default=None, description="修改日期")
    fdocumentstatus: str = Field(description="审批状态")
    fapproverid: Optional[int] = Field(default=None, description="审核人ID")
    fapprovetime: Optional[datetime] = Field(default=None, description="审核时间")
    fremark: Optional[str] = Field(default=None, description="备注")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "fid": 100001,
                "fbillno": "AR20260319001",
                "fdate": "2026-03-19T00:00:00",
                "fcustid": 1001,
                "fcustname": "测试客户A",
                "fbillamount": 100000.00,
                "fpaymentamount": 30000.00,
                "fallocateamount": 20000.00,
                "funallocateamount": 50000.00,
                "fstatus": "A",
                "fcompanyid": 1,
                "fdocumentstatus": "C",
            }
        }
