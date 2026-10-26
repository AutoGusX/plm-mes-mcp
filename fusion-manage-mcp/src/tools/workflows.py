from ..client import FusionManageClient


async def get_history(client: FusionManageClient, ws_id: int, dms_id: int) -> dict:
    return await client.get_workflow_history(ws_id, dms_id)


async def transition(
    client: FusionManageClient,
    ws_id: int,
    dms_id: int,
    transition_id: int,
    step: int,
    comments: str,
) -> dict:
    return await client.transition_workflow(ws_id, dms_id, transition_id, step, comments)
