from ..client import FusionOperationsClient


async def list_clients(client: FusionOperationsClient, page: int, page_size: int) -> dict:
    return await client.list_clients(page=page, page_size=page_size)


async def get_client(client: FusionOperationsClient, client_id: str) -> dict:
    return await client.get_client(client_id)


async def list_suppliers(client: FusionOperationsClient, page: int, page_size: int) -> dict:
    return await client.list_suppliers(page=page, page_size=page_size)


async def get_supplier(client: FusionOperationsClient, supplier_id: str) -> dict:
    return await client.get_supplier(supplier_id)
