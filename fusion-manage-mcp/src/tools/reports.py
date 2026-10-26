from ..client import FusionManageClient


async def get_report(client: FusionManageClient, report_id: int) -> dict:
    return await client.get_report(report_id)
