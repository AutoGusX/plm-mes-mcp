from ..client import FusionOperationsClient


async def list_movements(client: FusionOperationsClient, page: int, page_size: int) -> dict:
    return await client.list_inventory_movements(page=page, page_size=page_size)


async def create_movement(
    client: FusionOperationsClient,
    product_id: str,
    quantity: float,
    from_location: str,
    to_location: str,
    movement_date: str,
    notes: str,
) -> dict:
    return await client.create_inventory_movement(
        {
            "product": {"id": product_id},
            "quantity": quantity,
            "from_location": from_location,
            "to_location": to_location,
            "movement_date": movement_date,
            "notes": notes,
        }
    )
